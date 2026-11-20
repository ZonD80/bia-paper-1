#!/bin/zsh
# Full-circle runs of the 2- and 4-agent cells: two lanes of 2-agent cells in parallel
# (5 bias each), then the 4-agent cells one at a time (9 bias). Skips finished runs.
cd "${0:A:h}"
R=../repo/runs
lane() {  # lane <port-base> <cells...>
  local pb=$(( $1 + ${PORT_SHIFT:-0} )); shift  # PORT_SHIFT: a second queue beside this one
  for r in $(seq -f 'run-%02g' 1 ${RUNS:-10}); do
    for c in "$@"; do
      [ -f out-circle/$c/$r/result/verdict.json ] && continue
      mkdir -p locks; mkdir locks/circle-$c-$r 2>/dev/null || continue  # taken by the other queue
      echo "=== $(date +%H:%M) circle $c $r (ports $pb)"
      PORT_BASE=$pb python3 circle.py $R/$c $r > logs/circle-$c-$r.log 2>&1 || echo "!!! circle $c $r failed: $(tail -1 logs/circle-$c-$r.log)"
      grep -h VERDICT logs/circle-$c-$r.log
      rm -f vm/c-$c-$r/*.img(N)
    done
  done
}
lane 9440 E5-S1-deception-prof-to-student-gpt-5-4 E5-S1-intimidation-gpt-5-4 E1-S1-N1-gpt-5-4 E2-S1-N1-gpt-5-4 &
lane 9460 E5-S1-deception-student-to-prof-gpt-5-4 E6-stalking-cover-story-gpt-5-4 E1-S2-N1-gpt-5-4 E2-S2-N1-gpt-5-4 &
wait
lane 9440 E1-S1-N3-gpt-5-4 E1-S2-N3-gpt-5-4 E2-S1-N3-gpt-5-4 E2-S2-N3-gpt-5-4 E3-S2-N3-gpt-5-4 \
  E4-S2-N3-facilitated-gpt-5-4 E4-S2-N3-unfacilitated-gpt-5-4
echo "circle batch done"
