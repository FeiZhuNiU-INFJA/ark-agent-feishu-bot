# 轨迹抽取摘要（3 条）

- 轨迹：['trajectory1.json', 'trajectory2.json', 'trajectory3.json']
- api 回放键：9（工具名=api_call）
- time 工具（current_time）：有
- skill 正文/子文档：5 份（加载器=skill_invoke）
- 键冲突（同键不同返回，取最长成功版）：1
- 仍为错误返回的回放键：1 ['api|query_object|obj=interaction_log|where=ticket_id=T-1003']

## skill 正文清单

- `kb_search` -> 178 chars（来自 trajectory2.json）
- `macro_suggester` -> 169 chars（来自 trajectory3.json）
- `ticket_triage` -> 409 chars（来自 trajectory1.json）
- `ticket_triage|severity-rubric.md` -> 221 chars（来自 trajectory1.json）
- `ticket_triage|sla-policy.md` -> 185 chars（来自 trajectory2.json）

## 覆盖矩阵（每条轨迹触发）

### trajectory1.json
- skills: ['ticket_triage']
- skill_docs: ['ticket_triage/severity-rubric.md']
- apis: ['get_authed_columns', 'query_object']
- objects: ['customer', 'interaction_log', 'ticket']
- other_tools: []

### trajectory2.json
- skills: ['kb_search', 'ticket_triage']
- skill_docs: ['ticket_triage/sla-policy.md']
- apis: ['kb_lookup', 'query_object', 'recommend_macro']
- objects: ['ticket']
- other_tools: []

### trajectory3.json
- skills: ['macro_suggester']
- skill_docs: []
- apis: ['get_authed_columns', 'query_object', 'recommend_macro']
- objects: ['customer', 'interaction_log', 'ticket']
- other_tools: []
