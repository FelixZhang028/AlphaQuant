"""Start the migration API on loopback, with explicit configuration."""

import argparse
import json
import threading
import time
import webbrowser
from pathlib import Path

import uvicorn

from quant_platform.api.main import create_app


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="启动 AlphaQuant 本机 API")
    parser.add_argument("--config", default="configs/app.yaml")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--web", action="store_true", help="同时提供构建后的 React 网页")
    parser.add_argument(
        "--open-browser", action="store_true", help="服务就绪后打开浏览器（需 --web）"
    )
    parser.add_argument("--export-openapi", type=Path, help="导出接口契约后退出，不启动服务")
    args = parser.parse_args(argv)
    if args.export_openapi:
        args.export_openapi.parent.mkdir(parents=True, exist_ok=True)
        args.export_openapi.write_text(
            json.dumps(create_app(args.config).openapi(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"Wrote {args.export_openapi}")
        return
    if not Path(args.config).is_file():
        parser.error("应用配置文件不存在；请从项目根目录启动或指定 --config")
    if not 1 <= args.port <= 65535:
        parser.error("端口必须在1～65535之间")
    if args.open_browser and not args.web:
        parser.error("--open-browser 需要同时指定 --web")
    server = uvicorn.Server(
        uvicorn.Config(
            create_app(args.config, serve_frontend=args.web),
            host="127.0.0.1",
            port=args.port,
            proxy_headers=False,
        )
    )
    if args.open_browser:

        def open_when_ready():
            for _ in range(300):
                if server.started:
                    webbrowser.open(f"http://127.0.0.1:{args.port}/app")
                    return
                if server.should_exit:
                    return
                time.sleep(0.1)

        threading.Thread(target=open_when_ready, daemon=True).start()
    server.run()


if __name__ == "__main__":
    main()
