# UCAL Architecture

> **Universal Content Access Layer** — MCP Server for unified multi-platform content access.

- **Version**: 0.1.0
- **Python**: >= 3.11
- **License**: MIT
- **Last Updated**: 2026-02-18

---

## 1. Overview

UCAL is an MCP (Model Context Protocol) server that allows LLMs (primarily Claude Code) to search, read, and extract structured data from multiple content platforms through a unified interface.

### Core Problem

Different content platforms have different access methods (API vs. browser), authentication mechanisms, and anti-bot measures. UCAL abstracts these differences into 5 standard tools.

### Design Philosophy

- **Unified Interface**: One set of tools works across all platforms
- **Dual Access Strategy**: API when available, browser automation as fallback
- **Anti-Detection First**: Browser platforms require stealth measures to avoid detection
- **Session Persistence**: Login once, reuse sessions across server restarts
- **Human Behavior Simulation**: Mimic natural user interactions to reduce bot detection

---

## 2. System Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Claude Code (LLM)                     │
└──────────────────────┬──────────────────────────────────┘
                       │ MCP Protocol (stdio)
┌──────────────────────▼──────────────────────────────────┐
│                  FastMCP Server (server.py)              │
│  ┌────────────────────────────────────────────────────┐  │
│  │  5 MCP Tools:                                      │  │
│  │  login / search / read / extract / browser_action  │  │
│  └────────────────────┬───────────────────────────────┘  │
│                       │                                   │
│  ┌────────────────────▼───────────────────────────────┐  │
│  │           Adapter Router (_get_adapter)             │  │
│  └───────┬──────────┬──────────┬──────────┬───────────┘  │
│          │          │          │          │               │
│  ┌───────▼───┐ ┌────▼────┐ ┌──▼───┐ ┌───▼────┐ ┌─────┐ │
│  │ Twitter   │ │ Discord │ │ XHS  │ │ Zhihu  │ │ Gen │ │
│  │ (API)     │ │ (API)   │ │(Brw) │ │ (Brw)  │ │(Brw)│ │
│  └───────────┘ └─────────┘ └──┬───┘ └───┬────┘ └──┬──┘ │
│                                │         │         │     │
│  ┌─────────────────────────────▼─────────▼─────────▼──┐  │
│  │                Core Layer                           │  │
│  │  BrowserManager / SessionManager / AntiDetect       │  │
│  └─────────────────────────┬──────────────────────────┘  │
│                            │                              │
│  ┌─────────────────────────▼──────────────────────────┐  │
│  │           Human Behavior Simulation                 │  │
│  │  smooth_track / human_type / human_scroll / delay   │  │
│  └────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────┘
                       │
            ┌──────────▼──────────┐
            │  Playwright + Chromium │
            └─────────────────────┘
```

---

## 3. Directory Structure

```
ucal/
├── docs/
│   └── ARCHITECTURE.md          # 本文件
├── config/
│   ├── platforms.yaml           # API tokens, browser settings
│   └── sessions/                # 自动生成的 session 文件 (.gitignore)
│       ├── xhs_session.json
│       └── zhihu_session.json
├── src/ucal/
│   ├── server.py                # MCP server 入口, 5 个 tool 定义
│   ├── adapters/                # 平台适配器
│   │   ├── base.py              # BaseAdapter 抽象基类 + 数据模型
│   │   ├── twitter.py           # X/Twitter (API adapter)
│   │   ├── discord_api.py       # Discord (API adapter)
│   │   ├── xhs.py               # 小红书 (browser adapter)
│   │   ├── zhihu.py             # 知乎 (browser adapter)
│   │   └── generic.py           # 通用网站 (browser adapter)
│   ├── core/                    # 核心基础设施
│   │   ├── browser.py           # BrowserManager: Playwright 生命周期
│   │   ├── session.py           # SessionManager: cookie 持久化
│   │   └── anti_detect.py       # 反检测: stealth + 指纹伪装
│   └── utils/
│       └── human_behavior.py    # 人类行为模拟: 鼠标/滚动/打字
├── tests/
│   ├── test_base.py
│   ├── test_human_behavior.py
│   └── test_session.py
├── pyproject.toml
├── README.md
├── QUICKSTART.md
└── DEPLOYMENT.md
```

---

## 4. Core Components

### 4.1 MCP Tools (server.py)

5 个工具通过 FastMCP 注册，构成 UCAL 的全部对外接口：

| Tool | 用途 | 只读 | 幂等 |
|------|------|:----:|:----:|
| `ucal_platform_login` | 登录平台，保存 session | No | Yes |
| `ucal_platform_search` | 搜索平台内容 | Yes | Yes |
| `ucal_platform_read` | 读取 URL 完整内容 (Markdown) | Yes | Yes |
| `ucal_platform_extract` | 提取结构化字段 (JSON) | Yes | Yes |
| `ucal_browser_action` | 低级浏览器操作 (兜底) | No | No |

**Lifespan 管理**: Server 启动时通过 `app_lifespan` 初始化所有 adapter 和 BrowserManager，关闭时统一清理。

**Platform 路由**: `_get_adapter()` 根据 platform 参数从 adapter 字典中取出对应实例。`browser_action` 还支持通过 `_detect_platform_from_url()` 自动识别 URL 所属平台以复用 session。

### 4.2 Adapter Pattern (adapters/)

所有平台适配器继承 `BaseAdapter`，实现 4 个抽象方法：

```python
class BaseAdapter(abc.ABC):
    platform_name: str
    adapter_type: AdapterType  # API or BROWSER

    async def login(method) -> LoginStatus
    async def search(query, limit) -> list[SearchResult]
    async def read(url) -> ContentResult
    async def extract(url, fields) -> ExtractResult
