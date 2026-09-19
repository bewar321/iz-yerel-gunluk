"""Start local services without installing software or using a remote AI endpoint."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import urllib.request
import webbrowser

ROOT = Path(__file__).resolve().parent.parent


def service_ready(port):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(f"http://127.0.0.1:{port}/api/version", timeout=2) as response:
            return response.status == 200
    except OSError:
        return False


def ollama_path():
    local = ROOT / "data" / "runtime" / "ollama" / ("ollama.exe" if os.name == "nt" else "ollama")
    return str(local) if local.exists() else shutil.which("ollama")


def start_ollama():
    if service_ready(11434):
        return None
    binary = ollama_path()
    if not binary:
        print("Ollama bulunamadı. Günlük çalışır; AI için python3 scripts/setup.py kullanın.")
        return None
    data = ROOT / "data"
    data.mkdir(exist_ok=True, mode=0o700)
    env = dict(os.environ, OLLAMA_NO_CLOUD="1", OLLAMA_HOST="127.0.0.1:11434", OLLAMA_MODELS=str(data / "models"))
    # Logs contain service diagnostics, not application journal content.
    with (data / "ollama.log").open("a") as log:
        process = subprocess.Popen([binary, "serve"], env=env, stdout=log, stderr=log)
    for _ in range(40):
        if service_ready(11434):
            return process
        if process.poll() is not None:
            break
        time.sleep(0.25)
    print("Ollama başlamadı; data/ollama.log dosyasını kontrol edin.")
    return process


def main():
    model_process = start_ollama()
    process = subprocess.Popen([sys.executable, "-m", "journal"], cwd=ROOT)
    try:
        # Show the app only once its listening socket is ready.
        import socket
        for _ in range(60):
            if process.poll() is not None:
                return process.returncode
            try:
                with socket.create_connection(("127.0.0.1", 8765), timeout=0.25):
                    webbrowser.open("http://127.0.0.1:8765")
                    break
            except OSError:
                time.sleep(0.25)
        print("Kapatmak için bu terminalde Ctrl+C kullanın.")
        return process.wait()
    except KeyboardInterrupt:
        return 0
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=10)
        if model_process and model_process.poll() is None:
            model_process.terminate()
            model_process.wait(timeout=10)


if __name__ == "__main__":
    raise SystemExit(main())
