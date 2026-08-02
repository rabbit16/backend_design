import argparse
from pathlib import Path

from alembic import command
from alembic.config import Config

ROOT = Path(__file__).resolve().parents[1]
ALEMBIC_INI = ROOT / "alembic.ini"


def get_config() -> Config:
    return Config(str(ALEMBIC_INI))


def migrate(message: str) -> None:
    cfg = get_config()
    command.revision(cfg, message=message, autogenerate=True)
    command.upgrade(cfg, "head")


def main() -> None:
    parser = argparse.ArgumentParser(description="Database migration helper")
    subparsers = parser.add_subparsers(dest="command", required=True)

    migrate_parser = subparsers.add_parser("migrate", help="autogenerate a revision and upgrade to head")
    migrate_parser.add_argument("-m", "--message", default="auto migration")

    revision_parser = subparsers.add_parser("revision", help="create a migration revision")
    revision_parser.add_argument("-m", "--message", required=True)
    revision_parser.add_argument("--autogenerate", action="store_true")

    upgrade_parser = subparsers.add_parser("upgrade", help="upgrade database")
    upgrade_parser.add_argument("revision", nargs="?", default="head")

    downgrade_parser = subparsers.add_parser("downgrade", help="downgrade database")
    downgrade_parser.add_argument("revision")

    args = parser.parse_args()
    cfg = get_config()

    if args.command == "migrate":
        migrate(args.message)
    elif args.command == "revision":
        command.revision(cfg, message=args.message, autogenerate=args.autogenerate)
    elif args.command == "upgrade":
        command.upgrade(cfg, args.revision)
    elif args.command == "downgrade":
        command.downgrade(cfg, args.revision)


if __name__ == "__main__":
    main()
