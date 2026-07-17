from __future__ import annotations

import ast
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE_ROOT = ROOT / "src"
WEB_ROOT = ROOT / "web" / "src"

PRESENTATION_SERVICE_OWNERS = {
    "src.cli.logging",
    "src.cli.notifications",
}
LEGACY_MODULES = {
    "src/application/translate.py",
    "src/services/crawler.py",
    "src/services/configs.py",
    "src/api/jobs.py",
    "src/services/packaging.py",
    "src/services/importer.py",
}
RAW_PERSISTENCE_METHODS = {
    "mkdir",
    "iterdir",
    "read_text",
    "rmdir",
    "unlink",
    "write_bytes",
    "write_text",
}
API_IMPORT = re.compile(r"from\s+['\"]@/api/(?:client|sse)['\"]")


def _module(path: Path) -> str:
    relative = path.relative_to(ROOT).with_suffix("")
    parts = list(relative.parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    result: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            result.update(alias.name for alias in node.names if alias.name.startswith("src"))
        elif isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("src"):
            result.add(node.module)
    return result


def _python_modules() -> dict[str, Path]:
    return {_module(path): path for path in SOURCE_ROOT.rglob("*.py")}


def test_backend_dependency_direction() -> None:
    violations: list[str] = []
    for owner, path in _python_modules().items():
        for target in _imports(path):
            if owner.startswith("src.domain.") and not target.startswith("src.domain"):
                violations.append(f"{owner} -> {target}: domain must remain independent")
            if owner.startswith("src.services.") and target.startswith(("src.application", "src.api", "src.cli", "src.graph")):
                violations.append(f"{owner} -> {target}: infrastructure cannot depend on upper layers")
            if owner.startswith("src.application.") and target.startswith(("src.api", "src.cli")):
                violations.append(f"{owner} -> {target}: application cannot depend on adapters")
            if owner.startswith("src.graph.") and target.startswith(("src.application", "src.api", "src.cli")):
                violations.append(f"{owner} -> {target}: graph infrastructure cannot depend on adapters or application")
            if (
                owner.startswith(("src.api.routes.", "src.cli."))
                and target.startswith(("src.domain", "src.graph", "src.services"))
                and owner not in PRESENTATION_SERVICE_OWNERS
            ):
                violations.append(f"{owner} -> {target}: adapters must enter through application workflows")
    assert not violations, "\n".join(violations)


def test_backend_import_graph_has_no_cycles() -> None:
    modules = _python_modules()
    graph: dict[str, set[str]] = defaultdict(set)
    for owner, path in modules.items():
        for target in _imports(path):
            if target in modules and target != owner:
                graph[owner].add(target)

    visiting: list[str] = []
    visited: set[str] = set()

    def visit(module: str) -> None:
        if module in visiting:
            start = visiting.index(module)
            cycle = " -> ".join([*visiting[start:], module])
            raise AssertionError(f"Import cycle: {cycle}")
        if module in visited:
            return
        visiting.append(module)
        for dependency in graph[module]:
            visit(dependency)
        visiting.pop()
        visited.add(module)

    for module in modules:
        visit(module)


def test_application_has_no_raw_persistence_calls() -> None:
    violations: list[str] = []
    for path in (SOURCE_ROOT / "application").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in RAW_PERSISTENCE_METHODS:
                violations.append(f"{path.relative_to(ROOT)}:{node.lineno}: {node.func.attr}()")
    assert not violations, "Raw persistence belongs in services:\n" + "\n".join(violations)


def test_infrastructure_does_not_print_user_messages() -> None:
    violations: list[str] = []
    for layer in ("domain", "graph", "services"):
        for path in (SOURCE_ROOT / layer).rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "print":
                    violations.append(f"{path.relative_to(ROOT)}:{node.lineno}")
    assert not violations, "Infrastructure must use structured logging:\n" + "\n".join(violations)


def test_frontend_api_operations_live_in_composables() -> None:
    violations: list[str] = []
    for path in WEB_ROOT.rglob("*"):
        if path.suffix not in {".ts", ".vue"}:
            continue
        relative = path.relative_to(WEB_ROOT)
        if relative.parts[0] in {"api", "composables"}:
            continue
        text = path.read_text(encoding="utf-8")
        if API_IMPORT.search(text):
            if relative == Path("App.vue") and "setAuthToken" in text and "api." not in text:
                continue
            violations.append(str(relative))
    assert not violations, "Frontend API operations must be owned by composables:\n" + "\n".join(violations)


def test_superseded_modules_are_absent() -> None:
    present = sorted(path for path in LEGACY_MODULES if (ROOT / path).exists())
    assert not present, "Superseded modules remain:\n" + "\n".join(present)
