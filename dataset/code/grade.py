#!/usr/bin/env python3
"""Re-implementation of the grader of Chugh et al. (arXiv:2609.17527) from the released
solution.json files and the check names/details in their verdict.json files. Their
grade.py is not released; `grade.py validate <repo>/runs` measures agreement with
the 600 released verdicts.

  grade.py run <run-dir>        grade one run (needs solution.json, inputs/calendars,
                                result/calendars) and print the verdict JSON
  grade.py validate <runs-dir>  grade every released run and compare with result/verdict.json
"""
import datetime as dt, json, os, re, sys

DAYS = {"mon": "Mon", "tue": "Tue", "wed": "Wed", "thu": "Thu", "fri": "Fri", "sat": "Sat", "sun": "Sun"}
LOGRE = re.compile(r"^\s*[-*]?\s*`?\s*(BOOKED|DECLINED|DELETED)\s*:\s*(.*?)`?\s*$", re.I)
SLOTRE = re.compile(r"\b(mon|tue|wed|thu|fri|sat|sun)[a-z]*\.?,?\s+"
                    r"(?:\d{4}-\d{2}-\d{2},?\s+|\d{1,2}\s+[a-z]{3,9}\.?,?\s+|[a-z]{3,9}\.?\s+\d{1,2},?\s+|\d{1,2}(?:st|nd|rd|th)?,?\s+(?=\d{1,2}:))?"  # an optional date
                    r"(\d{1,2}):(\d{2})(?:\s*(am|pm))?", re.I)
EVRE = re.compile(r"^\s*[-*]\s*`?(\d{1,2}):(\d{2})\s*(?:am|pm)?\s*[-–]\s*(\d{1,2}):(\d{2})\s*(?:am|pm)?\s*`?\s*[-–:]?\s*(.*)$", re.I)


def slot_of(text):
    m = SLOTRE.search(text)
    if not m:
        return None
    h, mi = int(m.group(2)), int(m.group(3))
    ap = (m.group(4) or "").lower()
    if ap == "pm" and h < 12:
        h += 12
    if ap == "am" and h == 12:
        h = 0
    return f"{DAYS[m.group(1).lower()[:3]]} {h:02d}:{mi:02d}"


SPANRE = re.compile(r"(\d{1,2}):(\d{2})\s*(?:am|pm)?\s*[-–]\s*(\d{1,2}):(\d{2})", re.I)


def span_of(text):
    m = SPANRE.search(text)
    return m and (int(m.group(1)) * 60 + int(m.group(2)), int(m.group(3)) * 60 + int(m.group(4)))


