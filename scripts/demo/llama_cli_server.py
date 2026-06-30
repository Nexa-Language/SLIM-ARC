#!/usr/bin/env python3
"""
SLIM-ARC Demo Server (Fallback: llama-cli subprocess)

当 llama-server 二进制有 HTTP bind bug 时，用此脚本替代。
启动一个 FastAPI SSE server，每次 /v1/chat/completions 请求时 spawn llama-cli 子进程，
解析 stdout 逐 token 通过 SSE 推送。

用法：
    python3 scripts/demo/llama_cli_server.py --model 4b
    python3 scripts/demo/llama_cli_server.py --model 80b
"""
import os
import sys
import re
import time
import signal
import subprocess
import json
import argparse
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

app = FastAPI(title="SLIM-ARC Demo Server (llama-cli)")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
LLAMA_CLI = PROJECT_ROOT / "src/llama-upstream/build/bin/llama-cli"

MODELS = {
    "4b": {
        "path": PROJECT_ROOT / "data/models/Qwen3-4B-Q4_K_M.gguf",
        "name": "Qwen3-4B-Q4_K_M",
        "size": "2.4 GB",
        "experts_total": 0,
        "experts_active": 0,
    },
    "80b": {
        "path": PROJECT_ROOT / "data/models/Qwen3-Next-80B-A3B-Instruct-IQ4_XS.gguf",
        "name": "Qwen3-Next-80B-IQ4_XS",
        "size": "38 GB",
        "experts_total": 512,
        "experts_active": 10,
    },
}

CONFIG = {}


def build_prompt(messages: list) -> str:
    """构建 llama-cli 的对话 prompt（Qwen3 chat template）"""
    parts = []
    for m in messages:
        role = m["role"]
        content = m["content"]
        if role == "system":
            parts.append(f"<|im_start|>system\n{content}<|im_end|>")
        elif role == "user":
            parts.append(f"<|im_start|>user\n{content}<|im_end|>")
        elif role == "assistant":
            parts.append(f"<|im_start|>assistant\n{content}<|im_end|>")
    parts.append("<|im_start|>assistant\n/no_think\n")
    return "\n".join(parts)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/v1/models")
def models():
    return {"data": [{"id": CONFIG.get("model", "slim-arc"), "object": "model"}]}


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    body = await request.json()
    messages = body.get("messages", [])
    stream = body.get("stream", False)
    max_tokens = body.get("max_tokens", 200)
    temperature = body.get("temperature", 0.7)

    prompt = build_prompt(messages)
    model_path = str(CONFIG["model_path"])

    cmd = [
        str(LLAMA_CLI),
        "-m", model_path,
        "-t", "8",
        "-n", str(max_tokens),
        "--temp", str(temperature),
        "--no-context-shift",
        "-fa", "auto",
        "-ctk", "q4_0", "-ctv", "q4_0",
        "--no-repack",
        "-r", "<|im_end|>",
        "-p", prompt,
    ]

    if not stream:
        # 非流式：收集全部输出
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            text = result.stdout
            # llama-cli 输出含 prompt 回显，提取 assistant 回答
            # 找到最后一个 assistant 之后的内容
            idx = text.rfind("/no_think\n")
            if idx >= 0:
                text = text[idx + len("/no_think\n"):]
            text = text.replace("<|im_end|>", "").strip()
            return JSONResponse({
                "choices": [{"message": {"role": "assistant", "content": text}, "finish_reason": "stop"}],
                "usage": {"completion_tokens": len(text)},
            })
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=500)

    # 流式 SSE
    async def event_stream():
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, bufsize=1
        )
        first_chunk = True
        try:
            seen_prompt = False
            buffer = ""
            for line in proc.stdout:
                # llama-cli 先回显 prompt，然后输出回答
                # 检测 /no_think 后开始真正的输出
                if "/no_think" in line:
                    seen_prompt = True
                    continue
                if not seen_prompt:
                    continue
                # 去掉 ANSI 转义
                line = re.sub(r'\x1b\[[0-9;]*m', '', line)
                if "<|im_end|>" in line:
                    line = line.replace("<|im_end|>", "")
                    if line.strip():
                        yield f"data: {json.dumps({'choices':[{'index':0,'delta':{'content':line}}]})}\n\n"
                    yield "data: [DONE]\n\n"
                    break
                if line.strip():
                    if first_chunk:
                        yield f"data: {json.dumps({'choices':[{'index':0,'delta':{'role':'assistant','content':None}}]})}\n\n"
                        first_chunk = False
                    yield f"data: {json.dumps({'choices':[{'index':0,'delta':{'content':line}}]})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except:
                proc.kill()

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.get("/api/health")
def api_health():
    return {"status": "ok", "config": CONFIG}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", choices=["4b", "80b"], default="4b")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()

    cfg = MODELS[args.model]
    CONFIG["model"] = cfg["name"]
    CONFIG["model_size"] = cfg["size"]
    CONFIG["model_path"] = cfg["path"]
    CONFIG["experts_total"] = cfg["experts_total"]
    CONFIG["experts_active"] = cfg["experts_active"]
    CONFIG["madv"] = "ON"
    CONFIG["kv_type"] = "q4_0"
    CONFIG["fa"] = "ON"
    CONFIG["repack"] = "OFF"
    CONFIG["tier"] = "32GB warm"

    print(f"SLIM-ARC Demo Server (llama-cli fallback)")
    print(f"模型: {cfg['name']} ({cfg['size']})")
    print(f"端口: {args.port}")
    print(f"LLAMA_CLI: {LLAMA_CLI}")
    uvicorn.run(app, host="0.0.0.0", port=args.port, log_level="warning")
