import json
import os
import socket
import subprocess
import sys
import time
import urllib.request


def test_launcher_and_second_invocation(tmp_path):
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    env = {**os.environ, "STORE_PORT": str(port), "STORE_DATA_DIR": str(tmp_path / "launcher-data")}
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    process = subprocess.Popen([sys.executable, "-m", "app", "--no-browser"], env=env,
                               stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    try:
        ready = False
        for _ in range(100):
            if process.poll() is not None:
                raise AssertionError(process.stderr.read().decode())
            try:
                with opener.open(f"http://127.0.0.1:{port}/health", timeout=.2) as response:
                    assert json.load(response)["application"] == "store-sale"
                ready = True
                break
            except OSError:
                time.sleep(.05)
        assert ready
        second = subprocess.run([sys.executable, "-m", "app", "--no-browser"], env=env,
                                capture_output=True, text=True, timeout=10)
        assert second.returncode == 0, second.stderr
        assert "Existing StoreSale" in second.stdout
        assert process.poll() is None
        with opener.open(f"http://127.0.0.1:{port}/setup", timeout=2) as response:
            assert "ساخت حساب مدیر" in response.read().decode()
    finally:
        process.terminate()
        process.wait(timeout=10)
        process.stderr.close()
