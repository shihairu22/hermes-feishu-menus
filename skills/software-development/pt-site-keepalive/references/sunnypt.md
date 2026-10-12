# SunnyPT（sunnypt.top）—— 登录 + 签到（已接入例行，第 29 站）

> 结论：**Next.js SPA（非 NexusPHP）+ 纯 JSON API，纯 Python 即可**，无图形验证码、无 Cloudflare 挑战。
> 2026-09-27 实测：浏览器签到成功「获得 30 魔力，连续签到 1 天」；纯 Python 复现全链路成功。

## 1. 站点特征

- 域名 `sunnypt.top`，API 子域 `api.sunnypt.top`，直连可通（无需代理）。
- 前端 **Next.js App Router**（`/_next/static/chunks/...`），**不是 NexusPHP**。
- 主题是**海贼王**（登船 / 船员 / 赏金公会 / 名号 / 保持登船状态）。
- 站点版本 `v0.0.24`，Copyright 2023-2026 SUNNYPT.TOP。
- 规模：种子数 324、注册用户 2,735（小众站）。
- 页面路由（从 JS chunk `6287-*.js` 的路由表提取）：
  `/home`、`/torrents`、`/torrents?category=All`、`/user/control`、**`/user/attendance`（签到）**、
  `/user/bookmarks`、`/user/details`、`/user/assessments`、`/user/hit-and-runs`。
- 登录页 `/auth/sign-in`：字段 `username` / `password` / `code`（二次验证，可空）/ 一个复选框（rememberMe）。
  **没有图形验证码**，**没有 `securelogin` 这类 IP 锁定选项**（但仍遵守技能总则：复选框一律不勾）。

## 2. 登录（两步，必须都做）

```
① POST https://sunnypt.top/api/auth/session/login
   Content-Type: application/json
   {"username":"<账号>","password":"<密码>","code":"","rememberMe":true}
   → 200 {"data":{"username":"PTUSER"}}
   → 下发两个 cookie：AuthSession（path=/）、AuthRefresh（path=/api/auth/session）

② GET  https://sunnypt.top/api/auth/session        （带上面 cookie）
   → 200 {"data":{"accessToken":"<236 位 JWT>","class":7,"userId":10604,
                   "rememberMe":true,"sessionVersion":2,"iat":...,"exp":...}}
```

## 3. ★ 最大的坑：给 api 子域用的是 `accessToken`，不是 cookie

`api.sunnypt.top` 的接口**只认** `Authorization: Bearer <accessToken>`，其中 `accessToken` 来自第 ② 步的
`/api/auth/session` 响应体。以下做法**全部 401 `{"code":401000,"msg":"用户未登录"}`**：

- 用 `AuthSession` cookie 的值当 Bearer（那是会话 cookie，**不是** API 令牌）；
- 只带 cookie（`Cookie: AuthSession=...`）不带 Bearer；
- 只带 `x-auth-token` 之类的自定义头。

请求头要像浏览器：`Origin: https://sunnypt.top`、`Referer: https://sunnypt.top/`、`Accept: */*`。

## 3.5 ★ 续期优先（脚本已实现，别每次重登）

登录时站点下发**两个** cookie：

| cookie | path | 作用 |
|---|---|---|
| `AuthSession` | `/` | 会话 |
| **`AuthRefresh`** | `/api/auth/session` | **续期凭据** |

只要 `AuthRefresh` 还有效，**重新 `GET /api/auth/session` 就能换到新的 `accessToken`，无需再提交账号密码**。
`scripts/sunnypt_login.py` 已按此改造：

```python
COOKIE_FILE = '~/.pt-sessions/state/sunnypt_cookies.txt'
cj = http.cookiejar.MozillaCookieJar(COOKIE_FILE)
try:    cj.load(ignore_discard=True, ignore_expires=True)
except Exception: pass
# main() 里：先 GET /api/auth/session，拿到 accessToken 就跳过登录；否则才走完整登录
# 拿到 token 后 cj.save(ignore_discard=True, ignore_expires=True)
```

实测：第 1 次运行走完整登录并保存 cookie；第 2 次运行输出「**★ 续期成功（用历史会话换到 accessToken，236 位）**」。
**注意**：不要用普通 `CookieJar`（纯内存、进程结束即丢，会导致每次都重登）；cookie 文件别删。

## 4. 签到

```
GET  https://api.sunnypt.top/api/v1/attendance/status
     → {"code":0,"data":{"checked_in":true,"days":1,"total_days":562,
                        "points":30,"makeup_cards":0,"streak_bonuses":[...]}}
POST https://api.sunnypt.top/api/v1/attendance/check-in      （无 body）
     → 成功 {"code":0,...}；今天已签过 {"code":400001,"msg":"今天已经签到过了"}
GET  https://api.sunnypt.top/api/v1/attendance/monthly?month=9&year=2026   （签到日历）
GET  https://api.sunnypt.top/api/v1/user/details/info       （账号数据）
```

**判据顺序**：① `attendance/status` 的 `checked_in`（最硬）→ ② `check-in` 返回 `code:0`；
`code:400001` 表示今天已签过（**不是错误**）。

**签到规则**：基础 30 魔力；连续签到有加成（连签 10 天 +10、20 天 +20 … 150 天 +200）；
有**补签卡**机制（`makeup_cards`）。

## 5. 账号数据（2026-09-27）

- 用户 `PTUSER` / id **10604** / 等级 class **7**
- 魔力值（字段名 `seed_points`）：**1,205,784.58**
- 累计签到 **562 天**，连续 1 天（连续曾断过），补签卡 0 张
- 勋章：起航勋章、Sunny蛇年大吉、1st
- 邮箱 `2100***@qq.com`（与 M-Team 同一套账号体系）

## 6. 例行做法

跑 `scripts/sunnypt_login.py`（纯 Python，约 5 秒跑完）。
若账号以后开启两步验证：`SP_2FA=<动态码> python sunnypt_login.py`。
