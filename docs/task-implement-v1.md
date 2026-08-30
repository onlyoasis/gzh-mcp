# 任务书：gzh-mcp v1 实现

执行者：codex（gpt-5.6-sol）
委托方：Claude（主控，负责验收与提交）
日期：2026-08-30

## 目标

按 `docs/proposal.md`（v1.0 定稿）实现本 MCP server 并让测试全绿。
`docs/proposal.md` 是设计契约，`docs/codex-review.md` 是评审背景（意见已被吸收，
其中与 proposal 冲突处以 proposal 为准）。`CLAUDE.md` 是项目铁律。

## 动手前必须先查证的事实（授权反驳）

以下事实是设计方核实的，但你不得照单实现——先自己验证，发现与实际不符时
**以实际为准，并在最终报告中说明差异**：

1. **mcp Python SDK 当前版本与 API 形态**：`uv add mcp` 装到的实际版本、
   FastMCP 的导入路径与用法、`structuredContent` 的返回方式（可能是 SDK 自动
   处理 dict 返回值，也可能是显式构造）。以你装到的版本实际 API 为准，不要凭
   训练记忆写。若 SDK 实际行为与 proposal 4.6 节冲突，按 SDK 实际行为调整，
   并在报告中说明。
2. **draft/update 的请求体结构**：官方文档中该接口的精确字段（media_id、
   index、articles 的形状）。proposal 只写了接口名。
3. **draft/batchget、freepublish/get、freepublish/batchget 的响应字段名**：
   以官方文档为准写解析和测试的 mock。
4. **uploadimg 的严格限制**："小于 1MB" 是否严格小于；jpg/png 判定按魔数
   （JPEG FFD8FF、PNG 89504E47）。
5. **httpx 当前版本的 API**（AsyncClient、multipart 上传、timeout 用法）。

查证方式：`uv add` 后读实际安装的包源码、官方文档搜索。测试里的 mock 响应
结构必须来自你查证的文档，不是抄 proposal。

## 实现范围（proposal §4/§6 的可执行版）

结构：

```
src/gzh_mcp/
├── __init__.py
├── server.py           # FastMCP 入口 + 10 个工具 + 闸门一
├── wechat_client.py    # API 层：stable_token 缓存(single-flight)/素材/草稿/发布
├── validation.py       # HTML 外链图检测、<script> 检测、长度校验、魔数检查
└── errors.py           # 传输/HTTP状态/非JSON/业务errcode 四层 + 脱敏
```

工具（名称精确一致）：`check_credentials`、`upload_content_image`、
`upload_cover_image`、`create_draft`、`get_draft`、`update_draft`、
`list_drafts`、`get_publish_status`、`list_published`、`publish_draft`（仅
`GZH_MCP_ALLOW_PUBLISH` 严格真值为 `1`/`true` 时注册；调用必须 `confirm=true`）。

不可绕过的行为契约（每条都要有对应测试）：

- B1 `GZH_MCP_ALLOW_PUBLISH` 为 `0`/`false`/空串/空格/未设置 → tools/list 里
  **没有** publish_draft；为 `1`/`true`（大小写敏感按文档定，倾向只认小写
  `true` 和 `1`）→ 有。
- B2 `publish_draft(confirm=false)` 或缺省 → 直接拒绝，不发任何 HTTP 请求。
- B3 create_draft 前置校验：title>32 字符、digest>120、content≥20000 字符、
  HTML 含非微信域 img src、含 `<script>` → 分别报错且不发请求。
- B4 create_draft 成功后自动 draft/get 回读：标题不一致 / 图片数量不一致 /
  正文长度缩水超过阈值（自定合理阈值并写注释）→ 报错但返回 media_id。
- B5 正文图上传：文件不存在、非 jpg/png（按魔数）、≥1MB → 前置报错。
- B6 非幂等接口（draft/add、freepublish/submit）遇网络传输错误 → 返回
  "状态不确定"错误，不重试。
- B7 业务接口返回 40014/42001 → 刷 token 重试一次；stable_token 接口自身
  40001 → 不重试不刷新。
- B8 所有错误输出不含 access_token 与 secret（有脱敏测试：构造含 token 的
  errmsg 验证输出已打码）。
- B9 stdout 无任何非 JSON-RPC 输出（测试启动 server 进程发 initialize 验证）。
- B10 中文正文 JSON 序列化 ensure_ascii=False（测试断言请求体字节含原文中文）。

## 测试纪律（硬要求）

- 全部用 pytest + mock（httpx MockTransport 或 monkeypatch），**禁止真实调用
  微信 API**。
- 每个行为契约至少一个用例；mock 响应结构来自你自己查证的官方文档。
- **红灯验证**：写完测试后，逐个把被测行为退化（例如把 confirm 检查删掉、把
  严格真值改成 `bool(os.environ.get(...))`），确认对应测试真的失败，再还原。
  在最终报告里列出你红灯验证过的契约编号。
- 若实测与任务书预期不符：说明原因，**禁止修改期望值迁就实现**；确属任务书
  错误的，以实际为准并报告。

## 红线

- **禁止任何 git 操作**（add/commit/branch 等）——主控验收后统一提交。
- 禁止真实调用 api.weixin.qq.com（含 check_credentials——测试全 mock）。
- 禁止读取或修改 ~/.claude/、~/.agents/、.claude/skills/ 下任何文件。
- 禁止把 WECHAT_APPID/WECHAT_SECRET 写进任何文件或测试。
- 只在 /Users/lzc/Projects/tools/gzh-mcp 内写文件。
- 不实现 proposal 明确排除的功能（群发、排版、合规检查、素材库管理）。

## 完成定义

1. `uv run pytest` 全绿。
2. `uv run gzh-mcp` 可启动（配假 env，stdio 等 stdin 不崩，Ctrl-C/EOF 正常退出）。
3. pyproject.toml 声明 console script `gzh-mcp` 与依赖 `mcp>=2,<3`、`httpx`。
4. README 已有的安装段与实际一致（命令能跑）。

## 报告格式

最终回复（stdout 最后一部分）按此结构：

```
## 查证差异
（任务书/方案说法 vs 实际，逐条；无差异则写"无"）
## 实现清单
（文件、工具、契约编号 → 测试名）
## 红灯验证记录
（契约编号 → 退化方式 → 观察到的失败）
## 测试结果
（pytest 输出摘要：数量、通过率）
## 遗留问题
```
