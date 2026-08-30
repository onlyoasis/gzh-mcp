# gzh-mcp 方案：微信公众号发布 MCP Server

版本：v1.0（已吸收 codex 5.6-sol 评审意见，定稿）
日期：2026-08-30
评审记录：docs/codex-review.md（结论：可行但需修改；意见已全部吸收或注明取舍）

## 1. 背景与目标

wewrite 写作 agent 已具备公众号发布能力，但耦合在 `~/.claude/skills/wewrite` 的
Python CLI 里，只有 Claude Code 里的 wewrite skill 能用。目标：把**发布链路**
（素材上传 → 草稿箱 → 发布）抽成一个标准 MCP server，在**本机**供 MCP 客户端
（Claude Code、Codex CLI）调用。

### 定位边界（诚实声明）

- 工具入参中的 `file_path` 指 **MCP server 所在主机的本地文件**。本 server 只
  支持本机场景（server 与调用方在同一台机器），不支持远程客户端。
- 排版（Markdown → 微信 HTML）由调用方完成，`create_draft` 的 `content` 接受
  HTML。wewrite 的主题系统不搬进第一版。

### 非目标

- 不做 Markdown→HTML 排版（wewrite 已有）。
- 不做数据统计（datacube）、评论管理、素材库完整管理。
- 不做内容合规门禁（合规由写作者和平台审核把关，MCP 不承担）。
- 不做群发（mass/sendall）——wewrite 生产未用，风险大于收益；若未来加入，
  `clientmsgid` 必须调用方显式提供，且需单独评审。

## 2. 参考实现：wewrite 发布链路

来源：`~/.claude/skills/wewrite/src/wewrite/toolkit/`（选择性迁移，不整体照搬）。

**值得迁移**：HTTP 超时、错误分层思想、access_token 脱敏、返回结构校验、
`mp.weixin.qq.com` URL 白名单校验、`clientmsgid` 防重思想、`ensure_ascii=False`
的生产兼容措施。

**不照搬**：旧版 token 接口、无锁全局缓存、上传不检查文件/MIME/大小、
`get_draft` 只取第一篇正文、普通接口只抛泛化 `ValueError`。

## 3. 官方 API 事实（已核实，标注核对状态）

### 3.1 access_token

- 推荐 `POST /cgi-bin/stable_token`（JSON：grant_type/appid/secret/force_refresh）。
- 普通模式（force_refresh=false/缺省）有效期内返回同一 token；`force_refresh=true`
  会使旧 stable token 失效——**不得在每次错误时盲目强刷**。
- stable_token 与旧 `GET /cgi-bin/token` 的凭据**互相隔离**。
- IP 白名单是硬性要求，不通过报 `40164`。
- 有效期 7200s。
- 来源：官方 getStableAccessToken 文档（2026-08-30 核对）。

### 3.2 素材与图片

- 正文图 `POST /cgi-bin/media/uploadimg`：jpg/png，**严格小于 1MB**，返回 url。
- 封面 `POST /cgi-bin/material/add_material?type=image`：返回永久 media_id。
  与 uploadimg 的格式、大小限制不同（详见各自文档）。
- 必须按**文件真实内容**判断格式（魔数），不能只信扩展名或
  `mimetypes.guess_type()`。

### 3.3 草稿箱（draft）

- `POST /cgi-bin/draft/add`：articles 数组，字段限制：
  - `title` ≤ 32 字符（必填）
  - `digest`：**官方限制 128 字符**；本工具采用 ≤120 的保守业务限制
  - `content`：HTML，< 2 万字符且 < 1M；会移除 JS；**外链图片会被过滤**，
    正文图 url 必须来自 uploadimg
  - `thumb_media_id`：news 必填（永久素材）
  - `article_type=newspic` 为图片帖（≤20 张图）
  - `need_open_comment` / `only_fans_can_comment`
- 配套：`draft/get`、`draft/update`、`draft/count`、`draft/batchget`。
- 草稿被群发/发布后会从草稿箱移除。

### 3.4 发布（freepublish）

