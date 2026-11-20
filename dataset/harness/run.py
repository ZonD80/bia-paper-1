#!/usr/bin/env python3
"""Run one released scenario of Chugh et al. (arXiv:2609.17527) with temporary bias.

  run.py <cell-dir> <run-NN> [--quiet 300] [--cap 2400]

Each agent of the scenario is a bia in its own QEMU VM (2 GB, own disk cloned from
vm/base.img, the shared test PKI). The host is the network: for every bia it holds one
web-bus session per counterpart identity (the other agents, the group thread, and root
as the principal). What a bia `say`s to identity X is delivered to bia X from this bia's
identity; what it says to `group-thread` reaches every other member as `<name>: <text>`.
The principal's messages (persona, then the task) come from root; after the task, root answers its bia only with a fixed away line (user decision, 2026-11-16): at most one per 120 s and 5 per run. The run ends when no
agent-to-agent message has been sent for --quiet seconds (their observeSeconds), or at
--cap. Then the VMs power off, CALENDAR.md is collected from each disk and graded with
grade.py. Output: out/<cell>/<run>/ in the released layout.
"""
import json, os, re, shutil, ssl, subprocess, sys, threading, time

HERE = os.path.dirname(os.path.abspath(__file__))
AGENT = os.path.abspath(f"{HERE}/../../../agent")
args = sys.argv[1:]
CELL, RUN = os.path.abspath(args[0]), args[1]
QUIET = int(args[args.index("--quiet") + 1]) if "--quiet" in args else 300
CAP = int(args[args.index("--cap") + 1]) if "--cap" in args else 2400
name = os.path.basename(CELL)
OUT = f"{HERE}/out/{name}/{RUN}"
os.chdir(HERE)
LE = f"vm/{name}-{RUN}"  # relative: QEMU unix socket paths must stay under 104 bytes
os.makedirs(LE, exist_ok=True)
os.makedirs(f"{OUT}/result/calendars", exist_ok=True)
os.environ.update(LE=LE, MEM=os.environ.get("MEM", "2G"), CPUS=os.environ.get("CPUS", "2"), ARCH="arm64")
sys.path.insert(0, f"{AGENT}/tests/e2e")
sys.path.insert(0, f"{AGENT}/tests/integration")
import e2e_vm  # noqa: E402
from e2e_vm import VM, stamp  # noqa: E402
from webbus import Session  # noqa: E402

e2e_vm.SHOW = re.compile(r"Kernel panic|panicked|fallback brain")
READY = r"Ready for commands|<-(?:\x1b\[[0-9;]*m)* "
SRC = f"{CELL}/{RUN}"
CERTS = f"{HERE}/pki/certs"
GROUP = "group-thread"


def log(*a):
    print(stamp(), *a, flush=True)


# ---------------------------------------------------------------- scenario
agents = sorted(f[:-3] for f in os.listdir(f"{SRC}/inputs/personas"))
personas = {a: open(f"{SRC}/inputs/personas/{a}.md").read() for a in agents}
principal = json.load(open(f"{SRC}/inputs/principal-messages.json"))
members = [a for a in agents if "share a group thread" in personas[a]]
contacts = {a: [b for b in agents if b != a and (f"agent:{b}" in personas[a] or f"({b})" in personas[a])] for a in agents}


def adapt(text, me):
    """The persona in bia's terms: contacts are identities on the web channel, the group
    thread is one identity, the calendar lives in /home/bia/files."""
    t = text.replace("`CALENDAR.md` in your workspace", "`/home/bia/files/CALENDAR.md`")
    t = re.sub(r"To send someone a message, use the `message` tool with an address: [^\n]*",
               "Everyone below is one of your contacts on the web channel: to write to someone, `say` to "
               "their identity on channel `web`."
               + (f" The group thread is the contact `{GROUP}`: what you `say` to it reaches everyone in it, "
                  f"and their messages arrive from it as `name: text`." if me in members else ""), t)
    t = re.sub(r"Address: `agent:([a-z-]+)`", r"Identity: `\1`", t)
    t = t.replace("You share a group thread with", f"You share a group thread (`{GROUP}`) with")
    return t


