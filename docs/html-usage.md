# 正文 HTML 使用说明

`gzh-mcp` 不做排版：`create_draft` / `update_draft` 接受的是**已排版的微信
HTML**，Markdown → HTML 的转换由调用方（writer 等）完成。本文说明这段
HTML 的正确写法、图片引用方式、本地校验规则与平台真实行为，依据为
`src/gzh_mcp/validation.py`、`src/gzh_mcp/wechat/draft.py` 与
`docs/api-verification.md` 的真机证据。

## 1. HTML 用在哪里

| 工具 | 参数 | 说明 |
|---|---|---|
| `create_draft` | `articles[].content` | 每篇文章的 HTML 正文，多图文传数组 |
| `update_draft` | `article.content` | 按 `index` 更新草稿中的单篇，校验规则完全相同 |

`articles` 数组元素即微信 `draft/add` 的 article 对象，未做本地限制的字段
（`author`、`content_source_url`、`need_open_comment` 等）会原样透传给微信。

## 2. 本地硬校验（发出 HTTP 请求前）

以下三条在本地解析 HTML 强制执行，失败不发任何请求，错误信息直达 MCP
调用方：

| # | 规则 | 拒绝时的错误信息 |
|---|---|---|
| 1 | `content` 必须是非空字符串 | `content 必须是非空字符串` |
| 2 | 禁止 `<script>` 标签（大小写不敏感，`<SCRIPT>` 同样拒绝） | `content 不能包含 script 标签` |
| 3 | 每个 `<img>` 的 `src`（或 `data-src`）必须是 `http(s)://` 协议且域名为 `mmbiz.qpic.cn` / `mmbiz.qlogo.cn` | `content 含非微信正文图片 URL: <URL 列表>` |

关于图片域规则：

- **为什么**：微信保存草稿时会过滤外链图片，先在本地报错可以避免「创建
  成功但图全丢」的静默失败。
- 相对路径（`<img src="a.png">`）、其他域名、非 http(s) scheme 一律拒绝。
- 没有 `src`/`data-src` 属性的 `<img>` 不计入图片数，也不会触发拒绝。

## 3. 不做本地限制、交由微信平台判定的项

- **标题长度**：只校验非空。真机实测 39 个 Unicode 字符（83 个 UTF-8 字节）
  可正常保存并精确回读，旧的本地 32 字符上限已移除。
- **正文长度**：只校验非空。真机实测 24061 字符正文可保存，旧的 2 万字符
  上限已移除。超限由微信按当前契约报业务错误（errcode 透传）。
- **摘要 `digest`**：仍保留本地保守限制 ≤ 120 字符（官方上限 128）。

## 4. 正文图片：先上传、后引用

HTML 里的图片必须先经 `upload_content_image` 上传到微信，用返回的 URL 替换
`src`：

```
upload_content_image("/path/a.png")
→ {"url": "https://mmbiz.qpic.cn/mmbiz_png/xxxx.png"}

HTML 中写：<img src="https://mmbiz.qpic.cn/mmbiz_png/xxxx.png">
```

`upload_content_image` 的约束：

- 只接受 **JPEG / PNG**，按文件魔数判定真实格式（扩展名伪装无效，GIF/BMP
  会以 `图片真实格式必须是 JPEG 或 PNG` 拒绝）。
- **严格小于 1MB**（恰好 1MiB 也拒绝）。
- `file_path` 是 MCP server 所在主机的本地文件路径（server 与客户端须同机）。

## 5. 封面与图片帖（不写在 HTML 里）

- **封面**：走 `upload_cover_image` 返回的 `thumb_media_id` 字段，不是
  HTML 的一部分。支持 JPEG/PNG/GIF/BMP，≤ 10MB。
- **图片帖**（`article_type=newspic`）：`content` 只是说明文字，图片由
  `image_info.image_list[].image_media_id` 提供——1～20 个非空永久素材
  media_id（可用 `upload_cover_image` 上传图片素材获得）。本地校验图片数，
  回读时核对。

## 6. article 字段速查

