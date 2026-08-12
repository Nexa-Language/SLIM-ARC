#!/usr/bin/env python3
"""
SLIM-ARC Demo Monitor Backend

提供 /api/monitor 端点，返回实时系统监控数据：
- RAM 用量（total/available/cached）
- 模型配置（专家数、MADV 状态、KV 量化、FlashAttention）
- 模拟的 tokens/s（从 llama-server /metrics 读取，或静态展示）

通过环境变量配置展示参数：
- SLIM_ARC_MODEL: 模型名（显示用）
- SLIM_ARC_MODEL_SIZE: 模型大小
- SLIM_ARC_EXPERTS_TOTAL: 总专家数（如 512）
- SLIM_ARC_EXPERTS_ACTIVE: 激活专家数（如 10）
- SLIM_ARC_MADV: "ON" / "OFF"
- SLIM_ARC_KV_TYPE: "q4_0" / "f16"
- SLIM_ARC_FA: "ON" / "OFF"
- SLIM_ARC_REPACK: "OFF" / "ON"
- LLAMA_SERVER_URL: llama-server 地址（用于读取 /metrics 获取真实 t/s），默认 http://127.0.0.1:8080
"""
import os
import time
import threading
import socket
import subprocess
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import uvicorn
import requests

app = FastAPI(title="SLIM-ARC Monitor")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 配置（从环境变量读取）
CONFIG = {
    "model": os.environ.get("SLIM_ARC_MODEL", "Qwen3-4B-Q4_K_M"),
    "model_size": os.environ.get("SLIM_ARC_MODEL_SIZE", "2.4 GB"),
    "experts_total": int(os.environ.get("SLIM_ARC_EXPERTS_TOTAL", "0")),
    "experts_active": int(os.environ.get("SLIM_ARC_EXPERTS_ACTIVE", "0")),
    "madv": os.environ.get("SLIM_ARC_MADV", "ON"),
    "kv_type": os.environ.get("SLIM_ARC_KV_TYPE", "q4_0"),
    "fa": os.environ.get("SLIM_ARC_FA", "ON"),
    "repack": os.environ.get("SLIM_ARC_REPACK", "OFF"),
    "tier": os.environ.get("SLIM_ARC_TIER", "32GB warm"),
}

LLAMA_SERVER = os.environ.get("LLAMA_SERVER_URL", "http://127.0.0.1:8080")

# ============================================================
# SLIM-ARC FEATURE 2026-08-12: UI 模型热切换（4B <-> 80B）
# ------------------------------------------------------------
# 说明：
#   - POST /api/switch-model 接收 {"model": "4b"|"80b"}
#   - 后端停止当前 llama-server，按模型配置 nohup 重启新的 llama-server
#   - GET /api/switch-status 报告切换进度/错误，供前端轮询
#   - 安全：仅允许本机（回环 + 本机全部网卡 IP）发起切换
#   - monitor.py 自身进程不会被 pkill "llama-server" 波及（命令行不含该串）
# ============================================================

# --- 路径探测（与 start-demo.sh 逻辑保持一致） ---
DEMO_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = DEMO_DIR.parent.parent
LLAMA_DIR = PROJECT_ROOT / "src" / "llama-upstream"
if not (LLAMA_DIR / "build" / "bin" / "llama-server").exists():
    # 兼容 llama-upstream 位于仓库外的布局（PROJECT_ROOT/../src/llama-upstream）
    LLAMA_DIR = PROJECT_ROOT.parent / "src" / "llama-upstream"
LLAMA_SERVER_BIN = LLAMA_DIR / "build" / "bin" / "llama-server"
MODELS_DIR = PROJECT_ROOT / "data" / "models"
LLAMA_LOG = PROJECT_ROOT / "logs" / "demo-llama-server.log"

# --- 模型配置（与 start-demo.sh 保持一致） ---
MODEL_CONFIGS = {
    "4b": {
        "file": "Qwen3-4B-Q4_K_M.gguf",
        "name": "Qwen3-4B-Q4_K_M",
        "size": "2.4 GB",
        "experts_total": 0,
        "experts_active": 0,
        "threads": 4,
        "ctx": 2048,
        "n_parallel": 1,
    },
    "80b": {
        # SLIM-ARC FIX 2026-08-12: 迁移后 80B 实际文件为 Q4_K_M（约 46GB），
        # 原 IQ4_XS（38GB）已不存在。
        "file": "Qwen3-Next-80B-A3B-Instruct-Q4_K_M.gguf",
        "name": "Qwen3-Next-80B-Q4_K_M",
        "size": "46 GB",
        "experts_total": 512,
        "experts_active": 10,
        # 80B MoE 在 4GB 设备上 KV cache 需更小（-c 1024），
        # 尽量把内存留给 mmap+MADV_RANDOM 的按需加载。
        "threads": 4,
        "ctx": 1024,
        "n_parallel": 1,
    },
}

