import argparse
from waitress import serve
from .app import MAX_RESTORE_BYTES, create_app


def main():
    parser = argparse.ArgumentParser(description="Yerel Günlük")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--data-dir", default=None)
    args = parser.parse_args()
    app = create_app(args.data_dir)
    print(f"Yerel Günlük: http://127.0.0.1:{args.port} (erişim için Başlat.command kullanın)", flush=True)
    serve(app, host="127.0.0.1", port=args.port, threads=6,
          max_request_body_size=MAX_RESTORE_BYTES)


if __name__ == "__main__":
    main()