```

**两类适配器**:

| 类型 | 平台 | 访问方式 | 认证方式 |
|------|------|----------|----------|
| **API** | X/Twitter | httpx HTTP 请求 | Bearer Token (环境变量) |
| **API** | Discord | httpx HTTP 请求 | Bot Token (环境变量) |
| **Browser** | 小红书 (xhs) | Playwright 页面操作 | 扫码登录 |
| **Browser** | 知乎 (zhihu) | Playwright 页面操作 | 手动登录 |
| **Browser** | 通用 (generic) | Playwright 页面操作 | 无需登录 |

**设计决策**: 为什么用两种类型？
- API 适配器更快、更稳定，但需要申请 API 权限，且平台可能限制 API 功能
- Browser 适配器更通用，能访问任何页面内容，但需要处理反检测和登录态
- 有些平台（如小红书）没有公开 API，只能走浏览器

### 4.3 Data Models (adapters/base.py)

4 个 dataclass 统一所有平台的输出格式：

```
SearchResult   → title, url, summary, author, platform, extra
ContentResult  → title, content(Markdown), author, url, platform, extra
ExtractResult  → fields(dict), url, platform
LoginStatus    → success, platform, method, message, session_file
```

所有模型都有 `to_dict()` 方法，最终在 server.py 中序列化为 JSON 返回。

### 4.4 BrowserManager (core/browser.py)

管理单个 Playwright 实例，为所有 browser adapter 提供共享浏览器：

```
BrowserManager
  ├── start()           → 启动 Playwright + Chromium
  ├── get_context()     → 获取/创建平台专属 BrowserContext (自动恢复 session)
  ├── new_page()        → 创建 stealth page (自动注入反检测)
  ├── save_session()    → 保存当前 context 的 cookie/storage_state
  ├── close_context()   → 关闭单个平台 context
  └── close()           → 关闭所有 context + browser + playwright
```

**关键设计**:
- **单实例共享**: 一个 Playwright 进程服务所有平台，减少资源开销
- **Context 隔离**: 每个平台有独立的 BrowserContext，cookie 互不干扰
- **自动 Session 恢复**: `get_context()` 时自动加载已保存的 storage_state
- **重试机制**: `with_retry()` 提供指数退避重试，应对浏览器操作的不稳定性

### 4.5 SessionManager (core/session.py)

管理 cookie / storage_state 的持久化：

```
SessionManager
  ├── save_session()         → context.storage_state() → JSON 文件
  ├── load_session_state()   → JSON 文件 → dict (传给 new_context)
  ├── has_session()          → 检查是否有已保存的 session
  └── delete_session()       → 删除 session 文件
