#!/usr/bin/env bash
# 核心接口健康门禁：可用性 + 延迟。阈值可由环境变量覆盖。
set -uo pipefail

BASE="${HEALTH_BASE_URL:-http://127.0.0.1:8000}"
ERROR_RATIO_LIMIT="${HEALTH_ERROR_RATIO_LIMIT:-0.05}"
P95_LATENCY_MS_LIMIT="${HEALTH_P95_MS_LIMIT:-2000}"

total=0
fail=0
latencies=""
for _ in $(seq 1 10); do
  start=$(python3 -c "import time; print(int(time.time()*1000))")
  code=$(curl -sS -o /dev/null -w '%{http_code}' --max-time 10 "$BASE/health")
  end=$(python3 -c "import time; print(int(time.time()*1000))")
  total=$((total + 1))
  if [ "$code" != "200" ]; then
    fail=$((fail + 1))
  fi
  latencies="$latencies $((end - start))"
done

ratio=$(python3 -c "print($fail / $total)" 2>/dev/null || echo 1)
p95=$(printf '%s\n' $latencies | sort -n | awk '{a[NR]=$1} END {print a[int(NR*0.95)+1]}')

if python3 -c "exit(0 if $ratio <= $ERROR_RATIO_LIMIT and ${p95:-99999} <= $P95_LATENCY_MS_LIMIT else 1)"; then
  echo "HEALTH_GATE_OK ratio=$ratio p95=${p95}ms"
  exit 0
else
  echo "HEALTH_GATE_FAIL ratio=$ratio p95=${p95}ms"
  exit 1
fi
