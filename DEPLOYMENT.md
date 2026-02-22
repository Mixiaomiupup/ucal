# UCAL 部署完成

## 状态
✅ MCP Server 已注册
✅ 所有测试通过
✅ Playwright Chromium 已安装
✅ 服务器连接成功

## 已注册的工具

| 工具名 | 功能 |
|--------|------|
| `ucal_platform_login` | 登录平台（小红书、知乎、X、Discord） |
| `ucal_platform_search` | 搜索平台内容 |
| `ucal_platform_read` | 读取完整内容（Markdown格式） |
| `ucal_platform_extract` | 提取结构化字段（JSON格式） |
| `ucal_browser_action` | 低级浏览器操作（兜底方案） |

## 快速开始

### 1. 登录小红书（首次使用）

在新的 Claude Code 会话中调用：

```
ucal_platform_login(
    platform="xhs",
    method="browser"
)
```

这会：
1. 打开浏览器窗口
2. 显示小红书登录页
3. 等待你扫码登录（或手动登录）
4. 自动保存 session 到 `config/sessions/xhs_session.json`

### 2. 搜索小红书内容

登录后即可搜索：

```
ucal_platform_search(
    platform="xhs",
    query="减脂餐",
    limit=10
)
```

### 3. 读取笔记详情

```
ucal_platform_read(
    platform="xhs",
    url="https://www.xiaohongshu.com/explore/..."
)
```

## 支持的平台

| 平台 | 登录方式 | 搜索 | 读取 |
|------|---------|------|------|
| **xhs** (小红书) | QR扫码 | ✅ | ✅ |
| **zhihu** (知乎) | 手动登录 | ✅ | ✅ |
| **x** (Twitter) | API Token | ✅ | ✅ |
| **discord** | Bot Token | ✅ | ✅ |
| **generic** (任意网站) | 无需登录 | ❌ | ✅ |

## 使用建议

### 美食偏好调研工作流

1. **登录小红书和知乎**（一次性操作）
   ```
   ucal_platform_login(platform="xhs", method="browser")
   ucal_platform_login(platform="zhihu", method="browser")
   ```

2. **搜索相关内容**
   ```
   # 小红书搜索
   ucal_platform_search(platform="xhs", query="食格测评", limit=20)
   ucal_platform_search(platform="xhs", query="美食性格", limit=20)

   # 知乎搜索
   ucal_platform_search(platform="zhihu", query="为什么喜欢吃辣", limit=20)
   ```

3. **读取详细内容**
   ```
   # 从搜索结果中选择感兴趣的URL
   ucal_platform_read(platform="xhs", url="...")
   ```

4. **提取结构化数据**
   ```
   ucal_platform_extract(
       platform="xhs",
       url="...",
       fields=["title", "author", "content", "likes", "comments"]
   )
   ```

## 注意事项

1. **首次登录需要手动操作** — 浏览器窗口会弹出，扫码或输入密码后，session 会自动保存
2. **Session 持久化** — 登录一次后，下次启动会自动恢复登录状态
3. **反爬虫** — 已集成 playwright-stealth 和人类行为模拟，降低被检测风险
4. **速率控制** — 建议搜索/读取操作之间间隔 1-2 秒，避免触发限流

## 下一步

你现在可以：
- ✅ 开始登录小红书/知乎
- ✅ 搜索美食相关内容
- ✅ 分析用户偏好数据

需要我帮你开始第一次登录吗？或者直接用 Tavily 先做一轮初步搜索？
