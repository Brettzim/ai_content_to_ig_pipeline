"""
Temporary local file server via ngrok.

Used as a FALLBACK to host downloaded videos at a public URL when the
original xAI temporary URL has expired.  Not needed for the standard
pipeline (which passes the xAI URL straight to Instagram while fresh).

Usage:
    with FileServer(ngrok_path="C:/path/to/ngrok.exe", port=8000) as server:
        public_url = server.public_url_for("videos/my_video.mp4")
        # public_url is now accessible by Instagram
"""

import http.server
import socketserver
import subprocess
import threading
import time
import logging
from pathlib import Path

import requests

logger = logging.getLogger(__name__)


class FileServer:
    def __init__(self, ngrok_path: str, port: int = 8000, serve_dir: str = "."):
        self.ngrok_path = Path(ngrok_path)
        self.port = port
        self.serve_dir = Path(serve_dir).resolve()
        self._httpd = None
        self._thread = None
        self._ngrok = None
        self.public_url: str = ""

    def start(self) -> "FileServer":
        # Start Python file server rooted at serve_dir
        handler = http.server.SimpleHTTPRequestHandler

        class SilentHandler(handler):
            def log_message(self, *args):
                pass  # suppress request logs

        self._httpd = socketserver.TCPServer(("", self.port), SilentHandler)
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()
        logger.info(f"Local file server started on port {self.port} (serving {self.serve_dir})")

        # Start ngrok tunnel
        if not self.ngrok_path.exists():
            raise FileNotFoundError(f"ngrok not found at {self.ngrok_path}")

        self._ngrok = subprocess.Popen(
            [str(self.ngrok_path), "http", str(self.port)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        time.sleep(2)  # give ngrok time to establish tunnel

        # Fetch the public URL from ngrok's local API
        resp = requests.get("http://localhost:4040/api/tunnels", timeout=10)
        resp.raise_for_status()
        tunnels = resp.json().get("tunnels", [])
        if not tunnels:
            raise RuntimeError("ngrok tunnel not found — is ngrok authenticated?")

        self.public_url = tunnels[0]["public_url"]
        logger.info(f"ngrok tunnel: {self.public_url}")
        return self

    def public_url_for(self, relative_path: str) -> str:
        """Return the public URL for a file relative to the project root."""
        # Strip leading ./ or /
        clean = str(relative_path).lstrip("./\\")
        return f"{self.public_url}/{clean}"

    def stop(self):
        if self._httpd:
            self._httpd.shutdown()
        if self._ngrok:
            self._ngrok.terminate()
        logger.info("File server and ngrok stopped")

    def __enter__(self):
        return self.start()

    def __exit__(self, *_):
        self.stop()
