"""wiki.py: a small LLM wiki. Standard library only, no network, no database.

    python wiki.py init [root]         lay down the spine
    python wiki.py resolve             print the layout
    python wiki.py index               rebuild INDEX.md from page frontmatter
    python wiki.py ingest <file>       propose pages from a raw source
    python wiki.py ingest <file> --apply    write the proposal
    python wiki.py query "question"    search the pages, offline
    python wiki.py lint                what is broken or rotting
    python wiki.py log <op> "message"  append to LOG.md

Every command except init works on the wiki found by walking up from the current
folder to the nearest _wiki/config.json, or on $WIKI_ROOT if that is set. In a
folder with no wiki it exits with a message and touches nothing.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import os
import pathlib
import re
import sys
from collections import Counter

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

DASHES = "".join(map(chr, (0x2012, 0x2013, 0x2014, 0x2015)))
SPINE = ("INDEX.md", "LOG.md")
DEFAULT_EXCLUDE = ("_wiki", ".git", ".claude", "__pycache__", "node_modules", ".venv", "venv")
WORD = re.compile(r"[a-z0-9']+")
LINK = re.compile(r"\[\[([^\]]+)\]\]")
FM = re.compile(r"\A---\n(.*?)\n---\n", re.S)
SECRETISH = re.compile(
    r"\b(sk-[A-Za-z0-9_-]{20,}|xox[bpa]-[A-Za-z0-9-]{10,}|AIza[0-9A-Za-z_-]{30,}"
    r"|ghp_[A-Za-z0-9]{30,}|-----BEGIN [A-Z ]*PRIVATE KEY-----)")
STOP = set("""a an the and or but if of to in on for with at by from as is are was were be been
this that these those it its their his her our your my we you they i he she not no do does did
have has had will would can could should may might there here what which who when where how why
about into over under out up down then than so such very more most some any all each other""".split())


def root() -> pathlib.Path:
    """The wiki root: $WIKI_ROOT if set, else the nearest ancestor of the cwd
    holding _wiki/config.json. Exits if there is none.

    This script is installed globally, so it must do nothing in a folder that has
    no wiki. Scanning an unrelated repo's markdown would produce pure noise.
    """
    env = os.environ.get("WIKI_ROOT")
    if env:
        d = pathlib.Path(env).expanduser().resolve()
        if (d / "_wiki" / "config.json").is_file():
            return d
        sys.exit(f"WIKI_ROOT={d} has no _wiki/config.json. Run: python3 wiki.py init {d}")
    here = pathlib.Path.cwd().resolve()
    for d in [here, *here.parents]:
        if (d / "_wiki" / "config.json").is_file():
            return d
    sys.exit("no wiki here (no _wiki/config.json in this folder or above, and WIKI_ROOT is unset). "
             "Run `init` in the folder that should hold one.")


def config(r: pathlib.Path) -> dict:
    p = r / "_wiki" / "config.json"
    if not p.is_file():
        return {"raw": ["raw"], "exclude": list(DEFAULT_EXCLUDE)}
    return json.loads(p.read_text(encoding="utf-8"))


def is_raw(r: pathlib.Path, p: pathlib.Path, cfg: dict) -> bool:
    rel = p.relative_to(r).as_posix()
    return any(rel == d or rel.startswith(d.rstrip("/") + "/") for d in cfg.get("raw", []))


def pages(r: pathlib.Path, cfg: dict):
    ex = cfg.get("exclude", [])
    for p in sorted(r.rglob("*.md")):
        rel = p.relative_to(r).as_posix()
        # A bare name (node_modules) excludes that folder at any depth; a path (a/b) only from the root.
        if p.name in SPINE or any(
                rel.startswith(e.rstrip("/") + "/") or rel == e or ("/" not in e and e in p.relative_to(r).parts)
                for e in ex):
            continue
        if is_raw(r, p, cfg):
            continue
        yield p


def frontmatter(text: str) -> dict:
    m = FM.match(text)
    if not m:
        return {}
    out = {}
    for line in m.group(1).splitlines():
        if ":" in line and not line.startswith((" ", "-")):
            k, v = line.split(":", 1)
            out[k.strip()] = v.strip()
    return out


def body(text: str) -> str:
    m = FM.match(text)
    return text[m.end():] if m else text


def tokens(s: str):
    return [w for w in WORD.findall(s.lower()) if w not in STOP and len(w) > 1]


# ------------------------------------------------------------------ commands

def cmd_init(args) -> int:
    r = pathlib.Path(args.root or ".").resolve()
    (r / "_wiki").mkdir(parents=True, exist_ok=True)
    (r / "raw").mkdir(exist_ok=True)
    cfg = r / "_wiki" / "config.json"
    if not cfg.exists():
        cfg.write_text(json.dumps({
            "raw": ["raw"],
            "exclude": list(DEFAULT_EXCLUDE),
        }, indent=2), encoding="utf-8")
    idx = r / "INDEX.md"
    if not idx.exists():
        idx.write_text("# Index\n\nStart here. Rebuild with `python wiki.py index`.\n\n"
                       "<!-- pages:start -->\n<!-- pages:end -->\n", encoding="utf-8")
    log = r / "LOG.md"
    if not log.exists():
        log.write_text("# Log\n\nAppend-only. Newest at the bottom.\n", encoding="utf-8")
    print(f"wiki ready at {r}")
    print("  raw/       put transcripts and exports here. Never edited.")
    print("  INDEX.md   the entry point")
    print("  LOG.md     what changed and why")
    return 0


def cmd_resolve(args) -> int:
    r = root()
    cfg = config(r)
    ps = list(pages(r, cfg))
    raws = [p for d in cfg.get("raw", []) for p in sorted((r / d).rglob("*")) if p.is_file()]
    print(f"root      {r}")
    print(f"pages     {len(ps)}")
    print(f"raw files {len(raws)} under {', '.join(cfg.get('raw', []))}")
    return 0


def cmd_index(args) -> int:
    r = root()
    cfg = config(r)
    rows = []
    for p in pages(r, cfg):
        fmv = frontmatter(p.read_text(encoding="utf-8"))
        title = fmv.get("title") or p.stem.replace("-", " ")
        updated = fmv.get("updated", "")
        rel = p.relative_to(r).as_posix()
        rows.append(f"- [{title}]({rel})" + (f"  _{updated}_" if updated else ""))
    idx = r / "INDEX.md"
    text = idx.read_text(encoding="utf-8") if idx.exists() else "# Index\n\n<!-- pages:start -->\n<!-- pages:end -->\n"
    block = "<!-- pages:start -->\n" + "\n".join(rows) + "\n<!-- pages:end -->"
    if "<!-- pages:start -->" in text:
        text = re.sub(r"<!-- pages:start -->.*?<!-- pages:end -->", block, text, flags=re.S)
    else:
        text = text.rstrip("\n") + "\n\n" + block + "\n"
    idx.write_text(text, encoding="utf-8")
    print(f"index rebuilt: {len(rows)} page(s)")
    return 0


def cmd_ingest(args) -> int:
    """Propose pages from a raw source. Writes nothing without --apply.

    The proposal is the whole point. A tool that silently folds a transcript into
    your knowledge base gives you confident text nobody checked.
    """
    r = root()
    cfg = config(r)
    src = pathlib.Path(args.file).resolve()
    if not src.is_file():
        print(f"no such file: {src}")
        return 2
    text = src.read_text(encoding="utf-8", errors="replace")
    rel = src.relative_to(r).as_posix() if src.is_relative_to(r) else str(src)

    existing = {p.stem: p for p in pages(r, cfg)}
    terms = Counter(tokens(text))
    hits = []
    for stem, p in existing.items():
        overlap = sum(terms[t] for t in set(tokens(p.read_text(encoding="utf-8"))))
        if overlap:
            hits.append((overlap, stem))
    hits.sort(reverse=True)

    print(f"SOURCE   {rel}")
    print(f"         {len(text.split()):,} words")
    print()
    print("EXISTING PAGES THIS TOUCHES, most related first:")
    if hits:
        for score, stem in hits[:8]:
            print(f"  {score:>6}  {stem}")
        print()
        print("  Fold new material into these rather than creating near-duplicates.")
    else:
        print("  none. This is new ground.")
    print()
    print("WHAT TO DO NOW, as the assisting model:")
    print("  1. Read the source.")
    print("  2. Decide the SMALLEST set of pages that covers it, one idea each.")
    print("  3. For each: is it an edit to a page above, or a new page?")
    print("  4. Show the user the list with a one-line summary of each change.")
    print("  5. On their yes, write the pages, then run: python wiki.py index")
    print(f"  6. Then: python wiki.py log ingest \"{rel}: <what you filed>\"")
    print()
    print("  Every page you write carries frontmatter with title, updated, status,")
    print(f"  and sources including {rel}. No dash glyphs. Link related pages with [[name]].")
    if args.apply:
        print()
        print("  --apply is accepted for symmetry, but writing the pages is YOUR job,")
        print("  not this script's: only you have read the source. Write them, then index.")
    return 0


def cmd_query(args) -> int:
    """BM25 over page bodies. Offline, no index to maintain."""
    r = root()
    cfg = config(r)
    docs = []
    for p in pages(r, cfg):
        t = p.read_text(encoding="utf-8")
        docs.append((p, frontmatter(t), tokens(body(t)), body(t)))
    if not docs:
        print("no pages yet. Ingest something first.")
        return 0
    N = len(docs)
    avg = sum(len(d[2]) for d in docs) / N
    df = Counter()
    for _, _, toks, _ in docs:
        df.update(set(toks))
    q = tokens(args.question)
    k1, b = 1.5, 0.75
    scored = []
    for p, fmv, toks, raw_body in docs:
        tf = Counter(toks)
        score = 0.0
        for term in q:
            if term not in tf:
                continue
            idf = math.log(1 + (N - df[term] + 0.5) / (df[term] + 0.5))
            score += idf * (tf[term] * (k1 + 1)) / (tf[term] + k1 * (1 - b + b * len(toks) / avg))
        if score > 0:
            scored.append((score, p, fmv, raw_body))
    scored.sort(key=lambda x: -x[0])
    if not scored:
        print("nothing matched. The wiki does not know this yet.")
        return 0
    for score, p, fmv, raw_body in scored[:args.limit]:
        rel = p.relative_to(r).as_posix()
        print(f"\n=== {fmv.get('title', p.stem)}  ({rel})  score {score:.1f}")
        if fmv.get("sources"):
            print(f"    sources: {fmv['sources']}")
        if fmv.get("updated"):
            print(f"    updated: {fmv['updated']}")
        best, bestscore = "", -1
        for para in [x.strip() for x in raw_body.split("\n\n") if x.strip()]:
            s = sum(1 for t in tokens(para) if t in set(q))
            if s > bestscore:
                best, bestscore = para, s
        print("    " + best[:600].replace("\n", "\n    "))
    return 0


def cmd_lint(args) -> int:
    r = root()
    cfg = config(r)
    problems = []
    ps = list(pages(r, cfg))
    names = {p.stem for p in ps}
    linked = set()
    today = dt.date.today()

    for p in ps:
        text = p.read_text(encoding="utf-8")
        rel = p.relative_to(r).as_posix()
        fmv = frontmatter(text)
        for ch in DASHES:
            if ch in text:
                problems.append(("ERROR", rel, f"dash glyph U+{ord(ch):04X}"))
                break
        if not fmv:
            problems.append(("ERROR", rel, "no frontmatter"))
        else:
            for key in ("title", "updated", "sources"):
                if key not in fmv:
                    problems.append(("WARN", rel, f"frontmatter missing {key}"))
            u = fmv.get("updated", "")
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}", u or ""):
                age = (today - dt.date.fromisoformat(u)).days
                if age > 180:
                    problems.append(("INFO", rel, f"last updated {age} days ago"))
            src = fmv.get("sources", "")
            for s in re.findall(r"[\w./-]+\.\w+", src):
                if not (r / s).exists():
                    problems.append(("WARN", rel, f"source not found: {s}"))
        m = SECRETISH.search(text)
        if m:
            problems.append(("ERROR", rel, f"looks like a credential: {m.group(0)[:12]}..."))
        for target in LINK.findall(text):
            linked.add(target.strip())
            if target.strip() not in names:
                problems.append(("INFO", rel, f"link to a page that does not exist yet: {target.strip()}"))

    for p in ps:
        if p.stem not in linked:
            problems.append(("INFO", p.relative_to(r).as_posix(), "orphan: nothing links to it"))

    if not (r / "LOG.md").exists():
        problems.append(("WARN", "LOG.md", "missing"))

    order = {"ERROR": 0, "WARN": 1, "INFO": 2}
    problems.sort(key=lambda x: (order[x[0]], x[1]))
    counts = Counter(p[0] for p in problems)
    for sev, where, what in problems:
        print(f"{sev:<6} {where}: {what}")
    print()
    summary = ", ".join(f"{counts[k]} {k}" for k in ("ERROR", "WARN", "INFO") if counts[k])
    print(f"{len(ps)} page(s). {summary or 'clean.'}")
    return 1 if counts["ERROR"] else 0


def cmd_log(args) -> int:
    r = root()
    log = r / "LOG.md"
    if not log.exists():
        log.write_text("# Log\n\nAppend-only. Newest at the bottom.\n", encoding="utf-8")
    stamp = dt.date.today().isoformat()
    with log.open("a", encoding="utf-8") as fh:
        fh.write(f"\n## [{stamp}] {args.op}\n{args.message}\n")
    print(f"logged: [{stamp}] {args.op}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(prog="wiki")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("init");    s.add_argument("root", nargs="?"); s.set_defaults(fn=cmd_init)
    s = sub.add_parser("resolve"); s.set_defaults(fn=cmd_resolve)
    s = sub.add_parser("index");   s.set_defaults(fn=cmd_index)
    s = sub.add_parser("ingest");  s.add_argument("file"); s.add_argument("--apply", action="store_true"); s.set_defaults(fn=cmd_ingest)
    s = sub.add_parser("query");   s.add_argument("question"); s.add_argument("--limit", type=int, default=5); s.set_defaults(fn=cmd_query)
    s = sub.add_parser("lint");    s.set_defaults(fn=cmd_lint)
    s = sub.add_parser("log");     s.add_argument("op"); s.add_argument("message"); s.set_defaults(fn=cmd_log)
    args = ap.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
