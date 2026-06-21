"""
Minimal dashboard API - serves the shared verdict store on /api/status.

This decouples the frontend from the uAgents stack: the dashboard's data contract
(GET /api/status -> {"hives": {hive_id: [verdict, ...]}}) is served straight from
data/verdicts.json, re-read on every request so live appends (from the coordinator or
the live-fleet generator) show up immediately. No mailbox, no Agentverse, no ports tug.

Run:   python api_server.py            (serves on http://127.0.0.1:8000)
       PORT=8010 python api_server.py  (different port)
Seed the data first:  python seed_apiary.py
The Vite frontend already proxies /api -> 127.0.0.1:8000, so it just works.
Only run ONE thing on 8000 (this OR the uAgents coordinator OR the frontend mock).
"""

import os
import json
from urllib.parse import urlparse, parse_qs
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import hive_state
import godfather
import explain as explain_mod
from src.store import get_store

PORT = int(os.getenv("PORT", "8000"))


def _query_embedding(verdict: dict):
    """Build an 86-d query vector from a hive's latest verdict so /api/similar can find
    look-alike past readings across the apiary. Reconstructs a sample-like dict from the
    verdict fields and reuses the same embedding the fleet stores."""
    from src import embedding
    sample = {
        "acoustic_stress": float(verdict.get("acoustic_stress", 0.0) or 0.0),
        "vision_mite_rate": float(verdict.get("vision_mite_rate", 0.0) or 0.0),
        "net_traffic": float(verdict.get("traffic", 0.0) or 0.0),
        "queenless_score": 1.0 if verdict.get("queenless_alert") else 0.0,
        "swarm_band_hz": 150.0 if verdict.get("swarm_alert") else 400.0,
        "swarm_rising": bool(verdict.get("swarm_alert")),
    }
    return embedding.embed_sample(sample)[0]


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body):
        payload = json.dumps(body).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")  # let the dashboard fetch directly
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")
        if path == "/api/status":
            self._send(200, {"hives": hive_state.load_verdicts()})
        elif path == "/api/apiary":   # the godfather's apiary-wide read
            self._send(200, godfather.apiary_analysis(hive_state.load_verdicts()))
        elif path == "/api/explain":  # plain-English explanation of a log line / term
            q = (parse_qs(parsed.query).get("q") or [""])[0]
            self._send(200, {"line": q, "explanation": explain_mod.explain(q)})
        elif path == "/api/advise":   # agentic, data-driven recommendation for one hive
            qs = parse_qs(parsed.query)
            p = {k: (qs.get(k) or [""])[0] for k in ("hive", "name", "status", "mite", "stress", "queen", "traffic")}
            self._send(200, {"hive": p["hive"], "advice": explain_mod.advise(p)})
        elif path == "/api/similar":  # Redis vector k-NN: past states like this hive's now
            self._handle_similar(parse_qs(parsed.query))
        elif path == "/api/events":   # Redis Pub/Sub -> SSE stream of live updates
            self._handle_events()
        else:
            self._send(404, {"error": "not found", "try": "/api/status, /api/apiary, /api/explain?q=..."})

    def _handle_similar(self, qs):
        """GET /api/similar?hive=A3&k=5 -> readings most similar to that hive's latest."""
        store = get_store()
        hive = (qs.get("hive") or [""])[0]
        try:
            k = int((qs.get("k") or ["5"])[0])
        except ValueError:
            k = 5
        if not store.available():
            self._send(200, {"hive": hive, "similar": [],
                             "note": "vector search needs Redis (run with USE_REDIS=1)"})
            return
        latest = store.latest(hive) if hive else None
        if not latest:
            self._send(200, {"hive": hive, "similar": [], "note": "no readings for that hive yet"})
            return
        emb = _query_embedding(latest)
        self._send(200, {"hive": hive, "similar": store.search_similar(emb, k=k)})

    def _handle_events(self):
        """GET /api/events -> Server-Sent Events bridged from the Redis Pub/Sub channel."""
        store = get_store()
        if not store.available() or not hasattr(store, "subscribe"):
            self._send(501, {"error": "live events need Redis (run with USE_REDIS=1)"})
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        try:
            for data in store.subscribe():
                self.wfile.write(f"data: {data}\n\n".encode("utf-8"))
                self.wfile.flush()
        except Exception:
            pass  # client disconnected

    def log_message(self, *args):
        pass  # quiet


def main():
    n = sum(len(v) for v in hive_state.load_verdicts().values())
    print(f"Serving /api/status on http://127.0.0.1:{PORT}  ({n} verdict points loaded)")
    print("Re-reads data/verdicts.json on every request, so live updates show instantly.")
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
