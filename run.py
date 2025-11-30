#!/usr/bin/env python3
import argparse

from web import create_app

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--env", default="development")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()
    app = create_app(args.env)
    app.run(host=args.host, port=args.port, debug=app.config["DEBUG"])
