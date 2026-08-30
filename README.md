# gzh-mcp

微信公众号发布 MCP server。把"素材上传 → 草稿箱 → 发布"链路封装成标准 MCP 工具，
供本机 MCP 客户端（Claude Code、Codex CLI 等）调用。

## 状态

v1 已实现。设计契约见 [docs/proposal.md](docs/proposal.md)，接口核对证据见
[docs/api-verification.md](docs/api-verification.md)。

## 功能范围

- 凭据检查（stable_token + IP 白名单诊断）
- 正文图片上传（media/uploadimg，jpg/png 且 <1MB）
- 封面上传（material/add_material，永久素材）
- 草稿：创建（多图文）/读取（完整结构）/更新/列表，创建后自动回读验证
- 发布状态轮询与已发布记录对账（freepublish）
- `publish_draft`（freepublish/submit）默认**不注册**，需环境变量 +
  每次调用 `confirm=true` 双闸门开启

不做：Markdown→HTML 排版（wewrite 负责）、群发、内容合规检查、素材库完整管理。

## 配置

| 环境变量 | 必填 | 说明 |
|---|---|---|
| `WECHAT_APPID` | 是 | 公众号 AppID |
| `WECHAT_SECRET` | 是 | AppSecret，经 MCP 客户端 env 注入，不落仓库 |
| `GZH_MCP_ALLOW_PUBLISH` | 否 | 设为 `1`/`true` 才注册 publish_draft |

前置条件：公众号后台"基本配置"中把本机出口 IP 加入 IP 白名单，否则
`check_credentials` 报 40164。发布接口（freepublish）仅认证账号可用，
个人主体账号通常无此权限（errcode 48001）。

## 安装

需要 Python 3.12+ 与 `uv`：

```bash
uv sync
uv run pytest
```

## 客户端配置

```json
{
  "mcpServers": {
    "gzh": {
      "command": "uv",
      "args": ["run", "--directory", "/Users/lzc/Projects/tools/gzh-mcp", "gzh-mcp"],
      "env": {
        "WECHAT_APPID": "<appid>",
        "WECHAT_SECRET": "<secret>"
      }
    }
  }
}
```

## 开发

```bash
uv sync
uv run pytest
uv run pytest --cov=gzh_mcp --cov-report=term-missing
```

`uv run gzh-mcp` 启动 stdio server。stdout 只用于 MCP JSON-RPC，诊断信息不得写入
stdout。缺少 `WECHAT_APPID` 或 `WECHAT_SECRET` 时 server 会快速失败。

## 工具

默认注册：`check_credentials`、`upload_content_image`、
`upload_cover_image`、`create_draft`、`get_draft`、`update_draft`、
`list_drafts`、`get_publish_status`、`list_published`。

只有 `GZH_MCP_ALLOW_PUBLISH=1` 或严格小写 `true` 时才注册 `publish_draft`；每次
调用仍必须显式传 `confirm=true`。修改环境变量后需重启 MCP 客户端以刷新工具列表。

`create_draft` 接收 `articles` 数组。每篇文章至少提供 `title`、HTML `content` 和
普通图文所需的永久封面 `thumb_media_id`。创建后会自动调用 `draft/get`；若标题、
图片数量或正文长度校验失败，结果返回 `verified=false`、`media_id` 和
`verification_errors`，调用方应人工复核，不要直接发布。

## 已知约定

server 无本地状态：`media_id → publish_id` 的映射由调用方记录；
发布结果用 `get_publish_status` 轮询，事后对账用 `list_published`。
