#!/usr/bin/env bash
# SLIM-ARC Demo 启动脚本
#
# 一键启动：llama-server (8080) + monitor.py (8001) + 前端 http (8090)
#
# 用法：
#   bash scripts/demo/start-demo.sh [4b|80b]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
# SLIM-ARC FIX 2026-08-10: llama-upstream 是独立 git clone，实际位于仓库外
# (PROJECT_ROOT/../src/llama-upstream)，此处自动探测两种布局，避免路径不存在
LLAMA_DIR="$PROJECT_ROOT/src/llama-upstream"
if [ ! -x "$LLAMA_DIR/build/bin/llama-server" ] && [ -x "$(dirname "$PROJECT_ROOT")/src/llama-upstream/build/bin/llama-server" ]; then
    LLAMA_DIR="$(dirname "$PROJECT_ROOT")/src/llama-upstream"
fi
# SLIM-ARC FIX 2026-08-12: 项目迁移到 data/ 后，llama-server 二进制内嵌 RUNPATH
# 仍指向旧路径（/home/yituodabian/SLIM-ARC/...），运行时找不到 libllama-server-impl.so。
# 用 LD_LIBRARY_PATH 显式指向 build/bin 解决（不修改二进制，不动 SLIM-ARC 核心）。
export LD_LIBRARY_PATH="$LLAMA_DIR/build/bin${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
DEMO_DIR="$PROJECT_ROOT/scripts/demo"

MODEL_CHOICE="${1:-4b}"
case "$MODEL_CHOICE" in
    4b)
        MODEL="$PROJECT_ROOT/data/models/Qwen3-4B-Q4_K_M.gguf"
        MODEL_NAME="Qwen3-4B-Q4_K_M"
        MODEL_SIZE="2.4 GB"
        EXPERTS_TOTAL=0
        EXPERTS_ACTIVE=0
        MODEL_THREADS=4
        MODEL_CTX=2048
        MODEL_PARALLEL=1
        ;;
    80b)
        # SLIM-ARC FIX 2026-08-12: 修正 80B 模型文件名。
        # 迁移后实际文件为 Qwen3-Next-80B-A3B-Instruct-Q4_K_M.gguf（约 46GB），
        # 原引用 Qwen3-Next-80B-A3B-Instruct-IQ4_XS.gguf（38GB）已不存在。
        MODEL="$PROJECT_ROOT/data/models/Qwen3-Next-80B-A3B-Instruct-Q4_K_M.gguf"
        MODEL_NAME="Qwen3-Next-80B-Q4_K_M"
        MODEL_SIZE="46 GB"
        EXPERTS_TOTAL=512
        EXPERTS_ACTIVE=10
        # SLIM-ARC FIX 2026-08-12: 80B MoE 在 4GB 端侧设备上 KV cache 需更小。
        # 原统一参数 -t 4 -c 2048 -np 1 仍可能吃满内存，改用更小 context，
        # 尽量给 mmap+MADV_RANDOM 的按需加载留出空间（4GB 上 OOM 仍属预期）。
        # SLIM-ARC FIX 2026-08-12: 修复 8GB 设备（RK3588，7.8GiB RAM，swap 未启用
        # SwapTotal=0）80B 启动 OOM：原 -c 0 会按模型训练上下文 n_ctx_train=262144
        # （256K）预分配 KV cache ~1.5GB，匿名内存升至 5.8GB 超过物理可用被 OOM
        # Killed（2026-08-12 实测）。改用 16384：KV cache 仅 96MiB，8GB 设备安全，
        # 可覆盖 15000 token 长输出 + ~1K prompt。如需更大上下文（如 32768，KV
        # 192MiB 仍安全）可另行调整，但默认推荐 16384。
        MODEL_THREADS=4
        MODEL_CTX=16384
        MODEL_PARALLEL=1
        ;;
    *)
        echo "用法: $0 [4b|80b]"
        exit 1
        ;;
esac

