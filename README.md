# gzh-mcp

微信公众号管理 MCP server。把草稿发布、素材、统计、用户标签、菜单、评论、
群发、定向推送与常用基础接口封装成标准 [MCP](https://modelcontextprotocol.io)
工具，供本机 MCP 客户端（Claude Code、Codex CLI 等）调用。

- 不做排版：`create_draft` 接受 HTML，Markdown → 微信 HTML 由调用方完成。
- 完整启用后共 58 个工具；自动发布和群发分别受独立环境变量控制。
- 不持久化业务状态；只有下载工具会按调用方指定的路径写文件，且拒绝覆盖。
- 凭据只从环境变量注入，错误信息中的 secret 和 access token 会脱敏。

## 工具清单

| 域 | 工具 | 注册规则 |
|---|---|---|
| v1 草稿发布（10） | `check_credentials`、`upload_content_image`、`upload_cover_image`、`create_draft`、`get_draft`、`update_draft`、`list_drafts`、`publish_draft`、`get_publish_status`、`list_published` | 除 `publish_draft` 外默认注册 |
| 发布补充（3） | `delete_draft`、`get_published_article`、`delete_published_article` | 默认注册；删除需 `confirm=true` |
| 素材（8） | `upload_video_material`、`upload_voice_material`、`get_material`、`delete_material`、`list_materials`、`count_materials`、`upload_temp_media`、`download_temp_media` | 默认注册；删除需确认，下载拒绝覆盖已有文件 |
| 数据统计（1） | `get_statistics_report` | 默认注册；支持的 report 与时间跨度会前置校验 |
| 用户与标签（14） | `list_users`、`get_user_info`、`batch_get_user_info`、`update_user_remark`、`create_tag`、`list_tags`、`update_tag`、`delete_tag`、`get_user_ids_by_tag`、`tag_users`、`untag_users`、`list_blacklist`、`blacklist_users`、`unblacklist_users` | 默认注册；删除标签需确认 |
| 菜单（6） | `create_menu`、`get_current_menu`、`delete_menu`、`create_conditional_menu`、`delete_conditional_menu`、`try_match_conditional_menu` | 默认注册；删除需确认 |
| 评论（3） | `list_comments`、`mark_comment_elect`、`unmark_comment_elect` | 默认注册 |
| 群发（6） | `mass_send_all`、`mass_send_by_tag`、`mass_send_by_openids`、`preview_mass_message`、`get_mass_status`、`delete_mass_message` | 前 4 个需开启群发闸门；发送还需 `clientmsgid` 与确认；状态查询和删除默认注册 |
| 定向推送（3） | `send_custom_message`、`send_template_message`、`send_subscribe_message` | 默认注册；每次发送需 `confirm=true` |
| 杂项（4） | `create_qrcode`、`get_jsapi_ticket`、`get_autoreply_config`、`get_server_ips` | 默认注册 |

明确不实现：`sns/*`、`shorturl`、`getarticletotal`、群发速度配置、模板行业配置、
`genShortKey`、Markdown 排版与内容合规检查。

## 安全模型

发布、群发、定向推送和删除会改变外部状态，本 server 采用以下控制：

1. **注册闸门（安装时）**：环境变量 `GZH_MCP_ALLOW_PUBLISH` 为 `1` 或小写
   `true`（严格匹配，`0`/`false`/`TRUE`/空串均不生效）时，`publish_draft`
   才会出现在工具列表。MCP 客户端缓存工具列表，修改后需重启客户端。
2. **确认闸门（每次调用）**：`publish_draft` 必须显式传 `confirm=true`，
   否则直接拒绝，不发出任何 HTTP 请求。
3. **群发双闸门**：`GZH_MCP_ALLOW_MASS_SEND` 必须严格为 `1` 或小写 `true`，
   `mass_send_all`、`mass_send_by_tag`、`mass_send_by_openids`、
   `preview_mass_message` 才注册；前三者还必须传非空 `clientmsgid` 和
   `confirm=true`。
4. **逐次确认**：删除类工具以及客服、模板、订阅通知发送工具必须显式传
   `confirm=true`；校验失败不会发 HTTP 请求。

其他安全相关行为：

- `WECHAT_SECRET` 与 access_token 全链路脱敏，不出现在错误信息、日志或
  stdout；stdout 只承载 MCP JSON-RPC 协议，诊断信息一律写 stderr。
- 非幂等接口（创建草稿、发布、群发与定向推送）遇网络传输错误返回
  「状态不确定」错误并**禁止自动重试**，防止重复建稿、重复提交。
- 只读接口遇传输错误、HTTP 5xx 或微信 `errcode=-1` 时最多退避重试一次。
- `create_draft` 前置拦截：非微信域正文图 URL（微信会过滤外链图）、
  `<script>`、超长标题/摘要/正文；图片按文件魔数校验真实格式。
- 创建草稿后自动回读验证（标题、图片数、正文长度），微信清洗了内容时
  返回 `verified=false` + 差异详情，不静默成功。
- `create_draft` 同时校验普通图文和 `article_type=newspic` 图片帖；图片帖要求
  1–20 个非空 `image_media_id`，回读时核对图片数。
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
uv run pytest   # 验证安装
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
        "GZH_MCP_PROXY": "http://127.0.0.1:2080",
        "GZH_MCP_ALLOW_PUBLISH": "0",
        "GZH_MCP_ALLOW_MASS_SEND": "0"
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
| `GZH_MCP_PROXY` | 否 | 显式 HTTP(S) 代理；server 不继承宿主代理环境，适用于固定出口 IP 白名单 |
| `GZH_MCP_ALLOW_PUBLISH` | 否 | `1`/`true` 注册 `publish_draft`；其余值一律视为关闭 |
| `GZH_MCP_ALLOW_MASS_SEND` | 否 | `1`/`true` 注册 4 个群发发送/预览工具；其余值一律视为关闭 |

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
- `get_material`、`download_temp_media` 的 `save_path` 也位于 MCP server 主机；
  自动创建父目录，但目标文件存在时拒绝覆盖。
- 发布为异步语义：提交成功（拿到 publish_id）不等于文章发布成功，以
  `get_publish_status` 终态为准。
- 正文图限制：jpg/png 且严格小于 1MB；封面支持 jpg/png/gif/bmp，≤10MB。
- 标题和正文必须非空，长度交由微信平台按当前真实契约校验；摘要官方上限
  128 字符（本工具按 120 保守限制）。正文仍前置拒绝脚本和非微信图片 URL。

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
- [docs/proposal-v2.md](docs/proposal-v2.md) —— v2 设计契约（47 个新增工具）
- [docs/task-implement-v2.md](docs/task-implement-v2.md) —— v2 实现任务书
  （含 B13～B24 行为契约）

## License

[MIT](LICENSE)
