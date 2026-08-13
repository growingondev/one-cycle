from __future__ import annotations

import argparse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib import request, error
import os


class AdminHandler(SimpleHTTPRequestHandler):
    api_base = "http://127.0.0.1:8000"

    def _proxy(self):
        target = f"{self.api_base}{self.path}"
        length = int(self.headers.get("Content-Length", "0") or 0)
        body = self.rfile.read(length) if length else None

        headers = {}
        for key in ("Content-Type", "Accept", "Cookie"):
            value = self.headers.get(key)
            if value:
                headers[key] = value

        req = request.Request(
            target,
            data=body,
            headers=headers,
            method=self.command,
        )

        try:
            resp = request.urlopen(req, timeout=300)
            status = resp.status
            payload = resp.read()
            response_headers = resp.getheaders()
        except error.HTTPError as exc:
            status = exc.code
            payload = exc.read()
            response_headers = exc.headers.items()
        except Exception as exc:
            status = 502
            payload = (
                '{"detail":"FastAPI 연결 실패: %s"}' % str(exc).replace('"', "'")
            ).encode("utf-8")
            response_headers = [("Content-Type", "application/json; charset=utf-8")]

        self.send_response(status)
        for key, value in response_headers:
            lower = key.lower()
            if lower in {"transfer-encoding", "connection", "content-length"}:
                continue
            self.send_header(key, value)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        if self.path.startswith("/api/"):
            return self._proxy()
        if self.path == "/":
            self.path = "/login.html"
        return super().do_GET()

    def do_POST(self):
        if self.path.startswith("/api/"):
            return self._proxy()
        self.send_error(405)

    def do_PATCH(self):
        if self.path.startswith("/api/"):
            return self._proxy()
        self.send_error(405)

    def do_PUT(self):
        if self.path.startswith("/api/"):
            return self._proxy()
        self.send_error(405)

    def do_DELETE(self):
        if self.path.startswith("/api/"):
            return self._proxy()
        self.send_error(405)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5500)
    parser.add_argument("--api", default="http://127.0.0.1:8000")
    args = parser.parse_args()

    os.chdir(Path(__file__).resolve().parent)
    AdminHandler.api_base = args.api.rstrip("/")

    server = ThreadingHTTPServer((args.host, args.port), AdminHandler)
    print(f"Admin UI : http://{args.host}:{args.port}")
    print(f"API proxy: {AdminHandler.api_base}")
    server.serve_forever()


if __name__ == "__main__":
    main()
