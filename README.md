# 网文一键发布系统 — Multi-Platform Novel Auto Publish

支持**起点中文网**、**番茄小说**、**飞卢小说**、**七猫小说**、**咪咕文学**五大平台的一键批量发布。

---

## 快速开始

### 1. 安装依赖

```bash
pip install playwright
playwright install chromium
```

### 2. 登录平台（每平台只需一次）

```bash
python login.py qidian      # 起点
python login.py fanqie      # 番茄
python login.py faloo       # 飞卢
python login.py qimao       # 七猫
python login.py migu        # 咪咕
```

登录后会在项目根目录生成 `state_<平台>.json`，保存 cookie 和登录状态，后续发布时会自动加载，无需重复登录。

### 3. 准备章节目录

```
chapters/
  <平台>/
    <书名>/
      第1章 标题.txt
      第2章 标题.txt
      ...
```

示例：

```
chapters/
  migu/
    西域少年行，风雪定山河/
      第1章 风雪驿铃.txt
      第2章 半符托孤.txt
  qidian/
    我的小说/
      第1章 开篇.txt
```

> 章节文件命名需包含"第N章"，如 `第1章 xxx.txt`、`第01章 xxx.txt`，系统按章节号自然排序发布。

### 4. 发布

```bash
# 交互模式（会让你选书、选数量）
python platforms/migu.py

# 无人值守模式 — 发布全部章节
python platforms/migu.py --headless --no-prompt

# 发布指定数量
python platforms/migu.py --count 1 --headless --no-prompt

# 指定书名 + 发布 N 章
python platforms/migu.py --book "西域少年行，风雪定山河" --count 3 --headless --no-prompt
```

发布成功后，txt 文件会自动归档到 `uploaded/<平台>/<书名>/` 目录。

---

## 命令行参数

| 参数 | 说明 | 默认值 |
|---|---|---|
| `--book BOOK` | 指定书名（文件夹名），不指则自动选第一本或交互选择 | — |
| `--count N` | 发布 N 章，不指则发布全部 | 全部 |
| `--volume N` | 归档到第 N 卷子目录 | 不分子卷 |
| `--no-prompt` | 无人值守模式，不等待用户输入 | 交互模式 |
| `--headless` | 后台运行，不显示浏览器窗口 | 显示浏览器 |

### 各平台入口

```bash
python platforms/migu.py   [参数]    # 咪咕文学
python publish.py --platform qidian [参数]    # 起点中文网
python publish.py --platform fanqie [参数]    # 番茄小说
python publish.py --platform faloo  [参数]    # 飞卢小说
python publish.py --platform qimao  [参数]    # 七猫小说
```

---

## 项目结构

```
novel_auto_publish/
├── publish.py              # 核心发布引擎（Playwright 自动化）
├── login.py                # 统一登录入口
├── platform_config.py      # 各平台配置（URL、按钮文本、选择器）
├── platform_utils.py       # 平台工具函数
├── anti_detect.py          # 反检测浏览器启动
├── main_webview.py         # WebView 桌面应用
│
├── platforms/              # 平台入口脚本
│   ├── migu.py             # 咪咕一键发布
│   ├── migu_login.py       # 咪咕登录
│   ├── fanqie_publish.py   # 番茄发布
│   ├── fanqie_login.py     # 番茄登录
│   └── ...
│
├── chapters/               # 待发布章节（按平台→书名组织）
│   ├── migu/
│   ├── qidian/
│   ├── fanqie/
│   ├── faloo/
│   └── qimao/
│
├── uploaded/               # 已发布归档（自动移入）
│   ├── migu/
│   ├── qidian/
│   └── ...
│
├── debug/                  # 调试截图和 HTML（发布过程中自动保存）
├── logs/                   # 定时任务日志
│
├── state_migu.json         # 咪咕登录态
├── state_qidian.json       # 起点登录态
├── state_fanqie.json       # 番茄登录态
├── state_faloo.json        # 飞卢登录态
└── state_qimao.json        # 七猫登录态
```

---

## 定时任务（Windows 任务计划程序）

创建计划任务，每天定时自动发布：

```
操作：启动程序
程序：python
参数：platforms/migu.py --headless --no-prompt --count 2
起始于：D:\BaiduSyncdisk\coding\novel_auto_publish
```

日志输出到 `logs/scheduled_publish.log`。

---

## 调试

如果发布失败，检查 `debug/` 目录下的截图和 HTML：

| 文件 | 说明 |
|---|---|
| `book_manage_page.png` | 作品管理页面 |
| `write_page_after_entry.png/html` | 进入编辑器后 |
| `after_fill_before_publish.png/html` | 填写标题和正文后 |
| `migu_after_publish_click.png/html` | 点击发布按钮后 |
| `migu_publish_unverified.png/html` | 发布验证失败时的页面 |

不带 `--headless` 运行可以看到浏览器实时操作过程：

```bash
python platforms/migu.py --count 1 --no-prompt
```

---

## 常见问题

**Q: 提示 "Login state not found"？**

先运行 `python login.py <平台>` 登录一次，会生成对应的 `state_*.json` 文件。

**Q: 登录状态过期了？**

重新运行 `python login.py <平台>`，在弹出浏览器中重新登录即可刷新 cookie。

**Q: 章节顺序不对？**

确保文件名包含"第N章"，系统按章节号自然排序，不是按文件名排序。

**Q: 咪咕发布后提示定时发布对话框？**

系统已自动处理咪咕的两层确认对话框（字数确认 → 定时发布），无需手动操作。如果仍有问题，去掉 `--headless` 观察实际页面情况。
