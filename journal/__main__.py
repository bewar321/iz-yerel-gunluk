import argparse
import sys
from waitress import serve
from .app import create_app


def main():
    parser = argparse.ArgumentParser(description="Yerel Günlük")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--data-dir", default=None)
    args = parser.parse_args()
    print(f"Yerel Günlük: http://127.0.0.1:{args.port}", flush=True)
    # Let available process resources, not Waitress's 1 GiB default, bound backups.
    serve(create_app(args.data_dir), host="127.0.0.1", port=args.port, threads=6,
          max_request_body_size=sys.maxsize)


if __name__ == "__main__":
    main()
