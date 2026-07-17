"""Command-line adapter for glossary management."""

from __future__ import annotations

import argparse
import json

from src.application.errors import ResourceConflictError
from src.application.glossary import audit, replacements, storage
from src.application.languages import SUPPORTED_TARGET_LANGUAGES
from src.utils.display import DIM, GREEN, RED, RESET, YELLOW


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage novel glossary data")
    public_commands = "{list,add,remove,export,characters,pronoun,character,relationship,validate,audit,apply,dismiss,rollback}"
    subparsers = parser.add_subparsers(dest="command", required=True, metavar=public_commands)

    subparsers.add_parser("list", help="List glossary terms").add_argument("novel")

    add_parser = subparsers.add_parser("add", help="Add or update a glossary term")
    add_parser.add_argument("novel")
    add_parser.add_argument("original")
    add_parser.add_argument("translated")

    remove_parser = subparsers.add_parser("remove", help="Remove a glossary term")
    remove_parser.add_argument("novel")
    remove_parser.add_argument("original")

    subparsers.add_parser("export", help="Print full glossary JSON").add_argument("novel")
    subparsers.add_parser("characters", help="List character memory").add_argument("novel")

    pronoun_parser = subparsers.add_parser("pronoun", help="Set a character pronoun")
    pronoun_parser.add_argument("novel")
    pronoun_parser.add_argument("original")
    pronoun_parser.add_argument("pronoun")

    character_parser = subparsers.add_parser("character", help="Update a character name or role")
    character_parser.add_argument("novel")
    character_parser.add_argument("original")
    character_parser.add_argument("--translated-name", default="", help="Target-language character name")
    character_parser.add_argument("--name-vi", default="", help=argparse.SUPPRESS)
    character_parser.add_argument("--role", default="", help="Character role")

    relationship_parser = subparsers.add_parser("relationship", help="Add or update a character relationship")
    relationship_parser.add_argument("novel")
    relationship_parser.add_argument("from_char")
    relationship_parser.add_argument("to_char")
    relationship_parser.add_argument("relationship")
    relationship_parser.add_argument("--since", type=int, default=None, help="Chapter where this relationship starts")

    subparsers.add_parser("validate", help="Validate glossary JSON").add_argument("novel")

    clean_parser = subparsers.add_parser("clean", help=argparse.SUPPRESS)
    clean_parser.add_argument("novel")
    subparsers._choices_actions = [action for action in subparsers._choices_actions if action.dest != "clean"]

    subparsers.add_parser("audit", help="Audit translated output against glossary terms").add_argument("novel")

    apply_parser = subparsers.add_parser("apply", help="Apply edited terms and character names to existing output")
    apply_parser.add_argument("novel")
    apply_parser.add_argument("--target", choices=sorted(SUPPORTED_TARGET_LANGUAGES), default=None)
    apply_parser.add_argument("--write", action="store_true", help="Write changes; default is preview only")

    dismiss_parser = subparsers.add_parser("dismiss", help="Dismiss all pending glossary replacements")
    dismiss_parser.add_argument("novel")
    dismiss_parser.add_argument("--target", choices=sorted(SUPPORTED_TARGET_LANGUAGES), default=None)

    rollback_parser = subparsers.add_parser("rollback", help="Rollback a previous glossary replacement backup")
    rollback_parser.add_argument("novel")
    rollback_parser.add_argument("backup_id", help="Backup id reported by glossary apply --write")
    return parser


def _print_replacements(result: dict, *, requested_write: bool) -> None:
    replacements = result["replacements"]
    if not replacements:
        print(f"{DIM}No pending glossary replacements:{RESET} {result['novel']}")
        return

    did_write = result["write"]
    for report in sorted(replacements, key=lambda item: (item["chapter"], item["old"])):
        status = report["status"].upper()
        chapter = f"Ch.{report['chapter']}"
        term = "/".join(report["sources"])
        old = report["old"]
        new = report["new"]

        if status == "SAFE":
            color = GREEN if did_write else YELLOW
            label = "APPLIED   " if did_write else "SAFE      "
            print(
                f"{color}{label} {chapter:<6} {term}  {old} → {new}  "
                f"{report['occurrences']}/{report['source_count']} occurrences{RESET}"
            )
        elif status == "ALREADY_APPLIED":
            print(f"{DIM}APPLIED    {chapter:<6} {term}  {old} → {new}  already applied{RESET}")
        elif status == "AMBIGUOUS":
            print(
                f"{YELLOW}AMBIGUOUS {chapter:<6} {term}  source={report['source_count']}, output={report['output_count']}{RESET}"
            )
        elif status == "CONFLICT":
            news = " / ".join(report.get("conflict_news", [new]))
            print(f"{RED}CONFLICT  {chapter:<6} {term}  {old} → {news}{RESET}")
        elif status == "MISSING_OUTPUT":
            print(f"{YELLOW}MISSING   {chapter:<6} {term}  translated chapter not found{RESET}")

    if result["conflicted"]:
        print(f"\n{RED}✗ Conflict(s) detected. Cannot write replacements.{RESET}")
        if requested_write:
            raise SystemExit(1)

    print(f"\n{DIM}{result['changed_files']} output file(s) {'updated' if did_write else 'would be updated'}.{RESET}")
    if result.get("backup_id"):
        print(f"{DIM}Backup: {result['backup_id']}{RESET}")
    if not requested_write and result["changed_files"] and not result["conflicted"]:
        print(f"{DIM}Run again with --write to apply these changes.{RESET}")


