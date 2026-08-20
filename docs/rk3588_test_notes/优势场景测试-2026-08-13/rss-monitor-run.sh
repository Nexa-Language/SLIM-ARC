#!/bin/bash
# RSS 峰值监控测试驱动脚本（2026-08-13 补测用，非交互）
# 用法: rss-monitor-run.sh <日志输出路径> <ENV赋值串，可为空> <MemoryMax值或 none>
# 原理: 后台启动 llama-bench，循环采集所有 llama-bench 进程的 VmRSS/VmHWM 最大值；
#       scope 场景下同步轮询 cgroup memory.current 取峰值（5.10 内核无 memory.peak 接口，
#       memory.peak 自 kernel 5.15 引入；如存在仍会读取）。
# SLIM-ARC FIX 2026-08-13: 三处修正——
#   1) 用 pgrep -x llama-bench 精确匹配 comm，避免误匹配 systemd-run/sh 包装进程；
#   2) scope 场景直接按 unit 名定位 cgroup 路径，不再依赖进程 cgroup 探测；
#   3) 增加 cgroup memory.current 轮询峰值（CG_MEM_MAX）。
set -u

LOGFILE="$1"
ENVVARS="$2"
MEMMAX="$3"

BIN=/home/orangepi/src/llama-upstream/build/bin/llama-bench
MODEL=/home/orangepi/ssd/models/Qwen3-Next-80B-A3B-Instruct-Q4_K_M.gguf
SCOPE_NAME=""
CGROUP_DIR=""

{
  echo "===== RSS 补测 ====="
  echo "日期: $(date '+%Y-%m-%d %H:%M:%S %z')"
  echo "日志文件: $LOGFILE"
  echo "ENV: ${ENVVARS:-<none>}"
  echo "MemoryMax: $MEMMAX"
  echo "命令: $BIN -m $MODEL -p 128 -n 64 -r 1 --no-warmup"
  echo "主机: $(uname -a)"
  free -m | head -2
  echo ""
} > "$LOGFILE"

# ---- 启动被测进程 ----
if [ "$MEMMAX" != "none" ]; then
  SCOPE_NAME="rss$(date +%s)$$"
  CGROUP_DIR="/user.slice/user-1000.slice/$SCOPE_NAME.scope"
  env $ENVVARS systemd-run --user --scope --unit="$SCOPE_NAME" \
      -p MemoryMax="$MEMMAX" -p MemorySwapMax=0 \
      "$BIN" -m "$MODEL" -p 128 -n 64 -r 1 --no-warmup \
      >> "$LOGFILE" 2>&1 &
  LAUNCH_PID=$!
else
  env $ENVVARS "$BIN" -m "$MODEL" -p 128 -n 64 -r 1 --no-warmup \
      >> "$LOGFILE" 2>&1 &
  LAUNCH_PID=$!
fi

# 等待进程出现（最多 20 秒）；pgrep -x 按 comm 精确匹配，避开 systemd-run/sh 包装进程
BENCH_PID=""
for i in $(seq 1 40); do
  BENCH_PID=$(pgrep -x llama-bench | head -1 || true)
  if [ -n "$BENCH_PID" ]; then break; fi
  if ! kill -0 "$LAUNCH_PID" 2>/dev/null; then break; fi
  sleep 0.5
done

CG_CURRENT_FILE=""
if [ -n "$BENCH_PID" ]; then
  PROC_CG=$(cat "/proc/$BENCH_PID/cgroup" 2>/dev/null | head -1 | sed 's/^0:://')
  # SLIM-ARC FIX 2026-08-13: scope 实际位于 user@1000.service/app.slice/ 下，
  # 直接采用 /proc 读到的真实 cgroup 路径，避免按 unit 名猜测失败。
  if [ -n "$PROC_CG" ]; then CGROUP_DIR="$PROC_CG"; fi
  echo "[monitor] bench PID=$BENCH_PID proc_cgroup=$PROC_CG final_cgroup=$CGROUP_DIR" >> "$LOGFILE"
else
  echo "[monitor] 未能捕获到 llama-bench PID（进程可能极速退出）" >> "$LOGFILE"
fi

if [ -n "$CGROUP_DIR" ] && [ -f "/sys/fs/cgroup$CGROUP_DIR/memory.current" ]; then
  CG_CURRENT_FILE="/sys/fs/cgroup$CGROUP_DIR/memory.current"
