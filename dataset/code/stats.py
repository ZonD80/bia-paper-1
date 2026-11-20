#!/usr/bin/env python3
"""Per-arm results of the benchmark rerun, with Wilson 95% intervals and two-sided Fisher
exact tests of each arm against `away` on the same cells. Runs 1-10 of every cell only
(a few cells hold extra reruns). The full circle is graded owner-aware
(result/verdict-owner.json, see grade_owner.py); --strict uses the released grader.

  stats.py [--strict]     prints tables, writes stats.json
"""
import glob, json, math, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
STRICT = "--strict" in sys.argv
ARMS = [("released", "../repo/runs"), ("away", "out"), ("handbook", "out-handbook"), ("persons", "out-persons"), ("circle", "out-circle")]
RUNS = [f"run-{i:02d}" for i in range(1, 11)]


def verdict(d, arm):
    f = f"{d}/result/verdict-owner.json" if arm == "circle" and not STRICT else f"{d}/result/verdict.json"
    if not os.path.exists(f):
        f = f"{d}/result/verdict.json"
    return json.load(open(f))["pass"]


def load():
    t = {}
    for arm, p in ARMS:
        for c in sorted(glob.glob(f"{HERE}/{p}/*-gpt-5-4")):
            cell = os.path.basename(c)[:-len("-gpt-5-4")]
            vs = [verdict(f"{c}/{r}", arm) for r in RUNS if os.path.exists(f"{c}/{r}/result/verdict.json")]
            if vs:
                t.setdefault(cell, {})[arm] = (sum(bool(v) for v in vs), len(vs))
    return t


def wilson(k, n, z=1.96):
    if not n:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def fisher(a, b, c, d):
    """two-sided Fisher exact p for [[a, b], [c, d]]"""
    n1, n2, m = a + b, c + d, a + c
    N = n1 + n2
    lg = lambda x: math.lgamma(x + 1)
    pr = lambda x: math.exp(lg(n1) - lg(x) - lg(n1 - x) + lg(n2) - lg(m - x) - lg(n2 - m + x) - (lg(N) - lg(m) - lg(N - m)))
    p0 = pr(a)
    lo, hi = max(0, m - n2), min(m, n1)
    return min(1.0, sum(pr(x) for x in range(lo, hi + 1) if pr(x) <= p0 * (1 + 1e-7)))


GROUPS = [
    ("coord", "E1-E4 coordination, all cells", lambda c: c[:2] in ("E1", "E2", "E3", "E4")),
    ("coord-small", "E1-E4, 2-3 people (N1, N3)", lambda c: c[:2] in ("E1", "E2", "E3", "E4") and re.search(r"-N[13]\b", c)),
    ("coord-big", "E1-E4, 6-8 people (N5, N7)", lambda c: c[:2] in ("E1", "E2", "E3", "E4") and re.search(r"-N[57]\b", c)),
    ("e5", "E5 attacks that succeeded", lambda c: c.startswith("E5")),
    ("e6-cover", "E6 cover story, attack succeeded", lambda c: c == "E6-stalking-cover-story"),
]


def main():
    t = load()
    out = {"strict_circle": STRICT, "groups": {}}
    for key, title, pred in GROUPS:
        print(f"\n{title}")
        g = {}
        for arm, _ in ARMS:
            cells = [c for c in t if pred(c) and arm in t[c]]
            if not cells:
                continue
            k, n = sum(t[c][arm][0] for c in cells), sum(t[c][arm][1] for c in cells)
            row = {"k": k, "n": n, "rate": k / n, "ci": wilson(k, n)}
            cmp = ""
            for base in ("released", "away"):
                if arm in ("released", base):
                    continue
                both = [c for c in cells if base in t[c]]
                ak, an = sum(t[c][base][0] for c in both), sum(t[c][base][1] for c in both)
                bk, bn = sum(t[c][arm][0] for c in both), sum(t[c][arm][1] for c in both)
                row[f"vs_{base}"] = vs = {"cells": len(both), "base": [ak, an], "arm": [bk, bn],
                                          "p": fisher(bk, bn - bk, ak, an - ak)}
                cmp += f"  vs {base} {ak}/{an} ({vs['cells']} cells) p={vs['p']:.2g}"
            g[arm] = row
            lo, hi = row["ci"]
            print(f"  {arm:9} {k:3}/{n:<3} {100 * k / n:5.1f}%  [{100 * lo:4.1f}, {100 * hi:4.1f}]{cmp}")
        out["groups"][key] = {"title": title, "arms": g}
    out["cells"] = {c: {a: list(v) for a, v in t[c].items()} for c in t}
    json.dump(out, open(f"{HERE}/stats{'-strict' if STRICT else ''}.json", "w"), indent=1)


if __name__ == "__main__":
    main()
