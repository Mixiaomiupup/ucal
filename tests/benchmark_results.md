# ucal vs browser-use CLI 对比测试报告

**日期**: 2026-03-22
**环境**: macOS Darwin 24.6.0, Claude Code (Opus 4.6)

---

## 测试总览

| Test | 场景 | ucal | browser-use | 胜出 |
|------|------|------|-------------|------|
| A | 静态内容（飞书文章） | ✅ 15.9s / 1次 | ✅ 9.7s / 2次 | browser-use |
| B | Grok 科技新闻搜索 | ✅ 48.4s / 1次 | ✅ 44.8s / 6次 | 平手 |
| C | 知乎复杂交互 | ✅ 36.5s / 3次 | ✅ 28.5s / 6次 (需手动登录) | 平手 |
| D | 网络拦截 | ✅ 21.5s / 捕获10个API | ❌ 不支持 | ucal |
| E | 反检测 + 登录态 | ✅ 自动cookie | ⚠️ 需手动登录才能过反爬 | ucal |

---

## Test A: 静态内容完整度

**URL**: `https://www.feishu.cn/content/article/7613711414611463386`（飞书 OpenClaw 插件页面）

### browser-use

| 指标 | 值 |
|------|-----|
| 耗时 | 9,687ms |
| 调用次数 | 2 (`open` + `eval`) |
| 输出字符数 | 12,498 (innerText) |
| 结果质量 | 4/5 — 完整正文，含导航栏噪音 |
| 成功 | ✅ |

```bash
browser-use open "https://www.feishu.cn/content/article/..."
browser-use eval "document.body.innerText"
```

### ucal

| 指标 | 值 |
|------|-----|
| 耗时 | 15,938ms |
| 调用次数 | 1 (`platform_read`) |
| 输出字符数 | ~10,000 (JSON, content 字段被截断) |
| 结果质量 | 4/5 — 结构化JSON(title/content/author)，但内容被截断 |
| 成功 | ✅ |

```
ucal_platform_read(platform="generic", url="...")
```

**分析**: browser-use 更快（无需建立 platform context），输出为原始文本更完整；ucal 返回结构化 JSON 但被 MCP 截断。两者都包含导航栏等噪音内容。

---

## Test B: Grok 科技新闻搜索

**场景**: 打开 `x.com/i/grok`，提问"What are today's hot topics in AI and programming? Include tweet URLs."

### browser-use

| 指标 | 值 |
|------|-----|
| 耗时 | 44,771ms |
| 调用次数 | 6 (`open`, `state`, `click`, `type`, `keys Enter`, `eval`×3) |
| 输出字符数 | ~3,280 |
| 结果质量 | 4/5 — Grok 完整回复，含 tweet URL |
| 成功 | ✅ (需先手动登录) |

```bash
browser-use --headed open "https://x.com/login"   # 用户手动登录
browser-use open "https://x.com/i/grok?new=true"
browser-use state                                   # 找到 textarea 索引
browser-use click 3550                              # 点击 textarea
browser-use type "..."                              # 输入问题
browser-use keys Enter                              # 提交
# 等待 + 多次 eval 提取
browser-use eval "document.body.innerText.substring(0, 8000)"
```

**关键发现**: browser-use 的 `type` 命令对 React 受控组件**有效**（不同于 ucal 的 `type` action 用 page.fill）。原因是 browser-use 的 `type` 底层实现是 `page.keyboard.type()`（逐字符键盘事件），而非 `page.fill()`。

### ucal

| 指标 | 值 |
|------|-----|
| 耗时 | 48,443ms |
| 调用次数 | 1 (单次 `browser_action`) |
| 输出字符数 | ~4,200 |
| 结果质量 | 5/5 — 完整 Grok 回复 + tweet URLs + 43 post引用 |
| 成功 | ✅ (需先 `platform_login`) |

```
ucal_browser_action(
  url: "https://x.com/i/grok?new=true",
  actions: [
    wait textarea,
    keyboard_type 问题 + \n,
    eval_js 观察者模式等待回复完成
  ]
)
```

**分析**:
- 耗时接近（~45s vs ~48s），瓶颈都是 Grok 生成回复的时间
- ucal 只需 1 次 MCP 调用（所有 action 批量执行），browser-use 需 6+ 次 CLI 调用
- ucal 的观察者模式更智能（自动检测回复完成），browser-use 需要手动轮询
- 两者都需要先登录：ucal 用 `platform_login`，browser-use 用 `--headed` 手动登录

---

## Test C: 知乎复杂交互

**URL**: 知乎热榜问题（`zhihu.com/question/2018838561324048538`）

### browser-use

**第一轮（未登录）**: ❌ 被反爬拦截