fi

# ---- 循环采样 ----
MAX_VMRSS_KB=0
MAX_VMHWM_KB=0
MAX_CG_CURRENT_B=0
SAMPLES=0

while kill -0 "$LAUNCH_PID" 2>/dev/null; do
  for PID in $(pgrep -x llama-bench); do
    ST="/proc/$PID/status"
    [ -r "$ST" ] || continue
    VR=$(awk '/^VmRSS:/ {print $2}' "$ST" 2>/dev/null || echo 0)
    VH=$(awk '/^VmHWM:/ {print $2}' "$ST" 2>/dev/null || echo 0)
    VR=${VR:-0}; VH=${VH:-0}
    [ "$VR" -gt "$MAX_VMRSS_KB" ] 2>/dev/null && MAX_VMRSS_KB=$VR
    [ "$VH" -gt "$MAX_VMHWM_KB" ] 2>/dev/null && MAX_VMHWM_KB=$VH
  done
  if [ -n "$CG_CURRENT_FILE" ]; then
    CC=$(cat "$CG_CURRENT_FILE" 2>/dev/null || echo 0)
    CC=${CC:-0}
    [ "$CC" -gt "$MAX_CG_CURRENT_B" ] 2>/dev/null && MAX_CG_CURRENT_B=$CC
  fi
  SAMPLES=$((SAMPLES+1))
  sleep 0.5
done

wait "$LAUNCH_PID" 2>/dev/null
EXIT_CODE=$?

# ---- 进程结束后读取最终 VmHWM（内核记录的进程生命周期峰值）----
FINAL_VMHWM_KB=""
for PID in $(pgrep -x llama-bench); do
  ST="/proc/$PID/status"
  [ -r "$ST" ] || continue
  VH=$(awk '/^VmHWM:/ {print $2}' "$ST" 2>/dev/null || true)
  if [ -n "$VH" ] && [ "$VH" -gt "${FINAL_VMHWM_KB:-0}" ] 2>/dev/null; then
    FINAL_VMHWM_KB=$VH
  fi
done

# ---- cgroup 峰值 ----
CG_PEAK="N/A"
if [ -n "$CGROUP_DIR" ] && [ -f "/sys/fs/cgroup$CGROUP_DIR/memory.peak" ]; then
  CG_PEAK=$(cat "/sys/fs/cgroup$CGROUP_DIR/memory.peak" 2>/dev/null || echo N/A)
fi

{
  echo ""
  echo "===== RSS 监控结果 ====="
  echo "采样次数: $SAMPLES（间隔 0.5s）"
  echo "进程退出码: $EXIT_CODE"
  echo "轮询捕获最大 VmRSS: $((MAX_VMRSS_KB/1024)) MB ($MAX_VMRSS_KB kB)"
  echo "轮询捕获最大 VmHWM: $((MAX_VMHWM_KB/1024)) MB ($MAX_VMHWM_KB kB)"
  if [ -n "$FINAL_VMHWM_KB" ]; then
    echo "进程结束后读到的最终 VmHWM: $((FINAL_VMHWM_KB/1024)) MB ($FINAL_VMHWM_KB kB)"
  else
    echo "进程结束后读到的最终 VmHWM: 不可得（进程已退出）"
  fi
  if [ -n "$CGROUP_DIR" ]; then
    echo "cgroup 路径: /sys/fs/cgroup$CGROUP_DIR"
    echo "cgroup memory.current 轮询峰值: $((MAX_CG_CURRENT_B/1024/1024)) MB ($MAX_CG_CURRENT_B bytes)"
  fi
  echo "cgroup memory.peak: $CG_PEAK（kernel $(uname -r)$( [ "$CG_PEAK" = "N/A" ] && echo '，无 memory.peak 接口，5.15+ 才支持' ))"
  echo "结束时间: $(date '+%Y-%m-%d %H:%M:%S %z')"
} >> "$LOGFILE"

echo "DONE rc=$EXIT_CODE rss_max_mb=$((MAX_VMRSS_KB/1024)) hwm_max_mb=$((MAX_VMHWM_KB/1024)) cg_current_max_mb=$((MAX_CG_CURRENT_B/1024/1024))"
