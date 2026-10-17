import argparse
import importlib.metadata
import json
import platform
import sys

from pydantic import ValidationError

from aftercare.config import PROJECT_ROOT, Settings
from aftercare.offline import install_offline_guard


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="售后 Agent 工作台（阶段 0，仅离线）")
    commands = result.add_subparsers(dest="command", required=True)
    for name in ("doctor", "serve"):
        command = commands.add_parser(name)
        command.add_argument("--offline", action="store_true", help="禁止非本机网络（默认启用）")
        if name == "serve":
            command.add_argument("--port", type=int, default=8000)
            command.add_argument(
                "--container-network",
                action="store_true",
                help="容器内部监听所有接口；宿主映射仍须绑定 127.0.0.1",
            )
    db = commands.add_parser("db")
    db.add_argument("action", choices=["migrate", "current"])
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    install_offline_guard()
    try:
        settings = Settings(offline=True)
    except ValidationError:
        print(json.dumps({"status": "invalid_config", "code": "CONFIG_INVALID"}))
        return 2

    if args.command == "doctor":
        from aftercare.repositories.database import database_health

        health = database_health(settings)
        dependencies = {
            name: importlib.metadata.version(name)
            for name in ("deepagents", "langgraph", "psycopg", "fastapi", "alembic")
        }
        print(
            json.dumps(
                {
                    "settings": settings.public_summary(),
                    "python": platform.python_version(),
                    "dependencies": dependencies,
                    "database": health.model_dump(),
                    "next_step": "数据库未就绪时，按 docs/operations.md 启动专用数据库并迁移。",
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0 if health.status == "ready" else 1

    if args.command == "serve":
        import uvicorn

        from aftercare.api.app import create_app

        uvicorn.run(
            create_app(settings),
            host="0.0.0.0" if args.container_network else "127.0.0.1",
            port=args.port,
            access_log=False,
        )
        return 0

    if args.command == "db":
        from alembic import command
        from alembic.config import Config
        from sqlalchemy.engine import make_url

        from aftercare.repositories.database import is_local_database

        url = make_url(settings.database_url.get_secret_value())
        if not is_local_database(url) or url.database not in {"aftercare_demo", "aftercare_test"}:
            print("DEDICATED_LOCAL_DATABASE_REQUIRED")
            return 2
        config = Config(str(PROJECT_ROOT / "alembic.ini"))
        config.attributes["settings"] = settings
        try:
            if args.action == "migrate":
                command.upgrade(config, "head")
            else:
                command.current(config)
        except Exception:
            print("DATABASE_COMMAND_FAILED: check local database availability and permissions")
            return 1
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
