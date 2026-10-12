# M-Team 保活脚本

> 2026-09-30 迁移：工具链从 `~/.hermes/cache/documents/mteam_keepalive_test/` 整体迁出——
> venv → `~/.pt-sessions/venv`；有效档案 → `~/.pt-sessions/mteam-session`；脚本 → 技能 `scripts/mteam_login.py`；
> 旧目录已删除。旧 `mteam_keepalive.py` / `mteam_run.sh` 归档于 `_research/_superseded/mteam-legacy/`。

- 现行脚本：`scripts/mteam_login.py`（登录 + 抓数据；档案 `~/.pt-sessions/mteam-session`）
- 运行：`cd /tmp && MTEAM_NO_DELAY=1 xvfb-run -a ~/.pt-sessions/venv/bin/python <技能目录>/scripts/mteam_login.py`
- 站点：首页 `https://kp.m-team.cc/index.php`；登录页 `/login`

## 登录流程

1. 打开站点 → 页面含「退出」= 已登录，直接抓数据
2. 否则填 `#username`、`#password`，点「登錄」按钮提交
3. 提交后出现邮箱验证码页：`#email` 邮箱框 + 「輸入6位數字驗證碼」验证码框 + 「獲取驗證碼」按钮（邮箱框和验证码框会同时出现）
4. **先往 `#email` 填 `MTEAM_EMAIL_USER`**（漏掉这步，按钮点了也不会发信）→ 补发原生事件解禁按钮（`press('Tab')` + `dispatchEvent` input/change/blur）→ 点「獲取驗證碼」→ IMAP 读最新 6 位数字码（INBOX + Junk 都扫）填入 → 再点「登錄」。邮件通常秒到；若长时间无信，先核对「邮箱填了没、按钮是否 enabled」，不要反复重点。
5. 成功判据「退出」+ 抓 魔力值/邀請/分享率/上傳量/下載量 → Telegram 通知

## .env 关键键

`MTEAM_USERNAME` / `MTEAM_PASSWORD` / `MTEAM_EMAIL_USER` / `MTEAM_EMAIL_APP_PASSWORD` / `MTEAM_SITE` / `MTEAM_TELEGRAM_TO`（`MTEAM_TOTP_SECRET`、飞书、邮件告警已废弃/未配置）；凭据库 = `~/.pt-sessions/.env`。

## 邮箱

QQ 邮箱（imap.qq.com:993）。真实 IMAP 应用密码（纯 ASCII）在 `~/.config/himalaya/config.toml` 的 `[accounts.qq] imap.sasl.plain.password.command` 中（himalaya v1 时代为 `backend.auth.cmd`，2026-10-12 升级 v2 后改名）；`.env` 里的 `MTEAM_EMAIL_APP_PASSWORD` 曾为中文占位符导致 `UnicodeEncodeError`，需从 himalaya 配置取真实值修复。

## 既有修复（不要回归）

`do_login` 中触发获取验证码的逻辑：只要 `#email` 存在就必须调用 `_request_email_code`，不要 gate 在“OTP 框缺失”上（曾导致验证码不发、IMAP 等 90s 超时的根因）。

**发码前置条件：必须先把邮箱填进 `#email` 再点「獲取驗證碼」。** M-Team 是 React 受控表单——只 `fill` 不补事件（或只点按钮不填邮箱）时按钮保持禁用、邮件根本不会发出，表现是「点过了但邮箱永远等不到码」。正确写法（`mteam_login.py` 已修入）：`page.fill('#email', MTEAM_EMAIL_USER)` → `press('Tab')` → `dispatchEvent`(input/change/blur) → 遍历 `button` 找文案含「獲取驗證碼/获取验证码」且 `is_enabled()` 的再点击。读码范围 INBOX + Junk；等待时长读 `MTEAM_EMAIL_CODE_TIMEOUT`（当前 90s）。

## 会话与冷启动（清空压测注意）

- 档案唯一位置：`~/.pt-sessions/mteam-session`（`mteam_login.py` 的 `PROFILE` 默认指向它；旧双副本已合并且旧目录已删）。`clear_sessions.py` 自动发现（扫 `~/.pt-sessions/*/`）。
- **M-Team 是 React SPA：只清 `cookies.sqlite*` 不会登出** —— 登录态还存在档案的 `storage/default/https+++kp.m-team.cc`（localStorage/IndexedDB）。要真·冷启动（完整登录流程复测），需把档案的该目录 + `https+++challenges.cloudflare.com` 一并删除；否则打开就是登录态，看起来像“没跑到登录流程”。

## 调度现状

现行 `mteam_login.py` 不挂调度；要定期保活需另接调度（如每 6 天一次）。旧 `mteam_keepalive.py`（带 cron 入口 `mteam_run.sh`）已归档、未挂接。
