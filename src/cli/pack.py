"""Packager CLI: turn translated output into EPUB / PDF.

Re-exports the reusable building blocks from :mod:`src.services.packaging`
and keeps the argparse entry point :func:`pack_main`. The application
workflow in :mod:`src.application.pack` performs the actual work.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from src.application.config_context import get_config
from src.application.pack import (
    PackRequest,
    PackResult,
    run_pack,
)
from src.application.progress import ProgressEvent
from src.domain.target_language import SUPPORTED_TARGET_LANGUAGES
from src.services.packaging import package_file_stem
from src.utils.display import GREEN, RED, RESET, YELLOW

# Re-exported for tests and external callers.
__all__ = [
    "pack_main",
    "package_file_stem",
]


def _print_progress(event: ProgressEvent) -> None:
    if event.kind in {"phase", "chapter_loaded", "completed"}:
        if event.message:
            print(f"  {event.message}")
    elif event.kind == "skipped":
        print(f"  {event.message}")


def pack_main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="📦 Novel Translator Packager — Package output text files into EPUB/PDF",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "novel",
        help="Novel name (must match directory in translated/ or output/)",
    )
    parser.add_argument(
        "-f",
        "--format",
        choices=["epub", "pdf", "all"],
        default="all",
        help="Packaging format (default: all)",
    )
    parser.add_argument(
        "-t",
        "--title",
        default="",
        help="Custom book title (defaults to novel name)",
    )
    parser.add_argument(
        "-a",
        "--author",
        default="AI Translator",
        help="Author name in book metadata (default: AI Translator)",
    )
    parser.add_argument(
        "--target",
        choices=sorted(SUPPORTED_TARGET_LANGUAGES),
        default=get_config().target_language,
        help="Target language to package (default: vi)",
    )
    parser.add_argument(
        "-o",
        "--output",
        default="",
        help="Custom output directory to save EPUB/PDF",
    )
    parser.add_argument(
        "--dark",
        action="store_true",
        help="Enable dark mode for PDF (dark background, light text)",
    )

    args = parser.parse_args(argv) if argv is not None else parser.parse_args()

    novel_name = args.novel
    config = get_config()
    config.target_language = args.target

    formats = ("all",) if args.format == "all" else (args.format,)

    request = PackRequest(
        novel=novel_name,
        target_language=args.target,
        formats=formats,
        title=args.title,
        author=args.author,
        dark_mode=args.dark,
        output_dir=Path(args.output) if args.output else None,
    )

    try:
        result: PackResult = run_pack(request, progress_callback=_print_progress)
    except (SystemExit, KeyboardInterrupt):
        raise
    except Exception as error:
        print(f"{RED}✗ {error}{RESET}")
        sys.exit(1)

    if not result.artifacts:
        print(f"{YELLOW}⚠ No artifacts produced.{RESET}")
        return

    for artifact in result.artifacts:
        print(f"  {GREEN}✓ {artifact.format.upper()} file saved to: {artifact.path}{RESET}")
    print(f"\n{GREEN}🎉 Packaging complete!{RESET}\n")
