import http.client
import http.server
import json
import re
import shutil
import socket
import subprocess
import tempfile
import threading
import time
from pathlib import Path


class MockPeer(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        body = self.rfile.read(int(self.headers["Content-Length"]))
        response = json.dumps({
            "path": self.path,
            "content_type": self.headers.get("Content-Type"),
            "body": json.loads(body),
        }).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        self.wfile.write(response)

    def log_message(self, *args):
        pass


def request(port, path, method="GET", body=None):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
    try:
        connection.request(method, path, body=body)
        response = connection.getresponse()
        return response.status, response.read(), response.getheader("Content-Type", "")
    finally:
        connection.close()


binary = shutil.which("llama-swap")
assert binary, "llama-swap is missing from PATH"
with http.server.ThreadingHTTPServer(("127.0.0.1", 0), MockPeer) as peer:
    thread = threading.Thread(target=peer.serve_forever, daemon=True)
    thread.start()
    try:
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config.yaml"
            config.write_text(
                "models: {}\npeers:\n  smoke:\n"
                f"    proxy: http://127.0.0.1:{peer.server_port}\n"
                "    models: [test-model]\n",
                encoding="utf-8",
            )
            with socket.socket() as sock:
                sock.bind(("127.0.0.1", 0))
                port = sock.getsockname()[1]
            with tempfile.TemporaryFile(mode="w+b") as log:
                process = subprocess.Popen(
                    [binary, "-config", str(config), "-listen", f"127.0.0.1:{port}"],
                    cwd=directory, stdout=log, stderr=subprocess.STDOUT,
                )
                try:
                    deadline = time.monotonic() + 30
                    while time.monotonic() < deadline:
                        assert process.poll() is None, "llama-swap exited during startup"
                        try:
                            if request(port, "/health")[0] == 200:
                                break
                        except (OSError, http.client.HTTPException):
                            pass
                        time.sleep(0.1)
                    else:
                        raise AssertionError("llama-swap did not become healthy within 30 seconds")

                    status, html, content_type = request(port, "/ui/")
                    assert status == 200 and "text/html" in content_type
                    assets = re.findall(r'(?:src|href)="([^\"]+\.(?:js|css))"', html.decode())
                    assert assets, "embedded UI has no JS/CSS assets"
                    for asset in assets:
                        assert asset.startswith("/ui/"), asset
                        status, data, content_type = request(port, asset)
                        assert status == 200 and data and "text/html" not in content_type, asset

                    # Omit Content-Type to exercise v262's JSON fallback as well as routing.
                    status, data, _ = request(
                        port, "/v1/systemone", "POST",
                        json.dumps({"model": "smoke/test-model", "messages": []}),
                    )
                    assert status == 200, (status, data)
                    assert json.loads(data) == {
                        "path": "/v1/systemone",
                        "content_type": "application/json",
                        "body": {"model": "test-model", "messages": []},
                    }
                finally:
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=5)
                    log.seek(0)
                    print(log.read().decode("utf-8", errors="replace"))
    finally:
        peer.shutdown()
        thread.join(timeout=5)

print("Smoke test passed: health, embedded UI assets, and /v1/systemone forwarding")
