# 问题定位指南

## 日志
- 每次项目重启日志会清空，日志当前不存在滚动留存，仅保留当次启动的日志
- 服务端的问题排查通常优先查看日志

```
logs/
  ├── backend.log   # 服务端日志
  ├── frontend.log  # 前端日志
  └── langgraph.log # langgraph服务日志
```

## Debug

所有 debug 过程中产生的截图、日志片段等产物，统一存放在：

```
debug/
└── {workspace_id}/     # 以 workspace id 作为子目录名区分不同场景
    ├── before_submit.png
    ├── after_submit.png
    └── ...
```

## 使用 browser-use 排查前端问题

**基本流程：**

```bash
# 1. 打开页面，观察状态
browser-use open <url>
browser-use scroll down --amount 2000
browser-use state                        # 查看可交互元素与页面文本
browser-use screenshot debug/{ws_id}/step1.png  # 截图留存

# 2. 操作元素（先从 state 获取 index）
browser-use select <index> "选项"
browser-use click <index>
browser-use eval "document.querySelector('button[type=submit]').click()"

# 3. 再次截图确认结果
browser-use screenshot debug/{ws_id}/step2.png
```

**注入网络拦截器，观察实际发出的请求：**

```js
browser-use eval "
window.__fetchLog = [];
const orig = window.fetch;
window.fetch = async (...args) => {
  const url = typeof args[0] === 'string' ? args[0] : args[0]?.url;
  const body = args[1]?.body;
  try {
    const res = await orig(...args);
    window.__fetchLog.push({ url, body: typeof body === 'string' ? body.slice(0, 200) : null, status: res.status });
    return res;
  } catch(e) {
    window.__fetchLog.push({ url, error: String(e) });
    throw e;
  }
};
'ok'
"
# 操作后查看
browser-use eval "JSON.stringify(window.__fetchLog)"
```

**绕过前端直接验证后端：**

```bash
# 验证 LangGraph resume 是否正常
curl -s -X POST "http://localhost:2024/threads/{thread_id}/runs" \
  -H "Content-Type: application/json" \
  -d '{"assistant_id":"train_agent","command":{"resume":{...}}}'
# 后端通 → 问题在前端；后端不通 → 问题在后端
```
HEREDOC; __aone_exit=$?; pwd -P > '/var/folders/hc/15n2_8n91r99sdjxcgdb82k80000gp/T/aone-copilot-cwd-1781237439751-3ssty93h5a1.txt' 2>/dev/null; exit $__aone_exit