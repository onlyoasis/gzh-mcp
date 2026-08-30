# gzh-mcp v1 接口查证记录

核对日期：2026-08-30。

本记录只描述文档与本地依赖核对结果。本次实现和测试没有请求
`api.weixin.qq.com`，所有微信业务响应均由 `httpx.MockTransport` 提供。

## 本地依赖实测

- `uv 0.11.6` 使用 Python 3.12.13 建立项目环境。
- `mcp 2.1.1` 的高层服务类为
  `mcp.server.mcpserver.server.MCPServer`，可从 `mcp.server` 导入；v1 方案中所称
  `FastMCP` 已在 v2 更名。`@server.tool()` 返回带类型标注的 `dict` 时，SDK 自动
  生成文本 `content`、对象型 `structuredContent` 和 output schema。
- `httpx 0.28.1` 的 `AsyncClient.request()` 支持 `content`、`files`、`params`；
  `MockTransport` 支持同步或异步 handler；`Timeout` 支持总超时与单独 connect
  超时。本实现用 `content=json.dumps(..., ensure_ascii=False).encode("utf-8")`
  明确控制中文 JSON 字节。

参考：

- [MCP Python SDK v2](https://py.sdk.modelcontextprotocol.io/)
- [MCP v1 到 v2 迁移指南](https://py.sdk.modelcontextprotocol.io/migration/)
- [MCP 结构化输出](https://py.sdk.modelcontextprotocol.io/servers/structured-output/)
- [HTTPX Async 支持](https://www.python-httpx.org/async/)
- [HTTPX multipart 上传](https://www.python-httpx.org/quickstart/#sending-multipart-file-uploads)
- [HTTPX 超时](https://www.python-httpx.org/advanced/timeouts/)

## 微信官方接口字段

### Stable Access Token

官方接口为 `POST /cgi-bin/stable_token`，请求体包含 `grant_type`、`appid`、
`secret`，可选 `force_refresh`；响应包含 `access_token`、`expires_in`。普通模式
不会在有效期内更新 token，强制刷新会使旧 token 失效；当前有效期不超过 7200
秒，平台普通模式提前 5 分钟更新。本实现也提前 300 秒使进程内缓存失效，并用
`asyncio.Lock` 合并并发获取。

参考：[获取 Stable Access Token](https://developers.weixin.qq.com/doc/service/api/base/api_getstableaccesstoken.html)

### 更新草稿

`POST /cgi-bin/draft/update` 的请求体精确形状为：

```json
{
  "media_id": "MEDIA_ID",
  "index": 0,
  "articles": {
    "article_type": "news",
    "title": "标题",
    "content": "<p>正文</p>"
  }
}
```

`articles` 是单个对象，不是数组；`index` 从 0 开始。

参考：[更新草稿](https://developers.weixin.qq.com/doc/service/api/draftbox/draftmanage/api_draft_update)

### 草稿与发布响应

- `draft/batchget`：`total_count`、`item_count`、`item[]`；每项包含
  `media_id`、`content.news_item[]`、`update_time`。
- `freepublish/get`：`publish_id`、`publish_status`、成功时的 `article_id` 与
  `article_detail.count/item[].idx/article_url`，失败文章位置为 `fail_idx[]`。
- `freepublish/batchget`：`total_count`、`item_count`、`item[]`；每项包含
  `article_id`、`content.news_item[]`、`update_time`。

测试 mock 使用上述字段名，没有把相邻记录或截断文本当成同一响应。

参考：

- [获取草稿列表](https://developers.weixin.qq.com/doc/service/api/draftbox/draftmanage/api_draft_batchget)
- [发布状态查询](https://developers.weixin.qq.com/doc/service/api/public/api_freepublish_get)
- [获取已成功发布列表](https://developers.weixin.qq.com/doc/service/api/public/api_freepublish_batchget)

### 图片限制

正文图片接口 `media/uploadimg` 官方说明为仅支持 JPG/PNG，大小“必须在 1MB
以下”，所以恰好 1 MiB 也拒绝。格式判定使用文件魔数：JPEG `FF D8 FF`、PNG
`89 50 4E 47`。永久图片素材接口允许 BMP/PNG/JPEG/JPG/GIF，图片不超过 10MB；
本实现同样使用魔数，不依赖扩展名。

参考：

- [上传发表内容中的图片](https://developers.weixin.qq.com/doc/service/api/material/permanent/api_uploadimage)
- [新增永久素材](https://developers.weixin.qq.com/doc/service/api/material/permanent/api_addmaterial)

