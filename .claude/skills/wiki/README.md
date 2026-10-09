# wiki skill

Adapted from the "LLM Wiki" method (Andrej Karpathy, April 2026). Standard library
only, no network, no database. `SKILL.md` is what Claude reads; `wiki.py` is the
tool it runs.

Changes from the file this was taken from:

- Commands do nothing in a folder with no wiki (`_wiki/config.json`), so the skill is
  safe to install globally. `WIKI_ROOT` can point at a central wiki from any repo.
- `SKILL.md` calls the script by its real path. The original said `python wiki.py`,
  which only works if the script sits in the wiki folder.
- `lint` prints "clean" when it is clean. `.claude`, `.venv`, `venv` and nested
  `node_modules` are excluded from pages.
- Only `raw/` is gitignored. `_wiki/` holds just `config.json`, which a fresh clone
  needs to find the wiki root.

## Use it in this repo

It is already here, so any session in this repo has it. Nothing happens until a
wiki exists. Make one in its own folder, not the repo root, because lint treats
every `.md` it finds as a page:

    mkdir wiki && cd wiki
    python3 ../.claude/skills/wiki/wiki.py init .
    echo "raw/" >> .gitignore

## Install it for every repo on your machine

Claude Code reads user-level skills from `~/.claude/skills/`. Copy this folder there
once; it applies to every project afterwards.

macOS / Linux:

    mkdir -p ~/.claude/skills && cp -r .claude/skills/wiki ~/.claude/skills/wiki

Windows (PowerShell):

    New-Item -ItemType Directory -Force "$env:USERPROFILE\.claude\skills" | Out-Null
    Copy-Item -Recurse .claude\skills\wiki "$env:USERPROFILE\.claude\skills\wiki"

Restart Claude Code. A cloud session cannot write to your machine's home directory,
so this copy step has to be run by you locally.

Having it at both levels is harmless, but if the two copies diverge, which one loads
depends on Claude Code's skill precedence rules. Re-copy after changing this one so
they do not drift.
