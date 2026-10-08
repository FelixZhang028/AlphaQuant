"""Serve the built React app against temporary sample data, never production data."""

import argparse
import sys
import tempfile
from pathlib import Path

import uvicorn

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests/integration"))


def main():
    from test_api import completed, environment

    from quant_platform.api.main import create_app

    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8001)
    args = parser.parse_args()
    output = ROOT / "outputs/frontend-e2e"
    output.mkdir(parents=True, exist_ok=True)

    class Factory:
        def mktemp(self, name):
            return Path(tempfile.mkdtemp(prefix=name + "-", dir=output))

    generator = environment.__wrapped__(Factory())
    values = next(generator)
    try:
        root, _, _, service = values
        completed.__wrapped__(values)
        app = create_app(
            service.app_config_path, prior_path=root / "prior.json", serve_frontend=True
        )
        server = uvicorn.Server(
            uvicorn.Config(
                app, host="127.0.0.1", port=args.port, proxy_headers=False, log_level="warning"
            )
        )

        @app.post("/__test_shutdown", include_in_schema=False)
        def shutdown():
            server.should_exit = True
            return {"stopping": True}

        server.run()
    finally:
        generator.close()


if __name__ == "__main__":
    main()
