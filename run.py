#!/usr/bin/env python3
import argparse
import os
from web import create_app

# Support for 'flask run' and 'flask db' commands
# Flask checks for 'app' or 'application' in FLASK_APP module
app = create_app(os.getenv("FLASK_ENV", "development"))

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--env", default="development")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()
    
    # Check if we need to reload with a different env
    # Note: If FLASK_ENV was set, 'app' is already created with it above.
    # If args.env differs, we might recreate it, but usually the above global 'app' is what WSGI uses.
    # For direct execution:
    if args.env != os.getenv("FLASK_ENV", "development"):
        app = create_app(args.env)
        
    app.run(host=args.host, port=args.port, debug=app.config["DEBUG"])
