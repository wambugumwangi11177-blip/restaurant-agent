"""backend/owner/ — the owner API spine (docs/v2/SPEC.md §2).

Composes existing engine output for the owner's three pages (Home, OS, Reports) and owns the one
settings service every engine reads its thresholds from. Engines keep their own tests; this package
reshapes, it never re-implements their maths.
"""