# --- 切换状态（线程安全） ---
SWITCH_STATE = {
    "switching": False,       # 是否正在切换
    "target_model": None,     # 目标模型 key（"4b"/"80b"）
    "current_model": "4b",    # 当前生效模型 key
    "started_at": None,       # 切换开始时间戳
    "finished_at": None,      # 切换结束时间戳
    "llama_ready": False,     # llama-server 是否就绪（HTTP 200）
    "error": None,            # 最近一次错误信息
    "llama_pid": None,        # 新启动的 llama-server PID
}
switch_lock = threading.Lock()
# 根据环境变量推断初始模型（start-demo.sh 会导出 SLIM_ARC_MODEL）
_initial_env_model = os.environ.get("SLIM_ARC_MODEL", "Qwen3-4B-Q4_K_M")
SWITCH_STATE["current_model"] = "80b" if "80B" in _initial_env_model else "4b"

# 缓存的 t/s 历史（最近 60 个点）
tokens_history: list[dict] = []
history_lock = threading.Lock()
last_update = 0.0
last_tokens = 0


def read_meminfo() -> dict:
    """读取 /proc/meminfo"""
    info = {}
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                parts = line.split()
                if len(parts) >= 2:
                    key = parts[0].rstrip(":")
                    val = int(parts[1])  # kB
                    info[key] = val
    except Exception:
        pass
    total = info.get("MemTotal", 0) * 1024
    avail = info.get("MemAvailable", 0) * 1024
    cached = info.get("Cached", 0) * 1024
    used = total - avail
    return {
        "total": total,
        "available": avail,
        "used": used,
        "cached": cached,
        "used_gb": round(used / 1e9, 2),
        "available_gb": round(avail / 1e9, 2),
        "cached_gb": round(cached / 1e9, 2),
        "total_gb": round(total / 1e9, 2),
    }


def read_cgroup_memory() -> dict:
    """读取 cgroup memory.current（如果在 cgroup 内）"""
    cg_path = Path("/sys/fs/cgroup/memory.current")
    if cg_path.exists():
        try:
            current = int(cg_path.read_text().strip())
            max_path = Path("/sys/fs/cgroup/memory.max")
            max_val = int(max_path.read_text().strip()) if max_path.exists() else 0
            return {
                "current": current,
                "current_gb": round(current / 1e9, 2),
                "max": max_val,
                "max_gb": round(max_val / 1e9, 2) if max_val > 0 else 0,
            }
        except Exception:
            pass
    return None


def fetch_llama_metrics() -> dict:
    """从 llama-server /slots 读取推理状态"""
    global last_update, last_tokens, tokens_history
    try:
        r = requests.get(f"{LLAMA_SERVER}/slots", timeout=2)
        if r.status_code != 200:
            return {}
        slots = r.json()
        active_slot = None
        max_decoded = 0
        for s in slots:
            if s.get("is_processing"):
                active_slot = s
                break
            for nt in s.get("next_token", []):
                if nt.get("n_decoded", 0) > max_decoded:
                    max_decoded = nt["n_decoded"]
                    active_slot = s
        if not active_slot:
            return {"slots": len(slots), "active": False}
        total_decoded = 0
        for nt in active_slot.get("next_token", []):
            total_decoded += nt.get("n_decoded", 0)
        result = {
            "slots": len(slots),
            "active": True,
            "n_decoded": total_decoded,
            "n_prompt_tokens": active_slot.get("n_prompt_tokens", 0),
        }
        now = time.time()
        if total_decoded > 0 and last_tokens > 0 and now > last_update:
            dt = now - last_update
            dtokens = total_decoded - last_tokens
            if dt > 0 and dtokens > 0:
                tps = dtokens / dt
                with history_lock:
                    tokens_history.append({"t": now, "tps": round(tps, 2)})
                    if len(tokens_history) > 60:
                        tokens_history.pop(0)
        last_update = now
        last_tokens = total_decoded
        return result
    except Exception as e:
        return {"error": str(e)}


@app.get("/api/monitor")
def monitor():
    """返回完整监控数据"""
    mem = read_meminfo()
    cg = read_cgroup_memory()
    metrics = fetch_llama_metrics()
    with history_lock:
        history = list(tokens_history)
    return {
        "config": CONFIG,
        "memory": mem,
        "cgroup": cg,
        "metrics": {
            "n_decoded": metrics.get("n_decoded", 0),
            "n_prompt_tokens": metrics.get("n_prompt_tokens", 0),
            "active": metrics.get("active", False),
            "slots": metrics.get("slots", 0),
        },
        "tps_history": history,
        "timestamp": time.time(),
    }


