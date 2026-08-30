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


## 真实账号全链路验收（2026-08-30）

用另一项目（wewrite）配置的真实公众号凭据（仅注入子进程环境变量，不落盘），
通过 MCP stdio 协议调用 `gzh-mcp` 进程，对 10 个工具逐一实测。发布动作经
用户明确授权（`GZH_MCP_ALLOW_PUBLISH=1` + `confirm=true`）。

### 结果

| 工具 | 结果 |
| --- | --- |
| check_credentials | ✅ IP 白名单内，token 获取成功 |
| upload_content_image | ✅ 返回 mmbiz.qpic.cn 正文图 URL |
| upload_cover_image | ✅ 返回永久素材 media_id |
| create_draft | ✅（修复 data-src 计数后 verified=true） |
| get_draft | ✅（含 40007：草稿发布后被微信移除，属预期） |
| update_draft | ✅ errcode=0，摘要更新生效 |
| list_drafts | ✅ 附带 total_count |
| publish_draft | ✅（修复整型 publish_id 后全链路成功） |
| get_publish_status | ✅ publish_status=0 + article_id |
| list_published | ✅ 两条测试文章可对账 |

### 发现并修复的两个真实 bug

1. **create_draft 回读验证误报**：微信保存草稿会把 `img` 的 `src` 归一化为
   `data-src`（懒加载），回读正文里 `src` 消失，旧 `inspect_article_html`
   只统计 `src`，导致所有带图文章 `verified=false`。修复：`src` 与
   `data-src` 均计入图片计数。回归测试
   `test_b11_create_draft_verified_when_wechat_rewrites_src_to_data_src`
   （修复前红：`第 0 篇图片数量不一致 expected=1 actual=0`，与线上实测一致）。
2. **publish_draft 整型 publish_id 误报失败**：`freepublish/submit` 实际返回
   `"publish_id": 2247483949`（JSON 整数，`get_publish_status` 回显同为
   整数）。旧代码只接受 str，抛「缺少 publish_id」——而文章实际已发布成功，
   属最危险的"非幂等动作成功却报错"。修复：接受 `str | int`，统一转 str
   返回；报错信息附带实际返回字段名。回归测试
   `test_b12_publish_draft_accepts_integer_publish_id`（修复前红，错误与
   线上一致）。

### 其他实测结论

- 发布成功的草稿会被微信从草稿箱移除，之后 `draft/get` 返回 40007
  `invalid media_id`，调用方不应视为异常。
- 该账号（个人主体）freepublish 可用，未出现 48001。
- freepublish 属"发布"而非"群发"，不推送粉丝、不占群发次数，测试成本可控。
- 两条【测试】文章已留在账号主页（article_id `Hf0B...Big03pj5` 与
  `Hf0B...AzOYoRPpx`）；v1 无删除工具，如需清理在 mp.weixin.qq.com 手动删除。
