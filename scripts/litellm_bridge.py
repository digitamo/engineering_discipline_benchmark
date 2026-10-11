#!/usr/bin/env python3
"""Path bridge so the Kaggle Benchmarks library can talk to LiteLLM.

The library appends `/openapi` to whatever base URL it is given, then calls
`<base>/openapi/chat/completions`. LiteLLM serves `/v1/chat/completions`. This
listens on a local port and rewrites the prefix, so neither the library nor the
running LiteLLM has to change.

    python3 scripts/litellm_bridge.py [--port 4001] [--upstream http://127.0.0.1:4000/v1]

Then point the benchmark at it:

    export MODEL_PROXY_URL=http://127.0.0.1:4001
    export MODEL_PROXY_API_KEY=sk-local

Stdlib only, no dependencies.
"""

import argparse
import json
import sys
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

UPSTREAM_DEFAULT = "http://127.0.0.1:4000/v1"
PREFIX = "/openapi"


class Bridge(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        if self.server.verbose:
            sys.stderr.write("[bridge] " + fmt % args + "\n")

    def _target(self) -> str:
        path = self.path
        if path.startswith(PREFIX):
            path = path[len(PREFIX):]
        return self.server.upstream.rstrip("/") + path

    def _relay(self, body: bytes | None = None):
        headers = {
            key: value
            for key, value in self.headers.items()
            if key.lower() not in ("host", "content-length", "connection")
        }
        request = urllib.request.Request(
            self._target(), data=body, headers=headers, method=self.command
        )
        try:
            with urllib.request.urlopen(request, timeout=600) as response:
                payload = response.read()
                status = response.status
                ctype = response.headers.get("Content-Type", "application/json")
        except urllib.error.HTTPError as error:
            payload = error.read()
            status = error.code
            ctype = error.headers.get("Content-Type", "application/json")
        except Exception as error:  # noqa: BLE001
            payload = json.dumps({"error": {"message": str(error)}}).encode()
            status = 502
            ctype = "application/json"

        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        self._relay(self.rfile.read(length) if length else None)

    def do_GET(self):
        self._relay()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=4001)
    parser.add_argument("--upstream", default=UPSTREAM_DEFAULT)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    server = ThreadingHTTPServer(("127.0.0.1", args.port), Bridge)
    server.upstream = args.upstream
    server.verbose = args.verbose
    print(f"[bridge] 127.0.0.1:{args.port}{PREFIX}/* -> {args.upstream}/*", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
