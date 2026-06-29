"""
Novel AI Trans — single command-line entry point for the whole pipeline.

Crawls public novel websites, translates chapters with LLMs (Ollama,
Gemini, OpenRouter), and packages the result as EPUB/PDF.

Each subcommand lives in its own module under `src/cli/`:

  - src.cli.crawl        → crawl, generate, validate, import
  - src.cli.translate    → translate, translate glossary <subcmd>
  - src.cli.pack         → pack
  - src.cli.test         → test (ruff + pyright + pytest)
  - scripts.build        → build (web UI)

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
        from src.cli import crawl as crawl_module

        if subcommand == "crawl":
            sys.argv = [sys.argv[0], "crawl", *sys.argv[2:]]
            return crawl_module.main()
        if subcommand == "generate":
            return crawl_module.generate_main(sys.argv[2:])
        if subcommand == "validate":
            return crawl_module.validate_main(sys.argv[2:])
        if subcommand == "import":
            return crawl_module.import_main(sys.argv[2:])

    if subcommand == "translate":
        from src.cli import translate as translate_module

        if len(sys.argv) >= 3 and sys.argv[2] == "glossary":
            translate_module.glossary_main(sys.argv[3:])
            return 0
        translate_module.translate_main()
        return 0

    if subcommand == "pack":
        from src.cli import pack as pack_module

        pack_module.pack_main()
        return 0

    if subcommand == "glossary":
        from src.cli.translate import glossary_main

        glossary_main(sys.argv[2:])
        return 0

    if subcommand == "test":
        from src.cli import test as test_module

        return test_module.test_main(sys.argv[2:])

    if subcommand == "build":
        from scripts.build import main as build_main

        return build_main()

    if subcommand == "serve":
        from src.api.__main__ import main as serve_main

        return serve_main()

    print(f"Unknown command: {subcommand}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
