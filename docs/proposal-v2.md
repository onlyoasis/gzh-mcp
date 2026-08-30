# gzh-mcp 方案 v2：官方 API 全量覆盖

版本：v2.0（用户确认"全量补齐"档位，2026-08-30 定稿）
前置：docs/proposal.md（v1，发布链路 10 工具，已真机验收）
分工：本方案为设计契约；实现由 codex（gpt-5.6-sol）按 docs/task-implement-v2.md
执行；验收由 Claude 独立完成（测试/diff/红灯复核/真机 best-effort）。

## 1. 目标与边界

v1 定位"发布通道"。v2 扩展为公众号官方服务器间 API 的全量 MCP 覆盖：素材库
管理、数据统计、用户/标签/黑名单、菜单、评论、群发、定向消息推送、杂项能力。

- **v1 的 10 个工具名称与行为语义不变**（纯增量；现有测试语义不回退）。
- `file_path`/`save_path` 仍指 MCP server 所在主机的本地文件，仅本机场景。
- 无状态原则不变：不落库、不落盘（唯一例外：下载类工具按调用方指定的
  `save_path` 写文件，这是工具的本职输出，不是缓存）。

## 2. 官方 API 事实（核对状态标注）

以下为设计方已核对的事实；**未标注"已核对"的接口细节（路径/参数/响应字段/
限制）由实现方在动手前逐个查证官方文档**，查证清单见任务书。

1. 官方文档已拆分为订阅号（/doc/subscription/）与服务号（/doc/service/）
   两套，cgi-bin 接口基本一致；本项目以**订阅号文档**为主要参照。
   [已核对 2026-08-30]
2. `cgi-bin/shorturl` 长链接转短链接**已被官方停用**（公告：扫码识别能力
   提升后不再需要）→ 排除。[已核对 2026-08-30]
3. `freepublish/delete`：`article_id` 必填；`index` 可选、从 1 开始，
   **不填或填 0 删除该 article_id 下全部文章**；操作不可逆；**仅认证账号
   （企业主体）可调用**，个人主体预期 48001。[已核对 2026-08-30]
4. datacube 现行接口共 21 个（用户 2、图文 10、消息 7、接口分析 2）；
   `getarticletotal` 已停止维护（替代方向为"发表内容"新系列）→ 排除，
   **纳入 20 个**；数据统计向认证账号开放，个人主体预期 48001。
   [清单已核对 2026-08-30；各接口时间跨度限制待实现时逐个核对]
5. `material/get_material`：图文素材返回 JSON（news_item）；视频返回 JSON
   （title/description/down_url）；**图片、语音直接返回二进制内容**。
   [已核对 2026-08-30]

## 3. 工具清单（新增 47 个）

### 3.1 发布链路补齐（3）

| 工具 | 映射 API | 闸门 |
|---|---|---|
| `delete_draft(media_id, confirm)` | draft/delete | confirm |
| `get_published_article(article_id)` | freepublish 获取单篇已发布文章（接口名待查证） | 只读 |
| `delete_published_article(article_id, index=None, confirm)` | freepublish/delete | confirm |

### 3.2 素材管理（8）

| 工具 | 映射 API | 闸门 |
|---|---|---|
| `upload_video_material(file_path, title, introduction)` | material/add_material?type=video | 常规写 |
| `upload_voice_material(file_path)` | material/add_material?type=voice | 常规写 |
| `get_material(media_id, save_path)` | material/get_material | 只读（见 §5.1） |
| `delete_material(media_id, confirm)` | material/del_material | confirm |
| `list_materials(material_type, offset=0, count=20)` | material/batchget_material | 只读 |
| `count_materials()` | material/get_materialcount | 只读 |
| `upload_temp_media(file_path, media_type)` | media/upload | 常规写 |
| `download_temp_media(media_id, save_path)` | media/get | 只读（见 §5.1） |

参数名刻意用 `material_type`/`media_type`，避免与 Python 内建 `type` 混淆。

### 3.3 数据统计（1 个工具覆盖 20 个接口）

`get_statistics_report(report, begin_date, end_date)` → `POST /datacube/{report}`。

`report` 为枚举，20 个值与官方接口一一对应：

- 用户：`getusersummary`、`getusercumulate`
- 图文（旧系列）：`getarticlesummary`、`getuserread`、`getuserreadhour`、
  `getusershare`、`getusersharehour`
- 图文（发表内容新系列）：`getarticleread`、`getarticleshare`、
  `getbizsummary`、`getarticletotaldetail`
- 消息：`getupstreammsg`、`getupstreammsghour`、`getupstreammsgweek`、
  `getupstreammsgmonth`、`getupstreammsgdist`、`getupstreammsgdistweek`、
  `getupstreammsgdistmonth`
- 接口分析：`getinterfacesummary`、`getinterfacesummaryhour`

不拆 20 个工具的理由：接口完全同构（begin_date/end_date POST），拆开只
膨胀 tools/list。每个 report 的**最大时间跨度表**本地维护、前置校验（表值
以官方各接口详情页为准，见任务书查证项）。

