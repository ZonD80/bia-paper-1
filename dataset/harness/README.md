# Harness

The scripts that produced every run in `dataset/`. They boot each person, principal and the department
office as a bia in its own QEMU virtual machine and drive them over the bia web bus.

| Script | Arm |
|---|---|
| `run.py` | away: the released design (principal sends persona and task, then only an away line) |
| `persons.py` | persons, and handbook with `--handbook` (also the E6 variants in `../scenarios/`) |
| `circle.py` | full circle: principals are bias that role-play the human and answer |
| `img.py` | builds the per-VM disks from a bia release image (run inside the `bia-build` container) |
| `regrade.py` | regrades finished runs with `../code/grade.py` |
| `batch*.sh` | the queues we ran (one run at a time, ports from `PORT_BASE`) |
| `webbus.py` | the web-bus client, pinned to protocol 2 (bia 2.2.x); bia 2.3.0 moved to protocol 3 |

## What you need

- the bia repository (https://github.com/ZonD80/bia) checked out at `../../../agent` relative to the scripts,
  for `tests/e2e/e2e_vm.py` and the `bia-build` Docker image;
- a bia release image (we used 2.2.13) as `vm/rel.img`;
- `fmm.json` in the bia repository with your own model-provider key (we used DeepSeek V4.1 Flash via OpenRouter);
- QEMU with hardware acceleration (we used hvf on an Apple M3, 16 GB RAM) and Docker.

The scripts are released as they were run; paths and queue settings reflect our machine.
At list price the model cost was about $0.26 per away run and about $490 for all 1,220 runs.