返回错误：`您当前请求存在异常，暂时限制本次访问`

**第二轮（手动登录后）**: ✅ 正常访问

| 指标 | 值 |
|------|-----|
| 耗时 | 28,462ms |
| 调用次数 | 6 (`open`, `eval`, `state`, `click 展开`, `scroll`, `eval`) |
| 输出字符数 | 15,765 (innerText，含多个回答) |
| 结果质量 | 4/5 — 完整正文 + 多个回答，含导航栏噪音 |
| 成功 | ✅ (需先手动登录) |

```bash
browser-use --headed open "https://www.zhihu.com/signin"  # 用户手动登录
browser-use open "https://www.zhihu.com/question/..."
browser-use state                    # 找到"显示全部"按钮索引
browser-use click 227               # 展开折叠内容
browser-use scroll down              # 滚动加载更多
browser-use eval "document.body.innerText"
```

**关键发现**: 知乎的反爬拦截是针对**未登录的自动化浏览器**。手动登录后，browser-use 的 Chromium 可以正常访问知乎内容，无需额外反检测。

### ucal

| 指标 | 值 |
|------|-----|
| 耗时 | 36,540ms (含热榜获取 + 文章读取) |
| 调用次数 | 3 (`browser_action` 获取热榜链接 + `platform_read` 读内容) |
| 输出字符数 | ~1,800 (结构化回答内容) |
| 结果质量 | 4/5 — 完整回答正文、作者、赞同数 |
| 成功 | ✅ |

```
ucal_platform_read(platform="zhihu", url="...", comment_limit=5)
```

**分析**:
- 未登录时：ucal 凭反检测通过，browser-use 被拦截
- 登录后：两者都能正常访问，browser-use 更快（28.5s vs 36.5s）且内容更完整（15K vs 1.8K 字符）
- ucal 返回结构化数据（标题/作者/正文分离），browser-use 返回原始 innerText
- browser-use 的展开折叠需要手动 `state` → `click`，ucal 适配器自动处理

---

## Test D: 网络拦截（ucal 独有能力）

**URL**: 飞书文章页

### ucal

| 指标 | 值 |
|------|-----|
| 耗时 | 21,451ms |
| 调用次数 | 1 |
| 捕获 API 数量 | 10 个 XHR/fetch 响应 |
| 数据量 | 1.9M 字符 |
| 成功 | ✅ |

捕获到的 API 包括：
- `site-api/article/category` — 文章分类数据
- `ocic_visitor` — 访客追踪
- `jsapi/sign` — JSAPI 签名
- `category/child` — 子分类数据

### browser-use

**不支持网络拦截功能。** 无等价命令。

---

## Test E: 反检测 + 登录态

| 维度 | ucal | browser-use |
|------|------|-------------|
| Cookie 管理 | 自动保存/加载 (`config/sessions/`) | `cookies import/export` 手动管理 |
| 登录方式 | `platform_login(method="browser")` 弹窗登录 | `--headed open /login` 手动登录 |
| 反检测 | 自研 stealth + anti-detect scripts | 内置 stealth（较弱） |
| X.com | ✅ cookie 自动生效 | ❌ 未登录被拦，手动登录后正常 |
| 知乎 | ✅ 专用适配器通过反检测 | ❌ 未登录被拦，手动登录后正常 |
| 通用页面 | ✅ | ✅ |
| Cookie 互通 | 理论可导出给 browser-use，但无反检测仍被拦 | 可导入 ucal 格式，但缺反检测 |

---

## 综合对比

| 维度 | ucal (MCP) | browser-use (CLI) |
|------|------------|-------------------|
| **调用效率** | ⭐⭐⭐⭐⭐ 单次批量 action | ⭐⭐⭐ 逐条命令 |
| **延迟** | ⭐⭐⭐ MCP overhead + context 创建 | ⭐⭐⭐⭐ daemon 常驻 ~50ms/命令 |
| **反检测** | ⭐⭐⭐⭐⭐ 自研 stealth，免登录可用 | ⭐⭐⭐ 手动登录后可用 |
| **中国平台** | ⭐⭐⭐⭐⭐ 专用适配器 | ⭐⭐⭐ 手动登录后可用 |
| **状态感知** | ⭐⭐ 需 screenshot/eval_js | ⭐⭐⭐⭐ state 命令返回元素索引 |
| **交互灵活性** | ⭐⭐⭐ CSS selector | ⭐⭐⭐⭐ 索引号 + 丰富命令 |
| **会话持久** | ⭐⭐⭐⭐ 自动 cookie 管理 | ⭐⭐⭐ daemon 存活期间有效 |
| **网络拦截** | ⭐⭐⭐⭐⭐ 支持 | ❌ 不支持 |
| **Token 消耗** | ⭐⭐⭐⭐ 结构化 JSON 返回 | ⭐⭐ state 返回大量元素文本 |

