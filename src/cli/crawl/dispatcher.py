"""Combined dispatcher for crawl-related commands."""

from __future__ import annotations

import argparse

from src.cli.crawl import common, crawler, generator, importer, validator


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="novel-crawler",
        description="Download chapters using the selected novel's config.json.",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable debug logging.",
    )
    parser.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="Suppress crawler progress and non-error logs.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    crawl_parser = subparsers.add_parser(
        "crawl",
        help="Download a novel into text files.",
        add_help=False,
    )
    crawler.add_arguments(crawl_parser)

    generate_parser = subparsers.add_parser(
        "generate",
        help="Use AI to generate a novel crawl config from an information URL.",
        add_help=False,
    )
    generator.add_arguments(generate_parser)

    validate_parser = subparsers.add_parser(
        "validate",
        help="Test a config's selectors against live HTML.",
    )
    validator.add_arguments(validate_parser)

    import_parser = subparsers.add_parser(
        "import",
        help="Import an EPUB into the translated input directory.",
    )
    importer.add_arguments(import_parser)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    common.configure_logging(verbose=args.verbose, quiet=args.quiet)

    commands = {
        "crawl": crawler.run,
        "generate": generator.run,
        "validate": validator.run,
        "import": importer.run,
    }
    command = commands.get(args.command)
    if command is None:
        parser.error(f"Unknown command: {args.command}")
        return 2
    return command(args)
