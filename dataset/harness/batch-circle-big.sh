#!/bin/zsh
# Full-circle runs of the 6- and 8-person cells (N5: 13 bias, N7: 17 bias), one run at a time with
# smaller VMs (agents 1280M, principals and office 768M) so a run fits the 16 GB host. Skips finished runs.
# Order: run-01 of every cell, then run-02, ... so a stop leaves a balanced sample.
cd "${0:A:h}"
R=../repo/runs
CELLS=(E1-S1-N5 E1-S2-N5 E2-S1-N5 E2-S2-N5 E3-S2-N5 E4-S2-N5-facilitated E4-S2-N5-unfacilitated
       E1-S1-N7 E1-S2-N7 E2-S1-N7 E2-S2-N7 E3-S2-N7 E4-S2-N7-facilitated E4-S2-N7-unfacilitated)
pb=$(( 9440 + ${PORT_SHIFT:-0} ))
for r in $(seq -f 'run-%02g' 1 ${RUNS:-10}); do
  for c0 in $CELLS; do
    c=$c0-gpt-5-4
    [ -f out-circle/$c/$r/result/verdict.json ] && continue
    mkdir -p locks; mkdir locks/circle-$c-$r 2>/dev/null || continue
    echo "=== $(date +%H:%M) circle $c $r (ports $pb)"
    MEM=1280M WMEM=768M PORT_BASE=$pb python3 circle.py $R/$c $r > logs/circle-$c-$r.log 2>&1 || echo "!!! circle $c $r failed: $(tail -1 logs/circle-$c-$r.log)"
    grep -h VERDICT logs/circle-$c-$r.log
    rm -f vm/c-$c-$r/*.img(N) vm/c-$c-$r/efivars-*.fd(N)
  done
done
echo "circle big batch done"
