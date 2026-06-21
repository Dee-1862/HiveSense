"""
Local REST surface for the dashboard that runs the REAL HiveDoctor (Orkes Agentspan)
backend on its durable-registry fallback path - so the workflow is the correct
implementation with results you can show today, WITHOUT waiting on the Conductor
server download. With `agentspan server start` + AGENTSPAN_LIVE=1 the very same flow
(hive_doctor.start / respond) executes on the live durable engine instead.

Drop-in replacement for frontend/mock_coordinator.js on :8000 (what Vite proxies /api -> ).
Serves exactly what the dashboard's api.js already calls:
  GET  /api/status               ApiaryStatusResponse shape (header data-link)
  GET  /api/treatments           {treatments: [run, ...]}      (HiveDoctor runs)
  POST /api/treatment/start      {hive}            -> hive_doctor.start(hive)
  POST /api/treatment/respond    {id, approve, note} -> hive_doctor.respond(...)
  GET  /api/advise?hive=..&...   {advice}          (plain-language, VoI-grounded)

Run:  python -m src.agentspan.server      (PORT env overrides 8000)
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from src.agentspan import hive_doctor, runs  # noqa: E402
import hive_state  # noqa: E402

# Per-dashboard-hive sensor signals. Chosen so the Value-of-Information gate produces a
# realistic SPREAD - it asks only on genuine close calls and stays quiet otherwise:
#   B1/A3/C3 -> close call on mites          -> ASK (durable approval gate)
#   C1 (queenless), B3 (swarm)               -> confident -> AUTO-ACT
#   A1/A2/B2/C2 -> clearly calm              -> AUTO-HOLD (just watch)
SIGNALS = {
    "A1": dict(acoustic_stress=0.08, vision_mite_rate=0.000, vision_ran=True),                       # calm -> HOLD
    "A2": dict(acoustic_stress=0.10, vision_mite_rate=0.000, vision_ran=True),                       # calm -> HOLD
    "A3": dict(acoustic_stress=0.55, vision_mite_rate=0.000, vision_ran=False),                      # vision skipped, raised sound -> ASK
    "B1": dict(acoustic_stress=0.72, vision_mite_rate=0.038, vision_ran=True),                       # mites near the line -> ASK
    "B2": dict(acoustic_stress=0.09, vision_mite_rate=0.000, vision_ran=True),                       # calm -> HOLD
    "B3": dict(acoustic_stress=0.10, vision_mite_rate=0.000, vision_ran=True, swarm_alert=True),     # swarm flag -> AUTO-ACT
    "C1": dict(acoustic_stress=0.10, vision_mite_rate=0.000, vision_ran=True, queenless_alert=True), # queenless -> AUTO-ACT
    "C2": dict(acoustic_stress=0.10, vision_mite_rate=0.000, vision_ran=True),                       # calm -> HOLD
    "C3": dict(acoustic_stress=0.50, vision_mite_rate=0.000, vision_ran=False),                      # vision skipped -> ASK
}
HIVES = list(SIGNALS)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _seed_state() -> None:
    """Write the demo signals into the shared store as verdicts, so hive_doctor's
    compute_decision (which reads hive_state) runs the gate on real, varied inputs."""
    verdicts = {}
    for code, s in SIGNALS.items():
        verdicts[code] = [{
            "hive_id": code,
            "acoustic_stress": s.get("acoustic_stress", 0.0),
            "vision_mite_rate": s.get("vision_mite_rate", 0.0),
            "vision_ran": s.get("vision_ran", False),
            "queenless_alert": s.get("queenless_alert", False),
            "swarm_alert": s.get("swarm_alert", False),
            "timestamp": _now(),
        }]
    try:
        hive_state.save_verdicts(verdicts)
    except Exception as e:  # pragma: no cover
        print("warn: could not seed hive_state:", e)


def _reset_registry() -> None:
    """Start each demo from a clean slate of treatment runs."""
    try:
        runs._save({})  # one-time reset of data/treatments.json
    except Exception:
        pass


# Live-link payload: kept identical to the mock so the header behaves the same.
def _status_payload() -> dict:
    t = _now()
    return {"hives": {
        "hive3": [
            {"hive_id": "hive3", "varroa_status": "watch", "queenless_alert": False, "swarm_alert": False, "traffic": 12, "position": [0, 0], "timestamp": t},
            {"hive_id": "hive3", "varroa_status": "alert", "queenless_alert": False, "swarm_alert": False, "traffic": -82, "position": [0, 0], "timestamp": t},
        ],
        "hive5": [
            {"hive_id": "hive5", "varroa_status": "clear", "queenless_alert": False, "swarm_alert": True, "traffic": 64, "position": [3, 0], "timestamp": t},
        ],
    }}


def _advice(params: dict) -> str:
    """Plain-language advice grounded in the SAME VoI computation (no LLM needed, so it
    works keyless; swap for the Gemini advisor by setting GEMINI_API_KEY + reasoning.py)."""
    hive = (params.get("hive", ["?"])[0]).upper()
    plan = hive_doctor.compute_decision(hive) if hive in SIGNALS else None
    if not plan:
        return f"Hive {hive}: no live signals to advise on yet."
    lead = next((g for g in plan["gates"] if g["condition"] == plan["lead_condition"]), plan["gates"][0])
    tail = {"ask": "It's a close call, so the beekeeper's judgement is worth the interruption.",
            "auto_act": "Confident enough to handle it without interrupting you.",
            "auto_hold": "All calm - just keep watching, nothing to do."}[plan["decision"]]
    return f"{plan['headline']} {lead['explain']} {tail}"


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, obj) -> None:
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("content-type", "application/json")
        self.send_header("access-control-allow-origin", "*")
        self.send_header("access-control-allow-methods", "GET,POST,OPTIONS")
        self.send_header("access-control-allow-headers", "content-type")
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> dict:
        n = int(self.headers.get("content-length", 0) or 0)
        if not n:
            return {}
        try:
            return json.loads(self.rfile.read(n) or b"{}")
        except Exception:
            return {}

    def do_OPTIONS(self):
        self._send(204, {})

    def do_GET(self):
        path = urlparse(self.path).path
        if path.startswith("/api/status"):
            return self._send(200, _status_payload())
        if path.startswith("/api/treatments"):
            return self._send(200, {"treatments": runs.list_runs()})
        if path.startswith("/api/advise"):
            return self._send(200, {"advice": _advice(parse_qs(urlparse(self.path).query))})
        return self._send(404, {"error": "not found"})

    def do_POST(self):
        path = urlparse(self.path).path
        data = self._body()
        if path.startswith("/api/treatment/start"):
            hive = str(data.get("hive", "")).upper()
            if hive not in SIGNALS:
                return self._send(400, {"error": f"unknown hive {hive}"})
            return self._send(200, hive_doctor.start(hive))
        if path.startswith("/api/treatment/respond"):
            try:
                run = hive_doctor.respond(data.get("id"), bool(data.get("approve")), data.get("note", ""))
                return self._send(200, run or {"error": "unknown run"})
            except KeyError:
                return self._send(404, {"error": "unknown run id"})
            except Exception as e:
                return self._send(400, {"error": str(e)})
        return self._send(404, {"error": "not found"})

    def log_message(self, *a):  # quiet
        pass


def main():
    _reset_registry()
    _seed_state()
    port = int(os.getenv("PORT", "8000"))
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    live = os.getenv("AGENTSPAN_LIVE", "0") == "1" and hive_doctor.HAS_AGENTSPAN
    engine = "live Agentspan/Conductor" if live else "durable on-disk registry (no Conductor needed)"
    print(f"HiveDoctor + status server on http://127.0.0.1:{port}")
    print(f"  VoI gate: closed-form (always on) · approval engine: {engine}")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
