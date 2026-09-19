"""One-time setup. Downloads dependencies/models, never sends journal entries."""
import os
from pathlib import Path
import platform
import subprocess
import sys
import tarfile
import urllib.request
import venv

from run import ROOT, ollama_path, start_ollama

OLLAMA_VERSION = "0.34.2"
# Official vendor release, pinned for reproducible macOS setup.
OLLAMA_URL = f"https://github.com/ollama/ollama/releases/download/v{OLLAMA_VERSION}/ollama-darwin.tgz"


def main():
    if sys.version_info < (3, 9):
        raise SystemExit("Python 3.9 veya üzeri gerekli.")
    virtual = ROOT / ".venv"
    if not virtual.exists():
        venv.EnvBuilder(with_pip=True).create(virtual)
    python = virtual / ("Scripts/python.exe" if os.name == "nt" else "bin/python3")
    subprocess.run([str(python), "-m", "pip", "install", "-r", str(ROOT / "requirements.txt")], check=True)
    if not ollama_path():
        if platform.system() != "Darwin":
            raise SystemExit("Önce https://ollama.com/download adresinden Ollama kurun; ardından bu komutu tekrar çalıştırın.")
        target = ROOT / "data" / "runtime" / "ollama"
        target.mkdir(parents=True, exist_ok=True)
        archive = target.parent / "ollama.tgz"
        print("Resmî Ollama macOS paketi indiriliyor…", flush=True)
        urllib.request.urlretrieve(OLLAMA_URL, archive)
        with tarfile.open(archive) as package:
            # Reject archive traversal; shipped dylib symlinks are relative to this directory.
            for member in package.getmembers():
                dest = (target / member.name).resolve()
                if target.resolve() not in dest.parents and dest != target.resolve():
                    raise RuntimeError("Güvensiz arşiv yolu.")
                if member.issym() or member.islnk():
                    link = (dest.parent / member.linkname).resolve()
                    if target.resolve() not in link.parents:
                        raise RuntimeError("Güvensiz arşiv bağlantısı.")
                if not (member.isfile() or member.isdir() or member.issym() or member.islnk()):
                    raise RuntimeError("Desteklenmeyen arşiv öğesi.")
            package.extractall(target)
        archive.unlink()
    process = start_ollama()
    try:
        env = dict(os.environ, OLLAMA_HOST="127.0.0.1:11434", OLLAMA_NO_CLOUD="1")
        for model in ("qwen3:4b", "embeddinggemma:latest"):
            subprocess.run([ollama_path(), "pull", model], env=env, check=True)
        print("Hazır. macOS: Başlat.command dosyasını açın. Diğer sistemler: .venv Python ile scripts/run.py çalıştırın.")
    finally:
        if process and process.poll() is None:
            process.terminate()
            process.wait(timeout=10)


if __name__ == "__main__":
    main()
