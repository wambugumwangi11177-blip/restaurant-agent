"""
execution/codemap.py
─────────────────────
Builds the LEVIII code map from source (SPEC §S0.2): the Python import graph
(AST), the TypeScript import graph, and the engine × owner-surface coverage
matrix (SPEC figure 1.3). Deterministic: no timestamps, sorted output, so a
re-run on unchanged code produces an identical diff.

    python3 execution/codemap.py            # writes docs/v2/codemap.json + coverage.md
    python3 execution/codemap.py --check    # exit 1 if the committed files are stale

How "an engine appears on a surface" is derived (no hand-drawn dots):

  1. A SURFACE is a set of frontend entry files (e.g. app/vibanda/page.tsx).
     Their TypeScript import closure gives every file the surface can render.
  2. Every string/template literal in those files that matches a backend route
     (after stripping /api/v1, query strings, ${...}) is an API call the
     surface makes.
  3. Each backend route handler is analysed at FUNCTION granularity: the modules
     it imports (lazily or at module level) and the same-module helpers it calls
     are followed, through the Python import graph, to the engine modules.
     Traversal never enters routers/*, events/*, ai/orchestrator/*,
     integration/* or main — those are hubs that import everything and would
     make every engine look reachable from everywhere.
  4. An engine is "wired" on a surface when one of its modules (or, for symbol
     engines, one of its functions) is reached.

What a static graph cannot see — a panel that only renders when a source is
verified, an engine that is reached but whose output is thrown away — is NOT
guessed here. It is listed under CONDITIONAL below, each entry with the code
location a human verified, and is rendered as "partial".
"""
import ast
import json
import os
import re
import sys
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND = os.path.join(ROOT, "backend")
FRONTEND_SRC = os.path.join(ROOT, "frontend", "src")
OUT_JSON = os.path.join(ROOT, "docs", "v2", "codemap.json")
OUT_MD = os.path.join(ROOT, "docs", "v2", "coverage.md")

PY_EXCLUDE_DIRS = {"tests", "alembic", "scripts", "__pycache__", "venv", ".venv", "node_modules"}

# Modules that import (almost) everything. The traversal reports an edge INTO
# them but never walks OUT of them, otherwise every engine is "reachable" from
# every router. ai.decisions is deliberately NOT a hub: it is the ranked-decision
# layer Home genuinely consumes (see below: it is walked, one level, on purpose).
HUB_PREFIXES = ("routers.", "events.", "ai.orchestrator", "integration.", "main", "ai.plugins",
                "ai.workflows", "ai.enterprise", "ai.memory", "ai.escalation", "ai.whatsapp")

# ── Engines (rows of SPEC figure 1.3) ────────────────────────────────────────
# key, owner-facing row label, kind, targets. kind "module": any module path
# prefix match; kind "symbol": module + function name; kind "none": SPEC says it
# is not built — the map proves that by finding no module.
ENGINES = [
    ("sales_summary", "Sales summary", "symbol", ["routers.overview:_summarize"]),
    ("revenue_forecast", "Revenue forecast", "module", ["ai.revenue_forecaster"]),
    ("profit", "Profit intelligence (leaks, till gap, channels)", "module", ["ai.profit"]),
    ("pricing", "Pricing suggestions", "module", ["ai.pricing"]),
    ("menu", "Menu engineering", "module", ["ai.menu_engineer"]),
    ("simulator", "Price simulator", "module", ["ai.simulation.engine"]),
    ("inventory", "Stock prediction & reorder", "module", ["ai.inventory_predictor", "ai.reorder"]),
    ("custody", "Stock custody & variance", "module", ["ai.stock_custody"]),
    ("cash", "Cash drawer check", "module", ["ai.cash_reconciliation"]),
    ("fraud", "Fraud signals", "module", ["ai.fraud"]),
    ("kds", "Kitchen (KDS)", "module", ["ai.kds_intelligence"]),
    ("reservations", "Bookings", "module", ["ai.reservation_optimizer"]),
    ("labor", "Labour", "module", ["ai.labor"]),
    ("supply_chain", "Suppliers", "module", ["ai.supply_chain"]),
    ("marketing", "Marketing", "module", ["ai.marketing"]),
    ("roi", "ROI / savings", "module", ["ai.roi"]),
    ("twin", "30-day twin forecast", "module", ["ai.simulation.twin"]),
    ("data_quality", "Data quality / trust", "module", ["ai.data_quality"]),
    ("strategist", "Goal mode (strategist)", "module", ["ai.orchestrator.strategist"]),
    ("decisions", "Decision ranking", "module", ["ai.decisions"]),
    ("money", "Expenses · P&L · break-even · bills", "none", ["owner.money"]),
    ("mpesa_match", "M-Pesa statement match", "none", ["parsers.mpesa_csv"]),
    ("owner_settings", "Owner settings (targets, limits)", "none", ["owner.settings"]),
]

