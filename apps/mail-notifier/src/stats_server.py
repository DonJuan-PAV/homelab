"""
Tiny web endpoint for the Homepage dashboard.

  GET /stats  -> {"today": 3, "outlook_today": 2, "gmail_today": 1, ...}
  GET /health -> {"status": "ok"}

Only numbers are shared, never subjects or senders. Runs in a background
thread, so the mailbox checks keep going at the same time.
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class _StatsHandler(BaseHTTPRequestHandler):
    get_stats = None  # function returning the stats dict, set at startup

    def _send_json(self, status: int, data: dict) -> None:
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?")[0].rstrip("/")
        if path == "/stats":
            self._send_json(200, self.get_stats())
        elif path == "/health":
            self._send_json(200, {"status": "ok"})
        else:
            self._send_json(404, {"error": "not found"})

    def log_message(self, *args):
        pass  # Homepage polls often; don't flood the logs


def start_stats_server(get_stats, host: str, port: int) -> ThreadingHTTPServer:
    handler = type("StatsHandler", (_StatsHandler,), {"get_stats": staticmethod(get_stats)})
    server = ThreadingHTTPServer((host, port), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server