@app.get("/api/health")
def health():
    """健康检查（附切换状态，供前端在切换过程中统一轮询）"""
    with switch_lock:
        return {
            "status": "ok",
            "config": CONFIG,
            "switch": {
                "switching": SWITCH_STATE["switching"],
                "target_model": SWITCH_STATE["target_model"],
                "current_model": SWITCH_STATE["current_model"],
                "llama_ready": SWITCH_STATE["llama_ready"],
                "error": SWITCH_STATE["error"],
            },
        }


# ============================================================
# SLIM-ARC FEATURE 2026-08-12: 模型切换实现
# ============================================================

def _local_ips() -> set:
    """收集本机所有网卡 IPv4（用于切换接口的来源校验）"""
    ips = set()
    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None, socket.AF_INET):
            ips.add(info[4][0])
    except Exception:
        pass
    return ips


def is_local_request(request: Request) -> bool:
    """安全校验：仅允许本机（回环 + 本机网卡 IP）发起模型切换"""
    host = request.client.host if request.client else ""
    if host in ("127.0.0.1", "::1", "localhost"):
        return True
    return host in _local_ips()


def _read_llama_log_tail(n: int = 15) -> str:
    """读取 llama-server 日志尾部，供报错时给出可读信息"""
    try:
        if not LLAMA_LOG.exists():
            return "(无日志文件)"
        lines = LLAMA_LOG.read_text(errors="replace").strip().splitlines()
        return "\n".join(lines[-n:]) if lines else "(空日志)"
    except Exception as e:
        return f"(读取日志失败: {e})"


# SLIM-ARC FIX 2026-08-12: 快速失败关键字。
# 4GB 设备加载 80B（46GB）时，llama.cpp 可能先打印 "failed to fit params ...
# abort" 后进程卡在 swap 风暴中不退出，导致需等满 timeout。
# 检测到这些关键字即终止进程并提前判定失败，让 UI 快速显示错误。
_LLAMA_FAIL_KEYWORDS = (
    "failed to fit params",
    "failed to allocate",
    "error while loading",
    "not enough memory",
    "out of memory",
    "fatal error",
)


def _wait_llama_ready(proc, timeout: float = 600.0, interval: float = 3.0) -> bool:
    """轮询 llama-server /health 直到 HTTP 200，或进程退出/日志报错/超时"""
    deadline = time.time() + timeout
    start_size = 0
    if LLAMA_LOG.exists():
        try:
            start_size = LLAMA_LOG.stat().st_size
        except Exception:
            pass
    while time.time() < deadline:
        if proc.poll() is not None:
            # 进程已退出（4GB 设备上 80B 因内存不足 OOM 会走到这里，属预期）
            return False
        try:
            r = requests.get(f"{LLAMA_SERVER}/health", timeout=2)
            if r.status_code == 200:
                return True
        except Exception:
            pass
        # 仅检查本次启动后新增的日志，命中失败关键字即快速失败
        if LLAMA_LOG.exists():
            try:
                size = LLAMA_LOG.stat().st_size
                if size > start_size:
                    with open(LLAMA_LOG, "r", errors="replace") as f:
                        f.seek(start_size)
                        new_log = f.read()
                    for kw in _LLAMA_FAIL_KEYWORDS:
                        if kw.lower() in new_log.lower():
                            try:
                                proc.kill()  # 终止卡住进程，结束 swap 风暴
                            except Exception:
                                pass
                            return False
            except Exception:
                pass
        time.sleep(interval)
    return False


def _build_llama_cmd(cfg: dict) -> list:
    """构造 llama-server 启动命令（与 start-demo.sh 参数保持一致）"""
    return [
        str(LLAMA_SERVER_BIN),
        "-m", str(MODELS_DIR / cfg["file"]),
        "-t", str(cfg["threads"]),
        "-c", str(cfg["ctx"]),
        "-np", str(cfg["n_parallel"]),
        "--host", "0.0.0.0",
        "--port", "8080",
        "-fa", "auto",
        "-ctk", "q4_0",
        "-ctv", "q4_0",
        "--no-repack",
        "--no-context-shift",
    ]


def _apply_config(cfg: dict) -> None:
    """切换后更新展示配置（供 /api/monitor 与前端顶栏显示）"""
    CONFIG["model"] = cfg["name"]
    CONFIG["model_size"] = cfg["size"]
    CONFIG["experts_total"] = cfg["experts_total"]
    CONFIG["experts_active"] = cfg["experts_active"]


