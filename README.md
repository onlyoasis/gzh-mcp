# gzh-mcp

微信公众号发布 MCP server。把"素材上传 → 草稿箱 → 发布"链路封装成标准 MCP 工具，
供本机 MCP 客户端（Claude Code、Codex CLI 等）调用。

## 状态

开发中。设计方案见 [docs/proposal.md](docs/proposal.md)（v1.0，已过 codex 5.6-sol
独立评审，评审记录见 [docs/codex-review.md](docs/codex-review.md)）。

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

## 安装与客户端配置（实现后生效）

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
```

## 已知约定

server 无本地状态：`media_id → publish_id` 的映射由调用方记录；
发布结果用 `get_publish_status` 轮询，事后对账用 `list_published`。
