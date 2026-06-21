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
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import hive_state
import godfather

PORT = int(os.getenv("PORT", "8000"))


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
        path = self.path.rstrip("/")
        if path == "/api/status":
            self._send(200, {"hives": hive_state.load_verdicts()})
        elif path == "/api/apiary":   # the godfather's apiary-wide read
            self._send(200, godfather.apiary_analysis(hive_state.load_verdicts()))
        else:
            self._send(404, {"error": "not found", "try": "/api/status or /api/apiary"})

    def log_message(self, *args):
        pass  # quiet


def main():
    n = sum(len(v) for v in hive_state.load_verdicts().values())
    print(f"Serving /api/status on http://127.0.0.1:{PORT}  ({n} verdict points loaded)")
    print("Re-reads data/verdicts.json on every request, so live updates show instantly.")
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
