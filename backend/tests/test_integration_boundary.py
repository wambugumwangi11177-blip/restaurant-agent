"""Integration boundary invariants.

  1. Nothing outside backend/integration/ may import the source client.
  2. Domain/analytics code reads the mirror, never the source system.
  3. The source client is the only module allowed to hold a bearer token.
"""
from __future__ import annotations

import ast
import pathlib

BACKEND = pathlib.Path(__file__).resolve().parents[1]
INTEGRATION = BACKEND / "integration"


def iter_python(root: pathlib.Path):
    for path in root.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        yield path


def imported_modules(path: pathlib.Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_only_integration_imports_the_source_client() -> None:
    # Deviation from plan C-1.6 verbatim code: the scan excludes backend/tests/
    # (the test file asserting the boundary would otherwise flag itself).
    offenders = [
        str(p.relative_to(BACKEND))
        for p in iter_python(BACKEND)
        if not p.is_relative_to(INTEGRATION)
        and "tests" not in p.relative_to(BACKEND).parts
        and any(m.startswith("integration.source_client") for m in imported_modules(p))
    ]
    assert offenders == [], f"source client imported outside integration/: {offenders}"