# Every module under backend/ai that is NOT a row above must be classified here, with a
# reason, so a new engine cannot be built and silently left off the map (the test in
# backend/tests/test_codemap.py fails on any unclassified ai.* module). Keys are
# prefixes: "ai.whatsapp" covers ai.whatsapp.brain etc.
INFRASTRUCTURE = {
    "ai.analysis_clock": "window anchor / freshness used by engines",
    "ai.cost_model": "LLM token cost accounting",
    "ai.llm_client": "provider client",
    "ai.spend_cap": "LLM spend cap",
    "ai.pii_scrub": "PII redaction for LLM payloads",
    "ai.reasoning": "grounded narration + number verification",
    "ai.owner_narrative": "narration helpers",
    "ai.routing": "model routing",
    "ai.memory": "agent memory store",
    "ai.evaluation": "forecast tracking / audit log / feedback loop",
    "ai.notify": "outbound notification helpers",
    "ai.whatsapp": "WhatsApp channel (brain, conversation, opt-out)",
    "ai.plugins": "marketplace plugin SDK",
    "ai.workflows": "workflow engine",
    "ai.orchestrator": "agent orchestration (strategist is its own engine row)",
    "ai.escalation": "alert escalation engine (feeds S5.3 alert levels)",
    "ai.simulation.signals": "calendar signals consumed by the twin (D12 holidays live here)",
}
# Real analysis modules the figure 1.3 rows do not cover. Not infrastructure: S1.4 must
# either register each as an engine or give a written reason it is not one.
CANDIDATES = {
    "ai.ops_manager": "operations dashboard = owner 'restaurant health' (SPEC §3.4)",
    "ai.creative": "creative layer = owner 'LEVIII's read' (Home zone 5)",
    "ai.home_specialists": "glue that turns engine output into Home cards",
    "ai.graph": "knowledge-graph impact analysis (strategist tool)",
    "ai.enterprise": "multi-branch benchmarking (OS 'compare' form, P5)",
    "ai.order_stock": "order-time stock helper",
}


# ── Surfaces (columns of figure 1.3) ─────────────────────────────────────────
# Entry files are relative to frontend/src. Demo is also flagged as a PARALLEL
# implementation surface: it reaches backend/demo_scenario.py instead of engines.
SURFACES = [
    ("home", "Home", ["app/vibanda/page.tsx"]),
    ("area", "Area pages", ["app/vibanda/[area]/page.tsx"]),
    ("os", "OS", ["app/vibanda/os/page.tsx"]),
    ("reports", "Reports", ["app/vibanda/reports/page.tsx"]),
    ("demo", "Demo", ["app/demo/page.tsx", "app/demo/[area]/page.tsx",
                      "app/demo/os/page.tsx", "app/demo/reports/page.tsx"]),
    ("old_dash", "Old dash", ["app/dashboard/**/page.tsx"]),
]
PARALLEL_BACKENDS = {"demo": ["demo_scenario", "routers.demo"]}
# An engine shows as re-implemented (≈) on a surface whose parallel backend
# (demo_scenario + routers/demo.py) computes the same topic itself: the backend's
# source mentions one of these words. This is keyword EVIDENCE, reported as such;
# it says "the demo has its own maths for this", not that the maths is equivalent.
PARALLEL_KEYWORDS = {
    "sales_summary": ["revenue"], "revenue_forecast": ["forecast"], "profit": ["margin", "profit"],
    "pricing": ["price"], "menu": ["dish"], "simulator": ["simulat"],
    "inventory": ["on_hand", "reorder", "low_cover"], "custody": ["variance", "custody", "handover"],
    "cash": ["cash", "drawer"], "fraud": ["fraud", "void"], "kds": ["kitchen", "prep"],
    "reservations": ["booking", "reservation", "covers"], "labor": ["labor", "labour"],
    "supply_chain": ["supplier"], "marketing": ["marketing", "campaign"], "roi": ["roi"],
    "twin": ["forecast"], "data_quality": ["data quality"], "strategist": ["strateg"],
    "decisions": ["decision"], "money": ["expense", "p&l", "break-even"], "mpesa_match": ["mpesa", "m-pesa"],
}


