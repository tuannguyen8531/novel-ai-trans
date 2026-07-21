"""
Novel AI Trans — single command-line entry point for the whole pipeline.

Crawls public novel websites, translates chapters with LLMs (Ollama,
Gemini, OpenRouter), and packages the result as EPUB.

Each subcommand lives in its own module under `src/cli/`:

  - src.cli.crawl        → crawl-related command adapters
  - src.cli.insertion    → insert an empty source chapter
  - src.cli.translate    → translate, translate glossary <subcmd>
  - src.cli.pack         → pack
  - src.cli.test         → test (ruff + pyright + pytest)
  - src.cli.build        → build (web UI)

Usage:
    python main.py --help
    python main.py <command> --help
"""

from __future__ import annotations

import sys

COMMANDS = (
    "crawl",
    "generate",
    "validate",
    "import",
    "insert",
    "translate",
    "pack",
    "glossary",
    "build",
    "serve",
    "test",
)


def _print_help() -> None:
    print(__doc__)


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] in {"-h", "--help", "help"}:
        _print_help()
        return 0

    subcommand = sys.argv[1]

    if subcommand not in COMMANDS:
        print(f"Unknown command: {subcommand}\n", file=sys.stderr)
        _print_help()
        return 2

    if subcommand in {"crawl", "generate", "validate", "import"}:
        from src.cli.crawl import crawler, generator, importer, validator

        if subcommand == "crawl":
            return crawler.main(sys.argv[2:])
        if subcommand == "generate":
            return generator.main(sys.argv[2:])
        if subcommand == "validate":
            return validator.main(sys.argv[2:])
        if subcommand == "import":
            return importer.main(sys.argv[2:])

    if subcommand == "insert":
        from src.cli import insertion as insertion_module

        return insertion_module.main(sys.argv[2:])

    if subcommand == "translate":
        from src.cli import translate as translate_module

        translate_module.main(sys.argv[2:])
        return 0

    if subcommand == "pack":
        from src.cli import pack as pack_module

        pack_module.main(sys.argv[2:])
        return 0

    if subcommand == "glossary":
        from src.cli import glossary as glossary_module

        glossary_module.main(sys.argv[2:])
        return 0

    if subcommand == "test":
        from src.cli import test as test_module

        return test_module.main(sys.argv[2:])

    if subcommand == "build":
        from src.cli.build import main as build_main

        return build_main()

    if subcommand == "serve":
        from src.api.__main__ import main as serve_main

        return serve_main()

    print(f"Unknown command: {subcommand}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
