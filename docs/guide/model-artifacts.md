# Model Artifacts

模型权重不进入 Git。推荐在仓库外保存，或放在被忽略的 `data/models/`。

| Artifact | Upstream | Revision / SHA-256 |
|---|---|---|
| Qwen3-Next-80B-A3B-Instruct Q4_K_M | `Qwen/Qwen3-Next-80B-A3B-Instruct-GGUF` | revision `4c8630cf1f2ee13b4b9e9051602646ea52e20f77`; file SHA-256 `d103b2733ec1012a52d01edda66b7e5c24ae50508c9f99f5297ea459ef3c061a` |
| SLIM-ARC IQ2_M | local quantization from the same model | file SHA-256 `d8c223bde11695dd562cc5144bf952a059a66e4b6b654b57efddf4a6746406c3` |
| Full imatrix | calibration artifact recorded in the macOS evidence | SHA-256 `0d574fc250a9b163c14dfe86e5c87e25db389bb83fe7de96dd644b9d897465e1` |

下载后必须自行核对 SHA-256。量化来源、参数和 macOS 最终结果见
`docs/macos_test_notes/2026-08-21/`。第三方模型许可证和访问条件由其发布者决定。
