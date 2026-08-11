# macOS 80B 受限实验计划 v2：并行 Range 下载增量

## 目标

在不改变模型 revision、文件名、字节数和 SHA-256 验收口径的前提下，为 v1 Task 4 增加显式的 8 路 curl Range 下载模式，缩短单连接吞吐不足对 12 小时实验窗口的占用。

## 前置条件

- v1 host preflight、Colima 数据盘、campaign deadline 与模型元数据校验已完成。
- 官方文件支持 HTTP Range；实测 100 MiB 独立请求返回 HTTP 206，吞吐约 3.75 MB/s。
- 现有 `.partial.metadata` 与 revision `4c8630cf7af926a9c5095cb4bbbbc65d36e20f77`、大小 `48410988384`、LFS SHA-256 绑定。

## 步骤拆解

1. 为 Range 切分函数增加 Shell 单元测试，覆盖不整除边界和无重叠连续区间。
2. 新增 guest segmented downloader：从现有 partial 末尾切分剩余区间，并发下载到有 start/end 命名的临时段。
3. 每个 worker 使用 HTTP/1.1，以 256 MiB 原子小块续写所属分片；每块必须返回 HTTP 206 且字节数精确，因此一次 CDN 断流最多损失当前小块，而不是重下约 5 GB 的完整分片。
4. 全部分片完成后按序追加，每追加一段即验证 partial 新长度并删除该临时段。
5. 只在最终文件大小和完整 SHA-256 均匹配时原子改名；默认下载模式仍保留单连接 `curl --continue-at -`。
6. 终止旧单连接时只处理从精确 Qwen URL 解析出的 PID；TERM 超时后才对同一组 PID 使用 KILL，等待原 host controller 退出后再启动 8 路模式。

## 验收标准

- Range 单元测试、Shell syntax 与 `git diff --check` 通过。
- 所有分段 HTTP code 为 206，区间连续、无重叠、无缺口。
- 最终大小为 `48410988384`，SHA-256 为 `d103b2733ec1012a52d01edda66b7e5c24ae50508c9f99f5297ea459ef3c061a`。
- 模型仍只以最终 `.gguf` 或与 metadata 绑定的 `.partial` 形式存在于 VM 数据盘，不进入 Git。

## 风险

- 并发连接可能被 CDN 限速或中断；脚本保留完整段和已提交的小块，并在重跑时按精确大小续写。
- 合并瞬间需要一个额外分段大小的磁盘空间；启动前按 remaining + largest segment + 1 GB reserve 检查。
- 分段只有大小/HTTP 206 校验，内容完整性最终仍由全文件 SHA-256 决定。