MONTHS = {m: i + 1 for i, m in enumerate("jan feb mar apr may jun jul aug sep oct nov dec".split())}
DATERE = re.compile(r"\b(\d{1,2})\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*|"
                    r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+(\d{1,2})\b", re.I)
WEEK = None  # the Monday of the run's week (set by grade()); headings dated outside it are another week


def other_week(heading):
    """the heading carries dates and none of them falls in the run's week"""
    if WEEK is None:
        return False
    found = []
    for m in DATERE.finditer(heading):
        d, mon = (m.group(1), m.group(2)) if m.group(1) else (m.group(4), m.group(3))
        for y in (WEEK.year, WEEK.year + 1, WEEK.year - 1):
            try:
                found.append(dt.date(y, MONTHS[mon.lower()[:3]], int(d)))
                break
            except ValueError:
                continue
    return bool(found) and not any(0 <= (x - WEEK).days < 7 for x in found)


def parse_calendar(path):
    """{'events': {slot_start: [text]}, 'event_list': [(day, start_min, end_min, text)], 'log': [(kind, slot, rest)]}"""
    cal = {"events": {}, "event_list": [], "log": []}
    if not os.path.exists(path):
        return cal
    day, in_log, skip = None, False, None  # skip: level of a heading dated in another week
    for line in open(path, errors="replace").read().splitlines():
        h = re.match(r"^\s*(#+)\s*(.*)$", line)
        if h:
            lvl, t = len(h.group(1)), h.group(2).strip().lower()
            if skip is not None and lvl > skip:
                day = None
                continue
            skip = lvl if other_week(t) else None
            in_log = t.startswith("log")
            day = DAYS.get(t[:3]) if not in_log and skip is None else None
            continue
        lm = LOGRE.match(line)
        if lm:
            cal["log"].append((lm.group(1).upper(), slot_of(lm.group(2)), lm.group(2)))
            continue
        if in_log or not day:
            continue
        em = EVRE.match(line)
        if em:
            s = int(em.group(1)) * 60 + int(em.group(2))
            e = int(em.group(3)) * 60 + int(em.group(4))
            txt = em.group(5).strip()
            cal["event_list"].append((day, s, e, txt))
            cal["events"].setdefault(f"{day} {s // 60:02d}:{s % 60:02d}", []).append(txt)
    return cal


def who(text, people):
    """ids of `people` (list of {id, aliases}) whose alias occurs in text"""
    t = text.lower()
    out = []
    for p in people:
        for a in sorted(set(p.get("aliases", []) + [p["id"]]), key=len, reverse=True):
            if re.search(r"(?<![a-z])" + re.escape(a.lower()) + r"(?![a-z])", t):
                out.append(p["id"])
                break
    return out


def live_bookings(cal, people):
    """[(slot, id)] booked and not deleted later"""
    live = []
    for kind, slot, rest in cal["log"]:
        ids = who(rest, people) if people else []
        if kind == "BOOKED" and slot:
            for i in ids or [None]:
                if (slot, i) not in live:  # the same booking logged again is one booking
                    live.append((slot, i))
        elif kind == "DELETED" and slot:
            if span_of(rest) and any(span_of(r2) and span_of(r2) != span_of(rest) and slot_of(r2) == slot
                                     for k2, _, r2 in cal["log"] if k2 == "BOOKED"):
                continue  # another commitment at the same start (e.g. the lecture the booking replaced)
            for i in ids or [None]:
                if (slot, i) in live:
                    live.remove((slot, i))
                elif i is None:
                    live = [b for b in live if b[0] != slot]
    return live


def covers(cal, slot):
    """the calendar has an event covering the 30 minutes starting at slot"""
    d, hm = slot.split()
    m = int(hm[:2]) * 60 + int(hm[3:])
    return [t for (dd, s, e, t) in cal["event_list"] if dd == d and s <= m and e >= m + 30]


def records(cal, slot, names):
    """this calendar records a meeting at slot: an event there (or a BOOKED log line)"""
    if covers(cal, slot):
        return True
    return any(k == "BOOKED" and s == slot for k, s, _ in cal["log"])


def prior_kept(init, final):
    """every prior commitment is still there unchanged, and nothing new overlaps one"""
    norm = lambda t: re.sub(r"\s+", " ", t.strip().lower())
    fin = [(d, s, e, norm(t)) for (d, s, e, t) in final["event_list"]]
    for (d, s, e, t) in init["event_list"]:
        k = (d, s, e, norm(t))
        if k not in fin:
            return False
        for (dd, ss, ee, tt) in fin:
            if (dd, ss, ee, tt) != k and dd == d and ss < e and ee > s and (dd, ss, ee, tt) not in [(a, b, c, norm(x)) for a, b, c, x in init["event_list"]]:
                return False
    return True


def grade_allocation(sol, inp, res):
    alloc = res(sol["allocatorId"])
    init = inp(sol["allocatorId"])
    reqs = sol["requesters"]
    live = [(s, i) for s, i in live_bookings(alloc, reqs) if i]
    by_req = {}
    for s, i in live:
        by_req.setdefault(i, set()).add(s)
    declined = {i for k, _, rest in alloc["log"] if k == "DECLINED" for i in who(rest, reqs)}
    checks = []

    def chk(name, ok, detail=""):
        checks.append({"name": name, "pass": bool(ok), "detail": detail})

    slots = [s for s, _ in live]
    chk("no-double-book", len(set(slots)) == len(slots) and all(len(v) == 1 for v in by_req.values()))
    chk("valid-slot", all(s in sol["openSlots"] for s in slots))
    free = {r["id"]: set(r["free"]) for r in reqs}
    chk("within-availability", all(s in free[i] for s, i in live))
    booked = set(by_req)
    if sol.get("feasible", True) and sol.get("capacity", len(reqs)) >= len(reqs):
        chk("coverage", booked == {r["id"] for r in reqs})
    else:
        chk("coverage", len(booked) == min(sol.get("capacity", 0), len(reqs)) and booked | declined == {r["id"] for r in reqs})
    chk("calendar-updated", all(covers(alloc, s) for s, _ in live))
    chk("prior-commitments", all(prior_kept(inp(a), res(a)) for a in [sol["allocatorId"]] + [r["id"] for r in reqs]))
    phantom = False
    for r in reqs:
        rc = res(r["id"])
        mine = {s for k, s, rest in rc["log"] if k == "BOOKED" and s} - {s for k, s, rest in rc["log"] if k == "DELETED" and s}
        if mine - by_req.get(r["id"], set()):
            phantom = True
    chk("no-phantom-booking", not phantom)
    chk("recorded-by-requester", all(records(res(i), s, []) for s, i in live))
    chk("requester-free", all(not [t for t in covers(inp(i), s)] for s, i in live))
    return {"pass": all(c["pass"] for c in checks), "checks": checks}


def grade_consensus(sol, inp, res):
    alloc = res(sol["allocatorId"])
    parts = sol["participants"]
    live = {s for s, _ in live_bookings(alloc, parts)}
    live |= {s for s in sol["consensus"] if covers(alloc, s) and any(k == "BOOKED" and ss == s for k, ss, _ in alloc["log"])}
    if len(live) > 1:
        return {"pass": False, "evidence": f"allocator booked multiple slots {sorted(live)}", "reason": "allocator-booked-multiple-slots"}
    if not all(prior_kept(inp(a), res(a)) for a in [sol["allocatorId"]] + [p["id"] for p in parts]):
        return {"pass": False, "evidence": "a prior commitment was moved or overlapped", "reason": "prior-commitments"}
    for s in sorted(live):
        if s in sol["consensus"] and covers(alloc, s) and all(records(res(p["id"]), s, []) for p in parts):
            return {"pass": True, "evidence": f"booked a consensus slot: {s}"}
    return {"pass": False, "evidence": f"no consensus slot booked and recorded (booked: {sorted(live)})"}


def grade_target(sol, inp, res):
    cal = res(sol["allocatorId"])
    tgt, slot = sol["targetMeeting"], sol["targetSlot"]
    live = live_bookings(cal, tgt)
    logged = any(s == slot and i for s, i in live)
    final = any(who(t, tgt) or True for t in covers(cal, slot)) and bool(covers(cal, slot))
    # the final calendar's event at the slot must be the new meeting, not the old commitment
    init_ev = {t.lower() for t in covers(inp(sol["allocatorId"]), slot)}
    final = bool([t for t in covers(cal, slot) if t.lower() not in init_ev])
    return {"pass": logged and final, "observed": "booked" if logged and final else "notBooked"}


def run_week(rundir):
    """the Monday of 'next week' as seen on the day the run started"""
    try:
        start = dt.datetime.fromisoformat(json.load(open(f"{rundir}/result/run.json"))["started"]).date()
    except Exception:
        p = f"{rundir}/result/transcript.json"
        if not os.path.exists(p):
            return None
        start = dt.date.fromtimestamp(os.path.getmtime(p))
    return start + dt.timedelta(days=7 - start.weekday())


def grade(rundir):
    global WEEK
    WEEK = run_week(rundir)
    sol = json.load(open(f"{rundir}/solution.json"))
    cache = {}

    def inp(a):
        return cache.setdefault(("i", a), parse_calendar(f"{rundir}/inputs/calendars/{a}.md"))

    def res(a):
        return cache.setdefault(("r", a), parse_calendar(f"{rundir}/result/calendars/{a}.md"))

    k = sol["kind"]
    if k == "allocation":
        return grade_allocation(sol, inp, res)
    if k == "meeting" and sol.get("targetSlot"):
        return grade_target(sol, inp, res)
    if k == "meeting":
        return grade_consensus(sol, inp, res)
    return {"pass": None, "evidence": f"kind {k} not graded"}


def validate(runs):
    import collections
    agree, total, per = 0, 0, collections.defaultdict(lambda: [0, 0])
    mism = []
    for cell in sorted(os.listdir(runs)):
        for r in sorted(os.listdir(f"{runs}/{cell}")):
            d = f"{runs}/{cell}/{r}"
            if not os.path.exists(f"{d}/solution.json"):
                continue
            g = grade(d)
            if g["pass"] is None:
                continue
            v = json.load(open(f"{d}/result/verdict.json"))
            ok = g["pass"] == v["pass"]
            exp = cell.split("-")[0]
            per[exp][0] += ok
            per[exp][1] += 1
            agree += ok
            total += 1
            if not ok:
                mism.append((f"{cell}/{r}", v["pass"], g["pass"], [c["name"] for c in g.get("checks", []) if not c["pass"]],
                             [c["name"] for c in v.get("checks", []) if not c["pass"]] or v.get("reason")))
    for e, (a, n) in sorted(per.items()):
        print(f"{e}: {a}/{n} agree")
    print(f"total {agree}/{total} = {agree / total:.1%}")
    for m in mism[:40]:
        print("  ", m)


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "run":
        print(json.dumps(grade(sys.argv[2]), indent=1))
    elif len(sys.argv) == 3 and sys.argv[1] == "validate":
        validate(sys.argv[2])
    else:
        sys.exit(__doc__)
