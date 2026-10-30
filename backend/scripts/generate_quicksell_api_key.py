#!/usr/bin/env python3
"""Generate a new QuickSell webhook API key (print once — copy into env)."""
from __future__ import annotations

import secrets

if __name__ == "__main__":
    key = secrets.token_urlsafe(32)
    print("Set this in your environment (shown once):")
    print(f"QUICKSELL_API_KEY={key}")