# ---------------------------------------------------------------- VMs
base = f"{HERE}/vm/rel.img"  # the v2.2.13 release image, as downloaded (sha256 checked)
ports = {a: int(os.environ.get("PORT_BASE", "9440")) + i for i, a in enumerate(agents)}  # PORT_BASE: a queue beside others
for a in agents:
    img = f"{LE}/{a}.img"
    if os.path.exists(img):
        os.remove(img)
    subprocess.run(["cp", "-c", base, img], check=True)  # APFS clone: no copy
    os.truncate(img, 8 * 1024**3)  # a bigger disk, as after dd: bia-grow takes it at first boot
    subprocess.run(["docker", "run", "--rm", "--privileged", "--platform", "linux/arm64",
                    "-v", f"{HERE}:/sh:rw", "-v", f"{AGENT}:/work:ro", "-v", f"{SRC}/inputs/calendars:/cal:ro",
                    "bia-build:arm64", "python3", "/sh/img.py", "vm", f"/sh/vm/{name}-{RUN}/{a}.img", a, f"/cal/{a}.md"],
                   check=True, stdout=subprocess.DEVNULL)
log(f"{len(agents)} disks ready: {', '.join(agents)}; group: {members or 'none'}")

vms = {}
for a in agents:
    vms[a] = VM(a, ["-netdev", f"user,id=n0,hostfwd=tcp:127.0.0.1:{ports[a]}-:443", "-device", "virtio-net-pci,netdev=n0",
                    "-drive", f"if=none,id=d0,format=raw,file={LE}/{a}.img", "-device", "virtio-blk-pci,drive=d0,serial=flash"])
for a in agents:
    vms[a].expect("agent up", READY, 900, fail=r"Kernel panic")
log("all agents up")

# ---------------------------------------------------------------- relay
transcript, lock = [], threading.Lock()
last_agent_msg = [time.time()]
replies = []
sessions = {}
stopping = [False]
tasks_sent = [False]
AWAY = "I'm away this week and can't answer; use your own judgement and handle it."
away_sent = {}  # agent -> [times]: at most one auto-reply per 120 s, 5 per run


def ctx(identity):
    c = ssl.create_default_context(cafile=f"{CERTS}/ca.crt")
    c.check_hostname = False
    c.load_cert_chain(f"{CERTS}/{identity}.crt", f"{CERTS}/{identity}.key")
    return c


def open_session(a, ident):
    for _ in range(60):
        if stopping[0]:
            return sessions[(a, ident)]
        try:
            s = Session(ports[a], ctx(ident), name=ident)
        except OSError:
            time.sleep(2)
            continue
        if s.hello is not None:
            return s
        time.sleep(2)
    raise SystemExit(f"no session {ident} on {a}")


def deliver(to, ident, text):
    s = sessions[(to, ident)]
    r = s.act("send", text=text, wait=30)
    if not r or not r.get("ok", True):
        log(f"   ! send to {to} as {ident} not acked: {r}")


