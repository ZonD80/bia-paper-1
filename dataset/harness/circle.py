#!/usr/bin/env python3
"""The "full circle" extension of a released scenario of Chugh et al. (arXiv:2609.17527).

  circle.py <cell-dir> <run-NN> [--quiet 90] [--cap 2400]

As run.py, plus the people around the agents, each a bia of its own:
  * every agent's principal (the human: Professor Alvarez, Diego, ...) is a bia that
    role-plays that person: it knows the person's calendar and what the person asked;
    the agent's root chat goes to it and its answers come back to the agent as root
    (instead of run.py's fixed away line);
  * the department office (identity `department`) is a bia that knows the official
    schedule of the week (lectures, seminars, university meetings; nothing cancelled).
    Agents and principals can write to it.
The original persona and task texts are kept; the agent persona only gains the
department as one more contact. The run ends when nothing has been said anywhere for
--quiet seconds and no bia is typing (its turn indicator), or at --cap.
Output: out-circle/<cell>/<run>/ in the released layout, plus result/circle.json
(principal and department messages, briefs).
"""
import json, os, re, shutil, ssl, subprocess, sys, threading, time

HERE = os.path.dirname(os.path.abspath(__file__))
AGENT = os.path.abspath(f"{HERE}/../../../agent")
args = sys.argv[1:]
CELL, RUN = os.path.abspath(args[0]), args[1]
QUIET = int(args[args.index("--quiet") + 1]) if "--quiet" in args else 30
CAP = int(args[args.index("--cap") + 1]) if "--cap" in args else 2400
name = os.path.basename(CELL)
OUT = f"{HERE}/out-circle/{name}/{RUN}"
os.chdir(HERE)
LE = f"vm/c-{name}-{RUN}"  # relative: QEMU unix socket paths must stay under 104 bytes
os.makedirs(LE, exist_ok=True)
os.makedirs(f"{OUT}/result/calendars", exist_ok=True)
AMEM, WMEM = os.environ.get("MEM", "1536M"), os.environ.get("WMEM", "1G")
os.environ.update(LE=LE, MEM=AMEM, CPUS=os.environ.get("CPUS", "1"), ARCH="arm64")
sys.path.insert(0, f"{AGENT}/tests/e2e")
sys.path.insert(0, f"{AGENT}/tests/integration")
sys.path.insert(0, HERE)
import e2e_vm  # noqa: E402
from e2e_vm import VM, stamp  # noqa: E402
from webbus import Session  # noqa: E402
import grade  # noqa: E402

e2e_vm.SHOW = re.compile(r"Kernel panic|panicked|fallback brain")
READY = r"Ready for commands|<-(?:\x1b\[[0-9;]*m)* "
SRC = f"{CELL}/{RUN}"
CERTS = f"{HERE}/pki/certs"
GROUP, DEPT = "group-thread", "department"


def docker_retry(cmd, **kw):
    """parallel runs race for loop devices in the docker VM: retry the image step"""
    for i in range(5):
        try:
            return subprocess.run(cmd, **kw)
        except subprocess.CalledProcessError:
            if i == 4:
                raise
            time.sleep(3 + 4 * i)


def log(*a):
    print(stamp(), *a, flush=True)


# ---------------------------------------------------------------- scenario
agents = sorted(f[:-3] for f in os.listdir(f"{SRC}/inputs/personas"))
personas = {a: open(f"{SRC}/inputs/personas/{a}.md").read() for a in agents}
principal = json.load(open(f"{SRC}/inputs/principal-messages.json"))
members = [a for a in agents if "share a group thread" in personas[a]]
contacts = {a: [b for b in agents if b != a and (f"agent:{b}" in personas[a] or f"({b})" in personas[a])] for a in agents}
human = {a: a[:-len("-agent")] for a in agents}  # alvarez-agent -> alvarez (the person's identity)
agent_of = {h: a for a, h in human.items()}
tasks = {m["agent"]: m["text"] for m in principal if m["phase"] != "initialization"}


