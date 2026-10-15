"""
execution/lint_ratchet.py
──────────────────────────
ESLint "ratchet" for the v2 build gate (docs/v2/SPEC.md E1).

The frontend was NOT lint-clean when v2 started (see docs/v2/PROGRESS.md,
baseline), so "lint clean" is enforced as: no file may have more ESLint errors
or warnings than recorded in docs/v2/eslint-baseline.json, and no file absent
from the baseline may have any. Improvements are reported, and `--update`
re-records the baseline (use only after fixing, never to hide a regression).

Usage (from repo root):
    python3 execution/lint_ratchet.py            # check
    python3 execution/lint_ratchet.py --update   # re-record baseline
"""
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND = os.path.join(ROOT, "frontend")
BASELINE = os.path.join(ROOT, "docs", "v2", "eslint-baseline.json")


def run_eslint() -> dict[str, list[int]]:
    proc = subprocess.run(
        ["npx", "eslint", "-f", "json"], cwd=FRONTEND,
        capture_output=True, text=True,
    )
    # eslint exits 1 when it finds errors; that is expected here. Anything
    # without JSON on stdout is a real failure (crash, missing config).
    try:
        report = json.loads(proc.stdout)
    except json.JSONDecodeError:
        sys.stderr.write(proc.stderr[-2000:] or proc.stdout[-2000:])
        raise SystemExit("eslint did not produce JSON output")
    found: dict[str, list[int]] = {}
    for entry in report:
        errors, warnings = entry["errorCount"], entry["warningCount"]
        if errors or warnings:
            rel = os.path.relpath(entry["filePath"], FRONTEND)
            found[rel] = [errors, warnings]
    return found


def main() -> int:
    current = run_eslint()
    total_e = sum(v[0] for v in current.values())
    total_w = sum(v[1] for v in current.values())

    if "--update" in sys.argv:
        os.makedirs(os.path.dirname(BASELINE), exist_ok=True)
        with open(BASELINE, "w") as fh:
            json.dump(dict(sorted(current.items())), fh, indent=2)
            fh.write("\n")
        print(f"lint ratchet: baseline recorded — {total_e} errors, {total_w} warnings "
              f"in {len(current)} files")
        return 0

    with open(BASELINE) as fh:
        baseline = json.load(fh)

    regressions, improvements = [], []
    for path, (errors, warnings) in sorted(current.items()):
        b_err, b_warn = baseline.get(path, [0, 0])
        if errors > b_err or warnings > b_warn:
            regressions.append(f"  {path}: {errors}E/{warnings}W (baseline {b_err}E/{b_warn}W)")
    for path, (b_err, b_warn) in sorted(baseline.items()):
        errors, warnings = current.get(path, [0, 0])
        if errors < b_err or warnings < b_warn:
            improvements.append(f"  {path}: {errors}E/{warnings}W (baseline {b_err}E/{b_warn}W)")

    print(f"lint ratchet: {total_e} errors, {total_w} warnings in {len(current)} files "
          f"(baseline {sum(v[0] for v in baseline.values())}E/"
          f"{sum(v[1] for v in baseline.values())}W)")
    if improvements:
        print("improved (run with --update to lock in):\n" + "\n".join(improvements))
    if regressions:
        print("REGRESSIONS:\n" + "\n".join(regressions))
        return 1
    print("lint ratchet: OK (no new problems)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