| 字段 | 必填 | 本地校验 | 说明 |
|---|---|---|---|
| `title` | 是 | 非空 | 长度交平台判定 |
| `content` | 是 | 见 §2 | HTML 正文；newspic 时为说明文字 |
| `thumb_media_id` | 图文必填 | — | 封面永久素材 ID |
| `digest` | 否 | ≤120 字符 | 摘要，默认空 |
| `article_type` | 否 | — | `newspic` 表示图片帖 |
| `image_info` | newspic 必填 | 1–20 个非空 `image_media_id` | 图片帖图集 |
| 其他 | 否 | — | 原样透传微信 |

## 7. 创建后的自动回读验证

`create_draft` 成功后会立即 `draft/get` 回读，逐篇核对：

- 文章数量、标题一致性；
- 图片数量（`src` 与 `data-src` 都计入——微信保存时会把 `src` 归一化为
  `data-src` 懒加载形式，这是**正常现象**，不是错误）；
- 正文长度：回读正文短于提交正文的 95% 即视为「被微信清洗」，报
  `第 N 篇正文长度缩水超过 5%`。

任一项不符时返回 `verified=false` + `verification_errors` 数组列出差异，
**不静默成功**；此时草稿已创建（`media_id` 有效），需人工在公众号后台复核
或 `update_draft` 修正。

## 8. 排版建议（非强制）

本地只强制 §2 的三条，但为兼容微信编辑器清洗行为，建议：

- 样式全部写内联 `style` 属性；不要依赖 `<style>` 块或外部 CSS。
- 主体用 `section` / `p` / `span` / `img` 结构，与微信编辑器产物一致。
- 长文不必在调用方截断：正文长度上限由平台判定，报错会原样透传
  errcode/errmsg。

## 9. 最小完整流程

```
1. check_credentials                       # 确认凭据与 IP 白名单
2. upload_cover_image(cover.png)           # → thumb_media_id
3. upload_content_image(a.png)             # → 微信图片 URL
4. 组装 HTML，把 URL 填进 <img src>
5. create_draft([{title, content, thumb_media_id, digest}])
   # → {media_id, verified: true|false, verification_errors?}
6. 人工在公众号后台复核后发布；或开启 GZH_MCP_ALLOW_PUBLISH=1 后：
   publish_draft(media_id, confirm=true)   # → publish_id
   get_publish_status(publish_id)          # 轮询至终态
```

可用的最小 HTML 示例（已通过本地校验形状）：

```html
<section style="margin: 0; padding: 16px;">
  <p style="font-size: 15px; line-height: 1.75;">正文第一段。</p>
  <p style="font-size: 15px; line-height: 1.75;">
    <img src="https://mmbiz.qpic.cn/mmbiz_png/xxxx.png"
         style="width: 100%;">
  </p>
</section>
```

## 10. 常见错误速查

| 错误信息 | 原因 | 处理 |
|---|---|---|
| `content 不能包含 script 标签` | HTML 含 `<script>`（含大小写变体） | 移除脚本 |
| `content 含非微信正文图片 URL: …` | `src` 非微信域 / 相对路径 | 先 `upload_content_image` 再替换 URL |
| `content 必须是非空字符串` | content 为空 | 补正文 |
| `digest 不能超过 120 字符` | 摘要超长 | 截短摘要 |
| `图片真实格式必须是 JPEG 或 PNG` | 正文图魔数不符 | 转换格式 |
| `正文图片必须严格小于 1MB` | 正文图 ≥ 1MiB | 压缩图片 |
| `第 N 篇图片数量不一致`（verified=false） | 微信过滤了图片（多为外链漏网） | 检查错误数组中的差异详情 |
| `第 N 篇正文长度缩水超过 5%`（verified=false） | 微信清洗了部分内容 | 后台复核或 `update_draft` 修正 |

## 维护约定

修改本文所描述的校验行为时，先更新 `docs/proposal.md` §4.3 与
`docs/api-verification.md` 的证据记录，再改 `src/gzh_mcp/validation.py`，
并按项目守则完成回归测试的红灯验证。
