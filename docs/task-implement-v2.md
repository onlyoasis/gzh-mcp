# 任务书：gzh-mcp v2 实现（官方 API 全量覆盖）

执行者：codex（gpt-5.6-sol，xhigh 推理力度）
委托方：Claude（主控，负责验收与提交）
日期：2026-08-30
基线：v1 已完成并真机验收，`uv run pytest` 基线 **66 个测试全绿**
（server_tools 12 / validation 25 / wechat_client 29）。

## 目标

按 `docs/proposal-v2.md`（v2.0 定稿）实现 47 个新工具、模块拆分与全部测试。
`docs/proposal-v2.md` 是设计契约；`CLAUDE.md` 是项目铁律；两者冲突时先停下
报告，不要自行取舍。

## 动手前必须先查证的事实（授权反驳）

以下事实是设计方核实的，但你不得照单实现——先自己查证官方文档
（developers.weixin.qq.com，以**订阅号文档** /doc/subscription/ 为主），
发现与本文档不符时**以实际为准，并在最终报告中说明差异**：

1. **每个接口的精确路径、HTTP 方法、请求参数、响应字段**。本任务书和
   proposal-v2 写的路径是设计方记忆+部分核对的结果，**必须逐个对官方文档
   核实**。测试 mock 的响应结构必须来自你查证的文档，不是抄本任务书。
2. **datacube 20 个接口各自的 begin_date/end_date 格式与最大时间跨度**
   （逐个详情页核对；跨度表要做成代码里的显式表）。proposal §3.3 列的
   20 个 report 值如有增减，以官方现行文档为准。
3. **freepublish 获取单篇已发布文章的接口名与参数**（proposal 只写了
   "接口名待查证"，工具名 `get_published_article` 不变）。
4. **群发**：sendall/send/preview/get/delete 的完整参数；clientmsgid 的
   官方语义；msgtype 允许集合（mpnews/text/voice/image/music/mpvideo/wxcard
   中哪些适用哪个接口）；mass/send 的 openid 列表数量上限。
5. **永久素材**：video/voice 的格式与大小限制、add_material 的
   description 表单字段（video 的 title/introduction）；batchget_material
   的 type 值集合与 count 上限。
6. **临时素材**：media/upload 的 type 集合与各类型大小限制；media/get 对
   video 返回的 JSON 形状、对图片/语音返回二进制的确认。
7. **菜单**：button/sub_button 数量上限、名称长度限制（中英文规则）、
   addconditional 的 matchrule 字段集合、trymatch/delconditional 参数。
8. **评论**：comment/list、markelect、unmarkelect 的参数形状（含
   comment_id/msg_data_id 等字段语义）。
9. **qrcode/create**：action_name 集合、scene_id/scene_str 的限制、
   expire_seconds 范围、响应字段。
10. **用户**：user/info 的 GET/POST 形态与 lang 合法值；user/info/batchget
    的 openid 数量上限；tags/members/batchtagging 等的 openid_list 上限。
11. **订阅通知**：message/subscribe/bizsend 的参数集合（page/miniprogram
    等可选字段）、touser/template_id 语义。
12. **ticket/getticket**：type 参数、返回字段（ticket/expires_in）。
13. **get_current_autoreply_info、getcallbackip** 的响应形状。
14. **mcp SDK 当前用法**：本仓库已装 mcp 2.1.1，`MCPServer`/`@server.tool`
    用法见现有 server.py——照现有模式写，不要凭记忆换写法。

查证方式：官方文档页 + 仓库现有代码。**禁止**凭训练记忆直接写参数。

## 实现范围

### 模块结构（proposal §6）

```
src/gzh_mcp/
├── server.py           # 按域拆 register_* 函数；两个环境变量闸门集中处理
├── wechat_client.py    # WechatClient 门面（组合各域 mixin，类表面不变）
├── wechat/{base,draft,publish,material,datacube,user,menu,comment,message,misc}.py
├── validation.py       # v1 + datacube 跨度表/菜单结构/消息 msgtype 校验
└── errors.py           # 不变
```

迁移约束：v1 `wechat_client.py` 的传输/token 逻辑迁 `wechat/base.py`，域方法
迁对应域模块；`WechatClient` 组合后**既有方法签名不变**，v1 测试除 import
路径外不得改动语义。

### 工具（名称精确一致，共 47 个新工具）

发布链路：`delete_draft`、`get_published_article`、`delete_published_article`；
素材：`upload_video_material`、`upload_voice_material`、`get_material`、
`delete_material`、`list_materials`、`count_materials`、`upload_temp_media`、
`download_temp_media`；统计：`get_statistics_report`；用户：
`list_users`、`get_user_info`、`batch_get_user_info`、`update_user_remark`、
`create_tag`、`list_tags`、`update_tag`、`delete_tag`、`get_user_ids_by_tag`、
`tag_users`、`untag_users`、`list_blacklist`、`blacklist_users`、
`unblacklist_users`；菜单：`create_menu`、`get_current_menu`、`delete_menu`、
`create_conditional_menu`、`delete_conditional_menu`、
`try_match_conditional_menu`；评论：`list_comments`、`mark_comment_elect`、
`unmark_comment_elect`；群发：`mass_send_by_tag`、`mass_send_by_openids`、
`preview_mass_message`、`get_mass_status`、`delete_mass_message`；定向推送：
`send_custom_message`、`send_template_message`、`send_subscribe_message`；
杂项：`create_qrcode`、`get_jsapi_ticket`、`get_autoreply_config`、
`get_server_ips`。

