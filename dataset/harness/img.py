#!/usr/bin/env python3
"""Image side of the social-harness runs. Runs in the bia-build container (root, loop devices),
with the agent repo at /work (ro) and bia-runs at /sh (rw).

  base <img>                       FMM keys (./fmm.json of the agent repo), the shared test PKI,
                                   no first-start / release-notes turn, no GGUF
  vm <img> <name> <calendar.md>    self.json name, CALENDAR.md in /home/bia/files
  collect <img> <outdir>           CALENDAR.md and the agent's journal out of a stopped VM
"""
import importlib.util, json, os, re, shutil, sys

spec = importlib.util.spec_from_file_location("ut", "/work/tests/e2e/update-e2e-img.py")
ut = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ut)


def own(path):
    for dp, ds, fs in os.walk(path):
        for n in ds + fs:
            os.lchown(os.path.join(dp, n), 1000, 1000)
    os.lchown(path, 1000, 1000)


def opened(img, ro=False):
    ut.IMAGES["x"] = img
    im = ut.Img("x", ro=ro)
    im.mount()
    return im


def base(img):
    im = opened(img)
    try:
        r = im.root
        ut.seed_fmm(im)
        st = f"{r}/home/bia/files/state"
        ver = re.search(r'^version = "(.*)"', open("/work/Cargo.toml").read(), re.M).group(1)
        # the image's agent may be older than the tree; read its own version if the image says so
        for f, text in (("welcomed", f"bia {ver}\n"), ("version", f"{ver}\n")):
            ut.put(f"{st}/{f}", text)
            os.chown(f"{st}/{f}", 1000, 1000)
        shutil.rmtree(f"{st}/pki", ignore_errors=True)
        shutil.copytree("/sh/pki/files/state/pki", f"{st}/pki")
        own(f"{st}/pki")
        print("base: fmm, pki, welcomed", ver)
    finally:
        im.close()


def vm(img, name, cal):
    """A release image as bia deploy leaves it before the first boot (the dd path): FMM keys,
    language/name/gender and the seeded PKI on the ESP; the scenario's CALENDAR.md in files."""
    im = opened(img)
    try:
        esp, r = im.esp, im.root
        os.makedirs(f"{esp}/EFI/bia/seed", exist_ok=True)
        shutil.copyfile("/work/fmm.json", f"{esp}/EFI/bia/fmm.json")
        ut.put(f"{esp}/EFI/bia/self.json", json.dumps({"lang": "en", "name": name, "gender": "neutral"}))
        shutil.rmtree(f"{esp}/EFI/bia/seed/pki", ignore_errors=True)
        src = "/sh/pki/files/state/pki"
        for dp, ds, fs in os.walk(src):  # FAT: plain copies, no permissions
            os.makedirs(f"{esp}/EFI/bia/seed/pki/{os.path.relpath(dp, src)}", exist_ok=True)
            for f in fs:
                shutil.copyfile(os.path.join(dp, f), f"{esp}/EFI/bia/seed/pki/{os.path.relpath(os.path.join(dp, f), src)}")
        files = f"{r}/home/bia/files"
        os.makedirs(files, exist_ok=True)
        os.chown(files, 1000, 1000)
        if os.path.exists(cal):  # agents whose persona has no calendar get none (faulty agents, E5/E6 roles)
            shutil.copyfile(cal, f"{files}/CALENDAR.md")
            os.chown(f"{files}/CALENDAR.md", 1000, 1000)
        print(f"vm {name}: ESP fmm.json, self.json, seed/pki; CALENDAR.md")
    finally:
        im.close()


def collect(img, out):
    im = opened(img, ro=True)
    try:
        r = im.root
        os.makedirs(out, exist_ok=True)
        for src, dst in ((f"{r}/home/bia/files/CALENDAR.md", "CALENDAR.md"),
                         (f"{r}/home/bia/files/state/journal.jsonl", "journal.jsonl")):
            if os.path.exists(src):
                shutil.copyfile(src, f"{out}/{dst}")
        # any other calendar file the agent may have written instead
        for dp, ds, fs in os.walk(f"{r}/home/bia/files"):
            ds[:] = [d for d in ds if d not in ("state", "MCPs", ".cache")]
            for f in fs:
                if f.lower().startswith("calendar") and os.path.join(dp, f) != f"{r}/home/bia/files/CALENDAR.md":
                    shutil.copyfile(os.path.join(dp, f), f"{out}/other-{f}")
        print(f"collected {sorted(os.listdir(out))}")
    finally:
        im.close()


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[:1] == ["base"]:
        base(a[1])
    elif a[:1] == ["vm"]:
        vm(a[1], a[2], a[3])
    elif a[:1] == ["collect"]:
        collect(a[1], a[2])
    else:
        sys.exit(__doc__)