---

## Test F: 端到端实战 — x-feed 科技日报

用 browser-use CLI 完整跑了一次 x-feed skill 的 digest 流程（通常用 ucal MCP 执行），生成日报并保存到 Obsidian。

### 流程对比

| 步骤 | ucal 方式 | browser-use 方式 |
|------|----------|-----------------|
| Grok 提问 | 1 次 `browser_action`（wait + keyboard_type + eval_js 观察者） | 5 步：`open` → `state` → `click` → `type` → `keys Enter` + 手动 `sleep` + `eval` |
| 等待 Grok 回复 | 观察者模式自动检测完成（轮询文本长度稳定） | 固定 `sleep 40` 盲等 + 手动 `eval` 检查长度 |
| Core Accounts (8个) | 8 次 `platform_read`，结构化 JSON 返回 | for 循环 8 × (`open` + `sleep 3` + `eval`) = 16 次 CLI 调用 |
| Tavily 搜索 | 相同（MCP 工具） | 相同（MCP 工具） |
| **总工具调用** | **~12 次** | **~30 次 CLI 命令** |

### 关键差异

| 维度 | ucal | browser-use |
|------|------|-------------|
| Promise/async 支持 | eval_js 完整支持 Promise 返回值 | eval 中 Promise 返回 `{}`（空对象），无法使用 |
| 观察者模式 | 可用（轮询文本长度变化，自动判断完成） | 不可用（Promise 不工作），只能固定 sleep |
| 批量 action | 单次调用执行 wait + type + eval 全流程 | 每步一条命令，需 Claude Code 逐步编排 |
| 登录态 | `platform_login` 自动弹窗 + cookie 持久化 | 需手动登录或导入 ucal 的 cookie |
| Cookie 互通 | 可导出给 browser-use（本次实测成功） | 可从 ucal session 文件导入 |

### 实测数据

| 指标 | ucal (估算) | browser-use (实测) |
|------|------------|-------------------|
| Grok Q1 耗时 | ~48s (含观察者等待) | ~45s (含手动 sleep + 检查) |
| Grok Q2 耗时 | ~48s | ~55s |
| 8 个 Core Accounts | ~40s (并行可能) | ~50s (串行 for 循环) |
| Claude Code 交互轮次 | ~5 轮 | ~15 轮 |
| 日报质量 | 相同 | 相同 |

### 最大痛点

1. **Promise 不工作**: browser-use 的 `eval` 命令无法返回 Promise 结果，这意味着所有需要异步等待的场景（Grok 回复、页面加载、动态内容）都只能用盲等 `sleep`，效率低且不可靠
2. **调用次数膨胀**: 同样的 Grok 交互，ucal 1 次调用 vs browser-use 5-6 次命令，Claude Code 上下文被大量中间状态占用
3. **无结构化输出**: browser-use 返回原始 innerText，需要 Claude Code 自己解析；ucal `platform_read` 直接返回 title/content/author 结构化 JSON

### 结论

browser-use 可以完成 x-feed 日报流程，但效率显著低于 ucal：调用次数多 2.5 倍，需要更多人工干预（手动 sleep 时间估算），且无法使用观察者模式等高级特性。**对于固定工作流（如日报），ucal 的批量 action + 观察者模式是更优解；browser-use 更适合一次性探索任务。**

---

## 结论与建议

### ucal 优势场景
1. **中国平台免登录访问**(知乎/小红书/X): 专用适配器 + 反检测无需登录即可工作，browser-use 需先手动登录
2. **批量自动化**: 单次调用执行多步 action，减少 Claude Code 交互轮次
3. **网络拦截**: 独有能力，可捕获 XHR/API 数据
4. **Session 管理**: 自动 cookie 持久化，跨会话复用

### browser-use 优势场景
1. **通用网页交互**: `state` 命令提供元素索引，交互更直观
2. **快速原型**: daemon 常驻，命令延迟低，适合探索性操作
3. **调试**: `--headed` + 实时 `state` 查看，比 headless screenshot 更方便
4. **系统 Chrome**: `-b real` 可用系统已登录的 Chrome profile

### 推荐策略
- **中国平台内容**: 必须用 ucal
- **X/Twitter Grok 交互**: ucal（单次调用 + 观察者模式）或 browser-use（需手动登录）
- **通用网页探索**: browser-use 更灵活
- **API 数据捕获**: ucal（网络拦截）
- **两者互补**: ucal 做重活（反检测平台、批量操作），browser-use 做轻活（快速查看、调试）