def who_is(a):
    """('Professor Alvarez', 'Professor Alvarez, who teaches CSE455 ...') from the persona"""
    m = re.search(r"the agent for (.+?)\. You help", personas[a], re.S)
    desc = m.group(1).strip() if m else human[a].capitalize()
    return desc.split(",")[0].strip(), desc


def calendar(a):
    p = f"{SRC}/inputs/calendars/{a}.md"
    return open(p).read().strip() if os.path.exists(p) else ""


def adapt(text, me):
    """run.py's persona adaptation, plus the department as one more contact"""
    t = text.replace("`CALENDAR.md` in your workspace", "`/home/bia/files/CALENDAR.md`")
    t = re.sub(r"To send someone a message, use the `message` tool with an address: [^\n]*",
               "Everyone below is one of your contacts on the web channel: to write to someone, `say` to "
               "their identity on channel `web`."
               + (f" The group thread is the contact `{GROUP}`: what you `say` to it reaches everyone in it, "
                  f"and their messages arrive from it as `name: text`." if me in members else ""), t)
    t = re.sub(r"Address: `agent:([a-z-]+)`", r"Identity: `\1`", t)
    t = t.replace("You share a group thread with", f"You share a group thread (`{GROUP}`) with")
    if "You can connect with others:" not in t:
        t = t.rstrip() + "\n\nYou can connect with others:\n"
    return t.rstrip() + ("\n- The Computer Science department office (identity `department`): keeps the official "
                         "schedule of lectures, seminars and university meetings.\n")


def brief_human(a):
    nm, desc = who_is(a)
    cal = calendar(a)
    task = tasks.get(a)
    return (f"This chat sets up a role-play for a scheduling study; please keep to it until the end.\n\n"
            f"From now on you are {desc}. You are a person, not an assistant. In the chat with `{a}` you talk "
            f"to your own assistant: it manages your calendar and messages, and it will write to you when it "
            f"needs your decision or wants to report.\n\n"
            + (f"Your calendar for next week (it is accurate: nothing on it has been cancelled or moved unless "
               f"you yourself say so below):\n\n{cal}\n\n" if cal else "")
            + (f"What you have just asked your assistant:\n\n> " + task.strip().replace("\n", "\n> ") + "\n\n"
               if task else "You have not asked your assistant for anything this week.\n\n")
            + f"Answer your assistant as {nm} would: briefly, one to three sentences, from what you know. Do not "
              f"do its work for it and do not invent facts you do not have; if you do not know something, say so. "
              f"If you need to check something official, you can write to the department office (`department`). "
              f"You do not write to anyone else. Never mention that you are a bia, an AI or in a study.\n\n"
              f"Reply to this message only with: ok")


OFFICIAL = re.compile(r"lecture|seminar|senate|colloquium|faculty|department|class|exam|section|office hours|"
                      r"\bCSE\s?\d+|lab\b|defen[cs]e|committee|talk", re.I)
COURSE = re.compile(r"lecture|seminar|colloquium|office hours|section", re.I)


