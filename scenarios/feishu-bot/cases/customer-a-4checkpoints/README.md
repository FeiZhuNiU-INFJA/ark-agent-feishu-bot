# Case A · 客户A 四卡点 ABCD（MA 迁移 Demo）

本 case 演示客户A 迁移到火山方舟 Managed Agents（MA）时遇到的四个卡点，如何在飞书 Bot 对话里逐一落地：

| 卡点 | 主题 |
|---|---|
| **A** | 身份鉴权（`static_bearer` + OpenID 白名单） |
| **B** | 用户 OpenID 透传（会话级环境变量注入） |
| **C** | 岗位信息注入（`system.message`，24h 缓存） |
| **D** | 跨 Session 记忆（每用户 Memory Store 挂 `/mnt/memory/`） |

## 运行代码在哪

本 case **没有独立的运行代码**——它的实现就是本场景（`scenarios/feishu-bot/`）共享的通用件：

- 网关 / 方舟客户端 / 飞书接入 / 四卡点编排：[../../arkagent/](../../arkagent/)
- 客户A 演示用 MCP Server：[../../mock_mcp/](../../mock_mcp/)
- 起步与运行方式：见场景 README [../../README.md](../../README.md)

## 文档

- [四卡点方案与运行说明](MA迁移Demo-四卡点方案与运行说明.md) —— 每个卡点的方案、归属与运行步骤。
- [四卡点数据流转说明](MA迁移Demo-四卡点数据流转说明.md) —— 时序图 + Gateway 入口 + mock 数据 + 预期结果 + 日志验证。
- [组件关系与生命周期](MA迁移Demo-组件关系与生命周期.md) —— 各模块如何协作、资源生命周期。
