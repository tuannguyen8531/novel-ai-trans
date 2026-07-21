"""CLI adapter for inserting an empty source chapter."""

from __future__ import annotations

import argparse
import sys
from uuid import uuid4

from src.application.errors import ApplicationError
from src.application.novel.insertion import InsertRequest, insert_chapter
from src.application.progress import ProgressEvent
from src.utils.display import GREEN, RED, RESET, YELLOW


def _print_progress(event: ProgressEvent) -> None:
    if event.message:
        print(f"  {event.message}")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Insert an empty source chapter and shift later chapter data forward.",
        epilog="Example: uv run insert my-novel 301",
    )
    parser.add_argument("novel", help="Novel name under translated/.")
    parser.add_argument("chapter", type=int, help="Chapter number to insert before.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        result = insert_chapter(
            InsertRequest(
                novel=args.novel,
                number=args.chapter,
                content="",
                operation_id=str(uuid4()),
            ),
            progress_callback=_print_progress,
        )
    except ApplicationError as error:
        print(f"{RED}✗ {error}{RESET}", file=sys.stderr)
        return 1
    except OSError as error:
        print(f"{RED}✗ Could not insert chapter: {error}{RESET}", file=sys.stderr)
        return 1

    print(f"{GREEN}✓ Inserted empty chapter {result.chapter} into {result.novel}.{RESET}")
    print(
        f"  Shifted {result.shifted_sources} source chapter(s), "
        f"{result.shifted_translations} translation(s), and {result.shifted_reports} report(s)."
    )
    print(f"  Backup ID: {result.backup_id}")
    if result.repack_required:
        print(f"{YELLOW}⚠ Pack the novel again to update its EPUB.{RESET}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
