#!/usr/bin/env python3
"""Static release gate for Developer OS.

This validates the repository package before the real CI/host build is executed.
"""
from __future__ import annotations

import json
import py_compile
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
errors: list[str] = []

for forbidden in ("node_modules", ".git", "__pycache__"):
    if (ROOT / forbidden).exists():
        errors.append(f"release artifact present: {forbidden}")

for path in ROOT.rglob("*.sqlite3"):
    errors.append(f"local database must not ship: {path.relative_to(ROOT)}")

for path in (ROOT / "Backend").rglob("*.py"):
    if "__pycache__" in path.parts:
        continue
    try:
        py_compile.compile(str(path), doraise=True)
    except Exception as exc:
        errors.append(f"python compile failed: {path.relative_to(ROOT)}: {exc}")

for rel in ("Frontend/package.json", "Frontend/package-lock.json"):
    path = ROOT / rel
    try:
        json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        errors.append(f"invalid JSON: {rel}: {exc}")

for path in list((ROOT / "Frontend/src").rglob("*.jsx")) + list((ROOT / "Frontend/src").rglob("*.js")):
    text = path.read_text(encoding="utf-8", errors="replace")
    for match in re.finditer(r"""(?:from|import)\s*["'](\.{1,2}/[^"']+)["']""", text):
        spec = match.group(1)
        base = path.parent / spec
        candidates = [
            base, Path(str(base) + ".js"), Path(str(base) + ".jsx"),
            Path(str(base) + ".css"), base / "index.js", base / "index.jsx",
        ]
        if not any(candidate.exists() for candidate in candidates):
            errors.append(f"missing frontend import: {path.relative_to(ROOT)} -> {spec}")

for rel in ("README.md", "FINAL_RELEASE.md", "DEPLOYMENT.md"):
    text = (ROOT / rel).read_text(encoding="utf-8", errors="replace").lower()
    if "prototype / mvp" in text or "professional mvp" in text:
        errors.append(f"obsolete MVP release language remains in {rel}")

if errors:
    print("RELEASE GATE: FAIL")
    for error in errors:
        print(f"- {error}")
    sys.exit(1)

print("RELEASE GATE: PASS")
print("Static package checks passed. Run the real CI/frontend build/backend tests on the target environment.")
