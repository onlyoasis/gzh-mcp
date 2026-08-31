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

### 2026-08-31 标题上限纠正

writer-agent MCP 上线验收发现：一个 39 个 Unicode 字符、83 个 UTF-8 字节的标题
已经由同一真实公众号成功保存，`draft/batchget` 也能精确回读原题；本地原有
`title <= 32` 校验却在请求到达微信前错误拒绝。由于真实平台证据与旧文档核对结论
冲突，当前只保留标题非空校验，长度交由微信平台按当前契约判定，不截断标题。

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

## v2 验收记录（2026-08-30）

实现：codex（gpt-5.6-sol，xhigh）；独立验收：Claude（主控）。

### 执行过程

codex 分三轮完成：前两轮各运行约 33 分钟后被运行环境的后台任务时限强制
终止（rollout 无内部错误，属外部 SIGKILL；非 codex 或用户行为）；第三轮以
`start_new_session=True` 脱离任务管理独立运行，5 分钟收尾。三轮的工作文件
全部保留在工作树中，最终一轮完成盘点与补齐。

### 独立验收结果

- `uv run pytest` 主控重跑：**179 passed**（基线 66 + v2 新增 112 + 主控
  补 1，增量可解释；实现方自报 178，主控修复缺陷后 +1）。
- 代码通读：`wechat/` 包 9 模块 + server.py 47 工具注册 + validation 扩展，
  v1 语义（token single-flight、40014/42001 刷新、read-only 退避、
  非幂等 uncertain、create_draft 回读验证、整型 publish_id 修复）全部保留；
  `test_server_tools.py` 仅 2 处断言由相等放宽为子集（v2 默认工具集扩大所
  必需，闸门语义保留）。
- 红灯复验（主控亲自退化 → 确认变红 → 还原）：B13 群发闸门退化为恒 True
  → 6 failed；B15 仅移除 delete_menu 的 confirm → 精确 1 failed；B18 移除
  下载已存在前置检查 → 1 failed（open("xb") 兜底救不了断言，测试有效）。
- stdio 冒烟：完整 JSON-RPC 握手后 tools/list 返回 **53 个工具**（10 v1 +
  47 v2 − 1 发布闸 − 3 群发闸），stdout 全为合法 JSON-RPC，stderr 无敏感信息。

### 官方文档核对（主控独立执行）

| 项 | 任务书/方案 | 官方实际 | 处置 |
|---|---|---|---|
| 标签下粉丝列表 | `/tags/members/getidlist` | `POST /cgi-bin/user/tag/get`（tagid+next_openid） | codex 纠正正确，采纳 |
| 单篇已发表文章 | 接口名待查证 | `POST /cgi-bin/freepublish/getarticle` | 采纳 |
| 菜单名称限制 | 中英文字符口径 | UTF-8 字节：一级 16B、二级 60B | codex 纠正正确，采纳 |
| datacube 跨度表 | 待逐个核对 | 20 项跨度值与官方详情页一致（新系列 4 项均 1 天） | 采纳 |
| 临时素材限制 | — | image 2M / voice 2M / video 10M / thumb 64KB | 实现正确 |
| **永久语音限制** | （codex 实现 5M） | **2M，mp3/wma/wav/amr**（add_material 页逐字核对） | **缺陷，已修** |

### 验收发现并修复的缺陷（主控修复，红灯闭环）

**upload_voice_material 大小上限 5MB，官方为 2M**。codex 未读到该文档页
原文（其报告中已声明），推测受第三方文档干扰。修复：`validate_permanent_media`
voice 上限 5M→2M；补回归测试 `test_permanent_voice_limit_is_official_2mb`
（恰好 2MB 通过、2MB+1 拒绝；修复前红 `DID NOT RAISE`，修复后绿）。

### 真机 best-effort（个人主体账号）

| 接口 | 结果 |
|---|---|
| check_credentials / get_server_ips / get_autoreply_config / get_jsapi_ticket | ✅ |
| list_users（4 粉丝）/ list_tags / list_blacklist | ✅ |
| count_materials（68 图）/ list_materials / list_drafts（7）/ list_published（27） | ✅ |
| datacube getusersummary（单日） | ✅ 返回空集（个人号无统计异常透传） |
| get_current_menu | errcode=46003 menu no exist（账号无菜单，业务错误正确透传） |
| create_tag → delete_tag 闭环 | ✅ 建标签 100 后即删，已清理 |

群发/定向推送/评论类接口按红线未真机调用（外部可见行为，需用户逐次授权）。