```

**存储位置**: `config/sessions/<platform>_session.json`

**安全**: session 文件在 `.gitignore` 中，不会被提交到版本控制。

---

## 5. Anti-Detection System

Browser adapter 面临的核心挑战：平台会检测自动化访问并封禁。UCAL 采用三层防护：

### 5.1 Layer 1: Playwright Stealth (anti_detect.py)

使用 `playwright-stealth` 库修补 Playwright 的自动化痕迹：

```python
_stealth = Stealth()
await _stealth.apply_stealth_async(page)
```

### 5.2 Layer 2: Fingerprint Randomization (anti_detect.py)

每次创建 BrowserContext 时随机化浏览器指纹：

| 指纹项 | 策略 |
|--------|------|
| **Viewport** | 从 5 种常见分辨率中随机选择 (1920x1080 ~ 1280x720) |
| **User-Agent** | 从 3 种 Chrome UA 中随机选择 (macOS/Windows) |
| **语言** | zh-CN 或 en-US |
| **时区** | Asia/Shanghai |
| **地理位置** | 上海 (31.23, 121.47) |

额外注入 JS 脚本覆盖：
- `navigator.webdriver` → `undefined`
- `navigator.plugins` → 模拟 5 个插件
- `navigator.languages` → `['zh-CN', 'zh', 'en']`
- `window.chrome.runtime` → 模拟 Chrome 环境

### 5.3 Layer 3: Human Behavior Simulation (human_behavior.py)

模拟真实用户的交互模式，来源于 csfilter 项目的 captcha_solver.py：

| 行为 | 实现 | 参数 |
|------|------|------|
| **鼠标移动** | 物理加速-减速模型 + ease-in-out 曲线 | 15-30 步, ±2px 抖动 |
| **滚动** | 分块滚动, 每块 60-160px | 步间延迟 20-120ms |
| **打字** | 逐字输入, 随机延迟 | 50-180ms/字, 5% 概率长停顿 |
| **思考延迟** | 操作间随机等待 | 0.5-2.0s |

**鼠标移动物理模型**:
```
距离的前 70%: 加速 (a = 3~5)
距离的后 30%: 减速 (a = -4~-6)
最大速度上限: 20 px/step
```

---

## 6. Data Flow

### 6.1 Search Flow

```
LLM 调用 ucal_platform_search(platform="zhihu", query="...")
  │
  ├─ API platform? → adapter.search() → httpx API call → SearchResult[]
  │
  └─ Browser platform?
       │
       ├─ BrowserManager.start() (if not running)
       ├─ BrowserManager.get_context("zhihu") → 加载已保存 session
       ├─ BrowserManager.new_page("zhihu") → apply_stealth + anti_detect
       ├─ adapter.search()
       │    ├─ 导航到搜索页
       │    ├─ human_type() 输入搜索词
       │    ├─ 等待结果加载
       │    └─ 解析 DOM → SearchResult[]
       └─ 返回 JSON
```

### 6.2 Login Flow

```
LLM 调用 ucal_platform_login(platform="xhs", method="browser")
  │
  ├─ BrowserManager.headless = False (需要可见窗口)
  ├─ BrowserManager.start()
  ├─ adapter.login(LoginMethod.BROWSER)
  │    ├─ 打开平台登录页
  │    ├─ 等待用户手动操作 (扫码/输入)
  │    └─ 检测登录成功
  ├─ BrowserManager.save_session("xhs")
  │    └─ → config/sessions/xhs_session.json
  └─ 返回 LoginStatus(success=True)
```

### 6.3 browser_action Flow

```
LLM 调用 ucal_browser_action(url="https://zhihu.com/...", actions=[...])
  │
  ├─ _detect_platform_from_url() → "zhihu"
  ├─ GenericAdapter.execute_actions(url, actions, platform="zhihu")
  │    ├─ BrowserManager.get_context("zhihu") → 复用知乎 session
  │    └─ 按顺序执行 actions:
  │         goto → click → scroll → extract_text → ...
  └─ 返回 [{type, success, ...}, ...]
