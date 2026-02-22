# UCAL — Universal Content Access Layer

MCP Server for unified multi-platform content access.

## Features

- **API Platforms**: X/Twitter, Discord (via official APIs)
- **Browser Platforms**: 小红书 (XHS), 知乎 (Zhihu), Generic websites
- **Anti-Detection**: Playwright + stealth + human behavior simulation
- **Session Persistence**: Login once, reuse sessions across restarts

## Installation

```bash
# Install dependencies
cd /Users/mixiaomiupup/projects/ucal
uv sync

# Install Playwright browsers
uv run playwright install chromium
```

## Registration with Claude Code

```bash
claude mcp add ucal -- uv run --directory /Users/mixiaomiupup/projects/ucal ucal
```

## Tools

| Tool | Description |
|------|-------------|
| `ucal_platform_login` | Login to a platform (browser QR scan, cookie restore, or API key) |
| `ucal_platform_search` | Search content on a platform |
| `ucal_platform_read` | Read full content from a URL (returns Markdown) |
| `ucal_platform_extract` | Extract structured fields (returns JSON) |
| `ucal_browser_action` | Low-level browser automation (click, type, scroll, screenshot) |

## Supported Platforms

- `x` — X/Twitter (requires `X_BEARER_TOKEN` env var)
- `discord` — Discord (requires `DISCORD_BOT_TOKEN` env var)
- `xhs` — 小红书 (browser-based, needs manual QR login)
- `zhihu` — 知乎 (browser-based, needs manual login)
- `generic` — Any website (browser-based, no login)

## Example Usage

### Login to XHS (小红书)

```python
ucal_platform_login(platform="xhs", method="browser")
# Browser window opens → Scan QR code → Session saved
```

### Search XHS

```python
ucal_platform_search(platform="xhs", query="减脂餐", limit=10)
# Returns list of notes with titles, URLs, authors
```

### Read XHS Note

```python
ucal_platform_read(platform="xhs", url="https://www.xiaohongshu.com/explore/...")
# Returns full content in Markdown format
```

## Configuration

Edit `config/platforms.yaml` to add API tokens (optional, can use env vars):

```yaml
platforms:
  x:
    bearer_token: "YOUR_X_BEARER_TOKEN"
  discord:
    bot_token: "YOUR_DISCORD_BOT_TOKEN"
```

## Architecture

- **Browser Engine**: Playwright + playwright-stealth
- **Anti-Detection**: Random viewport, UA rotation, human behavior simulation (from csfilter)
- **Session Manager**: Saves cookies/storage_state to `config/sessions/`
- **Adapters**: Pluggable platform implementations (API vs Browser)

## Testing

```bash
uv run pytest tests/ -v
```
