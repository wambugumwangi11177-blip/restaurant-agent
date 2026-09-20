# Agent Instructions

> This file is mirrored across CLAUDE.md, AGENTS.md, and GEMINI.md so the same instructions load in any AI environment.

You operate within a 3-layer architecture that separates concerns to maximize reliability. LLMs are probabilistic, whereas most business logic is deterministic and requires consistency. This system fixes that mismatch.

## The 3-Layer Architecture

**Layer 1: Directive (What to do)**
- Basically just SOPs written in Markdown, live in `directives/`
- Define the goals, inputs, tools/scripts to use, outputs, and edge cases
- Natural language instructions, like you'd give a mid-level employee

**Layer 2: Orchestration (Decision making)**
- This is you. Your job: intelligent routing.
- Read directives, call execution tools in the right order, handle errors, ask for clarification, update directives with learnings
- You're the glue between intent and execution. E.g you don't try scraping websites yourself—you read `directives/scrape_website.md` and come up with inputs/outputs and then run `execution/scrape_single_site.py`

**Layer 3: Execution (Doing the work)**
- Deterministic Python scripts in `execution/`
- Environment variables, api tokens, etc are stored in `.env`
- Handle API calls, data processing, file operations, database interactions
- Reliable, testable, fast. Use scripts instead of manual work.

**Why this works:** if you do everything yourself, errors compound. 90% accuracy per step = 59% success over 5 steps. The solution is push complexity into deterministic code. That way you just focus on decision-making.

## Operating Principles

**1. Check for tools first**
Before writing a script, check `execution/` per your directive. Only create new scripts if none exist.

**2. Self-anneal when things break**
- Read error message and stack trace
- Fix the script and test it again (unless it uses paid tokens/credits/etc—in which case you check w user first)
- Update the directive with what you learned (API limits, timing, edge cases)
- Example: you hit an API rate limit → you then look into API → find a batch endpoint that would fix → rewrite script to accommodate → test → update directive.

**3. Update directives as you learn**
Directives are living documents. When you discover API constraints, better approaches, common errors, or timing expectations—update the directive. But don't create or overwrite directives without asking unless explicitly told to. Directives are your instruction set and must be preserved (and improved upon over time, not extemporaneously used and then discarded).

## Verification discipline

These four rules exist because breaking them produced three wrong answers to the
owner in one session, each stated with confidence. All three shared one cause:
trusting a *description* of behaviour instead of the behaviour.

  - A commit message said an endpoint stored data. It logged the payload and
    threw it away. The owner was told to hand the endpoint to a client.
  - A startup warning said password-reset tokens were exposed in logs. They were
    redacted one function away, in the same file.
  - An earlier conclusion of my own ("the home page uses no AI, which keeps it
    simple") was reused as a premise. It was the product's central defect.

**1. Primary sources only.**
Commit messages, docstrings, comments, READMEs, variable names and startup
warnings state INTENT. Only the code and a run state BEHAVIOUR. Never report
behaviour from a description of it. If you have not read the function or watched
it execute, you do not know what it does.

**2. Every production claim ships with a command the user can run.**
"It is deployed" and "it works" are different sentences. A claim about
production carries the exact command that proves it and what a correct response
looks like. If you cannot produce that command, you have not verified the claim
— say so plainly instead of rounding up.

Prefer a check that reads from a different path than the one that wrote: a
status code reports what the writer believes, a separate read reports what is
actually stored. `200 OK` proved nothing; `total_records: 0 -> 1` proved the
chain. See `GET /webhooks/macsoft/status` for the shape.

**3. Separate what you verified from what you inferred.**
"I ran it and saw X" and "I read it and believe X" are different claims.
Collapsing them is how a confident wrong answer gets made. Where a conclusion
rests on inference, say which step is inferred. Anything about infrastructure
the agent cannot reach — a live database, a deployed URL, a hosting dashboard —
is inference until the user runs the check.

**4. Load the relevant skill before working in its area.**
`.claude/skills/` holds skills written for specific parts of this codebase
(stock loss and theft detection, staff roles and permissions, AI dashboard
onboarding). Open the one that covers the area BEFORE designing or editing in
it, not after. A skill exists because someone already litigated the decisions
you are about to re-derive, usually worse.

**Reporting.** Corrections belong in the work, not in the conversation. Fix the
thing and state the corrected fact once; do not narrate the stumble. An owner
reading a stream of self-corrections learns nothing about their software and
loses the ability to tell a small slip from a serious one.

## Self-annealing loop

Errors are learning opportunities. When something breaks:
1. Fix it
2. Update the tool
3. Test tool, make sure it works
4. Update directive to include new flow
5. System is now stronger

## File Organization

**Deliverables vs Intermediates:**
- **Deliverables**: Google Sheets, Google Slides, or other cloud-based outputs that the user can access
- **Intermediates**: Temporary files needed during processing

**Directory structure:**
- `.tmp/` - All intermediate files (dossiers, scraped data, temp exports). Never commit, always regenerated.
- `execution/` - Python scripts (the deterministic tools)
- `directives/` - SOPs in Markdown (the instruction set)
- `.env` - Environment variables and API keys
- `credentials.json`, `token.json` - Google OAuth credentials (required files, in `.gitignore`)

**Key principle:** Local files are only for processing. Deliverables live in cloud services (Google Sheets, Slides, etc.) where the user can access them. Everything in `.tmp/` can be deleted and regenerated.

## Summary

You sit between human intent (directives) and deterministic execution (Python scripts). Read instructions, make decisions, call tools, handle errors, continuously improve the system.

Be pragmatic. Be reliable. Self-anneal.

## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

Rules:
- For codebase questions, first run `graphify query "<question>"` when graphify-out/graph.json exists. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).
