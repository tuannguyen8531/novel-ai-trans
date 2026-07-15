"""CLI adapter for validating crawler configurations."""

from __future__ import annotations

import argparse

from src.application.crawl.validator import ConfigIssue, validate_config
from src.application.errors import ApplicationError
from src.cli.crawl import common
from src.utils.logging import get_logger


def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "novel",
        type=str,
        help="Novel slug from translated/<slug>/config.json.",
    )
    parser.add_argument(
        "-b",
        "--browser",
        action="store_true",
        help="Use headless browser to fetch pages.",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="validate",
        description="Test a config's selectors against live HTML.",
    )
    add_arguments(parser)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    common.configure_logging()
    return run(args)


def run(args: argparse.Namespace) -> int:
    """Test a config's selectors against live HTML."""
    try:
        result = validate_config(novel=args.novel, use_browser=args.browser)
    except ApplicationError as error:
        get_logger().error("Error: %s", error)
        return 1
    except Exception as error:  # noqa: BLE001 - keep CLI validation failures user-visible.
        get_logger().error("Error: %s", error)
        return 1

    print(f"\n{'═' * 60}")
    print("Validating config selectors")
    print(f"{'═' * 60}")
    print(f"Config: {result.config_path}")
    print(f"TOC URL: {result.toc_url}")
    print(f"Fetcher: {result.fetcher}")
    print()

    toc_labels = {
        "novel_title_selector",
        "author_selector",
        "chapter_link_selector",
        "toc_next_selector",
        "toc_expand_selector",
    }
    chapter_labels = {
        "chapter_title_selector",
        "chapter_content_selector",
    }
    toc_issues = [issue for issue in result.issues if issue.label in toc_labels]
    chapter_issues = [issue for issue in result.issues if issue.label in chapter_labels]
    remove_issues = [issue for issue in result.issues if issue.label == "remove_selectors"]

    print("📖 TOC Page")
    print(f"   URL: {result.toc_url}")
    for issue in toc_issues:
        print_selector_issue(issue)

    print()
    print(f"📚 Discovered {result.chapter_count} chapters")
    print(f"   Title: {result.metadata.get('title')}")
    if result.metadata.get("author"):
        print(f"   Author: {result.metadata['author']}")

    if result.sample_url:
        print()
        print("📄 Sample Chapter")
        print(f"   URL: {result.sample_url}")
        for issue in chapter_issues:
            print_selector_issue(issue)

        if remove_issues:
            print("   remove_selectors:")
            for issue in remove_issues:
                print_selector_issue(issue, indent="      ")
        else:
            print("   remove_selectors: [] (none configured)")

        if result.content_length is not None:
            print(f"   Extracted content length: {result.content_length} chars")
            if result.content_length < 100:
                print("   ⚠️  Content very short — check selectors or remove_selectors")
        else:
            print("   ❌ Could not extract content — chapter_content_selector returned 0 matches")

    print(f"\n{'═' * 60}")
    return 0


def print_selector_issue(issue: ConfigIssue, *, indent: str = "   ") -> None:
    if issue.status == "skipped":
        print(f"{indent}⏭  {issue.label}: null (skipped)")
        return

    if issue.label == "remove_selectors":
        status = "✅" if issue.status == "ok" else "⚠️"
        print(f"{indent}{status} '{issue.selector}' → {issue.matches} match(es)")
        return

    status = "✅" if issue.status == "ok" else "❌"
    print(f"{indent}{status} {issue.label}: '{issue.selector}' → {issue.matches} match(es)")