# Facts a static graph cannot see, each verified by reading the file named.
# They are FILE-scoped rules, never per-engine guesses.
#
# STATUS_ONLY: this file calls the route only to read connection/provenance
# state (data_provenance.source_connection) and renders none of its engine output.
STATUS_ONLY = {
    ("components/NotificationBell.tsx", "/overview/today"),
    ("components/vibanda/VibandaAreaClient.tsx", "/overview/today"),
    ("components/vibanda/OwnerHomeEmpty.tsx", "/overview/today"),
    ("components/vibanda/VibandaForecast.tsx", "/overview/today"),
    ("app/vibanda/os/page.tsx", "/overview/today"),
    ("app/vibanda/reports/page.tsx", "/overview/today"),
    ("components/vibanda/SourceUnavailable.tsx", "/observer/source-status"),
}
# CONDITIONAL_FILES: calls made only from here render only when a condition holds
# (a source verified), so an engine reached solely through them is "partial".
CONDITIONAL_FILES = {
    "components/vibanda/VibandaForecast.tsx": "forecast panel renders only when the source is verified",
}


# ═════════════════════════════════════════════════════════════════════════════
# Python import graph
# ═════════════════════════════════════════════════════════════════════════════

def module_name(path: str) -> str:
    rel = os.path.relpath(path, BACKEND)[:-3].replace(os.sep, ".")
    return rel[: -len(".__init__")] if rel.endswith(".__init__") else rel


def py_files() -> list[str]:
    out = []
    for dirpath, dirnames, filenames in os.walk(BACKEND):
        dirnames[:] = sorted(d for d in dirnames if d not in PY_EXCLUDE_DIRS and not d.startswith("."))
        out += [os.path.join(dirpath, f) for f in sorted(filenames) if f.endswith(".py")]
    return out


class PyModule:
    def __init__(self, path: str):
        self.path = path
        self.name = module_name(path)
        self.is_pkg = os.path.basename(path) == "__init__.py"
        with open(path, encoding="utf-8") as fh:
            self.src = fh.read()
        self.tree = ast.parse(self.src, filename=path)
        self.loc = self.src.count("\n") + 1


def resolve_from(mod: PyModule, node: ast.ImportFrom, known: set[str]) -> list[tuple[str, str | None]]:
    """-> [(target_module, imported_name_or_None)] for one ImportFrom."""
    base = node.module or ""
    if node.level:
        parts = mod.name.split(".")
        pkg = parts if mod.is_pkg else parts[:-1]
        pkg = pkg[: len(pkg) - (node.level - 1)] if node.level > 1 else pkg
        base = ".".join(pkg + ([base] if base else []))
    out = []
    for alias in node.names:
        sub = f"{base}.{alias.name}" if base else alias.name
        if sub in known:
            out.append((sub, None))
        elif base in known:
            out.append((base, alias.name))
    return out


def resolve_import(node: ast.Import, known: set[str]) -> list[tuple[str, None]]:
    out = []
    for alias in node.names:
        parts = alias.name.split(".")
        for i in range(len(parts), 0, -1):
            cand = ".".join(parts[:i])
            if cand in known:
                out.append((cand, None))
                break
    return out