echo "=============================================="
echo "  SLIM-ARC Live Demo"
echo "  模型: $MODEL_NAME ($MODEL_SIZE)"
echo "  llama-server: http://127.0.0.1:8080"
echo "  monitor:      http://127.0.0.1:8001"
echo "  前端:         http://127.0.0.1:8090"
echo "=============================================="
echo ""

# 确保日志目录存在
mkdir -p "$PROJECT_ROOT/logs"

# 启动前清理残留进程（避免端口冲突）
# 只清理明确的服务进程，不碰脚本本身
echo "[0/3] 清理残留进程..."
PIDS_TO_KILL=$(pgrep -f "llama-server|scripts/demo/monitor\.py|http\.server 8090" 2>/dev/null || true)
if [ -n "$PIDS_TO_KILL" ]; then
    echo "  发现残留进程: $PIDS_TO_KILL"
    # 排除当前脚本及其父进程
    SELF_PID=$$
    for p in $PIDS_TO_KILL; do
        if [ "$p" != "$SELF_PID" ] && [ "$p" != "$PPID" ]; then
            kill "$p" 2>/dev/null || true
        fi
    done
    sleep 2
    # 强制杀还在的
    REMAIN=$(pgrep -f "llama-server|scripts/demo/monitor\.py|http\.server 8090" 2>/dev/null || true)
    if [ -n "$REMAIN" ]; then
        for p in $REMAIN; do
            if [ "$p" != "$SELF_PID" ] && [ "$p" != "$PPID" ]; then
                kill -9 "$p" 2>/dev/null || true
            fi
        done
        sleep 1
    fi
    echo "  已清理"
else
    echo "  无残留"
fi
# 确保端口空闲
sleep 1

# 导出环境变量给 monitor
export SLIM_ARC_MODEL="$MODEL_NAME"
export SLIM_ARC_MODEL_SIZE="$MODEL_SIZE"
export SLIM_ARC_EXPERTS_TOTAL="$EXPERTS_TOTAL"
export SLIM_ARC_EXPERTS_ACTIVE="$EXPERTS_ACTIVE"
export SLIM_ARC_MADV=ON
# SLIM-ARC FIX 2026-08-12: KV 量化参数化（SLIM_ARC_KV_TYPE，实验用）
# 默认 q4_0；SLIM_ARC_KV_TYPE=f16 时切换为 f16（对照实验用），
# 不改变默认行为，也不改动 llama.cpp 核心机制。
export SLIM_ARC_KV_TYPE="${SLIM_ARC_KV_TYPE:-q4_0}"
export SLIM_ARC_FA=ON
export SLIM_ARC_REPACK=OFF
export SLIM_ARC_TIER="32GB warm"

# 1. 启动 llama-server（后台，日志到文件）
echo "[1/3] 启动 llama-server..."
# SLIM-ARC FIX 2026-08-12: 参数适配 4GB 端侧设备（yituodabian/RK3588 实测）。
# 原 -t 8 -c 8192（隐含 4 slots）在 4GB/4 核设备上导致 KV cache 内存爆掉、
# 疯狂 swap、推理 <0.3 t/s。调整为 -t 4（4 核）、-c 2048、-np 1 显著降低内存。
# 保留 mmap/MADV 相关开关（--no-repack 等），不破坏 SLIM-ARC 优化链。
# 可通过环境变量 SLIM_ARC_CTX 覆盖 context（如 SLIM_ARC_CTX=8192 切回大上下文）。
# SLIM-ARC FIX 2026-08-12: KV 量化参数化（SLIM_ARC_KV_TYPE，实验用），
# 由上方导出的 $SLIM_ARC_KV_TYPE 决定，默认 q4_0，f16 时用 f16。
nohup "$LLAMA_DIR/build/bin/llama-server" \
    -m "$MODEL" -t "${MODEL_THREADS:-4}" -c "${SLIM_ARC_CTX:-$MODEL_CTX}" -np "${MODEL_PARALLEL:-1}" \
    --host 0.0.0.0 --port 8080 \
    -fa auto -ctk "${SLIM_ARC_KV_TYPE:-q4_0}" -ctv "${SLIM_ARC_KV_TYPE:-q4_0}" --no-repack --no-context-shift \
    > "$PROJECT_ROOT/logs/demo-llama-server.log" 2>&1 &