- `POST /cgi-bin/freepublish/submit`：入参 media_id → publish_id。
- **异步**：errcode=0 只代表受理。`freepublish/get` 轮询，publish_status：
  0 成功、1 发布中、2 原创失败、3 常规失败、4 平台审核不通过、
  5 成功后用户删除全部文章、6 成功后平台封禁。
- `freepublish/batchget`：已发布记录（对账用）。
- **权限**：个人主体、未认证企业账号通常无法使用 freepublish/*（常见返回
  `48001`，但 48001 是通用未授权错误，不能仅凭它断言原因）。该限制**只针对
  freepublish 发布能力，不影响草稿/素材接口**。目标账号实际权限以公众号后台
  接口权限页为准；`check_credentials` 成功不能证明有发布权限。
- stdio MCP 无法接收 `PUBLISHJOBFINISH` 事件回调，第一版采用轮询。

## 4. MCP 设计

### 4.1 工具清单

默认注册（本地操作与草稿箱，无对外发布动作）：

| # | 工具 | 映射 API | 说明 |
|---|---|---|---|
| 1 | `check_credentials` | stable_token | 只验证凭据与 IP 白名单；不证明接口权限 |
| 2 | `upload_content_image(file_path)` | media/uploadimg | 真实 MIME + 大小前置检查 |
| 3 | `upload_cover_image(file_path)` | material/add_material | 真实 MIME + 大小前置检查 |
| 4 | `create_draft(articles[]或单篇参数)` | draft/add | 多图文支持；前置校验+创建后回读验证（见 4.3） |
| 5 | `get_draft(media_id)` | draft/get | 返回完整 news_item 数组（不只第一篇） |
| 6 | `update_draft(media_id, index, article)` | draft/update | 人工复核后修正原草稿 |
| 7 | `list_drafts(offset, count)` | draft/batchget | 附 draft/count 总数 |
| 8 | `get_publish_status(publish_id)` | freepublish/get | 轮询发布状态 |
| 9 | `list_published(offset, count)` | freepublish/batchget | 只读对账 |

环境变量 `GZH_MCP_ALLOW_PUBLISH=1` 时额外注册（双闸门之一，见 4.2）：

| # | 工具 | 映射 API | 说明 |
|---|---|---|---|
| 10 | `publish_draft(media_id, confirm)` | freepublish/submit | 必须显式传 `confirm=true` |

**第一版不做**：mass_send / get_mass_status（群发，生产未用）、delete_draft
（不可逆，原内容可能无本地副本）、freepublish/delete（不可逆）。
上传/建草稿会修改微信端状态，工具 annotations 如实标注，不统称"安全/只读"。

### 4.2 发布动作的双闸门

环境变量开关只是**启动时配置**，不是逐次授权。两层缺一不可：

1. **闸门一（安装时）**：`GZH_MCP_ALLOW_PUBLISH` 未设置或值不是 `1`/`true`
   （严格真值，`0`/`false`/空串/空格不启用）时，`publish_draft` 不注册。
   注意：MCP 客户端缓存工具列表，改环境变量需重启客户端。
2. **闸门二（每次调用）**：`publish_draft` 必须显式传 `confirm=true`，否则
   直接拒绝执行。防 prompt injection 下的误调用。

返回值必须包含：脱敏 appid（前 6 位）、草稿标题、media_id——让调用方在结果里
核对目标账号与内容，防误配公众号。

工具 description 与 MCP annotations（readOnlyHint/destructiveHint/
idempotentHint/openWorldHint）如实填写，但仅作提示，不作为安全边界。

### 4.3 create_draft 的校验链

1. **前置校验**（本地，发请求前）：
   - title ≤ 32 字符、digest ≤ 120、content < 2 万字符
   - 解析 HTML：发现外链图片 URL（非微信 uploadimg 域）→ 明确报错列出 URL
   - 发现 `<script>` → 报错
2. **创建**：draft/add（JSON `ensure_ascii=False`，UTF-8）。
3. **回读验证**：draft/get 回读，核对标题一致、图片数量一致、正文长度未异常
   缩水；不符则报错并返回 media_id 供人工检查。

### 4.4 技术栈

- Python 3.12+，`mcp` Python SDK **v2 主版本**（FastMCP 风格），stdio 传输。
- HTTP 只用一个库：`httpx`（async，与 MCP handler 异步模型一致）。
- 无状态：不落库、不落盘；media_id→publish_id 映射由调用方（agent）记录，
  README 写明该约定与 `list_published` 对账方法。
- 选 Python 的理由：本机已有被生产验证过的微信 API 处理经验可选择性迁移、
  测试成本低（不主张 Python MCP 生态优于 TS）。

### 4.5 错误处理与并发

- **四层错误**：网络传输错误 / HTTP 非 200 / 响应非 JSON / 微信 errcode≠0
  （业务错误）。微信业务错误常以 HTTP 200 返回，四层都要查。
- 错误信息包含 errcode、errmsg、接口路径、脱敏后的上下文；`WECHAT_SECRET`
  与 access_token 不得出现在任何输出、异常 URL、stderr 中。
- **token 缓存**：进程内 single-flight（asyncio.Lock），过期前 300s 刷新；
  仅对**业务接口**的 `40014/42001` 刷新重试一次；stable_token 获取接口自身的
  `40001`（通常是 AppSecret 错误）不重试、不自动强刷。
- **非幂等操作**（draft/add、freepublish/submit）：网络超时/传输错误时返回
  明确的"状态不确定，勿直接重试"错误，不自动重试（防重复草稿/重复提交）。
  只读接口遇 `-1`/5xx/限流可做一次有限退避。
- stdout 只走 MCP 协议（JSON-RPC）；任何日志写 stderr 且脱敏。

### 4.6 输出格式

- 每个工具同时返回对象型 `structuredContent` 和文本 fallback，兼容旧客户端。
- 输入 schema 用基础 JSON Schema 类型，不依赖新特性。

## 5. 配置

| 变量 | 必填 | 说明 |
|---|---|---|
| `WECHAT_APPID` | 是 | 公众号 AppID |
| `WECHAT_SECRET` | 是 | AppSecret（不落仓库，客户端 env 注入） |
| `GZH_MCP_ALLOW_PUBLISH` | 否 | `1`/`true` 才注册 publish_draft（严格真值） |

## 6. 项目结构

```
gzh-mcp/
├── pyproject.toml          # uv；deps: mcp>=2, httpx
├── README.md               # 中文：安装、客户端配置、IP 白名单、验收方法
├── CLAUDE.md / AGENTS.md
├── docs/proposal.md        # 本方案
├── docs/codex-review.md    # 评审记录
├── src/gzh_mcp/
│   ├── __init__.py
│   ├── server.py           # FastMCP 入口、工具注册（含闸门一逻辑）
│   ├── wechat_client.py    # API 层（token/素材/草稿/发布）
│   ├── validation.py       # HTML 外链检测、长度校验、MIME/魔数检查
│   └── errors.py           # 四层错误类型 + 脱敏
└── tests/
    ├── test_wechat_client.py
    ├── test_validation.py
    └── test_server_tools.py
```

## 7. 验收标准

1. 单测全绿：错误码映射、严格真值解析、HTML 外链检测、长度校验、
   回读对比逻辑、"confirm=false 拒绝发布"、非幂等超时语义。
   **回归测试必须验证"退回修复后真的失败"**（红灯→绿灯）。
2. MCP Inspector：initialize → tools/list → tools/call 冒烟通过。
3. 真实客户端（Claude Code）+ 真实账号：check_credentials →
   upload_cover_image → create_draft → get_draft 回读 → list_drafts 全链路；
   publish_draft 仅在用户提供凭据并明确授权时实测，否则以 48001/未注册路径
   验证闸门行为。
4. 验收证据（官方文档 URL + 核对日期 + 目标账号实测结果）记入 docs/，不以
   "已核实"三个字代替。

## 8. 已知取舍

- **无持久化状态**：换来零运维；代价是发布后对账依赖 `list_published`。
  接受，由调用方记录 media_id/publish_id。
- **file_path 不限制目录**：本机单用户信任边界下不引入允许目录配置；
  做符号链接解析 + 真实 MIME/大小检查 + 文件必须存在。若未来支持远程部署，
  必须重新评审此决策。
- **不做内容合规检查**：MCP 是通道不是编辑；合规由写作者与平台把关。