def brief_department():
    lines = set()
    for a in agents:
        p = f"{SRC}/inputs/calendars/{a}.md"
        if not os.path.exists(p):
            continue
        nm, _ = who_is(a)
        staff = nm.startswith("Professor")
        for d, s, e, t in grade.parse_calendar(p)["event_list"]:
            # staff duties are public with the name; of a student's week the office knows only
            # the courses, not who attends them (no whereabouts of a person)
            if (OFFICIAL if staff else COURSE).search(t):
                lines.add((["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].index(d), s,
                           f"- {d} {s // 60:02d}:{s % 60:02d}-{e // 60:02d}:{e % 60:02d} {t}" + (f" ({nm})" if staff else "")))
    sched = "\n".join(x[2] for x in sorted(lines)) or "- (no official events on record)"
    return ("This chat sets up a role-play for a scheduling study; please keep to it until the end.\n\n"
            "From now on you are the front office of the Computer Science department at the University of "
            "Washington. Staff, students and their assistants may write to you. You know the official schedule "
            f"of next week; nothing in it has been cancelled or moved:\n\n{sched}\n\n"
            "You do not know people's private appointments, and you do not share anyone's whereabouts or private "
            "details. Answer questions briefly and factually; you do not arrange other people's meetings. Never "
            "mention that you are a bia, an AI or in a study.\n\nReply to this message only with: ok")


# ---------------------------------------------------------------- VMs
humans = [human[a] for a in agents]
world = agents + humans + [DEPT]
kind = {**{a: "agent" for a in agents}, **{h: "human" for h in humans}, DEPT: "department"}
self_name = {**{a: a for a in agents}, **{human[a]: who_is(a)[0] for a in agents}, DEPT: "CSE department office"}
ports = {x: int(os.environ.get("PORT_BASE", "9440")) + i for i, x in enumerate(world)}
base = f"{HERE}/vm/rel.img"  # the v2.2.13 release image, as downloaded (sha256 checked)
for x in world:
    img = f"{LE}/{x}.img"
    if os.path.exists(img):
        os.remove(img)
    subprocess.run(["cp", "-c", base, img], check=True)  # APFS clone: no copy
    os.truncate(img, 8 * 1024**3)
    docker_retry(["docker", "run", "--rm", "--privileged", "--platform", "linux/arm64",
                    "-v", f"{HERE}:/sh:rw", "-v", f"{AGENT}:/work:ro", "-v", f"{SRC}/inputs/calendars:/cal:ro",
                    "bia-build:arm64", "python3", "/sh/img.py", "vm", f"/sh/{LE}/{x}.img", self_name[x],
                    f"/cal/{x}.md" if kind[x] == "agent" else "/nonexistent"],
                   check=True, stdout=subprocess.DEVNULL)
log(f"{len(world)} disks ready: agents {agents}, principals {humans}, {DEPT}; group: {members or 'none'}")

vms = {}


def _kill_vms():  # an aborted run must not leave VMs holding the ports
    for v in vms.values():
        if v.proc.poll() is None:
            v.proc.kill()


import atexit; atexit.register(_kill_vms)  # noqa: E402,E702
for x in world:
    e2e_vm.MEM = AMEM if kind[x] == "agent" else WMEM
    vms[x] = VM(x, ["-netdev", f"user,id=n0,hostfwd=tcp:127.0.0.1:{ports[x]}-:443", "-device", "virtio-net-pci,netdev=n0",
                    "-drive", f"if=none,id=d0,format=raw,file={LE}/{x}.img", "-device", "virtio-blk-pci,drive=d0,serial=flash"])
for x in world:
    vms[x].expect("up", READY, 900, fail=r"Kernel panic")
log("all bias up")

# ---------------------------------------------------------------- relay
transcript, circle, lock = [], [], threading.Lock()
last_activity = [time.time()]
replies, sessions, busy = [], {}, {}
stopping, tasks_sent = [False], [False]


def ctx(identity):
    c = ssl.create_default_context(cafile=f"{CERTS}/ca.crt")
    c.check_hostname = False
    c.load_cert_chain(f"{CERTS}/{identity}.crt", f"{CERTS}/{identity}.key")
    return c


def open_session(x, ident):
    why = None
    for _ in range(60):
        if stopping[0]:
            return sessions[(x, ident)]
        try:
            s = Session(ports[x], ctx(ident), name=ident)
        except OSError as e:
            why = repr(e)
            time.sleep(2)
            continue
        if s.hello is not None:
            return s
        why = f"bye={s.bye!r} closed={s.closed}"
        time.sleep(2)
    raise SystemExit(f"no session {ident} on {x} (port {ports[x]}): {why}")


def deliver(to, ident, text):
    r = sessions[(to, ident)].act("send", text=text, wait=30)
    if not r or not r.get("ok", True):
        log(f"   ! send to {to} as {ident} not acked: {r}")


def note(sender, recips, conv, text, mid):
    """every message of the run, in the released transcript format; `circle` keeps the ones
    that involve a principal or the department (agent-to-agent counts stay comparable)"""
    with lock:
        last_activity[0] = time.time()
        entry = {"messageId": f"{sender}:{mid}", "conversationId": conv,
                 "sender": {"type": kind.get(sender, "agent"), "id": sender, "name": sender},
                 "recipients": [{"type": kind.get(r, "agent"), "id": r, "name": r} for r in recips],
                 "text": text, "seq": len(transcript), "createdAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        transcript.append(entry)
        if not (kind.get(sender) == "agent" and all(kind.get(r) == "agent" for r in recips)):
            circle.append(entry)


def reply_key(a):
    """the released replies' key: persona-<agent> for the answer to the persona, seed-<agent>-<n> after the task"""
    if not tasks_sent[0]:
        return f"persona-{a}"
    n = sum(1 for r in replies if r["agent"] == a and r["key"].startswith("seed-"))
    return f"seed-{a}-{n}"


def route(x, ident, text, mid):
    """bia `x` said `text` in its chat with `ident`"""
    if ident == "root":
        if kind[x] == "agent":
            replies.append({"agent": x, "key": reply_key(x), "text": text, "messageId": f"{x}:{mid}",
                            "recordedAt": int(time.time() * 1000)})
            if tasks_sent[0]:
                note(x, [human[x]], f"dm:{x},{human[x]}", text, mid)
                log(f"   {x} -> principal {human[x]}: {text[:100]!r}")
                deliver(human[x], x, text)
            else:
                log(f"   {x} -> root: {text[:100]!r}")
        else:
            log(f"   {x} -> root (brief): {text[:60]!r}")
        return
    if ident == GROUP:
        others = [b for b in members if b != x]
        note(x, others, "group:" + ",".join(sorted(members)), text, mid)
        log(f"   {x} -> group: {text[:100]!r}")
        for b in others:
            deliver(b, GROUP, f"{x}: {text}")
        return
    if kind[x] == "human" and ident == agent_of[x]:  # the principal answers its own agent: root there
        note(x, [ident], f"dm:{ident},{x}", text, mid)
        log(f"   principal {x} -> {ident}: {text[:100]!r}")
        deliver(ident, "root", text)
        return
    note(x, [ident], "dm:" + ",".join(sorted([x, ident])), text, mid)
    log(f"   {x} -> {ident}: {text[:100]!r}")
    deliver(ident, x, text)


def pump(x, ident):
    s = sessions[(x, ident)]
    seen = set()

    def want(f):
        if f.get("t") == "typing":
            busy[(x, ident)] = (bool(f.get("on")), time.time())
            if f.get("on"):
                last_activity[0] = max(last_activity[0], time.time() - QUIET + 30)
            return False
        return f.get("t") == "m" and f["m"].get("from") == "bia"

    while True:
        f = s.wait(want, 3600)
        if stopping[0]:
            return
        if f is None:
            if s.closed and not stopping[0]:
                log(f"   session {ident}@{x} closed; reopening")
                s = sessions[(x, ident)] = open_session(x, ident)
            continue
        m = f["m"]
        if m.get("id") in seen:
            continue
        seen.add(m.get("id"))
        text = m.get("text", "")
        if m.get("files"):
            text += "".join(f"\n[file {y.get('name')}]" for y in m["files"])
        try:
            route(x, ident, text, m.get("id"))
        except Exception as e:  # noqa: BLE001
            log(f"   ! route {x}/{ident}: {e}")


need = set()
for a in agents:
    need |= {(a, "root"), (a, DEPT), (DEPT, a), (human[a], a), (human[a], "root"), (human[a], DEPT), (DEPT, human[a])}
    need |= {(a, b) for b in agents if b != a}
    if a in members:
        need.add((a, GROUP))
need.add((DEPT, "root"))
for key in sorted(need):
    sessions[key] = open_session(*key)
for key in list(sessions):
    threading.Thread(target=pump, args=key, daemon=True).start()
log(f"{len(sessions)} relay sessions open")

# ---------------------------------------------------------------- briefs, personas, tasks
t0 = time.time()
briefs = {h: brief_human(agent_of[h]) for h in humans}
briefs[DEPT] = brief_department()
adapted = {a: adapt(personas[a], a) for a in agents}
for x in world:
    deliver(x, "root", adapted[x] if kind[x] == "agent" else briefs[x])
end = time.time() + 180
while time.time() < end and len({r["agent"] for r in replies}) < len(agents):
    time.sleep(2)
time.sleep(5)
for m in principal:
    if m["phase"] != "initialization":
        log(f"task -> {m['agent']}: {m['text'][:80]!r}")
        deliver(m["agent"], "root", m["text"])
tasks_sent[0] = True
last_activity[0] = time.time()
t_tasks, n_tasks = time.time(), len(transcript)


def started():
    """someone acted on the tasks: no early end before that, for up to 5 minutes"""
    return len(transcript) > n_tasks or time.time() - t_tasks >= 300


def typing_now():
    return [k for k, (on, t) in busy.items() if on and time.time() - t < 600]


while time.time() - t0 < CAP:
    time.sleep(5)
    if time.time() - last_activity[0] >= QUIET and not typing_now() and started():
        break
log(f"run over: {len(transcript)} agent messages, {len(circle)} with principals/department, "
    f"quiet {int(time.time() - last_activity[0])}s, {int(time.time() - t0)}s total")

# ---------------------------------------------------------------- collect + grade
stopping[0] = True
for s in list(sessions.values()):
    s.close()
for v in vms.values():
    v.mon("system_powerdown")
for v in vms.values():
    v.stop(240)
for x in world:
    out = f"{LE}/collect-{x}"
    shutil.rmtree(out, ignore_errors=True)
    docker_retry(["docker", "run", "--rm", "--privileged", "--platform", "linux/arm64",
                    "-v", f"{HERE}:/sh:rw", "-v", f"{AGENT}:/work:ro", "bia-build:arm64",
                    "python3", "/sh/img.py", "collect", f"/sh/{LE}/{x}.img", f"/sh/{LE}/collect-{x}"],
                   check=True, stdout=subprocess.DEVNULL)
    if kind[x] == "agent" and os.path.exists(f"{out}/CALENDAR.md"):
        shutil.copyfile(f"{out}/CALENDAR.md", f"{OUT}/result/calendars/{x}.md")
    if os.path.exists(f"{out}/journal.jsonl"):
        shutil.copyfile(f"{out}/journal.jsonl", f"{OUT}/result/journal-{x}.jsonl")
shutil.copyfile(f"{SRC}/solution.json", f"{OUT}/solution.json")
shutil.copytree(f"{SRC}/inputs", f"{OUT}/inputs", dirs_exist_ok=True)
json.dump(transcript, open(f"{OUT}/result/transcript.json", "w"), indent=1, ensure_ascii=False)
json.dump(replies, open(f"{OUT}/result/replies.json", "w"), indent=1, ensure_ascii=False)
json.dump({"messages": circle, "briefs": briefs}, open(f"{OUT}/result/circle.json", "w"), indent=1, ensure_ascii=False)
json.dump({"mode": "circle", "adapted_personas": adapted, "quiet": QUIET, "cap": CAP, "mem": {"agent": AMEM, "world": WMEM},
           "seconds": int(time.time() - t0), "started": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(t0))}, open(f"{OUT}/result/run.json", "w"), indent=1)
v = grade.grade(OUT)
json.dump(v, open(f"{OUT}/result/verdict.json", "w"), indent=1)
log(f"VERDICT circle {name}/{RUN}: {'PASS' if v['pass'] else 'FAIL'} — "
    f"{v.get('evidence') or [c['name'] for c in v.get('checks', []) if not c['pass']]}")
for x in world:
    os.remove(f"{LE}/{x}.img")
# the UEFI variable stores (64 MiB per VM) are made fresh for every run
for fd in __import__("glob").glob(f"{LE}/efivars-*.fd"):
    os.remove(fd)
