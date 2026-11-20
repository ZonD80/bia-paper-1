#!/bin/zsh
# "Handbook" runs: persons.py --handbook (everyone knows the department handbook; one student may be new).
# 2-person cells in three lanes (3 bias each), 4-person cells in two lanes (5 bias),
# then 6- and 8-person cells one at a time.
cd "${0:A:h}"
R=../repo/runs
lane() {  # lane <port-base> <cells...>
  local pb=$1; shift
  for r in $(seq -f 'run-%02g' 1 ${RUNS:-10}); do
    for c in "$@"; do
      [ -f out-handbook/$c/$r/result/verdict.json ] && continue
      echo "=== $(date +%H:%M) handbook $c $r (ports $pb)"
      local src=$R/$c; [ -d scenarios/$c ] && src=scenarios/$c
      PORT_BASE=$pb python3 persons.py $src $r --handbook > logs/handbook-$c-$r.log 2>&1 || echo "!!! handbook $c $r failed: $(tail -1 logs/handbook-$c-$r.log)"
      grep -h VERDICT logs/handbook-$c-$r.log
      rm -f vm/h-$c-$r/*.img(N)
    done
  done
}
lane 9440 E5-S1-deception-student-to-prof-gpt-5-4 E5-S1-intimidation-gpt-5-4 E1-S1-N1-gpt-5-4 &
lane 9460 E5-S1-deception-prof-to-student-gpt-5-4 E1-S2-N1-gpt-5-4 E2-S1-N1-gpt-5-4 &
lane 9480 E6-stalking-cover-story-gpt-5-4 E6-stalking-cover-story-newcomer-gpt-5-4 E6-stalking-boundary-gpt-5-4 E2-S2-N1-gpt-5-4 &
wait
MEM=1280M lane 9440 E1-S1-N3-gpt-5-4 E2-S1-N3-gpt-5-4 E3-S2-N3-gpt-5-4 E4-S2-N3-unfacilitated-gpt-5-4 &
MEM=1280M lane 9460 E6-stalking-boundary-hearsay-gpt-5-4 E1-S2-N3-gpt-5-4 E2-S2-N3-gpt-5-4 E4-S2-N3-facilitated-gpt-5-4 &
wait
MEM=1280M lane 9440 E1-S1-N5-gpt-5-4 E1-S2-N5-gpt-5-4 E2-S1-N5-gpt-5-4 E2-S2-N5-gpt-5-4 E3-S2-N5-gpt-5-4 \
  E4-S2-N5-facilitated-gpt-5-4 E4-S2-N5-unfacilitated-gpt-5-4 \
  E1-S1-N7-gpt-5-4 E1-S2-N7-gpt-5-4 E2-S1-N7-gpt-5-4 E2-S2-N7-gpt-5-4 E3-S2-N7-gpt-5-4 \
  E4-S2-N7-facilitated-gpt-5-4 E4-S2-N7-unfacilitated-gpt-5-4
echo "handbook batch done"