def build_python() -> dict:
    mods = {}
    for p in py_files():
        m = PyModule(p)
        mods[m.name] = m
    known = set(mods)

    edges = {}      # (src, dst) -> lazy?
    imported_names = defaultdict(dict)   # module -> {local_name: (target_module, name)}
    func_info = defaultdict(dict)        # module -> func -> {"refs": set(modules), "calls": set(funcs), "routes": [...]}

    for name, m in mods.items():
        # which import nodes are module level vs inside a function
        top_level_import_nodes = set()
        for node in m.tree.body:
            for sub in ast.walk(node):
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and sub is not node:
                    break
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                top_level_import_nodes.add(id(node))
            elif isinstance(node, (ast.If, ast.Try)):
                for sub in ast.walk(node):
                    if isinstance(sub, (ast.Import, ast.ImportFrom)):
                        top_level_import_nodes.add(id(sub))
        for node in ast.walk(m.tree):
            if isinstance(node, ast.ImportFrom):
                targets = resolve_from(m, node, known)
            elif isinstance(node, ast.Import):
                targets = resolve_import(node, known)
            else:
                continue
            lazy = id(node) not in top_level_import_nodes
            for dst, nm in targets:
                if dst == name:
                    continue
                key = (name, dst)
                edges[key] = edges.get(key, True) and lazy
                if id(node) in top_level_import_nodes:
                    local = (nm or dst.split(".")[-1])
                    if isinstance(node, ast.ImportFrom):
                        for alias in node.names:
                            if (nm is None and f"{dst}" .endswith(alias.name)) or alias.name == nm:
                                imported_names[name][alias.asname or alias.name] = (dst, nm)
                    else:
                        for alias in node.names:
                            imported_names[name][alias.asname or alias.name.split(".")[0]] = (dst, None)

        # function-level facts
        top_funcs = {n.name for n in m.tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
        # Dispatch tables like _HANDLERS = {"stock": _answer_stock, ...}: a function that
        # reads the table can reach every function stored in it.
        var_refs = {}
        for node in m.tree.body:
            targets = node.targets if isinstance(node, ast.Assign) else [node.target] if isinstance(node, ast.AnnAssign) else []
            value = getattr(node, "value", None)
            if value is None:
                continue
            held = {n.id for n in ast.walk(value) if isinstance(n, ast.Name) and n.id in top_funcs}
            for t in targets:
                if isinstance(t, ast.Name) and held:
                    var_refs[t.id] = held
        router_prefix = ""
        for node in m.tree.body:
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call) \
                    and getattr(node.value.func, "id", "") == "APIRouter":
                for kw in node.value.keywords:
                    if kw.arg == "prefix" and isinstance(kw.value, ast.Constant):
                        router_prefix = kw.value.value
        for fn in [n for n in m.tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]:
            refs, calls, routes = set(), set(), []
            for sub in ast.walk(fn):
                if isinstance(sub, ast.ImportFrom):
                    refs |= {(t, nm) for t, nm in resolve_from(m, sub, known)}
                elif isinstance(sub, ast.Import):
                    refs |= {(t, None) for t, _ in resolve_import(sub, known)}
                elif isinstance(sub, ast.Name):
                    if sub.id in top_funcs and sub.id != fn.name:
                        calls.add(sub.id)
                    if sub.id in var_refs:
                        calls |= (var_refs[sub.id] - {fn.name})
                    if sub.id in imported_names[name]:
                        refs.add(imported_names[name][sub.id])
                elif isinstance(sub, ast.Attribute) and isinstance(sub.value, ast.Name):
                    if sub.value.id in imported_names[name]:
                        refs.add(imported_names[name][sub.value.id])
            for dec in fn.decorator_list:
                if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute) \
                        and getattr(dec.func.value, "id", "") == "router" \
                        and dec.func.attr in {"get", "post", "put", "patch", "delete"} \
                        and dec.args and isinstance(dec.args[0], ast.Constant):
                    routes.append((dec.func.attr.upper(), router_prefix + dec.args[0].value))
            func_info[name][fn.name] = {"refs": refs, "calls": calls, "routes": routes,
                                        "line": fn.lineno}
    return {"mods": mods, "edges": edges, "func_info": func_info, "imported_names": imported_names}


def group_of(name: str) -> str:
    if name in {"models", "database", "auth", "time_utils"}:
        return "core"
    if name.startswith("routers."):
        return "router"
    if name.startswith("ai."):
        return "ai"
    if name.startswith("integration") or name in {"observer_mode"}:
        return "integration"
    if name in {"demo_scenario", "demo_report_pdf"} or name.startswith("demo"):
        return "demo"
    return "other"


def is_hub(name: str) -> bool:
    return any(name == p.rstrip(".") or name.startswith(p) for p in HUB_PREFIXES)


def engine_targets() -> list[str]:
    return [t for _k, _l, kind, tg in ENGINES if kind in ("module", "symbol") for t in tg]


def is_engine_leaf(name: str) -> bool:
    """A module that IS an engine (or lives inside one): reaching it counts, walking out of it does not."""
    for t in engine_targets():
        t = t.split(":")[0]
        if name == t or name.startswith(t + "."):
            return name != "ai.decisions" and not name.startswith("ai.decisions.")
    return False