### 3.4 用户/标签/黑名单（14）

| 工具 | 映射 API | 闸门 |
|---|---|---|
| `list_users(next_openid="")` | user/list | 只读 |
| `get_user_info(openid, lang="zh_CN")` | user/info | 只读 |
| `batch_get_user_info(openid_list)` | user/info/batchget | 只读 |
| `update_user_remark(openid, remark)` | user/info/updateremark | 常规写 |
| `create_tag(name)` | tags/create | 常规写 |
| `list_tags()` | tags/get | 只读 |
| `update_tag(tag_id, name)` | tags/update | 常规写 |
| `delete_tag(tag_id, confirm)` | tags/delete | confirm |
| `get_user_ids_by_tag(tag_id, next_openid="")` | tags/members/getidlist | 只读 |
| `tag_users(tag_id, openid_list)` | tags/members/batchtagging | 常规写 |
| `untag_users(tag_id, openid_list)` | tags/members/batchuntagging | 常规写 |
| `list_blacklist(next_openid="")` | tags/members/getblacklist | 只读 |
| `blacklist_users(openid_list)` | tags/members/batchblacklist | 常规写（可逆） |
| `unblacklist_users(openid_list)` | tags/members/batchunblacklist | 常规写 |

### 3.5 菜单（6）

| 工具 | 映射 API | 闸门 |
|---|---|---|
| `create_menu(buttons)` | menu/create | 常规写 |
| `get_current_menu()` | menu/get | 只读 |
| `delete_menu(confirm)` | menu/delete | confirm |
| `create_conditional_menu(buttons, match_rule)` | menu/addconditional | 常规写 |
| `delete_conditional_menu(menu_id, confirm)` | menu/delconditional | confirm |
| `try_match_conditional_menu(user_id)` | menu/trymatch | 只读 |

### 3.6 评论（3）

`list_comments`（comment/list，只读）、`mark_comment_elect`
（comment/markelect）、`unmark_comment_elect`（comment/unmarkelect），
参数形状以官方文档为准。需要留言功能权限。

### 3.7 群发（5，环境变量闸门）

| 工具 | 映射 API | 闸门 |
|---|---|---|
| `mass_send_by_tag(...)` | message/mass/sendall | env + confirm + clientmsgid 必填 |
| `mass_send_by_openids(...)` | message/mass/send | env + confirm + clientmsgid 必填 |
| `preview_mass_message(...)` | message/mass/preview | env（无 confirm，单发预览） |
| `get_mass_status(msg_id)` | message/mass/get | 只读，不闸 |
| `delete_mass_message(msg_id, article_idx, confirm)` | message/mass/delete | confirm |

群发消息体为透传结构：调用方给 `{"msgtype": ..., ...}`，本地只校验 msgtype
在官方允许集合内且对应字段存在（见任务书查证项），不做内容加工。

### 3.8 定向消息推送（3，confirm）

| 工具 | 映射 API |
|---|---|
| `send_custom_message(openid, message, confirm)` | message/custom/send |
| `send_template_message(openid, template_id, data, url=None, confirm)` | message/template/send |
| `send_subscribe_message(openid, template_id, data, confirm)` | message/subscribe/bizsend |

### 3.9 杂项（4）

`create_qrcode`（qrcode/create，常规写）、`get_jsapi_ticket`
（ticket/getticket?type=jsapi，只读）、`get_autoreply_config`
（get_current_autoreply_info，只读）、`get_server_ips`（getcallbackip，只读）。

## 4. 风险分层与闸门

| 层级 | 覆盖 | 闸门 |
|---|---|---|
| 只读 | 全部查询/列表/统计/下载 | 无 |
| 常规写 | 上传/建草稿/标签/菜单/备注/精选评论/拉黑(可逆) | 无 confirm（沿用 v1 先例） |
| 删除类 | delete_draft、delete_published_article、delete_material、delete_tag、delete_menu、delete_conditional_menu、delete_mass_message | `confirm=true` 必传，否则拒绝且不发 HTTP；destructiveHint=True |
| 定向推送 | send_custom/template/subscribe_message | `confirm=true` 必传 |
| 全量推送 | publish_draft（v1）、mass_send_by_tag、mass_send_by_openids | 环境变量 + `confirm=true`；群发另**强制调用方提供 `clientmsgid`**（官方参数可选，本工具设为必填以防重复推送） |

环境变量：

- `GZH_MCP_ALLOW_PUBLISH`：控制 `publish_draft`（v1 不变）。
- `GZH_MCP_ALLOW_MASS_SEND`：**新增**，同一严格真值解析（仅 `1`/`true`），
  控制 `mass_send_by_tag`、`mass_send_by_openids`、`preview_mass_message`。

两者分离的理由：已启用发布闸门的用户不应"顺手"获得群发能力——群发推给
全部粉丝，爆炸半径与发布差一个量级。`get_mass_status` 是只读查询，不闸。

## 5. 关键机制