参数与闸门标注见 proposal §3/§4，按已查证的官方文档补齐参数细节。

### 不可绕过的行为契约（每条都要有对应测试）

- B13 `GZH_MCP_ALLOW_MASS_SEND` 为 `0`/`false`/空串/空格/未设置 →
  tools/list 里**没有** mass_send_by_tag / mass_send_by_openids /
  preview_mass_message；为 `1`/`true` → 有。解析复用 `is_publish_enabled`。
- B14 mass_send_by_tag / mass_send_by_openids 缺 `clientmsgid` 或
  `confirm` 不为 true → 直接拒绝，不发任何 HTTP。
- B15 删除类（delete_draft、delete_published_article、delete_material、
  delete_tag、delete_menu、delete_conditional_menu、delete_mass_message）
  `confirm` 不为 true → 直接拒绝，不发任何 HTTP。
- B16 定向推送（send_custom_message、send_template_message、
  send_subscribe_message）`confirm` 不为 true → 直接拒绝，不发任何 HTTP。
- B17 `get_statistics_report`：report 不在枚举 / 日期非 `YYYY-MM-DD` /
  跨度超过该 report 的跨度表上限 / begin>end → 前置报错，不发 HTTP
  （表驱动测试，覆盖跨度表的代表性行）。
- B18 二进制下载（get_material、download_temp_media）：JSON 响应走既有
  四层错误协议（含 errcode 错误透传）；二进制写 `save_path`；父目录自动
  创建；**目标文件已存在 → 报错不覆盖**；成功返回 `file_path`（绝对路径）
  与 `size`。
- B19 create_menu / create_conditional_menu：button>3、sub_button>5、
  名称超官方长度限制 → 前置报错，不发 HTTP（限制值按你查证的文档）。
- B20 群发与客服消息：msgtype 不在官方允许集合 / 对应内容字段缺失 →
  前置报错，不发 HTTP。
- B21 新增非幂等接口（message/mass/sendall、message/mass/send、
  message/mass/preview、message/custom/send、message/template/send、
  message/subscribe/bizsend）遇网络传输错误 → `UncertainStateError`，
  不重试；新增只读接口全部走 read-only 退避（`-1`/5xx 重试一次）。
- B22 端点映射：47 个新工具每个至少一条用例，断言 HTTP 方法、路径、
  关键 payload 字段（parametrize 组织）。
- B23 v1 行为不回退：B1~B12 对应的既有测试不改语义地通过（允许改
  import 路径）；`publish_draft` 闸门行为不变。
- B24 脱敏延续：新增端点的错误输出同样经 redact（构造含 access_token
  的 errmsg 验证输出已打码）；stdout 仍只有 JSON-RPC。

## 测试纪律（硬要求）

- 全部 pytest + mock（httpx MockTransport 或 monkeypatch），**禁止真实调用
  微信 API**。
- 每个行为契约至少一个用例；mock 响应结构来自你自己查证的官方文档。
- **红灯验证**：新契约逐个退化（删 confirm 检查、改跨度表上限、跳过文件
  已存在检查等），确认对应测试真的失败，再还原。最终报告列出红灯验证过的
  契约编号。
- 若实测与任务书预期不符：说明原因，**禁止修改期望值迁就实现**；确属任务书
  错误的，以实际为准并报告。

## 红线

- **禁止任何 git 操作**（add/commit/branch 等）——主控验收后统一提交。
- 禁止真实调用 api.weixin.qq.com（所有测试全 mock）。
- 禁止读取或修改 ~/.claude/、~/.agents/、.claude/skills/ 下任何文件。
- 禁止把 WECHAT_APPID/WECHAT_SECRET 写进任何文件或测试。
- 只在 /Users/lzc/Projects/tools/gzh-mcp 内写文件。
- 不改 v1 既有工具名与行为语义；不实现 proposal §9 排除项（sns/*、
  shorturl、getarticletotal、群发速度配置、模板行业配置、genShortKey）。
- README 工具表需更新（47 个新工具按域列表）；不改 CLAUDE.md（主控维护）。

## 完成定义

1. `uv run pytest` 全绿，数量相对基线 66 的增量可解释（报告里给出数字）。
2. `uv run gzh-mcp` 可启动（配假 env，stdio 等 stdin 不崩）。
3. 47 个新工具全部注册；`GZH_MCP_ALLOW_MASS_SEND` 两态下 tools/list 差异
   符合 B13。
4. README 工具表与实现一致。

## 报告格式

最终回复（stdout 最后一部分）按此结构：

```
## 查证差异
（任务书/方案说法 vs 官方文档实际，逐条；无差异则写"无"）
## 实现清单
（文件、工具、契约编号 → 测试名）
## 红灯验证记录
（契约编号 → 退化方式 → 观察到的失败）
## 测试结果
（pytest 输出摘要：数量、通过率、相对基线增量）
## 遗留问题
```
