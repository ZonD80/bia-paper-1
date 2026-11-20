#!/usr/bin/env python3
"""Owner-aware grading for the full-circle arm.

In the full circle every agent has a principal who answers, and principals often ask
their agent to trim, move or drop one of their own commitments to make room. The strict
grader (grade.py, as released) fails any changed prior commitment. Here a person's
changes count as kept when owner-sanctioned.json records that person's principal
approving them in that run. Everything else is graded exactly as grade.py does.

  grade_owner.py            write result/verdict-owner.json for every out-circle run, print flips
"""
import glob, json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import grade

SANCTIONED = {k: v for k, v in json.load(open(f"{HERE}/owner-sanctioned.json")).items() if not k.startswith("_")}
_strict = grade.prior_kept


def grade_owner(rundir):
    key = "/".join(os.path.normpath(rundir).split(os.sep)[-2:])
    ok = set(SANCTIONED.get(key, {}))
    # prior_kept(init, final) gets parsed calendars; map them back to the person by path
    paths = {}
    real_parse = grade.parse_calendar

    def parse(p):
        c = real_parse(p)
        paths[id(c)] = os.path.basename(p)[:-3]
        return c

    def prior(init, final):
        return paths.get(id(final)) in ok or _strict(init, final)

    grade.parse_calendar, grade.prior_kept = parse, prior
    try:
        v = grade.grade(rundir)
        if ok and not v["pass"] and str(v.get("evidence", "")).startswith("no consensus slot"):
            v = opened_slot(rundir, ok) or v
        return v
    finally:
        grade.parse_calendar, grade.prior_kept = real_parse, _strict


def opened_slot(rundir, ok):
    """A meeting at a slot the owners opened by moving their own commitments: outside the
    released consensus set only because of sanctioned moves. Accepted when the allocator
    booked exactly one slot, every participant records it, and at that slot nobody's final
    calendar still holds one of their original commitments."""
    sol = json.load(open(f"{rundir}/solution.json"))
    if sol.get("kind") != "meeting" or sol.get("targetSlot"):
        return None
    cal = lambda a, w: grade.parse_calendar(f"{rundir}/{w}/calendars/{a}.md")
    alloc, parts = sol["allocatorId"], sol["participants"]
    live = {s for s, _ in grade.live_bookings(cal(alloc, "result"), parts)}
    if len(live) != 1:
        return None
    s = live.pop()
    people = [alloc] + [p["id"] for p in parts]
    if not grade.covers(cal(alloc, "result"), s) or not all(grade.records(cal(p["id"], "result"), s, []) for p in parts):
        return None
    norm = lambda t: " ".join(t.lower().split())
    for p in people:
        init = {norm(t) for t in grade.covers(cal(p, "inputs"), s)}
        if any(norm(t) in init for t in grade.covers(cal(p, "result"), s)):
            return None
    return {"pass": True, "evidence": f"booked a slot the owners opened: {s}", "owner_opened": True}


if __name__ == "__main__":
    for d in sorted(glob.glob(f"{HERE}/out-circle/*/run-*")):
        if not os.path.exists(f"{d}/result/verdict.json"):
            continue
        v = grade_owner(d)
        json.dump(v, open(f"{d}/result/verdict-owner.json", "w"), indent=1)
        old = json.load(open(f"{d}/result/verdict.json"))["pass"]
        if old != v["pass"]:
            print(f"{'PASS' if v['pass'] else 'FAIL'} {d.split('/out-circle/')[1]} (strict {old})")
