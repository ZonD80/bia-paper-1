#!/usr/bin/env python3
"""Regrade every finished run in out/ with the current grade.py (after a grader fix)."""
import glob, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import grade
for d in sorted(glob.glob(os.path.join(os.path.dirname(os.path.abspath(__file__)), "out/*/run-*"))):
    if not os.path.exists(f"{d}/result/transcript.json"):
        continue
    v = grade.grade(d)
    old = json.load(open(f"{d}/result/verdict.json")).get("pass") if os.path.exists(f"{d}/result/verdict.json") else None
    json.dump(v, open(f"{d}/result/verdict.json", "w"), indent=1)
    print(f"{'PASS' if v['pass'] else 'FAIL'} {os.path.relpath(d, 'out') if False else d.split('/out/')[1]}" + (f"  (was {old})" if old is not None and old != v["pass"] else ""))