def main(argv: list[str] | None = None) -> None:
    """Manage per-novel glossary data."""
    args = _build_parser().parse_args(argv)

    if args.command == "list":
        terms = storage.load_glossary(args.novel).get("terms", {})
        if not terms:
            print(f"{DIM}No glossary terms for {args.novel}.{RESET}")
            return
        for original, translated in sorted(terms.items()):
            print(f"{original}\t{translated}")
        return

    if args.command == "add":
        storage.save_term(args.novel, args.original, args.translated)
        print(f"{GREEN}✓ Added glossary term:{RESET} {args.original} → {args.translated}")
        return

    if args.command == "remove":
        terms = storage.load_glossary(args.novel).get("terms", {})
        if args.original not in terms:
            print(f"{YELLOW}Term not found:{RESET} {args.original}")
            return
        storage.remove_term(args.novel, args.original)
        print(f"{GREEN}✓ Removed glossary term:{RESET} {args.original}")
        return

    if args.command == "export":
        print(json.dumps(storage.load_glossary(args.novel), ensure_ascii=False, indent=2))
        return

    if args.command == "characters":
        entities = storage.load_glossary(args.novel).get("entities", {})
        if not entities:
            print(f"{DIM}No characters for {args.novel}.{RESET}")
            return
        for original, info in sorted(entities.items()):
            translated_name = info.get("translated_name") or info.get("name_vi", "")
            print(f"{original}\t{translated_name}\t{info.get('role', '')}\t{info.get('pronoun', '')}")
        return

    if args.command == "pronoun":
        updated = storage.save_character_pronoun(args.novel, args.original, args.pronoun)
        if updated:
            print(f"{GREEN}✓ Updated pronoun:{RESET} {args.original} → {args.pronoun}")
        else:
            print(f"{YELLOW}Character not found:{RESET} {args.original}")
        return

    if args.command == "character":
        translated_name = args.translated_name or args.name_vi
        if not translated_name and not args.role:
            print(f"{YELLOW}Nothing to update. Use --translated-name and/or --role.{RESET}")
            return
        entities = storage.load_glossary(args.novel).get("entities", {})
        if args.original not in entities:
            print(f"{YELLOW}Character not found:{RESET} {args.original}")
            return
        storage.save_character(
            args.novel,
            args.original,
            translated_name=translated_name,
            role=args.role,
        )
        print(f"{GREEN}✓ Updated character:{RESET} {args.original}")
        return

    if args.command == "relationship":
        entities = storage.load_glossary(args.novel).get("entities", {})
        if args.from_char not in entities or args.to_char not in entities:
            print(f"{YELLOW}Relationship not updated; both characters must exist.{RESET}")
            return
        storage.save_relationship(
            args.novel,
            from_char=args.from_char,
            to_char=args.to_char,
            relationship=args.relationship,
            since=args.since,
        )
        print(f"{GREEN}✓ Updated relationship:{RESET} {args.from_char} → {args.to_char} ({args.relationship})")
        return

    if args.command == "validate":
        issues = audit.validate_glossary(args.novel)
        if not issues:
            print(f"{GREEN}✓ Glossary valid:{RESET} {args.novel}")
            return
        for issue in issues:
            print(f"{RED}✗ {issue}{RESET}")
        raise SystemExit(1)

    if args.command == "clean":
        stats = storage.clean_glossary(args.novel)
        print(
            f"{GREEN}✓ Cleaned glossary:{RESET} {args.novel} "
            f"{DIM}entities={stats['entities']} edges={stats['edges_before']}→{stats['edges_after']} "
            f"address_rules={stats['address_rules_before']}→{stats['address_rules_after']} "
            f"pronoun_examples_removed={stats['pronoun_examples_removed']}{RESET}"
        )
        return

    if args.command == "audit":
        issues = audit.audit_glossary(args.novel)
        if not issues:
            print(f"{GREEN}✓ No glossary audit issues found:{RESET} {args.novel}")
            return
        for issue in issues:
            print(f"{RED}✗ Ch.{issue['chapter']} {issue['issue']}:{RESET} {issue['term']} → {issue['expected']}")
        raise SystemExit(1)

    if args.command == "apply":
        try:
            result = replacements.apply_pending_replacements(
                args.novel,
                target_language=args.target,
                write=args.write,
            )
        except ResourceConflictError as error:
            print(f"{RED}✗ Lock acquisition failed: {error}{RESET}")
            raise SystemExit(1) from error
        _print_replacements(result, requested_write=args.write)
        return

    if args.command == "dismiss":
        try:
            replacements.dismiss_pending_replacements(args.novel, target_language=args.target)
        except ResourceConflictError as error:
            print(f"{RED}✗ Lock acquisition failed: {error}{RESET}")
            raise SystemExit(1) from error
        print(f"{GREEN}✓ Dismissed all pending replacements for:{RESET} {args.novel}")
        return

    if args.command == "rollback":
        try:
            replacements.rollback_glossary_replacement(args.novel, args.backup_id)
        except FileNotFoundError as error:
            print(f"{RED}✗ Rollback failed: {error}{RESET}")
            raise SystemExit(1) from error
        except ResourceConflictError as error:
            print(f"{RED}✗ Lock acquisition failed: {error}{RESET}")
            raise SystemExit(1) from error
        print(f"{GREEN}✓ Successfully rolled back replacements for:{RESET} {args.novel} {DIM}from backup {args.backup_id}{RESET}")
