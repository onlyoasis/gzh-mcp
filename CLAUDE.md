# gzh-mcp 项目规则

微信公众号发布 MCP server（Python + mcp SDK，stdio）。

## 铁律

1. **stdout 只走 MCP JSON-RPC 协议**。任何日志/调试输出写 stderr，且必须先脱敏
   （access_token、WECHAT_SECRET 不得出现）。
2. **发布动作双闸门不可绕过**：`GZH_MCP_ALLOW_PUBLISH` 严格真值（仅 `1`/`true`）
   决定 publish_draft 是否注册；调用时必须显式 `confirm=true`。
3. **非幂等接口不自动重试**：draft/add、freepublish/submit 网络超时一律返回
   "状态不确定"错误。只读接口可以一次有限退避。
4. JSON 序列化微信接口请求体必须 `ensure_ascii=False` + UTF-8。

## 常用命令

```bash
uv sync          # 安装依赖
uv run pytest    # 全部测试
uv run gzh-mcp   # 启动 server（stdio，需要 WECHAT_APPID/WECHAT_SECRET）
```

## 修改守则

- 新增回归测试后必须验证：把修复退回、测试真的变红、再还原。没红灯过的回归
  测试不算数。
- 预期数值与实测不符时，说明原因，不要改断言迁就实现。
- 设计依据与官方文档核对记录在 docs/ 下，改接口行为先更新 docs/proposal.md。

## 边界

- 凭据只从环境变量读，不写任何文件。
- 无本地数据库/缓存目录；状态由调用方维护。
- 外部动作红线：真实发布、真实上传素材属于外部可见行为，测试中一律 mock，
  真实调用只在用户明确授权时进行。
