# 海棠PT（htpt.cc）—— 登录 + 签到（已接入例行，第 28 站）

> 结论：**标准 NexusPHP 分支，纯 Python（urllib）即可**，但有一个**致命坑**（见第二节）。
> 2026-09-27 实测：去掉 `securelogin` 字段后第 1 轮登录成功；`attendance.php` 显示「您今天已经签到过了」（当日已签，+350 魔力值）。

## 一、站点特征

- 标题 `海棠PT - 登录`，口号「一树梨花压海棠」；分支信息见 `aboutnexus.php`：**主版本 `HTPT-PT`、次版本 `1.1`、发布时间 2021-10-15**
- 域名 `www.htpt.cc`；CF 解析但**无 JS 挑战**，**本机直连即可，不需要代理**
- 登录：`POST https://www.htpt.cc/takelogin.php`（登录页注释写着「登录表单（原版逻辑 100% 保留）」）
- **登录页零 JavaScript**（内联 script 0 个、外部 script 0 个、无 on\* 事件）→ HTTP 提交与浏览器提交完全等价
- 表单字段：`username` / `password`（**有 name，明文**）/ `imagestring` / `imagehash`(hidden) / `logout` / `securelogin` / `ssl`(disabled) / `trackerssl`(disabled) / submit / reset
- 图形验证码：`image.php?action=regimage&imagehash=<32位md5>`（150×40，黑字+彩色噪点）
- **Cookie 只在登录成功后才发**（`c_secure_uid` / `c_secure_pass` / `c_secure_ssl` / `c_secure_tracker_ssl` / `c_secure_login`，经典 NexusPHP 会话 Cookie）；登录失败时 `Set-Cookie: None`
- 尝试次数：**10 次**（`[10] 次连续登录失败将导致你的IP地址被禁用!`）
- 注册：**仅邀请注册**；找回密码 `recover.php`（重置密码，新信息发邮箱）；重发验证邮件 `confirm_resend.php`
- 账号保留规则（站点公告）：未封存账号连续 **180 天**不登录删号；无流量账号 90 天删号

## 二、★ 致命坑：不要发 `securelogin` 字段！

**现象**：带上 `securelogin=yes` 提交，服务器一律回

```
登录失败！错误 : 用户名或密码不正确！或者你还没有通过验证
```

（有时是静默 302 回 `login.php`、连错误都不显示；尝试次数会照常递减）

**真相**：用浏览器实际提交时抓到的表单体是

```
username=PTUSER&password=***&imagestring=***&imagehash=***
```

—— **根本没有 `securelogin`**（那个复选框默认不勾）。改成一模一样后，**纯 Python 第 1 轮就登录成功**。

⇒ **提交字段严格只发 `username` / `password` / `imagestring` / `imagehash` 四个**，
   **不要带 `securelogin`（也不要带 `ssl` / `trackerssl` / `logout`）**。

⚠️ 这个坑极具误导性：错误文案会说“用户名或密码不正确！或者你还没有通过验证”，
   很容易被误判成“密码错/账号未验证”——实际是**多发了一个复选框字段**。

## 三、可复用流程（已验证）

```
1. GET  /login.php                          → 收 imagehash + 验证码 img src
2. GET  /image.php?action=regimage&imagehash=<IH>（带图片类 Accept）
   → 存图 → 打印点阵 → 双路识图 → 写 /tmp/ht_answer.txt
3. POST /takelogin.php
   username=<用户名>&password=<明文>&imagestring=<码>&imagehash=<IH>     ← 只这四个！
   → 成功：正文含「欢迎回来, <用户名>」+「退出」
4. GET  /attendance.php                     → 签到
   → 已签：正文「抱歉 您今天已经签到过了，请勿重复刷新。」
```

现成脚本：`scripts/htpt_login.py`（两阶段验证码 + 登录 + 签到 + 保存会话）。

## 四、签到与账号

- 签到入口：`GET /attendance.php`（`plugin_sign-in.php` / `signin.php` 均 404）
- 用户栏会显示 `(签到已得350)` 这种“当日已签”标记
- 2026-09-27 账号快照：魔力值 199,699.4 / 分享率 7.199 / 上传 5.883 TB / 下载 836.82 GB / 做种 111 / 邀请 9(0) / H&R 0 / 违规 0/10
- 会话可保存复用：`~/.pt-sessions/state/htpt_cookies.txt`（LWPCookieJar；2026-09-30 从旧目录迁入）

## 五、其它

- 站点有「游戏厅 / 曲苑杂坛 / 有声读物 / 保种 / ＰＭ」等版块；页脚显示 `Running PHP v8.2.29` + Redis
- 站规提醒：下载量 >100G 且分享率 <0.2 会被系统立即封禁
