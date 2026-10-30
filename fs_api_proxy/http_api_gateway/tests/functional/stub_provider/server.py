#!/usr/bin/env python3

from hashlib import sha256
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os


NAME = os.environ["BACKEND_NAME"]
ROUTES = json.loads(os.environ["ROUTES_JSON"])
DISCOVERY_PATH = "/.well-known/http-api-routes/v1"
REVISION = "sha256:" + sha256(
    json.dumps(ROUTES, sort_keys=True, separators=(",", ":")).encode()
).hexdigest()


class Handler(BaseHTTPRequestHandler):
    def send_json(self, document, status=200, include_body=True):
        body = json.dumps(document, sort_keys=True).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if include_body:
            self.wfile.write(body)

    def respond(self, include_body=True):
        path = self.path.split("?", 1)[0]
        if path.rstrip("/") == DISCOVERY_PATH:
            self.send_json(
                {
                    "schema_version": 1,
                    "revision": REVISION,
                    "routes": ROUTES,
                },
                include_body=include_body,
            )
            return
        self.send_json(
            {"backend": NAME, "method": self.command, "path": path},
            include_body=include_body,
        )

    do_GET = respond
    do_POST = respond
    do_PUT = respond

    def do_HEAD(self):
        self.respond(include_body=False)

    def log_message(self, message, *args):
        print(f"{self.address_string()} - {message % args}", flush=True)


ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
