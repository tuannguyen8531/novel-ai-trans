"""CLI adapter for generating crawler configurations."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.application.config import get_config
from src.application.crawl.generator import generate_config, save_generated_config
from src.application.errors import ApplicationError
from src.application.progress import ProgressEvent
from src.cli.crawl import common
from src.utils.logging import get_logger


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--help",
        action="help",
        help="Show this help message and exit.",
    )
    parser.add_argument("url", type=str, help="URL of the novel's main information page.")
    parser.add_argument(
        "--name",
        type=str,
        default=None,
        help="Novel slug (default: derived from URL).",
    )
    parser.add_argument(
        "--provider",
        type=str,
        default=None,
        help="LLM provider override (ollama/gemini).",
    )
    browser_mode = parser.add_mutually_exclusive_group()
    browser_mode.add_argument(
        "-b",
        "--browser",
        action="store_true",
        help="Use an ephemeral headless browser to fetch pages.",
    )
    browser_mode.add_argument(
        "-h",
        "--headed",
        action="store_true",
        help="Use a visible browser to fetch pages.",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Skip the HTML cache and always re-fetch pages.",
    )
    parser.add_argument(
        "--ignore-sample",
        action="store_true",
        help="Ignore bundled samples and known-domain configs; analyze live HTML with the LLM.",
    )
    parser.add_argument(
        "--translated-output",
        type=Path,
        default=None,
        help="Translated root. Default: TRANSLATED_DIR or ./translated.",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="generate",
        description="Use AI to generate a novel crawl config from an information URL.",
        add_help=False,
    )
    add_arguments(parser)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    common.configure_logging()
    return run(args)


def run(args: argparse.Namespace) -> int:
    """Generate a novel crawl config using AI."""
    try:
        result = generate_config(
            url=args.url,
            name=args.name,
            provider=args.provider,
            use_browser=args.browser,
            headed=args.headed,
            no_cache=args.no_cache,
            ignore_sample=args.ignore_sample,
            progress_callback=print_progress,
        )

        print(f"\n{'═' * 60}")
        print("Generated config:")
        print(f"{'═' * 60}")
        print(json.dumps(result.config, ensure_ascii=False, indent=2))
        print(f"{'═' * 60}")

        name = result.config.get("name", "generated")
        translated_root = args.translated_output or Path(get_config().translated_dir)
        dest = translated_root / str(name) / "config.json"
        answer = input(f"\nSave to {dest}? [Y/n] ").strip().lower()
        if answer in ("", "y", "yes"):
            path = save_generated_config(
                result.config,
                metadata=result.metadata,
                translated_root=translated_root,
            )
            print(f"✅ Config saved to {path}")
            print(f"✅ Metadata saved to {translated_root / str(name) / 'metadata.json'}")
            return 0

        print("Cancelled.")
        return 0
    except KeyboardInterrupt:
        print("\nCancelled.")
        return 130
    except ApplicationError as error:
        get_logger().error("Error: %s", error)
        return 1
    except Exception as error:  # noqa: BLE001 - CLI must report unexpected generation failures.
        get_logger().error("Error: %s", error)
        return 1


def print_progress(event: ProgressEvent) -> None:
    if event.kind == "log":
        get_logger().warning(event.message)