class Search:
    """Walk from one route handler through functions and modules, remembering how each node was reached."""

    def __init__(self, py: dict, module: str, func: str):
        self.py = py
        self.parent: dict = {}
        self.modules: set[str] = set()
        self.symbols: set[tuple[str, str]] = set()
        adj = defaultdict(set)
        for (src, dst) in py["edges"]:
            adj[src].add(dst)
        self.adj = adj
        self._run((module, func))

    def _visit_module(self, mod: str, via) -> None:
        stack = [(mod, via)]
        while stack:
            cur, parent = stack.pop()
            node = ("m", cur)
            if node in self.parent:
                continue
            self.parent[node] = parent
            self.modules.add(cur)
            if is_engine_leaf(cur) or is_hub(cur):
                continue
            for nxt in sorted(self.adj.get(cur, ())):
                stack.append((nxt, node))

    def _run(self, start: tuple[str, str]) -> None:
        info_all = self.py["func_info"]
        stack = [(("f",) + start, None)]
        while stack:
            node, parent = stack.pop()
            if node in self.parent:
                continue
            self.parent[node] = parent
            _, m, f = node
            info = info_all.get(m, {}).get(f)
            if info is None:
                continue
            self.symbols.add((m, f))
            for callee in sorted(info["calls"]):
                stack.append((("f", m, callee), node))
            for tgt, nm in sorted(info["refs"], key=lambda r: (r[0], r[1] or "")):
                hops = 0
                while nm and nm not in info_all.get(tgt, {}) and nm in self.py["imported_names"].get(tgt, {}) and hops < 4:
                    tgt, nm = self.py["imported_names"][tgt][nm]      # follow `from .x import y` re-exports
                    hops += 1
                if nm:
                    self.symbols.add((tgt, nm))
                if nm and nm in info_all.get(tgt, {}) and not is_engine_leaf(tgt):
                    stack.append((("f", tgt, nm), node))      # a helper function: follow it, not its whole module
                else:
                    self._visit_module(tgt, node)

    def chain(self, wanted_module: str) -> list[str]:
        for node in self.parent:
            if node[0] == "m" and (node[1] == wanted_module or node[1].startswith(wanted_module + ".")):
                out, cur = [], node
                while cur is not None:
                    out.append(cur[1] if cur[0] == "m" else f"{cur[1]}.{cur[2]}()")
                    cur = self.parent[cur]
                return list(reversed(out))
        return []


def handler_reach(py: dict, module: str, func: str) -> tuple[set[str], set[tuple[str, str]]]:
    s = Search(py, module, func)
    return s.modules, s.symbols


# ═════════════════════════════════════════════════════════════════════════════
# TypeScript import graph + API calls
# ═════════════════════════════════════════════════════════════════════════════

TS_IMPORT_RE = re.compile(r"""(?:from\s+|import\s*\(\s*|require\s*\(\s*|import\s+)["']([^"']+)["']""")
TS_STRING_RE = re.compile(r"""["'`](/[A-Za-z0-9_\-/{}$.?=&]*)["'`]""")


def ts_files() -> list[str]:
    out = []
    for dirpath, dirnames, filenames in os.walk(FRONTEND_SRC):
        dirnames[:] = sorted(d for d in dirnames if d not in {"node_modules", ".next"})
        out += [os.path.join(dirpath, f) for f in sorted(filenames) if f.endswith((".ts", ".tsx"))]
    return out


def resolve_ts(src_file: str, spec: str, files: set[str]) -> str | None:
    if spec.startswith("@/"):
        base = os.path.join(FRONTEND_SRC, spec[2:])
    elif spec.startswith("."):
        base = os.path.normpath(os.path.join(os.path.dirname(src_file), spec))
    else:
        return None
    for cand in (base, base + ".ts", base + ".tsx", os.path.join(base, "index.ts"), os.path.join(base, "index.tsx")):
        if cand in files:
            return cand
    return None


def build_typescript() -> dict:
    files = set(ts_files())
    edges, strings = defaultdict(set), {}
    for f in sorted(files):
        with open(f, encoding="utf-8") as fh:
            text = fh.read()
        for spec in TS_IMPORT_RE.findall(text):
            tgt = resolve_ts(f, spec, files)
            if tgt:
                edges[f].add(tgt)
        strings[f] = sorted(set(TS_STRING_RE.findall(text)))
    return {"files": sorted(files), "edges": edges, "strings": strings}


def expand_entries(ts: dict, entries: list[str]) -> list[str]:
    """Entries may be globs like app/dashboard/**/page.tsx (relative to frontend/src)."""
    import fnmatch
    rel = {os.path.relpath(f, FRONTEND_SRC): f for f in ts["files"]}
    out = []
    for e in entries:
        pattern = e.replace("[", "[[]") if "*" not in e else e
        out += [f for r, f in rel.items() if r == e or ("*" in e and fnmatch.fnmatch(r, e.replace("**/", "*")))]
    return sorted(set(out))


def ts_closure(ts: dict, entries: list[str]) -> set[str]:
    stack = expand_entries(ts, entries)
    seen = set()
    while stack:
        cur = stack.pop()
        if cur in seen:
            continue
        seen.add(cur)
        stack.extend(ts["edges"].get(cur, ()))
    return seen