LLAMA_PID=$!
echo "  PID: $LLAMA_PID"

# 2. 启动 monitor（后台）
echo "[2/3] 启动 monitor.py..."
nohup python3 "$DEMO_DIR/monitor.py" \
    > "$PROJECT_ROOT/logs/demo-monitor.log" 2>&1 &
MONITOR_PID=$!
echo "  PID: $MONITOR_PID"

# 3. 启动前端 http（后台）
echo "[3/3] 启动前端 http (8090)..."
nohup python3 -m http.server 8090 --directory "$DEMO_DIR" \
    > "$PROJECT_ROOT/logs/demo-http.log" 2>&1 &
HTTP_PID=$!
echo "  PID: $HTTP_PID"

echo ""
echo "等待服务就绪..."
# 80B 模型加载需要更久（mmap 38GB）
MAX_WAIT=8
if [ "$MODEL_CHOICE" = "80b" ]; then
    MAX_WAIT=36  # 36 * 5s = 180s = 3 分钟
fi
# 检查 llama-server
# SLIM-ARC FIX 2026-08-12: 就绪检测必须检查 HTTP 200 状态码。
# 原实现 `curl -s .../health` 对 HTTP 503（模型仍在加载）仍返回退出码 0，
# 会把 503 误判为就绪，导致 UI 在 server 未加载完成时就交互并收到 503。
for i in $(seq 1 $MAX_WAIT); do
    code=$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8080/health 2>/dev/null || echo 000)
    if [ "$code" = "200" ]; then
        echo "  llama-server 就绪 ✓ (HTTP 200)"
        break
    fi
    # 检查进程是否还活着
    if ! kill -0 $LLAMA_PID 2>/dev/null; then
        echo "  ⚠️ llama-server 进程已退出！查看 logs/demo-llama-server.log"
        tail -5 "$PROJECT_ROOT/logs/demo-llama-server.log" 2>/dev/null
        exit 1
    fi
    echo "  等待 llama-server ($i/$MAX_WAIT) 当前 HTTP $code ..."
    sleep 5
done

# 检查 monitor
if curl -s http://127.0.0.1:8001/api/health > /dev/null 2>&1; then
    echo "  monitor 就绪 ✓"
else
    echo "  ⚠️  monitor 未就绪，检查 logs/demo-monitor.log"
fi

# 检查前端
if curl -s http://127.0.0.1:8090/index.html > /dev/null 2>&1; then
    echo "  前端就绪 ✓"
fi

echo ""
echo "=============================================="
echo "  ✅ Demo 已启动！"
echo ""
echo "  打开浏览器: http://127.0.0.1:8090/index.html"
echo ""
echo "  停止: kill $LLAMA_PID $MONITOR_PID $HTTP_PID"
echo "  或: ps aux | grep -E 'llama-server|monitor.py|http.server' | grep -v grep | awk '{print \$2}' | xargs -r kill"
echo "=============================================="
echo ""

# 尝试打开浏览器
if command -v xdg-open > /dev/null; then
    xdg-open http://127.0.0.1:8090/index.html 2>/dev/null || true
elif command -v wslview > /dev/null; then
    wslview http://127.0.0.1:8090/index.html 2>/dev/null || true
fi

# 前台保持，显示 llama-server 日志
echo "服务运行中。Ctrl+C 停止所有服务。"
echo "（实时日志: tail -f logs/demo-llama-server.log）"
echo ""
trap "kill $LLAMA_PID $MONITOR_PID $HTTP_PID 2>/dev/null; exit 0" INT TERM
wait
