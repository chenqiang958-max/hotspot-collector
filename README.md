# 🔥 热点收集器 / Hotspot Collector

微博 · B站 · 知乎 · 小红书 · 抖音，全网热点一站收集。
Collect trending topics from Weibo, Bilibili, Zhihu, Xiaohongshu and Douyin in one place.

网页界面操作：双击启动后自动在浏览器打开操作页面。
Web UI: double-click to launch, the control panel opens in your browser automatically.

---

## 中文说明

### 一、软件是干什么的

热点收集器把各平台的热搜、榜单内容抓到一起，帮你做选题和找产品灵感。

### 二、第一次使用：激活 + 设密码

第一次打开软件，会依次经过：**激活 → 设密码**，之后就能用了。

**第 1 步：输入激活码**
打开软件后先看到「请输入激活码」页面，把拿到的激活码填进去点「激活」。

**第 2 步：设置开机密码**
激活后设一个开机密码（至少 4 位），输两遍确认。以后每次打开软件输这个密码即可（激活码只用一次）。

> ⚠️ 密码不能找回！请务必记牢。忘了只能删除软件文件夹里的 `data` 文件夹重来（数据会丢）。

### 三、怎么抓取热点

部分平台（微博、知乎、小红书）需要先登录账号才能抓。

**方式 A：快捷抓榜单（最简单）**
在页面上找到「⚡快捷抓榜单」按钮（微博热搜、知乎热榜等），点一下自动完成抓取归类。

**方式 B：抓网页（适合要下拉的页面）**
1. 在「抓取网页」区把网址粘进去，点「打开网址」
2. 在打开的页面里往下拉到想要的位置（拉得越多抓得越全）
3. 回到软件点绿色「抓取」按钮

### 四、看数据、导出、筛选

- **按批次查看**：每次收集自动成为独立「批次」，按收集时间分组；1 小时内的收集算同一批
- **去重标记**：和上次重复的热搜打灰色「🔁上次也有」标记，勾选「隐藏和上次重复的」只看新增
- **筛选**：按平台、榜单、标签、时间、批次、关键词筛选
- **导出 Excel**：点「📥导出Excel」，含收集时间、是否重复、链接

### 五、数据管理

顶部「总条数」下方有橙色设置条，可设置数据保留天数、清理和清空数据。

### 六、常见问题

| 问题 | 解决办法 |
|---|---|
| 点「完成」提示读不到浏览器 | 软件弹出的登录窗口被关了，重新点「登录」；必须在软件弹出的窗口里登录 |
| 忘了开机密码 | 密码不能找回，删除 `data` 文件夹重设（数据会丢） |
| 激活码用不了 | 检查是否输完整、有无多余空格；一个码只绑一台电脑，重装/换电脑请联系卖家 |
| 首次运行 | 先双击「首次安装.bat」装运行环境（只需一次）；需要 Python + Chrome/Edge |

### 七、卖家：发码工具

`发码工具/` 文件夹是卖家生成激活码用的（⚠️ 不要发给客户）：

1. 双击 `start_keygen.bat`（打不开就点 `发码工具_如果打不开点这个.bat` 看原因）
2. 网页界面点「生成激活码」，可记录发给谁、复制、导出备份
3. 自检：双击 `check_keygen.bat`

**换密钥**（建议）：`hotspot/activation.py` 和 `发码工具/发码工具.py` 里各有一行 `SECRET = "CHANGE-ME-..."`，改成只有你知道的随机长字符串，**两个文件必须改成一模一样**。改完旧码全部失效。

---

## English Guide

### 1. What is it

Hotspot Collector scrapes trending lists from major Chinese platforms (Weibo, Bilibili, Zhihu, Xiaohongshu, Douyin) into one dashboard — for content planning and product inspiration.

### 2. First run: activation + password

On first launch you go through **activation → set password**.

**Step 1: Enter activation code**
Paste the code you received and click activate.

**Step 2: Set a startup password**
At least 4 characters, entered twice. From then on, just enter this password each launch (the activation code is one-time only).

> ⚠️ The password cannot be recovered! If forgotten, delete the `data` folder to start over (data will be lost).

### 3. How to scrape

Some platforms (Weibo, Zhihu, Xiaohongshu) require logging in first.

**Method A: Quick scrape (easiest)**
Click the "⚡快捷抓榜单" (quick scrape) buttons for Weibo hot search, Zhihu hot list, etc. — fully automatic.

**Method B: Scrape a web page (for scroll-loaded pages)**
1. Paste the URL in the "抓取网页" (scrape page) section, click open
2. Scroll down in the opened page (the more you scroll, the more gets captured)
3. Back in the app, click the green scrape button

### 4. View, filter, export

- **Batches**: each collection becomes a batch grouped by time; collections within 1 hour count as one batch
- **Dedup**: items seen last time get a grey "🔁上次也有" (seen last time) tag; tick "hide duplicates" to see only new items
- **Filters**: by platform, list, tag, time, batch, keyword
- **Export Excel**: exports current filtered view with timestamps, dup flags and links

### 5. Data management

Under the total count at the top there's an orange settings bar: set data retention days, clean up or wipe data.

### 6. FAQ

| Issue | Fix |
|---|---|
| "Can't read browser" after login | The popup login window was closed — click login again; you must log in inside the app's popup window |
| Forgot password | Cannot be recovered; delete the `data` folder to reset (data lost) |
| Activation code doesn't work | Check for typos/extra spaces; one code binds one machine — contact the seller after reinstall/new PC |
| First run | Double-click `首次安装.bat` once to set up the environment; requires Python + Chrome/Edge |

### 7. For sellers: keygen tools

The `发码工具/` folder generates activation codes (⚠️ never share with customers):

1. Double-click `start_keygen.bat`
2. Generate codes in the web UI, record recipients, copy, export backups
3. Self-check: `check_keygen.bat`

**Change the secret** (recommended): both `hotspot/activation.py` and `发码工具/发码工具.py` contain `SECRET = "CHANGE-ME-..."` — replace with your own long random string, **identical in both files**. Old codes become invalid after changing.

---

## Requirements / 运行环境

- Python 3.12+
- Chrome or Edge browser
- `pip install -r hotspot/requirements.txt`（或双击「首次安装.bat」）

## License / 开源协议

MIT License — see [LICENSE](LICENSE).
