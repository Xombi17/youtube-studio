#!/usr/bin/env python3
"""
CreatorRadar Dashboard Local Web Server
Serves the interactive HTML dashboard on localhost with live video streaming support.
"""

import sys
import os
import webbrowser
from http.server import SimpleHTTPRequestHandler, HTTPServer
from pathlib import Path

STUDIO_ROOT = Path(__file__).resolve().parent.parent
PORT = 8080

class StudioHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(STUDIO_ROOT), **kwargs)

    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        super().end_headers()

def main():
    port = PORT
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            pass

    server_address = ("127.0.0.1", port)
    url = f"http://127.0.0.1:{port}/dashboard/index.html"
    
    print("\n" + "=" * 60)
    print("  CREATORRADAR STUDIO :: INTERACTIVE WEB DASHBOARD")
    print("=" * 60)
    print(f"• Dashboard URL: {url}")
    print(f"• Serving root:  {STUDIO_ROOT}")
    print("• Press Ctrl+C to stop the dashboard server.\n")

    try:
        httpd = HTTPServer(server_address, StudioHandler)
        # Attempt to open browser automatically
        try:
            webbrowser.open(url)
        except Exception:
            pass
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping dashboard server. Goodbye!")
    except OSError as e:
        if e.errno == 98: # Address in use
            alt_port = port + 1
            print(f"Port {port} busy. Try running: python3 dashboard/serve.py {alt_port}")
        else:
            raise

if __name__ == "__main__":
    main()