### 5.1 二进制下载

`get_material` 与 `download_temp_media` 增加 `save_path` 参数：

- 响应 Content-Type 为 JSON → 走既有四层错误协议（微信对错误统一返回
  errcode JSON，包括二进制接口）。
- 否则视为二进制 → 写入 `save_path`；父目录不存在自动创建；**目标文件已
  存在则报错，不覆盖**；返回 `{"file_path": 绝对路径, "size": 字节数}`。
- 视频/图文类型返回 JSON：原样透传（视频内含 `down_url` 供调用方自行下载）。
- 工具注记为只读（对微信端状态只读），description 说明会在本机写文件。

### 5.2 非幂等语义（v1 铁律 3 的扩展）

传输超时返回"状态不确定"错误的接口集合扩展为：draft/add、
freepublish/submit（v1）+ **message/mass/sendall、message/mass/send、
message/mass/preview、message/custom/send、message/template/send、
message/subscribe/bizsend**（超时后盲目重试会重复推送）。
删除类接口幂等（重删报错但无副作用），不设 uncertain。

### 5.3 前置校验（validation.py 扩展）

- datacube：report 枚举 + `YYYY-MM-DD` 格式 + 每 report 跨度表。
- 菜单：button ≤3、sub_button ≤5、名称长度限制（数值以官方文档为准）。
- 群发/客服消息：msgtype ∈ 官方允许集合，且对应内容字段存在。
- 上传类沿用 v1 魔数校验思路；video/voice 的格式与大小限制以官方文档为准。

### 5.4 重试语义

新增只读接口全部走 v1 的 read-only 有限退避（`-1`/5xx 重试一次）；
新增写接口不自动重试（与 v1 一致）。

## 6. 模块结构

```
src/gzh_mcp/
├── server.py           # 工具注册，按域拆 register_* 函数；闸门逻辑集中
├── wechat_client.py    # WechatClient 门面 = Base + 各域 mixin 组合（唯一入口，类表面不变）
├── wechat/
│   ├── __init__.py
│   ├── base.py         # stable_token 缓存/_api_request/_request_json/二进制请求（自 v1 wechat_client.py 迁移）
│   ├── draft.py        # 草稿域（v1 方法迁移）
│   ├── publish.py      # freepublish 域（v1 迁移 + 新增）
│   ├── material.py     # 素材域（v1 上传迁移 + 新增）
│   ├── datacube.py     # 统计域
│   ├── user.py         # 用户/标签/黑名单域
│   ├── menu.py         # 菜单域
│   ├── comment.py      # 评论域
│   ├── message.py      # 群发 + 定向推送域
│   └── misc.py         # 二维码/ticket/自动回复/服务器 IP
├── validation.py       # v1 校验 + §5.3 新增
└── errors.py           # 不变
```

现 `wechat_client.py` 中的传输/token 代码迁到 `wechat/base.py`，域方法迁到
对应模块，`WechatClient` 通过组合保持全部既有方法签名——v1 测试不经修改
（除 import 路径）必须继续通过。

## 7. 测试策略

- **端点映射测试（parametrize）**：47 个新工具每个至少一条用例，断言 HTTP
  方法、路径、关键 payload 字段。mock 响应结构来自实现方查证的官方文档。
- 闸门/confirm/校验/二进制/跨度表：每个行为契约至少一条用例（任务书 B13~B24）。
- 全部 mock（httpx MockTransport），禁止真实调用。
- 红灯纪律：每个新契约退化验证后还原，报告清单（v1 惯例）。

## 8. 验收标准

1. `uv run pytest` 全绿；测试数量相对基线 66 的增量可解释。
2. v1 行为不回退（B1~B12 对应测试不变绿转红）。
3. Claude 独立复核：通读 diff + 抽样红灯复验 + stdio 冒烟。
4. 真机 best-effort：个人主体账号上，**48001 等权限错误正确透传即算符合
   预期**；可真机验证的（素材读写、草稿删除等）实测通过；结果记入
   docs/api-verification.md（v2 章节）。
5. README 工具表与 CLAUDE.md 与实现一致。

## 9. 非目标

- 网页授权 sns/*（需要回调域名与浏览器跳转，非服务器间 API）。
- shorturl（官方已停用）、getarticletotal（停止维护）。
- 群发速度配置、模板行业配置类接口。
- genShortKey（服务号短 key 托管，超出本次确认范围）。
- 消息回调/事件推送接收（stdio server 无回调入口，v1 已定轮询模式）。

## 10. 已知取舍

- **工具数量 ~57**：agent 端 tools/list 变大。接受——每个工具薄而清晰，
  好过少数复合工具藏隐式行为。
- **大量接口在个人主体账号上 48001**：工具照常实现（按官方文档），权限由
  账号决定；真实验收覆盖受限是已知成本。
- **群发强制 clientmsgid**：比官方更严，换取防重确定性。
- **下载工具写本地文件**：唯一落盘点，路径由调用方显式提供，不覆盖已有文件。
