# UCAL — Universal Content Access Layer

MCP Server，提供统一的多平台内容访问能力。专为 LLM（Claude Code）设计，支持搜索、阅读、提取需要登录和反检测的平台内容。

## 为什么需要 UCAL？

通用 Web 工具（Jina、Crawl4AI、Tavily）在小红书等平台上会失败，因为这些平台有严格的反爬措施。UCAL 通过以下方式解决：

- **三层反检测**：Playwright stealth + 指纹随机化 + 人类行为模拟
- **Session 持久化**：登录一次（扫码/手动），跨服务重启复用
- **统一接口**：5 个 MCP 工具覆盖所有平台
- **网络拦截**：捕获底层 API 响应，获取结构化数据

## 支持平台

| 平台 | 访问方式 | 认证方式 | 搜索 | 阅读 | 评论 |
|------|----------|----------|:----:|:----:|:----:|
| **xhs**（小红书） | 浏览器 | 扫码登录 | Yes | Yes | Yes |
| **zhihu**（知乎） | 浏览器 | 手动登录 | Yes | Yes | No |
| **x**（X/Twitter） | 浏览器 | 手动登录 | Yes | Yes | N/A |
| **discord** | API | Bot Token | Yes | Yes | N/A |
| **generic**（任意网站） | 浏览器 | 无需登录 | No | Yes | N/A |

## 安装

```bash
git clone https://github.com/Mixiaomiupup/ucal.git
cd ucal
uv sync
uv run playwright install chromium
```

## 注册到 Claude Code

```bash
claude mcp add ucal -- uv run --directory /path/to/ucal ucal
```

## MCP 工具

| 工具 | 说明 |
|------|------|
| `ucal_platform_login` | 登录平台（浏览器扫码/手动登录、cookie 恢复、API key） |
| `ucal_platform_search` | 搜索平台内容 |
| `ucal_platform_read` | 读取 URL 完整内容（返回 Markdown） |
| `ucal_platform_extract` | 提取结构化字段（返回 JSON） |
| `ucal_browser_action` | 低级浏览器自动化 + 网络拦截 |

## 使用示例

### 登录小红书

```
ucal_platform_login(platform="xhs", method="browser")
# 浏览器窗口打开 → 扫码 → Session 自动保存
```

### 登录 X/Twitter

```
ucal_platform_login(platform="x", method="browser")
# 浏览器窗口打开 → 手动登录 → Session 自动保存
```

### 搜索

```
ucal_platform_search(platform="xhs", query="减脂餐推荐", limit=10)
```

### 阅读（含评论）

```
ucal_platform_read(
    platform="xhs",
    url="https://www.xiaohongshu.com/explore/...",
    comment_limit=20,
    expand_replies=2
)
```

### 读取 X/Twitter 内容

```
# 用户时间线
ucal_platform_read(platform="x", url="https://x.com/elonmusk")

# 单条推文 + 回复
ucal_platform_read(platform="x", url="https://x.com/user/status/123456")

# 关注列表
ucal_platform_read(platform="x", url="https://x.com/user/following")
```

### 浏览器操作 + 网络拦截

捕获页面通过 AJAX 加载的底层 API 响应：

```
ucal_browser_action(
    url="https://buff.163.com/goods/968165",
    network_intercept_patterns=["api/market/goods/buy_order"],
    actions=[
        {"type": "click", "selector": "#tab_container li.buying a"},
        {"type": "eval_js", "expression": "new Promise(r => setTimeout(r, 3000))"}
    ]
)
# 返回操作结果 + 捕获的 API JSON 数据
```

### 执行 JavaScript

```
ucal_browser_action(
    url="https://example.com",
    actions=[
        {"type": "eval_js", "expression": "document.querySelectorAll('.item').length"}
    ]
)
```

## 配置

API token 通过环境变量或 `config/platforms.yaml` 配置：

```bash
export DISCORD_BOT_TOKEN="your_token"
```

```yaml
# config/platforms.yaml
browser:
  headless: true
platforms:
  discord:
    bot_token: "your_token"
```

## 架构

```
Claude Code ──MCP──> FastMCP Server (server.py)
                        |
                  Adapter Router
                  ┌─────┼─────┐
               API|  Browser  |
            ┌─────┤  Adapters ├─────┬─────┐
            |     |           |     |     |
         Discord  X/Twitter  XHS  Zhihu Generic
                     |        |     |     |
                ┌────▼────────▼─────▼─────▼────┐
                |         Core Layer            |
                |  BrowserManager               |
                |  SessionManager               |
                |  AntiDetect                    |
                |  HumanBehavior                 |
                └─────────────┬────────────────┘
                              |
                       Playwright + Chromium
```

详细架构文档见 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)。

## 测试

```bash
uv run pytest tests/ -v
```

## License

MIT
