#!/bin/bash
# The cells that need 6-8 bias: 1.5 GB per VM (user, 2026-11-16). N5 first, then N7. (E6 collusion is graded by coverage, not implemented.)
cd "$(dirname "$0")"
./batch-small.sh  # first fill any small-cell run that failed to start
RUNS=${RUNS:-10}
mkdir -p logs
for group in "E1-S1-N5 E1-S2-N5 E2-S1-N5 E2-S2-N5 E3-S2-N5 E4-S2-N5-facilitated E4-S2-N5-unfacilitated" \
             "E1-S1-N7 E1-S2-N7 E2-S1-N7 E2-S2-N7 E3-S2-N7 E4-S2-N7-facilitated E4-S2-N7-unfacilitated"; do
  for r in $(seq -f 'run-%02g' 1 "$RUNS"); do
    for c in $group; do
      cell=$c-gpt-5-4
      [ -f "out/$cell/$r/result/verdict.json" ] && continue
      mkdir -p locks; mkdir "locks/away-$cell-$r" 2>/dev/null || continue  # taken by another queue
      echo "=== $(date +%H:%M) $cell $r"
      MEM=1536M CPUS=1 PORT_BASE=$(( 9440 + ${PORT_SHIFT:-0} )) python3 -u run.py "../repo/runs/$cell" "$r" > "logs/$cell-$r.log" 2>&1
      grep -h 'VERDICT\|run over' "logs/$cell-$r.log" || { echo "!!! $cell $r failed:"; tail -3 "logs/$cell-$r.log"; }
      pkill -f "qemu-system.*vm/$cell-$r/" 2>/dev/null
    done
  done
done
echo "=== big batch done"
