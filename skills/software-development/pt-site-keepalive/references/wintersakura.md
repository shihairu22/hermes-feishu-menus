# WinterSakura（冬樱，wintersakura.net）—— 登录 + 签到（已接入例行，第 25 站）

> 结论：**标准 NexusPHP，纯 Python（urllib）即可，无需浏览器**。
> 2026-09-27 实测：第 1 轮登录成功；`attendance.php` 打开即自动签到（第 939 次 / 连续 175 天 / +1888 魔力值）。

## 一、站点特征

- 标题：`WinterSakura :: 登录 A little Private Sharing Website. - Powered by NexusPHP`
- 界面**简繁混排**（首页用户栏是简体「欢迎回来, PTUSER」；导航有「论坛 / 种子 / 字幕 / 候选 / 征召」等）
- Cloudflare 前置（域名解析到 CF IP），但 **无 JS 挑战**，curl/urllib 直连可用
- 登录：`POST https://wintersakura.net/takelogin.php`
  - **表单是标准 NexusPHP**：`secret`(hidden) / `username` / **`password`（有 name，明文提交）** / `two_step_code` / `imagestring` / `imagehash`(hidden) / `logout` / `securelogin` / `ssl` / `trackerssl` / `input[type=submit]`
  - ⚠️ **没有 `input[name="response"]`、没有 `/api/challenge`、没有 crypto-js** → **不是 challenge-response 型**，不需要算 response
- 图形验证码：`image.php?action=regimage&imagehash=<hash>&secret=`（150×40，**黑字 + 彩色噪点**，底部有一条黑色横边框线——读点阵时要忽略 y=0 与 y=39 两行）
- 两步验证字段存在但**未开启可留空**
- 站点公告提到「邮件系统暂时禁用」（2024-04-29），不要指望邮件找回

## 二、验证码识图要点（与其它 NexusPHP 站共通）

- 彩色噪点 + 纯黑字 → 灰度阈值 `g < 100` 分离，噪点全消
- **必须去掉左右边框列与上下边框行**，再用「强列（列黑点数 ≥ 3）+ 间隔 < 4 合并」做字符分段
- **双路识图（自读点阵 + 视觉模型）一致再提交**；本次两边完全一致：`4R6N9R`
- 字符集：出现 4 / R / 6 / N / 9 等**字母+数字混合**；常规排除 `0/O/1/I`
- 取图请带上图片类 Accept 头（`image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8`）

## 三、可复用流程（已验证）

```
1. GET  /login.php                                  → 收 imagehash + 验证码 img src
2. GET  /image.php?action=regimage&imagehash=<IH>&secret=   （带图片 Accept）
   → 存图 → 打印点阵 → 双路识图 → 写 /tmp/ws_answer.txt
3. POST /takelogin.php
   secret=&username=PTUSER&password=<明文>&two_step_code=&imagestring=<码>&imagehash=<IH>&securelogin=yes
   → 成功：正文含「欢迎回来, PTUSER」+「退出」
4. GET  /attendance.php                             → 打开即签到
   → 正文出现「签到成功 这是您的第 N 次签到，已连续签到 M 天，本次签到获得 X 个魔力值」
```

现成脚本：`scripts/wintersakura_login.py`（两阶段等答案文件，登录 + 签到 + 保存会话）。

## 四、签到与账号

- 用户栏：`[签到已得1888, 补签卡: 76]`（与 DiscFan 同款的“签到已得 N”标记）
- 奖励规则（页面自述）：首次签到 50；**每次连续签到额外 +15，直到 1888 封顶**；连续第 10 天 +288；第 30 天 +1888；第 60 天 ……
- 有 **补签卡** 机制（点白色背景圆点补签）
- 2026-09-27 账号快照：魔力值 1,984,878.9 / 分享率 17.109 / 上传 39.673 TB / 下载 2.319 TB / 做种 2025 / 邀请 0(0)
- 会话可保存复用：`~/.pt-sessions/state/wintersakura_cookies.txt`（LWPCookieJar；2026-09-30 从旧目录迁入）

## 五、踩坑记录

- 探测时 `plugin_sign-in.php` / `signin.php` / `games.php` 均 404 → **签到入口就是 `/attendance.php`**
- 首页「签到相关链接」抓取可定位入口：`[签到已得N, 补签卡: M]` 指向 `attendance.php`