```

---

## 7. Platform Capabilities Matrix

| 能力 | X (API) | Discord (API) | XHS (Browser) | Zhihu (Browser) | Generic (Browser) |
|------|:-------:|:-------------:|:-------------:|:---------------:|:-----------------:|
| **Login** | API Key | Bot Token | QR 扫码 | 手动登录 | N/A |
| **Search** | Yes | Yes (channel_id:query) | Yes | Yes | No |
| **Read** | Yes | Yes | Yes | Yes | Yes |
| **Extract** | Yes | Yes | Yes | Yes | Yes |
| **browser_action** | N/A | N/A | Yes | Yes | Yes |
| **Session Persist** | N/A | N/A | Yes | Yes | N/A |
| **Anti-Detection** | N/A | N/A | Full | Full | Basic |

### 7.1 Platform Content Characteristics

不同平台的内容形态有本质差异，直接影响 adapter 的提取策略：

| 特征 | 小红书 (XHS) | 知乎 (Zhihu) | X/Twitter |
|------|:------------:|:------------:|:---------:|
| **主要内容载体** | 图片/视频 | 文字 | 短文字 |
| **正文文字** | 少，通常是图片说明 | 多，完整长文 | 280字以内 |
| **图片中的关键信息** | 大量（攻略、教程、菜单等核心内容在图中） | 少（配图为辅） | 少 |
| **评论区价值** | 高（补充信息、避坑提醒、真实反馈） | 中（讨论为主） | 中 |
| **OCR 需求** | 强烈 | 低 | 低 |
| **适合 read 直接提取** | 部分（只能拿到文字描述） | 完整 | 完整 |

**小红书的特殊挑战**:

小红书是一个**图片优先**的平台。很多笔记的核心内容（如旅行攻略的行程安排、美食推荐的店铺信息、穿搭教程的细节）都在图片中，而文字正文只是简短的引导或总结。当前 `platform_read` 只能提取文字内容，**图片中的信息会丢失**。

此外，小红书的**评论区**往往包含大量有价值的补充信息：
- 其他用户的真实体验和避坑建议
- 博主对具体问题的回复（如"这家店几点开门？""用的什么色号？"）
- 价格、地址等实用信息的更新

**对比知乎**: 知乎的核心内容在回答正文中，以长文字为主，`platform_read` 可以提取到几乎全部有价值的内容。评论区主要是讨论和追问，信息密度相对低。

**当前状态与改进方向**:

| 能力 | 当前状态 | 改进方向 |
|------|----------|----------|
| 小红书图片提取 | 不支持 | 下载图片 + OCR (Tesseract/云端 API) |
| 小红书评论区 | 不支持 | adapter 增加 `read_comments()` 方法 |
| 知乎评论区 | 不支持 | 优先级低，正文已包含主要内容 |
| 图片描述/Alt text | 不支持 | 提取 `<img>` 的 alt 属性作为补充 |

---

## 8. Configuration

### 8.1 platforms.yaml

```yaml
browser:
  headless: true               # false = 显示浏览器窗口
  session_dir: config/sessions  # session 存储路径

platforms:
  x:
    bearer_token: "..."         # 或使用环境变量 X_BEARER_TOKEN
  discord:
    bot_token: "..."            # 或使用环境变量 DISCORD_BOT_TOKEN