def do_switch(model_key: str) -> None:
    """后台执行切换：停旧进程 -> 启新进程 -> 等待就绪（daemon 线程，不阻塞 API）"""
    cfg = MODEL_CONFIGS[model_key]
    try:
        # 1. 停止当前 llama-server（命令行不含 monitor.py，不会波及自身）
        subprocess.run(["pkill", "-f", "llama-server"], capture_output=True)
        time.sleep(2)
        # 确保 8080 端口释放，避免新进程 bind 失败
        for _ in range(5):
            try:
                requests.get(f"{LLAMA_SERVER}/health", timeout=1)
                time.sleep(1)
            except Exception:
                break

        # 2. 后台启动新 llama-server（start_new_session 脱离控制终端，近似 nohup）
        os.makedirs(LLAMA_LOG.parent, exist_ok=True)
        # SLIM-ARC FIX 2026-08-12: 迁移后 llama-server 内嵌 RUNPATH 指向旧路径，
        # 需显式设置 LD_LIBRARY_PATH 指向 build/bin（与 start-demo.sh 保持一致）。
        env = dict(os.environ)
        bin_dir = str(LLAMA_DIR / "build" / "bin")
        env["LD_LIBRARY_PATH"] = bin_dir + ((":" + env["LD_LIBRARY_PATH"]) if env.get("LD_LIBRARY_PATH") else "")
        with open(LLAMA_LOG, "ab") as logf:
            proc = subprocess.Popen(
                _build_llama_cmd(cfg),
                stdout=logf,
                stderr=subprocess.STDOUT,
                start_new_session=True,
                env=env,
            )
        with switch_lock:
            SWITCH_STATE["llama_pid"] = proc.pid

        # 3. 立即更新展示配置（顶栏模型名同步切换）
        _apply_config(cfg)
        with switch_lock:
            SWITCH_STATE["current_model"] = model_key

        # 4. 等待就绪
        ready = _wait_llama_ready(proc, timeout=600.0)
        with switch_lock:
            SWITCH_STATE["llama_ready"] = ready
            SWITCH_STATE["error"] = None if ready else (
                "llama-server 启动失败（进程已退出）。"
                "80B 模型在 4GB 设备上可能因内存不足（OOM）无法加载，属预期情况。\n"
                "日志尾部:\n" + _read_llama_log_tail()
            )
            SWITCH_STATE["finished_at"] = time.time()
            SWITCH_STATE["switching"] = False
    except Exception as e:
        with switch_lock:
            SWITCH_STATE["error"] = f"切换异常: {e}"
            SWITCH_STATE["finished_at"] = time.time()
            SWITCH_STATE["switching"] = False


class SwitchModelRequest(BaseModel):
    """切换请求体：{"model": "4b"|"80b"}"""
    model: str


@app.post("/api/switch-model")
def switch_model(body: SwitchModelRequest, request: Request):
    """UI 模型热切换入口：{"model": "4b"|"80b"}"""
    # 安全：仅允许本机访问
    if not is_local_request(request):
        return JSONResponse(
            status_code=403,
            content={"status": "error", "error": "仅允许本地访问（模型切换）"},
        )
    # 注：使用 Pydantic body 而非 request.json()——后者在同步端点返回 coroutine 导致 500
    model = body.model
    if model not in MODEL_CONFIGS:
        return JSONResponse(
            status_code=400,
            content={"status": "error", "error": f"未知模型: {model}，可选 4b / 80b"},
        )
    with switch_lock:
        if SWITCH_STATE["switching"]:
            return JSONResponse(status_code=409, content={
                "status": "error",
                "error": f"已有切换进行中（目标: {SWITCH_STATE['target_model']}），请稍候",
                "switching": True,
            })
        SWITCH_STATE.update(
            switching=True,
            target_model=model,
            error=None,
            llama_ready=False,
            started_at=time.time(),
            finished_at=None,
        )
    # 后台线程执行，接口立即返回
    threading.Thread(target=do_switch, args=(model,), daemon=True).start()
    return {"status": "switching", "model": model, "note": "llama-server 重启中，约 2-3 分钟"}


@app.get("/api/switch-status")
def switch_status():
    """前端轮询切换状态"""
    with switch_lock:
        elapsed = (time.time() - SWITCH_STATE["started_at"]) if SWITCH_STATE["started_at"] else 0.0
        return {
            "switching": SWITCH_STATE["switching"],
            "target_model": SWITCH_STATE["target_model"],
            "current_model": SWITCH_STATE["current_model"],
            "llama_ready": SWITCH_STATE["llama_ready"],
            "error": SWITCH_STATE["error"],
            "elapsed": round(elapsed, 1),
            "llama_pid": SWITCH_STATE["llama_pid"],
        }


if __name__ == "__main__":
    port = int(os.environ.get("MONITOR_PORT", "8001"))
    print(f"SLIM-ARC Monitor on http://0.0.0.0:{port}")
    print(f"Config: {CONFIG}")
    print(f"LLAMA_SERVER: {LLAMA_SERVER}")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")
