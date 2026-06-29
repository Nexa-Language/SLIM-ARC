#!/usr/bin/env bash
# SLIM-ARC Demo 启动脚本
#
# 一键启动：llama-server (8080) + monitor.py (8001) + 打开浏览器
#
# 用法：
#   bash scripts/demo/start-demo.sh [4b|80b]
#   默认 4b（快速，适合演示 UI）
#   80b  需要预热（40GB 模型加载 + 热缓存）
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
echo "  前端:         scripts/demo/index.html"
echo "=============================================="
echo ""

# 启动 llama-server
echo "[1/3] 启动 llama-server..."
LLAMA_PID=$(SLIM_ARC_MODEL="$MODEL_NAME" \
    SLIM_ARC_MODEL_SIZE="$MODEL_SIZE" \
    SLIM_ARC_EXPERTS_TOTAL="$EXPERTS_TOTAL" \
    SLIM_ARC_EXPERTS_ACTIVE="$EXPERTS_ACTIVE" \
    SLIM_ARC_MADV=ON \
    SLIM_ARC_KV_TYPE=q4_0 \
    SLIM_ARC_FA=ON \
    SLIM_ARC_REPACK=OFF \
    SLIM_ARC_TIER="32GB warm" \
    setsid bash -c "exec $LLAMA_DIR/build/bin/llama-server \
        -m '$MODEL' -t 8 -c 8192 --host 0.0.0.0 --port 8080 \
        -fa auto -ctk q4_0 -ctv q4_0 --no-repack \
        --no-context-shift 2>&1 > $PROJECT_ROOT/logs/demo-llama-server.log" &)
echo "  PID: $LLAMA_PID (日志: logs/demo-llama-server.log)"

# 启动 monitor
echo "[2/3] 启动 monitor.py..."
MONITOR_PID=$(SLIM_ARC_MODEL="$MODEL_NAME" \
    SLIM_ARC_MODEL_SIZE="$MODEL_SIZE" \
    SLIM_ARC_EXPERTS_TOTAL="$EXPERTS_TOTAL" \
    SLIM_ARC_EXPERTS_ACTIVE="$EXPERTS_ACTIVE" \
    SLIM_ARC_MADV=ON \
    SLIM_ARC_KV_TYPE=q4_0 \
    SLIM_ARC_FA=ON \
    SLIM_ARC_REPACK=OFF \
    SLIM_ARC_TIER="32GB warm" \
    setsid python3 "$DEMO_DIR/monitor.py" 2>&1 > $PROJECT_ROOT/logs/demo-monitor.log &)
echo "  PID: $MONITOR_PID (日志: logs/demo-monitor.log)"

echo "[3/3] 等待服务就绪..."
sleep 3

# 检查 llama-server
for i in 1 2 3 4 5; do
    if curl -s http://127.0.0.1:8080/health > /dev/null 2>&1; then
        echo "  llama-server 就绪 ✓"
        break
    fi
    echo "  等待 llama-server ($i/5)..."
    sleep 5
done

# 检查 monitor
if curl -s http://127.0.0.1:8001/api/health > /dev/null 2>&1; then
    echo "  monitor 就绪 ✓"
else
    echo "  ⚠️  monitor 未就绪，检查 logs/demo-monitor.log"
fi

echo ""
echo "=============================================="
echo "  ✅ Demo 已启动！"
echo ""
echo "  打开浏览器访问: scripts/demo/index.html"
echo "  或用 python -m http.server 在 demo 目录开服务"
echo ""
echo "  停止: kill $LLAMA_PID $MONITOR_PID"
echo "=============================================="

# 尝试打开浏览器
if command -v xdg-open > /dev/null; then
    xdg-open "$DEMO_DIR/index.html" 2>/dev/null || true
elif command -v wslview > /dev/null; then
    wslview "$DEMO_DIR/index.html" 2>/dev/null || true
fi

# 保持前台，Ctrl+C 退出时清理
echo ""
echo "按 Ctrl+C 停止所有服务..."
trap "kill $LLAMA_PID $MONITOR_PID 2>/dev/null; exit" INT TERM
wait
