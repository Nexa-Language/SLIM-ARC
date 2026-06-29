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
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
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
    return {"status": "ok", "config": CONFIG}


if __name__ == "__main__":
    port = int(os.environ.get("MONITOR_PORT", "8001"))
    print(f"SLIM-ARC Monitor on http://0.0.0.0:{port}")
    print(f"Config: {CONFIG}")
    print(f"LLAMA_SERVER: {LLAMA_SERVER}")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")
