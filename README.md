# gzh-mcp

微信公众号发布 MCP server。把「素材上传 → 草稿箱 → 发布」链路封装成标准
[MCP](https://modelcontextprotocol.io) 工具，供本机 MCP 客户端（Claude Code、
Codex CLI 等）调用，替代在写作 agent 里手写公众号 API 对接。

- 只做**发布链路**，不做排版：`create_draft` 接受 HTML，Markdown → 微信 HTML
  由调用方完成。
- **默认安装只到草稿箱**：自动发布工具默认不注册，需环境变量 + 每次调用双重
  确认才会出现（见[安全模型](#安全模型)）。
- 无状态、零本地数据：不落库、不落盘，凭据只从环境变量注入。

## 工具清单

| 工具 | 用途 | 微信接口 | 默认注册 |
|---|---|---|---|
| `check_credentials` | 验证凭据与 IP 白名单（不证明接口权限） | `POST /cgi-bin/stable_token` | ✅ |
| `upload_content_image` | 上传正文图片，返回微信图片 URL | `POST /cgi-bin/media/uploadimg` | ✅ |
| `upload_cover_image` | 上传永久封面素材，返回 media_id | `POST /cgi-bin/material/add_material` | ✅ |
| `create_draft` | 创建单篇/多图文草稿，前置校验 + 创建后自动回读验证 | `POST /cgi-bin/draft/add` + `draft/get` | ✅ |
| `get_draft` | 读取草稿完整 news_item 结构 | `POST /cgi-bin/draft/get` | ✅ |
| `update_draft` | 更新草稿中的单篇文章 | `POST /cgi-bin/draft/update` | ✅ |
| `list_drafts` | 分页列出草稿，附总数 | `draft/batchget` + `draft/count` | ✅ |
| `get_publish_status` | 轮询异步发布状态 | `POST /cgi-bin/freepublish/get` | ✅ |
| `list_published` | 分页列出已发布文章（对账） | `POST /cgi-bin/freepublish/batchget` | ✅ |
| `publish_draft` | 提交草稿发布 | `POST /cgi-bin/freepublish/submit` | ⛔ 需开启 |

不做的能力：群发（mass/sendall）、删除草稿/已发布文章（不可逆）、Markdown
排版、内容合规检查、素材库完整管理、数据统计。

## 安全模型

发布是不可逆的外部动作，本 server 用**双闸门**控制：

1. **注册闸门（安装时）**：环境变量 `GZH_MCP_ALLOW_PUBLISH` 为 `1` 或小写
   `true`（严格匹配，`0`/`false`/`TRUE`/空串均不生效）时，`publish_draft`
   才会出现在工具列表。MCP 客户端缓存工具列表，修改后需重启客户端。
2. **确认闸门（每次调用）**：`publish_draft` 必须显式传 `confirm=true`，
   否则直接拒绝，不发出任何 HTTP 请求。

其他安全相关行为：

- `WECHAT_SECRET` 与 access_token 全链路脱敏，不出现在错误信息、日志或
  stdout；stdout 只承载 MCP JSON-RPC 协议，诊断信息一律写 stderr。
- 非幂等接口（`draft/add`、`freepublish/submit`）遇网络传输错误返回
  「状态不确定」错误并**禁止自动重试**，防止重复建稿、重复提交。
- `create_draft` 前置拦截：非微信域正文图 URL（微信会过滤外链图）、
  `<script>`、超长标题/摘要/正文；图片按文件魔数校验真实格式。
- 创建草稿后自动回读验证（标题、图片数、正文长度），微信清洗了内容时
  返回 `verified=false` + 差异详情，不静默成功。
- 发布结果带脱敏 appid 前缀、草稿标题、media_id，便于调用方核对目标账号。

## 前置要求

- Python 3.12+ 与 [uv](https://docs.astral.sh/uv/)
- 公众号的 AppID / AppSecret（公众平台官网 → 设置与开发 → 基本配置）
- **IP 白名单**：获取 access_token 的出口 IP 必须加入公众号 IP 白名单，
  否则报 `40164`
- **发布权限**：`freepublish/*` 仅对已认证账号开放，个人主体/未认证账号
  通常返回 `48001`。草稿与素材接口不受此限制

## 安装

```bash
git clone https://github.com/onlyoasis/gzh-mcp.git
cd gzh-mcp
uv sync
uv run pytest   # 验证安装：64 个测试应全部通过
```

## 客户端配置

MCP 客户端的 stdio server 配置（JSON）：

```json
{
  "mcpServers": {
    "gzh": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/gzh-mcp", "gzh-mcp"],
      "env": {
        "WECHAT_APPID": "<你的 AppID>",
        "WECHAT_SECRET": "<你的 AppSecret>",
        "GZH_MCP_ALLOW_PUBLISH": "0"
      }
    }
  }
}
```

Claude Code 也可用命令行注册：

```bash
claude mcp add gzh -s user \
  -e WECHAT_APPID=<你的 AppID> \
  -e WECHAT_SECRET=<你的 AppSecret> \
  -- uv run --directory /path/to/gzh-mcp gzh-mcp
```

### 环境变量

| 变量 | 必填 | 说明 |
|---|---|---|
| `WECHAT_APPID` | 是 | 公众号 AppID |
| `WECHAT_SECRET` | 是 | AppSecret，仅经环境变量注入，不落任何文件 |
| `GZH_MCP_ALLOW_PUBLISH` | 否 | `1`/`true` 注册 `publish_draft`；其余值一律视为关闭 |

## 典型工作流

发布一篇已排版的文章（HTML）：

```
1. check_credentials                → 确认凭据与 IP 白名单正常
2. upload_cover_image(cover.png)    → 得到 thumb_media_id
3. upload_content_image(a.png) ...  → 得到微信图片 URL，替换正文中的 src
4. create_draft([{title, content,   → 创建草稿，返回 media_id + verified
    thumb_media_id, digest}])
5. 人工在公众号后台复核草稿，发布
```

开启自动发布后（`GZH_MCP_ALLOW_PUBLISH=1`）：

```
6. publish_draft(media_id, confirm=true) → 提交发布，返回 publish_id
7. get_publish_status(publish_id)        → 轮询：0 成功 / 1 发布中 /
                                           2 原创失败 / 3 常规失败 /
                                           4 审核不通过 / 5、6 成功后被删/封禁
```

## 已知约定与限制

- server 无本地状态：`media_id → publish_id` 映射由调用方记录，事后对账用
  `list_published`。
- `file_path` 参数指 MCP server 所在主机的本地文件；server 与客户端须同机，
  不支持远程部署（若需远程部署，必须先重新评审文件路径信任边界）。
- 发布为异步语义：提交成功（拿到 publish_id）不等于文章发布成功，以
  `get_publish_status` 终态为准。
- 正文图限制：jpg/png 且严格小于 1MB；封面支持 jpg/png/gif/bmp，≤10MB。
- 标题 ≤ 32 字符；摘要官方上限 128 字符（本工具按 120 保守限制）；正文
  < 2 万字符。

## 开发

```bash
uv sync                                    # 安装依赖
uv run pytest                              # 全量测试
uv run pytest --cov=gzh_mcp --cov-report=term-missing   # 覆盖率
uv run gzh-mcp                             # 本地启动（stdio）
```

测试全部使用 mock，不会真实调用微信 API。本项目要求回归测试通过
「红灯验证」：修改行为前先确认对应测试在退化实现下真的失败。

## 文档

- [docs/proposal.md](docs/proposal.md) —— 设计方案 v1.0（工具清单、安全模型、
  错误分层、验收标准）
- [docs/codex-review.md](docs/codex-review.md) —— 独立 AI 评审记录
- [docs/api-verification.md](docs/api-verification.md) —— 官方接口字段与
  依赖版本的查证证据
- [docs/task-implement-v1.md](docs/task-implement-v1.md) —— v1 实现任务书
  （含 10 条行为契约与测试要求）

## License

[MIT](LICENSE)
