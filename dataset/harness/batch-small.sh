#!/bin/bash
# Run the C1 cells that fit on this Mac (≤4 agents), RUNS runs each, one at a time; skips finished runs.
cd "$(dirname "$0")"
RUNS=${RUNS:-10}
CELLS="E1-S1-N1 E1-S1-N3 E1-S2-N1 E1-S2-N3 E2-S1-N1 E2-S1-N3 E2-S2-N1 E2-S2-N3 E3-S2-N3
E4-S2-N3-facilitated E4-S2-N3-unfacilitated E5-S1-deception-prof-to-student E5-S1-deception-student-to-prof
E5-S1-intimidation E6-stalking-cover-story"
mkdir -p logs
for r in $(seq -f 'run-%02g' 1 "$RUNS"); do
  for c in $CELLS; do
    cell=$c-gpt-5-4
    [ -f "out/$cell/$r/result/verdict.json" ] && continue
    mkdir -p locks; mkdir "locks/away-$cell-$r" 2>/dev/null || continue  # taken by another queue
    echo "=== $(date +%H:%M) $cell $r"
    PORT_BASE=$(( 9440 + ${PORT_SHIFT:-0} )) python3 -u run.py "../repo/runs/$cell" "$r" > "logs/$cell-$r.log" 2>&1
    grep -h 'VERDICT\|run over' "logs/$cell-$r.log" || { echo "!!! $cell $r failed:"; tail -3 "logs/$cell-$r.log"; }
    pkill -f "qemu-system.*vm/$cell-$r/" 2>/dev/null
  done
done
echo "=== batch done"