# ═════════════════════════════════════════════════════════════════════════════
# Routes, surfaces, matrix
# ═════════════════════════════════════════════════════════════════════════════

def route_table(py: dict) -> list[dict]:
    rows = []
    for mod, funcs in sorted(py["func_info"].items()):
        if not mod.startswith("routers."):
            continue
        for fname, info in sorted(funcs.items()):
            for verb, path in info["routes"]:
                rows.append({"module": mod, "func": fname, "verb": verb, "path": path})
    return rows


def route_regex(path: str) -> re.Pattern:
    pattern = re.sub(r"\{[^}]+\}", "[^/]+", path.rstrip("/"))
    return re.compile("^" + pattern + "/?$")


def normalise_call(lit: str) -> str:
    lit = lit.split("?")[0]
    lit = re.sub(r"\$\{[^}]*\}", "x", lit)
    lit = lit[len("/api/v1"):] if lit.startswith("/api/v1/") else lit
    return lit.rstrip("/") or "/"


def surface_calls(ts: dict, routes: list[dict], entries: list[str]) -> list[dict]:
    """API routes the surface calls, each tagged with the files that call it and whether
    any call site is firm (renders engine output unconditionally)."""
    files = ts_closure(ts, entries)
    compiled = [(route_regex(r["path"]), r) for r in routes]
    hits: dict = {}
    for f in sorted(files):
        rel = os.path.relpath(f, FRONTEND_SRC)
        for lit in ts["strings"].get(f, ()):
            norm = normalise_call(lit)
            if not norm.startswith("/") or norm == "/":
                continue
            for rx, r in compiled:
                if not rx.match(norm):
                    continue
                if (rel, norm.split("/x")[0] if False else norm) in STATUS_ONLY or \
                        any(rel == sf and rx.match(sp) for sf, sp in STATUS_ONLY):
                    continue
                key = (r["module"], r["func"], r["verb"], r["path"])
                entry = hits.setdefault(key, {**r, "files": set()})
                entry["files"].add(rel)
    out = []
    for k in sorted(hits):
        e = hits[k]
        e["files"] = sorted(e["files"])
        e["conditional"] = all(f in CONDITIONAL_FILES for f in e["files"])
        out.append(e)
    return out


def matches_engine(kind: str, targets: list[str], modules: set[str], symbols: set[tuple[str, str]]) -> bool:
    if kind == "symbol":
        return any(tuple(t.split(":")) in symbols for t in targets)
    return any(m == t or m.startswith(t + ".") for t in targets for m in modules)


def parallel_mentions(py: dict, backends: list[str], ekey: str) -> bool:
    text = " ".join(py["mods"][b].src.lower() for b in backends if b in py["mods"])
    return any(kw in text for kw in PARALLEL_KEYWORDS.get(ekey, ()))


def build_matrix(py: dict, ts: dict, routes: list[dict]) -> dict:
    matrix, surface_detail = {}, {}
    for skey, slabel, entries in SURFACES:
        calls = surface_calls(ts, routes, entries)
        firm_m, firm_s, cond_m, cond_s = set(), set(), set(), set()
        for c in calls:
            m, sy = handler_reach(py, c["module"], c["func"])
            if c["conditional"]:
                cond_m |= m
                cond_s |= sy
            else:
                firm_m |= m
                firm_s |= sy
        all_modules = firm_m | cond_m | {c["module"] for c in calls}
        surface_detail[skey] = {
            "label": slabel, "entries": entries,
            "frontend_files": len(ts_closure(ts, entries)),
            "api_calls": [f"{c['verb']} {c['path']} -> {c['module']}.{c['func']}"
                          + (" [conditional]" if c["conditional"] else "") for c in calls],
            "parallel_backends": [b for b in PARALLEL_BACKENDS.get(skey, []) if b in all_modules],
        }
        for ekey, _label, kind, targets in ENGINES:
            if kind == "none":
                present = any(t in py["mods"] or any(k.startswith(t + ".") for k in py["mods"]) for t in targets)
                if not present:
                    state = "not_built"
                    if parallel_mentions(py, surface_detail[skey]["parallel_backends"], ekey):
                        state = "reimplemented"
                else:
                    state = "wired" if matches_engine("module", targets, firm_m, firm_s) else "not_shown"
            elif matches_engine(kind, targets, firm_m, firm_s):
                state = "wired"
            elif matches_engine(kind, targets, cond_m, cond_s):
                state = "partial"
            elif parallel_mentions(py, surface_detail[skey]["parallel_backends"], ekey):
                state = "reimplemented"
            else:
                state = "not_shown"
            matrix.setdefault(ekey, {})[skey] = state
    return {"matrix": matrix, "surfaces": surface_detail}


