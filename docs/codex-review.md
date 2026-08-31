## 事实核查

1. `draft/add` 字段限制

- 方案说法：`title ≤ 32`、`digest ≤ 120`、`content < 2 万字符 / 1MB`。
- 我的核查结果：
  - `title` 最多 32 个字符：这是当时的文档核对结论；2026-08-31 已被真实
    公众号草稿精确回读推翻，当前实现只校验非空并让平台判定长度。
  - `digest` 当前文档口径是最多 **128 个字符**，不是 120。120 可以作为保守业务限制，但不能写成“官方限制”。
  - `content` 少于 2 万字符且小于 1MB、会移除 JS、外部图片 URL 会被过滤：正确。
  - “字”“字符”“字节”不能混写，尤其 emoji 和扩展 Unicode 的计数可能与 Python `len()` 不一致。
- 结论：**部分不一致**。必须把 `digest ≤ 120` 改为“官方 ≤128；本工具可选采用 ≤120 的保守限制”。参见[微信官方新增草稿文档](https://developers.weixin.qq.com/doc/subscription/api/draftbox/draftmanage/api_draft_add.html)。

2. `freepublish/submit` 异步与状态枚举

- 方案说法：提交后异步处理；`publish_status` 为 0–6。
- 我的核查结果：正确。`errcode=0` 仅表示发布任务被受理，不表示文章成功发表。状态应精确写为：
  - `0`：发布成功
  - `1`：发布中
  - `2`：原创失败
  - `3`：常规失败
  - `4`：平台审核不通过
  - `5`：成功后用户删除全部文章
  - `6`：成功后平台封禁全部文章
- 结论：**一致**。但方案漏掉 `PUBLISHJOBFINISH` 事件回调；stdio MCP 通常无法直接接公网回调，因此第一版只能明确采用轮询和退避策略。参见[提交发布](https://developers.weixin.qq.com/doc/subscription/api/public/api_freepublish_submit.html)和[查询发布状态](https://developers.weixin.qq.com/doc/subscription/api/public/api_freepublish_get.html)。

3. 2025 年 7 月发布接口权限回收

- 方案说法：2025 年 7 月起，个人主体和未认证账号被回收发布接口权限；只有企业主体已认证账号可用。
- 我的核查结果：
  - 当前官方适用范围能够支持最重要的现状结论：个人主体、未认证企业和不支持认证的账号不能依赖 `freepublish/*` 完成 API 发布，通常返回 `48001`。
  - 这项限制针对的是 **`freepublish` 发布能力**，不能扩写成 `draft/add`、素材上传也必然不可用。当前官方适用范围仍将草稿和素材接口单独列出。
  - 本轮官方页面对抓取器拒绝返回正文，我没有找到可独立归档的官方公告来证明“2025 年 7 月”这个精确生效日期。因此“当前权限结论”可信，但方案把日期写成“已核实事实”的证据链不够。
  - `48001` 只是通用的 API 未授权，不能仅凭这个错误码断言具体原因一定是主体类型。
- 结论：**当前权限结论基本一致，但历史日期证据不足，且必须限定为 `freepublish/*`**。目标账号能否使用，最终应查看公众号后台的接口权限和认证状态；`stable_token` 获取成功不能证明有发布权限。

4. `uploadimg` 限制

- 方案说法：只支持 JPG/PNG，图片小于 1MB。
- 我的核查结果：正确；是严格“小于 1MB”，不是“≤1MB”。它与永久素材接口的格式、尺寸限制不同。
- 结论：**一致**。实现必须按真实文件内容检查格式，不能只信扩展名或 `mimetypes.guess_type()`。参见[微信官方素材接口文档](https://developers.weixin.qq.com/doc/subscription/api/material/permanent/api_uploadimage.html)。

5. `stable_token`、旧 token 与 IP 白名单

- 方案说法：`stable_token` 普通模式重复获取同一 token；推荐替代旧接口；40164 表示出口 IP 不在白名单。
- 我的核查结果：
  - 普通模式在有效期内返回当前 token；`force_refresh=true` 会生成新 token 并使旧 stable token 失效。
  - stable token 与旧 `GET /cgi-bin/token` 获取的凭据相互隔离，这一点方案漏了。
  - 多进程仍需协调，不能因为用了 stable token 就取消缓存和并发控制。
  - 公众号调用需要 IP 白名单，`40164` 解释正确。
- 结论：**基本一致但不完整**。`check_connection` 实际只验证凭据和 IP，应改名为 `check_credentials`；它不能证明草稿、发布或群发权限。参见[稳定版 access token](https://developers.weixin.qq.com/doc/offiaccount/Basic_Information/getStableAccessToken.html)和[旧版 access token](https://developers.weixin.qq.com/doc/offiaccount/Basic_Information/Get_access_token.html)。

## 架构意见

- [必须改] “API 层不负责 Markdown→HTML”这个内部边界合理，但当前对外定位不诚实。只接受 `content_html` 和服务端本地 `file_path`，不能宣称“任何 MCP 客户端都能使用同一套发布能力”。建议分成：
  - `wechat_client`：纯微信 HTTP API。
  - MCP 层：`create_draft_from_html`，负责字段校验、外链图片检测和回读验证。
  - Markdown 渲染器作为独立可选适配器，不把 wewrite 的 2000 行主题系统搬进第一版。

- [必须改] 不能只在 description 里提醒外链图片。`create_draft_from_html` 应在调用前解析 HTML，发现非微信正文图 URL、脚本、超限内容就明确失败；创建后调用 `draft/get` 回读，证明微信实际保存的标题、正文和图片没有被过滤。

- [必须改] `delete_draft` 不是“安全工具”。官方明确删除不可撤销，“草稿可重建”是假设，原内容可能没有本地副本。第一版应删除该工具，或与发布工具一样设置独立开关和逐次确认。

- [必须改] 第一版去掉 `mass_send` 和 `get_mass_status`。现役流程没有使用它，风险远大于“实现成本低”。如果以后加入：
  - `clientmsgid` 必须由调用者显式提供，不能可选。
  - 要按字节而不是 Python 字符数校验；方案和参考代码的“32 字符”口径还需重新核对当前群发文档。
  - 必须处理 API 群发保护、管理员确认、原创检查、频率限制和结果不确定状态。

- [必须改] 缺少 `update_draft`。人工复核发现问题后，正常动作应该是更新原草稿，而不是不断创建重复草稿。第一版至少需要 `create/get/update/list`。

- [必须改] `get_draft` 必须返回完整结构，而不是仅返回第一篇正文。参考实现当前只取 `news_item[0].content`，会丢标题、摘要、封面、评论设置和多图文其他文章：[publisher.py](/tmp/gzh-codex-review/wewrite-ref/publisher.py:84)。

- [建议] 支持多图文 `articles[]`，或明确第一版只支持单图文。参考实现已有 `create_draft_articles()`，方案把能力缩成单篇却没有说明：[publisher.py](/tmp/gzh-codex-review/wewrite-ref/publisher.py:49)。

- [建议] 增加只读 `list_published`。它比群发工具更有价值，可用于发布响应丢失后的人工对账；参考实现已经有发布记录查询和 URL 校验：[wechat_growth_api.py](/tmp/gzh-codex-review/wewrite-ref/wechat_growth_api.py:345)。

- [必须改] 方案 A 不是“类型系统防线”，只是启动时缩减工具注册表。漏洞包括：
  - 环境变量一旦启用，就是长期、全会话授权，不等于“本轮用户明确授权”。
  - 必须定义严格真值；`0`、`false`、空格不能因为“变量存在”而启用。
  - MCP 客户端通常缓存工具列表，修改环境变量后必须重启 server/client。
  - 工具一旦可见，prompt injection 或 agent 误判仍可调用。
  - 工具 description 和 MCP annotations 都只是提示，不是安全边界；MCP 官方也明确 annotations 不能代替授权。[MCP 工具安全说明](https://modelcontextprotocol.io/specification/2025-06-18/server/tools)
  - 最低要求是“双闸门”：启动配置允许能力，同时每次发布要求显式 `confirm=true`，并在参数/结果中包含目标账号、草稿标题和 media ID。群发应再使用独立开关。

- [建议] 为所有工具填写准确的 `readOnlyHint`、`destructiveHint`、`idempotentHint`、`openWorldHint`，但不要把它们当强制控制。

- [必须改] 选择 Python 可以，但理由不能是“直接移植即生产验证”。参考代码质量不一致，只能选择性迁移。当前 MCP SDK 已进入 v2；方案里的“FastMCP 风格”和 TypeScript 备选的旧包名 `@modelcontextprotocol/sdk` 都已经过时。Python 应锁定当前 v2 主版本；TypeScript v2 当前使用 `@modelcontextprotocol/server`。[Python SDK](https://github.com/modelcontextprotocol/python-sdk)、[TypeScript SDK](https://github.com/modelcontextprotocol/typescript-sdk)

- [建议] 最终仍选 Python。原因是团队已有 Python 发布代码、测试成本较低，而不是 Python MCP 生态天然优于 TypeScript。HTTP 库只选一个；若 handler 使用异步模型，优先 `httpx.AsyncClient`，不要同时引入 `requests` 和 `httpx`。

- [必须改] 参考实现值得迁移的部分：
  - HTTP 超时、`raise_for_status()`、传输错误/无效 JSON/微信业务错误分层。
  - access token 脱敏。
  - 返回结构类型校验。
  - 发布成功后仅接受 `mp.weixin.qq.com` 文章 URL。
  - `freepublish/get` 的 `article_url` 与 `batchget` 的 `url` 字段不能混用。
  - `clientmsgid` 防重复思想。
  这些集中在 [wechat_growth_api.py](/tmp/gzh-codex-review/wewrite-ref/wechat_growth_api.py:69)。

- [必须改] 参考实现不能照搬的部分：
  - 旧版 token、无锁的全局进程缓存：[wechat_api.py](/tmp/gzh-codex-review/wewrite-ref/wechat_api.py:7)。
  - 上传接口不检查文件存在、真实 MIME、大小，也不调用 `raise_for_status()`：[wechat_api.py](/tmp/gzh-codex-review/wewrite-ref/wechat_api.py:87)。
  - 普通草稿接口只抛泛化 `ValueError`，错误语义不足。
  - `get_draft` 丢失多图文数据。
  - 发布状态成功时只读取第一篇文章 URL。
  - `ensure_ascii=False` 可以保留为生产兼容措施，但 JSON 标准本身支持 `\uXXXX`；不要把参考实现的历史现象写成微信官方协议要求。

## 遗漏风险

- access token 缓存没有 single-flight/锁：并发过期会同时刷新；多个 MCP 进程也会各自刷新。
- `force_refresh` 会使旧 stable token 失效；不能在每个 400xx 上盲目强刷。
- 方案把 `40001/42001` 统一当“token 过期”是错的。错误码含义与 endpoint 有关；token 获取接口上的 `40001` 可表示 AppSecret 错误，不应自动重试。常见可刷新候选通常是 `40014/42001`，仍需按接口语义处理。
- 微信业务错误通常通过 HTTP 200 返回，必须同时检查 HTTP 状态、JSON 结构和 `errcode`。
- 非幂等调用发生连接超时后，状态是“不确定”，不是“失败”。`draft/add`、`freepublish/submit` 不应自动重试，否则可能重复草稿或重复提交。
- `-1`、HTTP 5xx、限流错误只能对只读/确定幂等调用做有限退避；不能统一重试。
- 无数据库意味着无法持久保存 `media_id → publish_id → 终态`。进程重启后容易失去待轮询任务和审计证据。
- `file_path` 指的是 MCP server 主机文件，不是客户端文件；远程客户端和沙箱客户端不可用。
- 任意 `file_path` 会让工具具备上传服务器本地文件的能力。至少限制允许目录、解析符号链接、检查真实 MIME 和大小。
- `WECHAT_SECRET`、access token 不能出现在工具结果、异常 URL、stderr 或请求库异常对象中。参考实现只替换响应消息里的 token，脱敏不完整。
- stdio 的 stdout 是 MCP 协议通道，任何普通日志都会破坏 JSON-RPC；只能写 stderr，且仍需脱敏。
- 应同时返回对象型 `structuredContent` 和文本 fallback，避免旧客户端无法解析；输入 schema 不要依赖过新的复杂 JSON Schema 特性。
- 必须用真实 Claude Code、Codex CLI 和 MCP Inspector 各跑一次 `initialize → tools/list → tools/call`，单测 SDK handler 不等于客户端兼容。
- 永久封面素材会消耗素材库额度；反复上传同一封面会留下垃圾。方案既不管理素材，也没有复用策略。
- `upload_content_image`、`upload_cover_image`、`create_draft` 都会修改微信端状态，不能统称为“安全/只读”。
- 创建草稿成功不等于内容正确。微信会清洗 HTML、CSS、链接和图片，必须回读或至少提供人工预览。
- 未处理封面素材与正文图不同的格式和大小限制。
- 未处理目标账号误配。发布前至少返回脱敏 AppID/账号标识和草稿标题，避免把文章发到错误公众号。
- `48001` 是通用未授权，可能是账号类型、认证状态或具体接口权限，不应映射成唯一原因。
- 评论能力、原创声明、转载判断、赞赏、内容来源等字段可能影响审核或导致失败，当前 schema 没有表达。
- freepublish 不等于群发：文章展示位置、是否推送粉丝、是否占群发额度不同，工具说明必须明确。
- 群发可能触发管理员确认、风险操作保护、原创检查、频率限制和账号处罚；只轮询 `msg_status` 不足。
- 内容合规、版权、医疗/金融等敏感表达、诱导关注、AI 生成内容和平台风控没有任何发布前门禁。
- `publish_status=0` 后文章仍可能进入 5/6；“曾成功”不等于“当前仍可访问”。
- 官方 API 权限和字段会变；需要把官方文档 URL、核对日期和目标账号实测结果固化为验收证据，而不是只写“已核实”。

## 总体结论

**可行但需修改**：API 抽取方向正确，但当前方案错误地把长期环境变量当逐次授权、把不可撤销删除当安全操作，并遗漏幂等性、完整草稿结构、真实客户端兼容和发布后对账，按现稿实现会产生误发、重复提交和错误成功判断。
