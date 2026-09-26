"""
app/kernel/memory/chunking.py
─────────────────────────────
Split a document into retrievable chunks that each carry their heading path
(e.g. "Pricing policy › Discounts"), so a citation says *where* in a document
an answer came from, not just which document.

Deterministic and dependency-free: Markdown headings start sections; long
sections are split on paragraph boundaries into chunks of at most
`max_chars`, with no overlap (citations stay unambiguous).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")


@dataclass(frozen=True)
class Chunk:
    index: int
    heading: str
    content: str
    char_start: int
    char_end: int


def _sections(text: str, title: str) -> list[tuple[str, int, int]]:
    """(heading_path, start, end) for each heading-delimited section."""
    stack: list[tuple[int, str]] = []
    sections: list[tuple[str, int, int]] = []
    cur_heading, cur_start = title, 0
    pos = 0
    for line in text.splitlines(keepends=True):
        m = _HEADING.match(line.rstrip("\n"))
        if m:
            if pos > cur_start:
                sections.append((cur_heading, cur_start, pos))
            level, name = len(m.group(1)), m.group(2).strip()
            stack = [(lvl, n) for lvl, n in stack if lvl < level] + [(level, name)]
            names = [n for _, n in stack]
            if names and names[0].strip().lower() == title.strip().lower():
                names = names[1:]
            cur_heading = " › ".join([title, *names])
            cur_start = pos
        pos += len(line)
    if pos > cur_start:
        sections.append((cur_heading, cur_start, pos))
    return sections


def chunk_document(text: str, title: str, max_chars: int = 1200) -> list[Chunk]:
    chunks: list[Chunk] = []
    for heading, start, end in _sections(text, title):
        body = text[start:end]
        # Paragraph spans, with absolute offsets.
        spans = [(start + m.start(), start + m.end()) for m in re.finditer(r"\S(?:.|\n(?!\s*\n))*", body)]
        buf_start: int | None = None
        buf_end = 0
        for s, e in spans:
            if buf_start is None:
                buf_start, buf_end = s, e
            elif e - buf_start <= max_chars:
                buf_end = e
            else:
                chunks.append(_make(len(chunks), heading, text, buf_start, buf_end, max_chars))
                buf_start, buf_end = s, e
        if buf_start is not None:
            chunks.append(_make(len(chunks), heading, text, buf_start, buf_end, max_chars))
    # A single paragraph longer than max_chars is hard-split.
    out: list[Chunk] = []
    for c in chunks:
        if len(c.content) <= max_chars:
            out.append(Chunk(len(out), c.heading, c.content, c.char_start, c.char_end))
            continue
        for off in range(0, len(c.content), max_chars):
            piece = c.content[off:off + max_chars]
            out.append(Chunk(len(out), c.heading, piece, c.char_start + off, c.char_start + off + len(piece)))
    return [c for c in out if c.content.strip()]


def _make(index: int, heading: str, text: str, start: int, end: int, max_chars: int) -> Chunk:
    return Chunk(index, heading[:500], text[start:end].strip(), start, end)
