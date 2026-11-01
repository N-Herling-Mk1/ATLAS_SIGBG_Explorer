"""serve_dev.py -- local dev server for the SIG/BG Feature Explorer.

Serves the repo root with no-cache headers, so a plain reload always picks up
edits to app.js / style.css / data/*.js (python -m http.server lets the browser cache them).
Served (not file://), so the in-browser "download this view as one PDF" works too.

    python tools/serve_dev.py              # http://localhost:8000/index.html
    python tools/serve_dev.py --port 8811 --open
"""
import argparse
import functools
import http.server
import os
import sys
import time
import webbrowser

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QUIET_EXT = (".png", ".jpg", ".woff", ".woff2", ".ico")   # don't log every plot image


class NoCache(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()

    def log_message(self, fmt, *args):
        path = self.path.split("?")[0]
        if path.lower().endswith(QUIET_EXT):
            return
        status = str(args[1]) if len(args) > 1 else "?"
        mark = "  " if status.startswith(("2", "3")) else "!!"
        sys.stdout.write(f"[{time.strftime('%H:%M:%S')}] {mark} {status}  {self.command:4s} {path}\n")
        sys.stdout.flush()


def main():
    ap = argparse.ArgumentParser(description="no-cache dev server for the SIG/BG site")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--open", action="store_true", help="open the site in the default browser")
    a = ap.parse_args()

    handler = functools.partial(NoCache, directory=ROOT)
    try:
        srv = http.server.ThreadingHTTPServer(("127.0.0.1", a.port), handler)
    except OSError as e:
        sys.exit(f"[serve_dev] port {a.port} unavailable ({e}); try --port {a.port + 1}")

    url = f"http://localhost:{a.port}/index.html"
    print(f"[serve_dev] root    {ROOT}")
    print(f"[serve_dev] serving {url}   (no-cache; Ctrl+C to stop)")
    print(f"[serve_dev] pages   {url}#/home   {url}#/flow")
    if a.open:
        webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n[serve_dev] stopped")
    finally:
        srv.server_close()


if __name__ == "__main__":
    main()