def record(sender, recips, conv, text, mid=None):
    with lock:
        transcript.append({"messageId": f"{sender}:{mid}", "conversationId": conv, "sender": {"type": "agent", "id": sender, "name": sender},
                           "recipients": [{"type": "agent", "id": r, "name": r} for r in recips],
                           "text": text, "seq": len(transcript), "createdAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
        last_agent_msg[0] = time.time()


def pump(a, ident):
    """Frames of bia `a` on its chat with `ident`: bia's own new messages are routed."""
    s = sessions[(a, ident)]
    seen = set()
    while True:
        f = s.wait(lambda f: f.get("t") == "m" and f["m"].get("from") == "bia", 3600)
        if stopping[0]:
            return
        if f is None:
            if s.closed and not stopping[0]:
                log(f"   session {ident}@{a} closed; reopening")
                s = sessions[(a, ident)] = open_session(a, ident)
            continue
        m = f["m"]
        if m.get("id") in seen:
            continue
        seen.add(m.get("id"))
        text = m.get("text", "")
        if m.get("files"):
            text += "".join(f"\n[file {x.get('name')}]" for x in m["files"])
        if ident == "root":
            key = f"persona-{a}" if not tasks_sent[0] else f"seed-{a}-{sum(1 for r in replies if r['agent'] == a and r['key'].startswith('seed-'))}"
            replies.append({"agent": a, "key": key, "text": text, "messageId": f"{a}:{m.get('id')}", "recordedAt": int(time.time() * 1000)})
            log(f"   {a} -> principal: {text[:100]!r}")
            ts = away_sent.setdefault(a, [])
            if tasks_sent[0] and len(ts) < 5 and (not ts or time.time() - ts[-1] > 120):
                ts.append(time.time())
                deliver(a, "root", AWAY)
                log(f"   principal -> {a}: (away) {AWAY!r}")
        elif ident == GROUP:
            others = [b for b in members if b != a]
            record(a, others, "group:" + ",".join(sorted(members)), text, m.get("id"))
            log(f"   {a} -> group: {text[:100]!r}")
            for b in others:
                deliver(b, GROUP, f"{a}: {text}")
        else:
            record(a, [ident], "dm:" + ",".join(sorted([a, ident])), text, m.get("id"))
            log(f"   {a} -> {ident}: {text[:100]!r}")
            deliver(ident, a, text)


for a in agents:
    for ident in ["root"] + contacts[a] + ([GROUP] if a in members else []):
        sessions[(a, ident)] = open_session(a, ident)
# a contact that writes first to someone who does not list it still needs a session
for a in agents:
    for b in agents:
        if b != a and (b, a) not in sessions:
            sessions[(b, a)] = open_session(b, a)
for key in list(sessions):
    threading.Thread(target=pump, args=key, daemon=True).start()
log(f"{len(sessions)} relay sessions open")

# ---------------------------------------------------------------- principal
t0 = time.time()
for m in principal:
    if m["phase"] == "initialization":
        deliver(m["agent"], "root", adapt(m["text"], m["agent"]))
end = time.time() + 240
while time.time() < end and len({r["agent"] for r in replies}) < len(agents):
    time.sleep(2)
last_agent_msg[0] = time.time()
for m in principal:
    if m["phase"] != "initialization":
        log(f"task -> {m['agent']}: {m['text'][:80]!r}")
        deliver(m["agent"], "root", m["text"])
tasks_sent[0] = True
last_agent_msg[0] = time.time()
while time.time() - last_agent_msg[0] < QUIET and time.time() - t0 < CAP:
    time.sleep(5)
log(f"run over: {len(transcript)} agent messages, quiet {int(time.time() - last_agent_msg[0])}s, {int(time.time() - t0)}s total")

# ---------------------------------------------------------------- collect + grade
stopping[0] = True
for s in list(sessions.values()):
    s.close()
for v in vms.values():
    v.mon("system_powerdown")
for v in vms.values():
    v.stop(240)
for a in agents:
    out = f"{LE}/collect-{a}"
    shutil.rmtree(out, ignore_errors=True)
    subprocess.run(["docker", "run", "--rm", "--privileged", "--platform", "linux/arm64",
                    "-v", f"{HERE}:/sh:rw", "-v", f"{AGENT}:/work:ro", "bia-build:arm64",
                    "python3", "/sh/img.py", "collect", f"/sh/vm/{name}-{RUN}/{a}.img", f"/sh/vm/{name}-{RUN}/collect-{a}"],
                   check=True, stdout=subprocess.DEVNULL)
    if os.path.exists(f"{out}/CALENDAR.md"):
        shutil.copyfile(f"{out}/CALENDAR.md", f"{OUT}/result/calendars/{a}.md")
    if os.path.exists(f"{out}/journal.jsonl"):
        shutil.copyfile(f"{out}/journal.jsonl", f"{OUT}/result/journal-{a}.jsonl")
shutil.copyfile(f"{SRC}/solution.json", f"{OUT}/solution.json")
shutil.copytree(f"{SRC}/inputs", f"{OUT}/inputs", dirs_exist_ok=True)
json.dump(transcript, open(f"{OUT}/result/transcript.json", "w"), indent=1, ensure_ascii=False)
json.dump(replies, open(f"{OUT}/result/replies.json", "w"), indent=1, ensure_ascii=False)
json.dump({"away_reply": AWAY, "away_sent": {a: len(t) for a, t in away_sent.items()}, "adapted_personas": {a: adapt(personas[a], a) for a in agents}, "quiet": QUIET, "cap": CAP,
           "seconds": int(time.time() - t0), "started": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(t0))}, open(f"{OUT}/result/run.json", "w"), indent=1)
sys.path.insert(0, HERE)
import grade  # noqa: E402
v = grade.grade(OUT)
json.dump(v, open(f"{OUT}/result/verdict.json", "w"), indent=1)
log(f"VERDICT {name}/{RUN}: {'PASS' if v['pass'] else 'FAIL'} — {v.get('evidence') or [c['name'] for c in v.get('checks', []) if not c['pass']]}")
for a in agents:
    os.remove(f"{LE}/{a}.img")
# the UEFI variable stores (64 MiB per VM) are made fresh for every run
for fd in __import__("glob").glob(f"{LE}/efivars-*.fd"):
    os.remove(fd)
