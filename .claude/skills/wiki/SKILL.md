---
name: wiki
description: Read, search, extend and correct a personal LLM wiki, a set of small linked markdown pages with sources, plus INDEX.md and LOG.md. Use only when the current folder (or $WIKI_ROOT) holds a wiki, meaning a _wiki/config.json file exists in it or above it, or when the user asks to set one up, file or ingest a transcript, note or document into it, check what is stale, or correct a fact in it. When a wiki exists, also use it before answering substantive questions about the user's own projects, people or decisions, because the answer is probably already written down. Do not use it for ordinary code questions in a repository that has no wiki.
---

# The wiki

A set of small linked markdown pages that this session reads before answering
anything about the user's own work. Raw sources are never edited; pages cite them.

## Running the script

`wiki.py` sits in the same folder as this file. Below, `WIKI` stands for the full
path to it, for example `~/.claude/skills/wiki/wiki.py` for a user install or
`<repo>/.claude/skills/wiki/wiki.py` for a project install. Use the base directory
this skill was loaded from. Run it as `python3 WIKI <command>` (on Windows, `py -3`).

It finds the wiki by walking up from the current folder to the nearest
`_wiki/config.json`, or uses `$WIKI_ROOT` if that is set. In a folder with no wiki
it exits with "no wiki here" and changes nothing.

**First step, always:** run `python3 WIKI resolve`. If it says "no wiki here", this
skill does not apply. Do not run `lint`, `query` or `index` anywhere else, and do
not run `init` unless the user asked for a wiki in that folder.

## Where things are

- `INDEX.md`   the entry point. Read it FIRST, every time.
- `LOG.md`     append-only history of ingests, corrections and decisions.
- `_wiki/config.json`  marks the wiki root and lists which folders are raw. Commit it.
- `raw/`       source material. **Never edit anything in here.** Keep it out of git.
- everything else: pages.

## The four things you do

**1. Answer a question.** Read `INDEX.md`, then run:

    python3 WIKI query "the question"

It returns the matching passages with their page and their source. Cite the page
you used. If the wiki does not answer it, say so plainly rather than guessing, and
offer to ingest something that would. The search is lexical, so if nothing matches,
try the question's key nouns before concluding the wiki is silent.

**2. File new material.** When the user gives you a transcript, a note or a
document:

    python3 WIKI ingest path/to/the/file

That prints what the source touches and which existing pages to fold it into. It
writes nothing, and neither should you yet. Read the source, then show the user the
proposal: which pages you would create, which you would change, and one line on
each. **Get a yes before writing.** After the yes:

1. write or edit the pages,
2. run `python3 WIKI index`,
3. run `python3 WIKI log ingest "<source>: <what you filed>"`.

Never skip the proposal step.

**3. Correct something.** When the user says a page is wrong, fix the page, then:

    python3 WIKI log correct "what was wrong, what is right, why"

The log entry matters as much as the fix. Six months later the question is not what
the page says, it is why it changed.

**4. Check the health of it.**

    python3 WIKI lint

Fix what it reports, or tell the user what needs their decision.

## The rules pages follow

- **One idea per page.** If a page needs two headings that could each stand alone,
  it is two pages.
- **Every page carries frontmatter**: `title`, `updated`, `status`, and `sources`
  listing the raw files it came from. A page with no source is a page nobody can
  check.
- **Link liberally.** `[[page-name]]` links a page. A link to a page that does not
  exist yet is fine; it marks something worth writing.
- **Date every claim that can go stale.** "As of March, the plan was X" ages
  honestly. "The plan is X" does not.
- **No dash glyphs in wiki pages.** Use a comma, a full stop, or two sentences. Lint
  reports them as errors. This applies to wiki pages only, not to other files.
- **Fold, do not append.** New material about an existing topic edits that page.
  Appending to the bottom is how a wiki becomes a pile.
- **Raw is immutable.** If a transcript is wrong, note the correction on the page,
  never by editing the transcript.
- **Never put a credential in a page.** Lint flags key-shaped strings; fix them at
  once.
