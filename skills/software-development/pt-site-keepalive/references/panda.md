# PANDA（`pandapt.net`）—— 熊猫高清

NexusPHP 站，**结构与 HDFans 完全同款**，可直接复用同一个脚本套路。2026-09-27 接入，例行第 21 站。

## 站点特征（与 HDFans 一致）

- 域名 `pandapt.net`，**Cloudflare** 承载（cf-ray 显示 AMS 节点），国内解析正常，直连 0.7 秒
- **无 Cloudflare 挑战、无前端 JS 密码加密** → `urllib`/`curl` 即可，**不需要 Camoufox**（与 HDU 形成对比）
- 表单 `action=takelogin.php`，字段：`secret`(hidden，实测空)、`username`、`password`、`two_step_code`(可空)、`imagestring`(验证码)、`imagehash`(hidden)、`logout`/`securelogin`/`ssl`/`trackerssl`
- 验证码：`image.php?action=regimage&imagehash=<hash>&secret=`
- 提交时勾 **`securelogin=yes`**（自动登录）
- 成功判据同上：跳 `index.php` + 出现用户名 + 无 `name="username"`

## 账号现状（2026-09-27 实测）

| 项 | 值 |
|---|---|
| 用户名 | PTUSER |
| 上传 / 下载 | 44.785 TB / 1.721 TB |
| 分享率 | **26.018** |
| 魔力值 | 92,060.8 |
| 签到 | 今天已签（签到已得 285，补签卡 23 张）|

## 签到

- `GET /attendance.php` —— **打开即自动签到**（与 HDFans / HDHome / PTHOME 同款）
- 已签到判据：用户栏出现 `[签到已得 N, 补签卡: M]`，或 attendance.php 出现「这是您的第 N 次签到，已连续签到 X 天，本次签到获得 Y 个魔力值」（实测 2026-09-27：第 1172 次 / 连续 56 天 / 得 285）

## ⚠️ 登录尝试只有 10 次（比别的站少）

- 登录页明确提示 `[10] 次连续登录失败将导致你的IP地址被禁用` （HDFans 是 30 次）
- 因此：验证码没双路读准**不要提交**；能用已保存的 cookie 就别重新登录
- 会话文件 `/tmp/panda_cookies.txt` **是 LWPCookieJar 格式**：读写都要用 `http.cookiejar.LWPCookieJar`，用 `MozillaCookieJar` 加载会报 `does not look like a Netscape format cookies file`
- 判定会话是否有效：**看能否拿到 `attendance.php` / `mybonus.php` 的真实内容**（不能拿首页是否含 `name="username"` 判——首页本身可能就带登录元素，会误报失效）

## 验证码识图

- 与 HDFans 同类：纯黑文字 + 彩色噪点，`(R<100)&(G<100)&(B<100)` 分离（本次 597 个黑像素，干扰很少）
- 双路交叉：视觉模型 + ASCII 点阵，一致再提交
- 实测：`C783M9`（第 1 位 C/G 争议 → 两路都判 C：右侧开口处无 G 的内向小钩）

## 脚本

`scripts/panda_login.py`（已存在，可直接用）：

```bash
# 阶段1 取图（零消耗）
<camoufox venv>/bin/python scripts/panda_login.py --stage1
# 阶段2 提交 + 签到检查
<camoufox venv>/bin/python scripts/panda_login.py --stage2 <六位验证码>
```

需要新站时，从 HDFans 脚本派生即可：
生成器（推荐）：`scripts/make_captcha_login.py`——模板＋站点常量统一维护；`--check` 验证现有两站与生成结果逐字节一致，新站在 `SITES` 加一条后 `--write`。历史手工公式（备查）：`sed 's|hdfans\.org|<新域名>|g; s|hdfans_|<前缀>_|g' hdfans_login.py > <新站>_login.py`
