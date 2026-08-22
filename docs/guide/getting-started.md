# Getting Started

## 依赖

- macOS 13+ 或 Ubuntu 22.04+
- Git、CMake 3.20+、支持 C++17 的编译器
- Python 3.10+ 与 `uv`

## 初始化

```bash
git clone https://github.com/Nexa-Language/SLIM-ARC.git
cd SLIM-ARC
make bootstrap
make build
make test
```

bootstrap 固定 llama.cpp 到 `360e1349f0009c5ad99d21e3c4546b707addc68a`，并在
`src/llama-upstream` 创建可再生工作树。可通过 `SLIM_ARC_LLAMA_ROOT` 或 Make 的
`LLAMA_ROOT=/path` 使用其他位置，但上游 revision 仍保持固定。

## 运行

模型不随仓库分发。准备 GGUF 后：

```bash
src/llama-upstream/build/bin/llama-cli \
  -m /path/to/model.gguf -p "Hello" -n 32
```

所有性能结论都必须记录模型哈希、缓存状态、线程、prompt、`pp/tg` 和资源限制。
