import os
import secrets
from pathlib import Path
from urllib.parse import urlsplit

from flask import Flask, jsonify, render_template, request
from werkzeug.exceptions import HTTPException

from .store import Store, ValidationError
from .ollama import Ollama, AIError
from .rag import Engine


def create_app(data_dir=None, ai=None):
    app = Flask(__name__)
    root = Path(data_dir or os.environ.get("JOURNAL_DATA_DIR", Path(__file__).resolve().parent.parent / "data"))
    store = Store(root / "journal.sqlite3")
    app.extensions["store"] = store
    model = ai or Ollama()
    engine = Engine(store, model)
    app.extensions["engine"] = engine
    token = secrets.token_urlsafe(32)
    app.config["LOCAL_TOKEN"] = token

    @app.before_request
    def local_only():
        # Backups grow with the journal; entry request limits must not cap restores.
        if request.path != "/api/restore":
            request.max_content_length = 16 * 1024 * 1024
        host = urlsplit("http://" + request.host).hostname
        if host not in ("127.0.0.1", "localhost", "::1"):
            return jsonify(error="Yalnızca yerel erişime izin verilir."), 403
        origin = request.headers.get("Origin")
        if origin and origin != request.host_url.rstrip("/"):
            return jsonify(error="Farklı kaynaktan gelen istek reddedildi."), 403
        if request.path.startswith("/api/"):
            supplied = request.headers.get("X-Journal-Token", "")
            if not secrets.compare_digest(supplied, token):
                return jsonify(error="Oturum yenilendi. Sayfayı yeniden açın."), 403

    @app.after_request
    def headers(response):
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        return response

    @app.errorhandler(ValidationError)
    def invalid(exc):
        return jsonify(error=str(exc)), 400

    @app.errorhandler(AIError)
    def model_error(exc):
        return jsonify(error=str(exc)), 503

    @app.errorhandler(KeyError)
    def missing(exc):
        return jsonify(error="Kayıt bulunamadı."), 404

    @app.errorhandler(HTTPException)
    def http_error(exc):
        return jsonify(error="İstek işlenemedi. Biçimi ve dosya boyutunu kontrol edin."), exc.code

    @app.get("/")
    def home():
        return render_template("index.html", token=token)

    @app.get("/api/entries")
    def list_entries():
        return jsonify(entries=store.entries(request.args.get("start"), request.args.get("end")), revision=store.revision())

    @app.get("/api/entries/<entry_id>")
    def get_entry(entry_id):
        entry = store.get(entry_id)
        if not entry:
            raise KeyError(entry_id)
        return jsonify(entry)

    @app.post("/api/entries")
    def create_entry():
        return jsonify(store.save(request.get_json())), 201

    @app.put("/api/entries/<entry_id>")
    def update_entry(entry_id):
        return jsonify(store.save(request.get_json(), entry_id))

    @app.delete("/api/entries/<entry_id>")
    def delete_entry(entry_id):
        store.delete(entry_id)
        return jsonify(ok=True, revision=store.revision())

    @app.get("/api/backup")
    def export_backup():
        response = jsonify(store.export())
        response.headers["Content-Disposition"] = 'attachment; filename="yerel-gunluk-yedek.json"'
        return response

    @app.post("/api/restore")
    def restore_backup():
        data = request.get_json()
        if not isinstance(data, dict) or data.get("confirm_replace") is not True:
            raise ValidationError("Geri yükleme mevcut kayıtların yerini alır; onay gerekli.")
        count = store.restore(data.get("backup"))
        return jsonify(count=count, revision=store.revision())

    @app.get("/api/status")
    def status():
        return jsonify(model.status())

    @app.get("/api/revision")
    def revision():
        return jsonify(revision=store.revision())

    @app.post("/api/ask")
    def ask():
        data = request.get_json()
        if not isinstance(data, dict):
            raise ValidationError("Geçerli bir soru gönderin.")
        return jsonify(engine.ask(data.get("question"), data.get("start"), data.get("end")))

    return app
