"""
Structural guards for execution/codemap.py (v2 S0.2).

These do NOT pin which engine is wired where — that changes by design as v2
connects things (E5 owns that question). They pin what must always hold so the
map stays trustworthy: it builds, it is deterministic, every backend/ai module
is classified (so an engine cannot be added and silently left off the map),
and every engine row points at code that exists.
"""
import importlib.util
import json
import os

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_SPEC = importlib.util.spec_from_file_location("codemap", os.path.join(_ROOT, "execution", "codemap.py"))
codemap = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(codemap)


@pytest.fixture(scope="module")
def built():
    payload, markdown = codemap.build()
    return payload, markdown


def test_codemap_builds_a_realistic_graph(built):
    payload, markdown = built
    stats = payload["stats"]
    assert stats["py_modules"] >= 140
    assert stats["py_edges"] >= 500
    assert stats["ts_files"] >= 200
    assert stats["routes"] >= 150
    assert "Engine × surface coverage" in markdown


def test_codemap_is_deterministic(built):
    payload, markdown = built
    again, markdown2 = codemap.build()
    assert json.dumps(payload, sort_keys=True) == json.dumps(again, sort_keys=True)
    assert markdown == markdown2


def test_every_ai_module_is_classified(built):
    """A new module under backend/ai must be an engine row, infrastructure, or a named candidate."""
    payload, _ = built
    unclassified = [r["module"] for r in payload["inventory"]["ai_modules"] if r["status"] == "unclassified"]
    assert unclassified == [], (
        "unclassified backend/ai modules — add an ENGINES row, or classify them in "
        f"execution/codemap.py (INFRASTRUCTURE / CANDIDATES): {unclassified}"
    )


def test_every_built_engine_row_points_at_real_code(built):
    payload, _ = built
    modules = {n["id"] for n in payload["python"]["nodes"]}
    for engine in payload["engines"]:
        if engine["kind"] == "none":
            continue
        for target in engine["targets"]:
            name = target.split(":")[0]
            assert any(m == name or m.startswith(name + ".") for m in modules), \
                f"engine '{engine['key']}' targets {name}, which no longer exists"
            if engine["kind"] == "symbol":
                module, func = target.split(":")
                funcs = {f for f in codemap.build_python()["func_info"][module]}
                assert func in funcs, f"{module}.{func} no longer exists"


def test_matrix_has_a_cell_for_every_engine_and_surface(built):
    payload, _ = built
    surfaces = list(payload["surfaces"])
    assert surfaces == ["home", "os", "reports", "old_dash"]
    for engine in payload["engines"]:
        assert set(payload["matrix"][engine["key"]]) == set(surfaces)
        for state in payload["matrix"][engine["key"]].values():
            assert state in {"wired", "partial", "not_shown", "reimplemented", "not_built"}


def test_home_surface_reaches_its_known_engines(built):
    """Sanity anchors that are true by construction today (Home is one call to owner.home, which reads the overview engines)."""
    payload, _ = built
    assert any("owner.home" in c for c in payload["surfaces"]["home"]["api_calls"])
    assert payload["matrix"]["decisions"]["home"] == "wired"
    assert payload["matrix"]["sales_summary"]["home"] == "wired"
