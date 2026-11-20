#!/usr/bin/env python3
"""Hand-review aid for owner-aware grading: for each given run, show every person whose prior
commitments changed (what went missing, what new entry overlaps) and that person's whole
principal chat, so a human can judge whether the principal asked for or approved the change.

  owner_review.py out-circle/<cell>/<run> ...
"""
import json, os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import grade

norm = lambda t: re.sub(r"\s+", " ", t.strip().lower())

for rundir in sys.argv[1:]:
    grade.WEEK = grade.run_week(rundir)
    print("=" * 100, "\n", rundir, json.load(open(f"{rundir}/result/verdict.json")).get("evidence", ""))
    chat = json.load(open(f"{rundir}/result/circle.json"))["messages"]
    for f in sorted(os.listdir(f"{rundir}/result/calendars")):
        a = f[:-3]
        i = grade.parse_calendar(f"{rundir}/inputs/calendars/{f}")
        r = grade.parse_calendar(f"{rundir}/result/calendars/{f}")
        if grade.prior_kept(i, r):
            continue
        ini = {(d, s, e, norm(t)) for d, s, e, t in i["event_list"]}
        fin = {(d, s, e, norm(t)) for d, s, e, t in r["event_list"]}
        print(f"\n--- {a}")
        for k in sorted(ini - fin):
            print("   gone:", k)
        for k in sorted(fin - ini):
            if any(k[0] == d and k[1] < e and k[2] > s for d, s, e, _ in ini):
                print("   new, overlaps:", k)
        p = a[:-len("-agent")]
        for m in chat:
            conv = m.get("conversationId", "")
            if conv == f"dm:{a},{p}" or conv == f"dm:{p},{a}":
                who = "PRINCIPAL" if m["sender"]["id"] == p else "agent"
                print(f"   [{who}] {m['text'][:600]}")