```

### 8.2 Environment Variables

| 变量 | 用途 |
|------|------|
| `X_BEARER_TOKEN` | X/Twitter API Bearer Token |
| `DISCORD_BOT_TOKEN` | Discord Bot Token |

### 8.3 MCP Registration

```bash
claude mcp add ucal -- uv run --directory /path/to/ucal ucal
```

---

## 9. Dependencies

| 依赖 | 用途 |
|------|------|
| `mcp[cli] >= 1.0.0` | FastMCP server framework |
| `httpx >= 0.27.0` | Async HTTP client (API adapters) |
| `playwright >= 1.40.0` | Browser automation engine |
| `playwright-stealth >= 1.0.6` | Anti-detection patches |
| `pyyaml >= 6.0` | YAML config parsing |
| `pydantic >= 2.0.0` | Input validation & data models |

Dev:
| `pytest` / `pytest-asyncio` | Testing |
| `ruff` | Linting & formatting (88 char) |

---

## 10. Design Decisions

### Q: 为什么不全部用 API？
Browser 适配器存在的原因：
1. **小红书没有公开 API** — 只能通过浏览器访问
2. **知乎 API 有严格限制** — 很多内容需要登录后浏览器访问
3. **API 的数据有时不完整** — 浏览器可以获取渲染后的完整页面

### Q: 为什么需要 human_behavior 模拟？
纯 Playwright 的操作模式（瞬间点击、瞬间输入）容易被平台检测为自动化访问。人类行为模拟通过物理模型让交互更自然，降低被封禁的风险。

### Q: UCAL vs 通用替代方案 (Crawl4AI, Jina, server-fetch 等)?

2026-02-22 完成了系统性对比测试 (详见 `docs/ALTERNATIVES_COMPARISON.md`)。结论:

1. **小红书**: UCAL 是唯一能稳定访问的方案。所有通用工具 (Jina/Crawl4AI/server-fetch/Tavily) 全部失败 — 域名封禁、SPA 空壳、或被安全系统拦截 (300017)。UCAL 的三层反检测 (stealth + 指纹 + 人类行为) 是关键差异。
2. **知乎**: Crawl4AI + UCAL session 可作为补充 (70K chars, 62 个回答), 但 UCAL 在结构化输出和站内搜索上仍有优势。
3. **结构化输出**: 通用方案返回原始 markdown (含导航栏/footer/法律文本), UCAL 返回干净的 JSON/Markdown。
4. **统一接口**: 5 个 MCP 工具 vs 每个方案独立的 API/配置方式。

**定位**: UCAL 不是通用爬虫, 而是**需要登录和反检测的中文平台的专用访问层**。对于不需要登录的通用网页, Crawl4AI 或 server-fetch 足够。

### Q: 为什么用 Playwright 而不是 Selenium？
- Playwright 原生支持 async
- 更好的 stealth 生态（playwright-stealth）
- 更快的执行速度和更小的资源占用
- 内置的 storage_state 序列化，方便 session 持久化

### Q: browser_action 为什么要自动检测 platform？
`browser_action` 是低级工具，用户传入的 URL 可能属于已登录的平台。自动检测后可以复用对应的 BrowserContext（包含 session cookie），避免遇到登录墙。

### Q: 为什么每个平台用独立的 BrowserContext？
- Cookie 隔离：各平台的登录态互不影响
- 安全性：一个平台的 session 泄露不影响其他平台
- 灵活性：可以独立管理每个平台的 session 生命周期

### Q: 为什么小红书和知乎用同一套 BaseAdapter 接口，但内容特征差异很大？
当前 BaseAdapter 的 4 个方法（login/search/read/extract）是最小公约数抽象，足以覆盖"搜索-阅读-提取"的基本流程。但小红书作为图片优先平台，其核心内容在图片和评论区中，纯文字提取只能拿到部分信息。未来可能需要扩展接口：
- `read_comments(url, limit)` — 提取评论区
- `download_images(url)` — 下载笔记图片
- 结合 OCR 能力从图片中提取文字信息

---

## 11. Known Limitations

### 平台通用
1. **反检测不是万能的** — 高频访问仍然可能触发验证码或封禁
2. **headless 模式下登录受限** — 扫码登录必须 `headless=false`
3. **Generic adapter 无 search** — 通用适配器只支持 read 和 extract，不支持搜索

### 小红书 (XHS)
4. **图片内容无法提取** — 小红书核心内容大量在图片中（攻略、教程、菜单等），当前只能提取文字描述，图片中的信息完全丢失。这是当前最大的能力缺口
5. **评论区无法提取** — 小红书评论区包含大量有价值信息（避坑提醒、博主回复、价格更新等），当前不支持提取
6. **搜索结果质量不稳定** — 部分笔记标题和 URL 提取不到，视频类笔记尤甚
7. **视频内容不支持** — 无法提取视频中的内容

### 知乎 (Zhihu)
8. **懒加载问题** — 长页面需要多次滚动才能加载所有回答，browser_action 滚动时页面可能丢失 DOM 状态
9. **长回答折叠** — 默认只展示部分内容，需要点击"展开"或"阅读全文"才能获取完整回答

---

## 12. Adding a New Platform

新增平台适配器的步骤：

1. **创建适配器文件**: `src/ucal/adapters/<platform>.py`
2. **继承 BaseAdapter**: 实现 `login`, `search`, `read`, `extract` 四个方法
3. **设置 adapter_type**: `AdapterType.API` 或 `AdapterType.BROWSER`
4. **注册到 server.py**:
   - 在 `app_lifespan()` 中实例化并加入 `adapters` 字典
   - 在 `PlatformName` 枚举中添加新平台
   - 如有需要，在 `_DOMAIN_PLATFORM_MAP` 中添加域名映射
5. **添加测试**: `tests/test_<platform>.py`

**API 适配器模板**:
```python
class NewPlatformAdapter(BaseAdapter):
    platform_name = "newplatform"
    adapter_type = AdapterType.API

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key
        self.client = httpx.AsyncClient(...)
```

**Browser 适配器模板**:
```python
class NewPlatformAdapter(BaseAdapter):
    platform_name = "newplatform"
    adapter_type = AdapterType.BROWSER

    def __init__(self, browser_manager: BrowserManager):
        self.bm = browser_manager
```
