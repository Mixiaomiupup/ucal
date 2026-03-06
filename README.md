# UCAL — Universal Content Access Layer

MCP Server for unified multi-platform content access. Designed for LLMs (Claude Code) to search, read, and extract structured data from platforms that require authentication and anti-detection.

## Why UCAL?

Generic web tools (Jina, Crawl4AI, Tavily) fail on platforms like XHS (Xiaohongshu) due to anti-bot measures. UCAL solves this with:

- **Three-layer anti-detection**: Playwright stealth + fingerprint randomization + human behavior simulation
- **Session persistence**: Login once (QR scan), reuse across server restarts
- **Unified interface**: 5 MCP tools work across all platforms
- **Network interception**: Capture underlying API responses for structured data

## Supported Platforms

| Platform | Access | Auth | Search | Read | Comments |
|----------|--------|------|:------:|:----:|:--------:|
| **xhs** (Xiaohongshu) | Browser | QR scan | Yes | Yes | Yes |
| **zhihu** (Zhihu) | Browser | Manual login | Yes | Yes | No |
| **x** (X/Twitter) | API | Bearer Token | Yes | Yes | N/A |
| **discord** | API | Bot Token | Yes | Yes | N/A |
| **generic** (any site) | Browser | None | No | Yes | N/A |

## Installation

```bash
git clone https://github.com/Mixiaomiupup/ucal.git
cd ucal
uv sync
uv run playwright install chromium
```

## Register with Claude Code

```bash
claude mcp add ucal -- uv run --directory /path/to/ucal ucal
```

## MCP Tools

| Tool | Description |
|------|-------------|
| `ucal_platform_login` | Login to a platform (browser QR scan, cookie restore, or API key) |
| `ucal_platform_search` | Search content on a platform |
| `ucal_platform_read` | Read full content from a URL (returns Markdown) |
| `ucal_platform_extract` | Extract structured fields from a URL (returns JSON) |
| `ucal_browser_action` | Low-level browser automation with network interception |

## Usage Examples

### Login to XHS

```
ucal_platform_login(platform="xhs", method="browser")
# Browser window opens → Scan QR code → Session saved automatically
```

### Search

```
ucal_platform_search(platform="xhs", query="减脂餐推荐", limit=10)
```

### Read with comments

```
ucal_platform_read(
    platform="xhs",
    url="https://www.xiaohongshu.com/explore/...",
    comment_limit=20,
    expand_replies=2
)
```

### Browser action with network interception

Capture the underlying API response when a page loads data via AJAX:

```
ucal_browser_action(
    url="https://buff.163.com/goods/968165",
    network_intercept_patterns=["api/market/goods/buy_order"],
    actions=[
        {"type": "click", "selector": "#tab_container li.buying a"},
        {"type": "eval_js", "expression": "new Promise(r => setTimeout(r, 3000))"}
    ]
)
# Returns action results + captured API JSON with structured order data
```

### Execute JavaScript

```
ucal_browser_action(
    url="https://example.com",
    actions=[
        {"type": "eval_js", "expression": "document.querySelectorAll('.item').length"}
    ]
)
```

## Configuration

API tokens via environment variables or `config/platforms.yaml`:

```bash
export X_BEARER_TOKEN="your_token"
export DISCORD_BOT_TOKEN="your_token"
```

```yaml
# config/platforms.yaml
browser:
  headless: true
platforms:
  x:
    bearer_token: "your_token"
  discord:
    bot_token: "your_token"
```

## Architecture

```
Claude Code ──MCP──▶ FastMCP Server (server.py)
                        │
                  Adapter Router
                  ┌─────┼─────┐
               API│  Browser  │
            ┌─────┤  Adapters ├─────┐
            │     │           │     │
         Twitter Discord  XHS Zhihu Generic
                          │     │     │
                     ┌────▼─────▼─────▼────┐
                     │    Core Layer        │
                     │  BrowserManager      │
                     │  SessionManager      │
                     │  AntiDetect          │
                     │  HumanBehavior       │
                     └─────────┬───────────┘
                               │
                        Playwright + Chromium
```

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for detailed design documentation.

## Testing

```bash
uv run pytest tests/ -v
```

## License

MIT
