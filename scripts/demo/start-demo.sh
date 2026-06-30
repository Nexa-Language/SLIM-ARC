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
LLAMA_DIR="$PROJECT_ROOT/src/llama-upstream"
DEMO_DIR="$PROJECT_ROOT/scripts/demo"

MODEL_CHOICE="${1:-4b}"
case "$MODEL_CHOICE" in
    4b)
        MODEL="$PROJECT_ROOT/data/models/Qwen3-4B-Q4_K_M.gguf"
        MODEL_NAME="Qwen3-4B-Q4_K_M"
        MODEL_SIZE="2.4 GB"
        EXPERTS_TOTAL=0
        EXPERTS_ACTIVE=0
        ;;
    80b)
        MODEL="$PROJECT_ROOT/data/models/Qwen3-Next-80B-A3B-Instruct-IQ4_XS.gguf"
        MODEL_NAME="Qwen3-Next-80B-IQ4_XS"
        MODEL_SIZE="38 GB"
        EXPERTS_TOTAL=512
        EXPERTS_ACTIVE=10
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
export SLIM_ARC_KV_TYPE=q4_0
export SLIM_ARC_FA=ON
export SLIM_ARC_REPACK=OFF
export SLIM_ARC_TIER="32GB warm"

# 1. 启动 llama-server（后台，日志到文件）
echo "[1/3] 启动 llama-server..."
nohup "$LLAMA_DIR/build/bin/llama-server" \
    -m "$MODEL" -t 8 -c 8192 --host 0.0.0.0 --port 8080 \
    -fa auto -ctk q4_0 -ctv q4_0 --no-repack --no-context-shift \
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
for i in $(seq 1 $MAX_WAIT); do
    if curl -s http://127.0.0.1:8080/health > /dev/null 2>&1; then
        echo "  llama-server 就绪 ✓"
        break
    fi
    # 检查进程是否还活着
    if ! kill -0 $LLAMA_PID 2>/dev/null; then
        echo "  ⚠️ llama-server 进程已退出！查看 logs/demo-llama-server.log"
        tail -5 "$PROJECT_ROOT/logs/demo-llama-server.log" 2>/dev/null
        exit 1
    fi
    echo "  等待 llama-server ($i/$MAX_WAIT)..."
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