### 边界合规记录

- codex 第一轮曾读取 `~/.agents/skills/skill-router/SKILL.md` 与
  `~/.codex/memories/MEMORY.md`（违反"禁读 ~/.agents/"指令；内容为其自身
  技能生态，未涉及本项目凭据，无害，记录在案）。
- 全程无 git 写操作、无微信业务 API 真实调用（测试全 mock）、无凭据落盘。

## v2 真机全量验收（2026-08-30，第二次）

承接上一节 mock 级验收，本次经用户授权用真实账号走 MCP stdio 协议对 v2 的
53 个无闸门工具做全量真机验证（与 v1 验收同一凭据来源）。发布/群发闸门工具
不注册（`tools/list` 恰为 53，与 stdio 冒烟一致）。

### 直接真机调用：43 个工具全部符合预期

- **用户/标签**：list_users（4 粉丝）、get_user_info、batch_get_user_info、
  update_user_remark（设值→回读→还原）、create_tag、update_tag、tag_users、
  get_user_ids_by_tag（回读到）、untag_users、delete_tag（含负闸门）、
  list_tags、list_blacklist。
- **素材**：count_materials、list_materials（image/voice）、get_material
  （永久素材下载落盘 2090B）、upload_temp_media、download_temp_media（回环）、
  upload_voice_material（16KB WAV）、upload_video_material（2.8KB MP4，经
  ffmpeg 生成）、delete_material（语音/视频均即时删除）。
- **草稿/发布**：list_drafts、list_published、get_published_article、
  create_draft（thumb 为空被微信 40007 拒绝→换真实封面 verified=true）、
  delete_draft（建删回环）、delete_published_article（负闸门 + 删除 2 篇
  v1 遗留测试文章 + 对账删净）。
- **菜单**：create_menu、get_current_menu、delete_menu、
  create_conditional_menu、try_match_conditional_menu、
  delete_conditional_menu（见下方修复）。
- **统计/杂项**：get_statistics_report（6 个报告 + 跨度本地拦截）、
  get_jsapi_ticket、get_autoreply_config、get_server_ips、check_credentials、
  list_comments（该号可用，errcode 0，评论为空）、get_mass_status
  （40059 业务错误透传）。
- get_draft/update_draft/publish_draft 为 v1 已真机验证语义，v2 重构未改；
  整型 publish_id 修复确认保留（wechat/publish.py）。

### 发现并修复的 bug（第三个整型 ID 案例）

**delete_conditional_menu 拒绝整型 menuid**：`menu/addconditional` 实际返回
`"menuid": 425787302`（JSON 整数），工具参数声明为 str，agent 把 create 的
返回原样回传给 delete 时被 pydantic `string_type` 拒绝，create→delete 自然
工作流被打断。修复：server 参数与 client 方法接受 `int | str`，payload 归一化
为字符串（与 publish_id 同模式）。回归测试 b25 两个（server 层整型入参、
client 层 payload 归一化 + bool 拒绝），均先红后绿；修复后真机用整型
menuid=425787305 完整走通建→匹配→删。

### 微信业务规则实测记录（非 gzh-mcp 缺陷）

| errcode | 场景 | 结论 |
| --- | --- | --- |
| 65303 | 无默认菜单时建个性化菜单 | 需先 create_menu |
| 65320 | match_rule 用 sex 圈人 | sex/city/province 定向违反隐私限制，用 tag_id |
| 65301 | 默认菜单删除后再删个性化菜单 | 删默认菜单会连带清掉个性化菜单 |
| 48001 | create_qrcode | 该个人号无二维码权限，业务错误正确透传 |
| 46003/40059/40007 | 无菜单 / 无效 msg_id / 无效 thumb | 业务错误透传正确 |

### 红线未真机调用（12 个，需用户逐次授权）

群发三件套（mass_send_by_tag / mass_send_by_openids / preview_mass_message，
闸门未开即未注册）、send_custom_message、send_template_message、
send_subscribe_message、blacklist_users、unblacklist_users（不碰真实粉丝）、
mark_comment_elect / unmark_comment_elect（无真实评论可操作，且为公开状态）。
publish_draft 本轮未重发（v1 已验证，重发会新增公开文章）。

### 收尾状态（全部还原/清理）

published 25 篇（2 条 v1 测试文章已删）、drafts 7 篇（真实草稿未动）、
素材 image=68/voice=0/video=0（测试上传已删）、标签仅剩默认「星标组」、
菜单无（46003）、用户备注已还原。