def classify_ai_module(name: str) -> tuple[str, str]:
    for _k, _l, kind, targets in ENGINES:
        if kind == "none":
            continue
        for t in targets:
            t = t.split(":")[0]
            if name == t or name.startswith(t + ".") or t.startswith(name + "."):
                return "engine", _k
    for table, label in ((INFRASTRUCTURE, "infrastructure"), (CANDIDATES, "candidate")):
        for prefix, why_ in table.items():
            if name == prefix or name.startswith(prefix + "."):
                return label, why_
    return "unclassified", ""


def engine_inventory(py: dict) -> dict:
    rows = []
    for name in sorted(py["mods"]):
        if name.startswith("ai."):
            status, note = classify_ai_module(name)
            rows.append({"module": name, "status": status, "note": note})
    return {"ai_modules": rows}


# ═════════════════════════════════════════════════════════════════════════════
# Output
# ═════════════════════════════════════════════════════════════════════════════

SYMBOL = {"wired": "●", "partial": "◐", "not_shown": "○", "reimplemented": "≈", "not_built": "✕",
          "built_not_shown": "○"}


def render_markdown(result: dict) -> str:
    surfaces = [(k, v["label"]) for k, v in result["surfaces"].items()]
    lines = [
        "# Engine × surface coverage (generated)",
        "",
        "Generated by `execution/codemap.py` from the code — do not edit by hand. "
        "Compare SPEC figure 1.3.",
        "",
        "● wired with real data · ◐ partial (condition a static graph cannot see; see notes) · "
        "○ not shown · ≈ re-implemented in a parallel backend · ✕ not built anywhere",
        "",
        "| Engine | " + " | ".join(label for _k, label in surfaces) + " |",
        "|---|" + "|".join(":-:" for _ in surfaces) + "|",
    ]
    for ekey, label, _kind, _t in ENGINES:
        cells = [SYMBOL[result["matrix"][ekey][sk]] for sk, _ in surfaces]
        lines.append(f"| {label} | " + " | ".join(cells) + " |")
    lines += ["", "## Surfaces", ""]
    for sk, label in surfaces:
        s = result["surfaces"][sk]
        lines.append(f"### {label}")
        lines.append(f"- entry files: {', '.join('`' + e + '`' for e in s['entries'])}")
        lines.append(f"- frontend files in import closure: {s['frontend_files']}")
        lines.append(f"- backend API calls found in those files: {len(s['api_calls'])}")
        if s["parallel_backends"]:
            lines.append(f"- parallel backend reached instead of engines: {', '.join(s['parallel_backends'])}")
        for call in s["api_calls"]:
            lines.append(f"  - `{call}`")
        lines.append("")
    lines += ["## File-scoped rules a static graph cannot see (human-verified)", ""]
    for (f, route) in sorted(STATUS_ONLY):
        lines.append(f"- status only: `{f}` calls `{route}` to read connection state, not to render engine output")
    for f, why_ in sorted(CONDITIONAL_FILES.items()):
        lines.append(f"- conditional: `{f}` — {why_} (engines reached only here show as ◐)")
    lines += ["", "## Python / TypeScript graph", "",
              f"- backend modules: {result['stats']['py_modules']}, imports: {result['stats']['py_edges']} "
              f"({result['stats']['py_lazy_edges']} lazy / inside functions)",
              f"- frontend files: {result['stats']['ts_files']}, imports: {result['stats']['ts_edges']}",
              f"- API routes found in routers: {result['stats']['routes']}",
              "", "## backend/ai modules not mapped to an engine row", ""]
    for status in ("candidate", "unclassified"):
        rows = [r for r in result["inventory"]["ai_modules"] if r["status"] == status]
        lines.append(f"### {status} ({len(rows)})")
        lines += [f"- `{r['module']}` — {r['note']}" if r["note"] else f"- `{r['module']}`" for r in rows] or ["- none"]
        lines.append("")
    infra = [r for r in result["inventory"]["ai_modules"] if r["status"] == "infrastructure"]
    lines.append(f"### infrastructure ({len(infra)} modules; reasons in `execution/codemap.py::INFRASTRUCTURE`)")
    return "\n".join(lines) + "\n"


