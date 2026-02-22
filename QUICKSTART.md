# UCAL 快速开始指南

## ✅ 部署状态

- **全局 MCP**: 已注册到 `~/.claude.json`
- **工具数量**: 5 个
- **可用范围**: 所有 Claude Code 会话（重启后生效）

## 🔄 重启 Claude Code

```bash
# 1. 退出当前会话（Ctrl+D 或输入 exit）
exit

# 2. 重新启动（任意目录都可以）
claude
```

## 🎯 第一次使用：登录小红书

重启后，在新会话中运行：

```
请帮我登录小红书，使用 ucal_platform_login 工具，参数：
- platform: xhs
- method: browser
```

Claude 会：
1. 打开浏览器窗口
2. 显示小红书登录页
3. 等待你扫码或输入账号密码
4. 登录成功后自动保存 session

## 📝 常用操作示例

### 搜索小红书内容

```
使用 ucal_platform_search 搜索小红书，参数：
- platform: xhs
- query: 减脂餐推荐
- limit: 10
```

### 读取笔记详情

```
使用 ucal_platform_read 读取小红书笔记，参数：
- platform: xhs
- url: [从搜索结果复制的URL]
```

### 提取结构化数据

```
使用 ucal_platform_extract 提取数据，参数：
- platform: xhs
- url: [笔记URL]
- fields: ["title", "author", "content", "likes", "comments"]
```

## 🔍 美食偏好调研完整流程

### Step 1: 登录平台（一次性）

```
1. 登录小红书：ucal_platform_login(platform="xhs", method="browser")
2. 登录知乎：ucal_platform_login(platform="zhihu", method="browser")
```

### Step 2: 搜索关键内容

```
# 小红书搜索
ucal_platform_search(platform="xhs", query="食格测评", limit=20)
ucal_platform_search(platform="xhs", query="美食性格", limit=20)

# 知乎搜索
ucal_platform_search(platform="zhihu", query="为什么喜欢吃辣", limit=20)
ucal_platform_search(platform="zhihu", query="美食偏好心理学", limit=20)
```

### Step 3: 批量提取数据

从搜索结果中选择 Top 10-20 个热门内容，批量读取：

```
# 方法1：逐个读取
for url in [url1, url2, url3, ...]:
    ucal_platform_read(platform="xhs", url=url)

# 方法2：结构化提取（推荐）
for url in [url1, url2, url3, ...]:
    ucal_platform_extract(
        platform="xhs",
        url=url,
        fields=["title", "author", "content", "tags", "likes"]
    )
```

### Step 4: 数据分析

让 Claude 分析提取的数据，总结：
- 高频关键词（口味偏好、食材偏好）
- 用户画像（年龄、地域、消费水平）
- 内容特点（测评维度、表达方式）
- 趋势洞察（新兴美食类型、网红单品）

## 🛠️ 故障排查

### 问题1：看不到 ucal 工具
**原因**: 配置修改后未重启会话
**解决**: 完全退出 Claude Code 后重新启动

### 问题2：登录失败
**原因**: 浏览器窗口未正确显示
**解决**: 检查 `config/platforms.yaml` 中 `headless: false`

### 问题3：搜索无结果
**原因**: 未登录或 session 过期
**解决**: 重新运行 `ucal_platform_login`

### 问题4：被平台限流
**原因**: 请求频率过高
**解决**: 在搜索/读取之间添加 1-2 秒延迟

## 📊 数据导出建议

分析完成后，可以让 Claude：
1. 生成 Excel 报告（使用 `xlsx` skill）
2. 创建 Markdown 总结（保存到 Obsidian）
3. 可视化数据（生成图表）

## 🔒 隐私提示

- Session 文件存储在 `config/sessions/`，包含登录 Cookie
- 建议将 `config/sessions/*.json` 加入 `.gitignore`（已配置）
- 不要分享 session 文件
