"""CLI adapter for importing EPUB books."""

from __future__ import annotations

import argparse
from pathlib import Path

from src.application.crawl.importer import ImportRequest, import_epub_workflow
from src.application.errors import ApplicationError
from src.cli.crawl import common
from src.utils.logging import get_logger


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("epub", type=Path, help="EPUB file path to import.")
    parser.add_argument(
        "-n",
        "--name",
        type=str,
        default=None,
        help="Output slug name. Defaults to the EPUB filename.",
    )
    parser.add_argument(
        "--translated-output",
        type=Path,
        default=None,
        help="Per-novel translated root. Default: TRANSLATED_DIR or ./translated.",
    )
    parser.add_argument(
        "--keep-existing",
        action="store_true",
        help="Keep existing chapter_*.txt files in the target input directory.",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="import",
        description="Import an EPUB into the translated input directory.",
    )
    add_arguments(parser)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    common.configure_logging()
    return run(args)


def run(args: argparse.Namespace) -> int:
    try:
        result = import_epub_workflow(
            ImportRequest(
                epub_path=args.epub,
                name=args.name,
                translated_output=args.translated_output,
                keep_existing=args.keep_existing,
            )
        )
    except ApplicationError as error:
        get_logger().error("Error: %s", error)
        return 1

    for warning in result.warnings:
        get_logger().warning(warning)
    common.print_output(f"Imported: {result.title} ({result.chapters} chapters, {result.illustrations} illustrations)")
    common.print_output(
        "Chapters: "
        f"retained {result.retained} · unchanged {result.unchanged} · "
        f"overwritten {result.overwritten} · added {result.added} · removed {result.removed}"
    )
    for chapter in result.overwritten_chapters:
        common.print_output(f"Overwritten chapter {chapter.number}: {chapter.title}")
    common.print_output(f"Output: {result.output_dir}")
    return 0
