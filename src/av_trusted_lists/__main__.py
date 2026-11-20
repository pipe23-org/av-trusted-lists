"""Command-line entry point for av-trusted-lists."""

import argparse
from pathlib import Path

from av_trusted_lists.page import build
from av_trusted_lists.watch import watch


def main(argv: list[str] | None = None) -> None:
    """Run the av-trusted-lists command."""
    parser = argparse.ArgumentParser(
        prog="av-trusted-lists",
        description="Archive the EU age-verification trusted lists and build a page from them.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    watch_parser = commands.add_parser(
        "watch", help="fetch both lists, archive a changed list, log the check"
    )
    watch_parser.add_argument("archive", type=Path, help="the archive directory")
    watch_parser.add_argument(
        "--reports", type=Path, default=Path("reports"), help="directory for change reports"
    )
    build_parser = commands.add_parser("build", help="build the page from the archive")
    build_parser.add_argument("archive", type=Path, help="the archive directory")
    build_parser.add_argument("out", type=Path, help="directory the page is written to")
    args = parser.parse_args(argv)
    if args.command == "watch":
        if not watch(args.archive, args.reports):
            raise SystemExit(1)
    else:
        build(args.archive, args.out)


if __name__ == "__main__":
    main()