def build() -> tuple[dict, str]:
    py = build_python()
    ts = build_typescript()
    routes = route_table(py)
    result = build_matrix(py, ts, routes)
    result["inventory"] = engine_inventory(py)
    result["stats"] = {
        "py_modules": len(py["mods"]),
        "py_edges": len(py["edges"]),
        "py_lazy_edges": sum(1 for lazy in py["edges"].values() if lazy),
        "ts_files": len(ts["files"]),
        "ts_edges": sum(len(v) for v in ts["edges"].values()),
        "routes": len(routes),
    }
    nodes = []
    for name, m in sorted(py["mods"].items()):
        nodes.append({"id": name, "kind": "py", "group": group_of(name), "loc": m.loc,
                      "path": os.path.relpath(m.path, ROOT)})
    graph_edges = [{"from": s, "to": d, "lazy": lazy} for (s, d), lazy in sorted(py["edges"].items())]
    out = {
        "stats": result["stats"],
        "engines": [{"key": k, "label": lb, "kind": kd, "targets": tg} for k, lb, kd, tg in ENGINES],
        "surfaces": result["surfaces"],
        "matrix": result["matrix"],
        "status_only": sorted([list(x) for x in STATUS_ONLY]),
        "conditional_files": CONDITIONAL_FILES,
        "inventory": result["inventory"],
        "python": {"nodes": nodes, "edges": graph_edges},
        "typescript": {"edges": [
            {"from": os.path.relpath(s, FRONTEND_SRC), "to": os.path.relpath(d, FRONTEND_SRC)}
            for s in sorted(ts["edges"]) for d in sorted(ts["edges"][s])]},
        "routes": routes,
    }
    return out, render_markdown(result)


def compare_spec() -> int:
    """Diff the derived matrix against SPEC figure 1.3 (docs/v2/figure_1_3.json)."""
    figure = json.load(open(os.path.join(ROOT, "docs", "v2", "figure_1_3.json")))
    payload, _ = build()
    diffs = []
    for ekey, want in figure["rows"].items():
        for col, w in zip(figure["columns"], want):
            got = payload["matrix"][ekey][col]
            if got != w:
                diffs.append((ekey, col, w, got))
    total = len(figure["rows"]) * len(figure["columns"])
    print(f"figure 1.3: {total - len(diffs)}/{total} cells reproduced from code")
    for ekey, col, w, got in diffs:
        print(f"  differs  {ekey:<16} x {col:<9} spec={w:<14} code={got}")
    return 0


def why(surface: str, engine: str) -> int:
    py, ts = build_python(), build_typescript()
    routes = route_table(py)
    entries = next((e for k, _l, e in SURFACES if k == surface), None)
    eng = next((e for e in ENGINES if e[0] == engine), None)
    if entries is None or eng is None:
        print("usage: codemap.py --why <surface> <engine>;  surfaces:",
              ", ".join(k for k, _l, _e in SURFACES), ";  engines:", ", ".join(e[0] for e in ENGINES))
        return 2
    found = False
    for call in surface_calls(ts, routes, entries):
        search = Search(py, call["module"], call["func"])
        for target in eng[3]:
            chain = search.chain(target.split(":")[0])
            if chain:
                found = True
                print(f"{call['verb']} {call['path']}  ({call['module']}.{call['func']})")
                print("   " + "  ->  ".join(chain))
    if not found:
        print(f"{engine} is not reachable from {surface}")
    return 0


def main() -> int:
    if "--compare-spec" in sys.argv:
        return compare_spec()
    if "--why" in sys.argv:
        i = sys.argv.index("--why")
        return why(*sys.argv[i + 1:i + 3]) if len(sys.argv) >= i + 3 else why("", "")
    payload, markdown = build()
    text = json.dumps(payload, indent=1, sort_keys=True) + "\n"
    if "--check" in sys.argv:
        stale = []
        for path, want in ((OUT_JSON, text), (OUT_MD, markdown)):
            have = open(path, encoding="utf-8").read() if os.path.exists(path) else None
            if have != want:
                stale.append(os.path.relpath(path, ROOT))
        if stale:
            print("codemap is stale: " + ", ".join(stale) + " — run python3 execution/codemap.py")
            return 1
        print("codemap is up to date")
        return 0
    os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
    with open(OUT_JSON, "w", encoding="utf-8") as fh:
        fh.write(text)
    with open(OUT_MD, "w", encoding="utf-8") as fh:
        fh.write(markdown)
    s = payload["stats"]
    print(f"codemap: {s['py_modules']} backend modules, {s['py_edges']} imports "
          f"({s['py_lazy_edges']} lazy); {s['ts_files']} frontend files, {s['ts_edges']} imports; "
          f"{s['routes']} routes")
    print(f"wrote {os.path.relpath(OUT_JSON, ROOT)} and {os.path.relpath(OUT_MD, ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
