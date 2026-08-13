#!/usr/bin/env bash
# phase-probe.sh — llama-cli 阶段级瓶颈测量（pp/tg 计时 + 缺页 + I/O + CPU）
#
# 用途：精确区分「算力瓶颈」与「I/O 瓶颈」，采样 /proc 统计。
# 三线通用：纯 Linux /proc，无 sudo，无 GPU，POSIX shell + awk。
#
# 用法：
#   OUT=logs/phase-probe/xxx.csv bash scripts/profile/phase-probe.sh \
#       [llama-cli 参数...]
#   例：
#   OUT=/tmp/probe.csv bash scripts/profile/phase-probe.sh \
#       -m data/models/Qwen3-Next-80B-A3B-Instruct-Q4_K_M.gguf \
#       -t 4 -c 256 -p "你好" -n 32 --single-turn < /dev/null
#   环境变量（透传给 llama-cli）：SLIM_ARC_EXPERT_CONF=1 等
#
# 输出：
#   $OUT.csv      每秒采样行：ts,utime_cs,stime_cs,minflt,majflt,rchar,read_bytes,VmRSS_kB
#   $OUT.summary  汇总：总时长、Δminflt、Δmajflt、Δread_bytes、CPU 时间占比、majflt/s
#
set -u
INTERVAL="${PHASE_PROBE_INTERVAL:-1}"
OUT="${OUT:-/tmp/phase-probe.csv}"
CLI="${LLAMA_CLI:-src/llama-upstream/build/bin/llama-cli}"

if [ ! -x "$CLI" ]; then
    echo "ERROR: llama-cli not found at $CLI" >&2
    exit 1
fi

CSV="${OUT}.csv"
SUMMARY="${OUT}.summary"
STDERR="${OUT}.stderr"
mkdir -p "$(dirname "$CSV")"

echo "ts_s,utime_cs,stime_cs,minflt,majflt,rchar,read_bytes,VmRSS_kB" > "$CSV"

START=$(date +%s.%N)
"$CLI" "$@" > "${OUT}.stdout" 2> "$STDERR" < /dev/null &
PID=$!

FIRST=""
while kill -0 "$PID" 2>/dev/null; do
    NOW=$(date +%s.%N)
    ELAPSED=$(awk -v a="$START" -v b="$NOW" 'BEGIN{printf "%.1f", b-a}')
    if [ -r "/proc/$PID/stat" ]; then
        # stat fields: 10=minflt 12=majflt 14=utime 15=stime (unit: clock ticks / USER_HZ)
        STATS=$(awk '{print $10, $12, $14, $15}' "/proc/$PID/stat" 2>/dev/null)
        MINFLT=$(echo "$STATS" | awk '{print $1}')
        MAJFLT=$(echo "$STATS" | awk '{print $2}')
        UTIME=$(echo "$STATS" | awk '{print $3}')
        STIME=$(echo "$STATS" | awk '{print $4}')
        IOCHAR=$(awk '/^rchar:/{r=$2} /^read_bytes:/{rb=$2} END{print r, rb}' "/proc/$PID/io" 2>/dev/null)
        RCHAR=$(echo "$IOCHAR" | awk '{print $1}')
        RBYTES=$(echo "$IOCHAR" | awk '{print $2}')
        RSS=$(awk '/^VmRSS:/{print $2}' "/proc/$PID/status" 2>/dev/null)
        [ -z "${FIRST}" ] && FIRST="$ELAPSED $UTIME $STIME $MINFLT $MAJFLT ${RCHAR:-0} ${RBYTES:-0}"
        echo "$ELAPSED,${UTIME:-0},${STIME:-0},${MINFLT:-0},${MAJFLT:-0},${RCHAR:-0},${RBYTES:-0},${RSS:-0}" >> "$CSV"
    fi
    sleep "$INTERVAL"
done
wait "$PID"
EXIT=$?
END=$(date +%s.%N)
TOTAL=$(awk -v a="$START" -v b="$END" 'BEGIN{printf "%.2f", b-a}')

LAST=$(tail -1 "$CSV" | tr ',' ' ')
awk -v total="$TOTAL" -v first="$FIRST" -v last="$LAST" -v exitcode="$EXIT" '
BEGIN {
    split(first, f, " "); split(last, l, " ");
    dut = l[2]-f[2]; dst = l[3]-f[3];
    dmin = l[4]-f[4]; dmaj = l[5]-f[5];
    drchar = l[6]-f[6]; drbytes = l[7]-f[7];
    hz = 100;
    cpu_s = (dut+dst)/hz;
    printf "exit_code=%s\n", exitcode;
    printf "wall_s=%.2f\n", total;
    printf "cpu_time_s=%.2f (utime=%.2f stime=%.2f)\n", cpu_s, dut/hz, dst/hz;
    printf "cpu_util_pct=%.1f\n", (total>0)? cpu_s/total*100 : 0;
    printf "delta_minflt=%d (%.1f/s)\n", dmin, dmin/total;
    printf "delta_majflt=%d (%.3f/s)\n", dmaj, dmaj/total;
    printf "delta_rchar=%d (%.1f MiB, %.2f MiB/s)\n", drchar, drchar/1048576, drchar/1048576/total;
    printf "delta_read_bytes=%d (%.1f MiB, %.2f MiB/s)\n", drbytes, drbytes/1048576, drbytes/1048576/total;
}' > "$SUMMARY"

echo "=== phase-probe summary ($OUT) ==="
cat "$SUMMARY"
echo "=== llama-cli timings ==="
grep -E "^\s*(llama_)?(load|pp|tg|.*tok/s)" "$STDERR" | tail -12
exit $EXIT
