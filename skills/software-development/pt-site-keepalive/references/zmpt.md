# 织梦（zmpt.cc）—— 登录 + 签到（已接入例行，第 26 站）

> 结论：**必须用 Camoufox 穿透 Cloudflare，但登录极简** —— 无图形验证码、无 challenge-response、无前端加密，填表提交即可。
> 2026-09-27 实测：第 1 次登录直接成功；`attendance.php` 打开即自动签到（第 1108 次 / 连续 82 天 / +300 电力值）。

## 一、站点特征

- 标题：`Just a moment...` → 穿透后为 `织梦 :: 登录 - Powered by NexusPHP`
- **Cloudflare JS 挑战（核心特征）**：直接 `curl https://zmpt.cc/login.php` 返回 **403 + Just a moment...**，**必须 Camoufox（带 xvfb）**，等挑战通过后页面才出现登录表单
- 别名域名：`zmpt.club`（同一个站）
- 界面**简体**；魔力值在本地叫「**电力值**」
- 登录：`POST https://zmpt.cc/takelogin.php`
  - 表单字段：`secret`(hidden×2) / `sitelanguage`(select) / `username`(text, class=username) / **`password`(type=password，有 name，明文)** / `two_step_code`(text) / `#wechat-qr-login`(IYUU 扫码按钮) / **`input[type=submit]`（值「登录」）** / reset
  - ✅ **无图形验证码**（无 regimage / image.php）
  - ⚠️ **实际上未启用 challenge-response**：页面里确实有 `/api/challenge` + `crypto-js` + 那段“通用 login()”JS，但那段 JS 只绑在 `input[type=button]` 的 click 上，**本站在用的是 `input[type=submit]`**，且 DOM 里**没有 `input[name=response]`** → 走**原生表单提交（明文密码）**。
    （NexusPHP 模板里的通用判断：`useChallengeResponseAuthentication = jqForm.find("input[name=response]").length > 0`，为假则 `jqForm.submit()`。）
- 尝试次数：**10 次**（`[10] 次连续登录失败将导致你的IP地址被禁用! 你还有 [N] 次尝试机会`）
- 其它入口：IYUU 扫码登录（`#wechat-qr-login`）、邀精频道/银行/借贷/双色球 等作弊玩法

## 二、可复用流程（已验证）

```
Camoufox（persistent_context，xvfb-run）：
1. goto /login.php → 等 CF 挑战通过（轮询直到出现 input[name=username]，每 2.5s，最多 12 次）
2. fill username / type password / 勾 securelogin（若存在）
3. click input[type=submit]
4. 成功判据：URL 变 index.php 且正文含「退出」/「欢迎回来」
5. goto /attendance.php → 打开即签到
   → 正文出现「签到成功 这是您的第 N 次签到，已连续签到 M 天，本次签到获得 X 个电力值」
```

现成脚本：`scripts/zmpt_login.py`（Camoufox 登录 + 签到；持久档案 `~/.pt-sessions/zm-session`，已登录时会跳过登录）。

## 三、签到与账号

- 用户栏：`[签到已得300, 补签卡: 3]`（同 DiscFan / 冬樱 的“签到已得 N”标记）
- 签到奖励有连续加成（日所得 280～300 波动，连续天数越高越高）
- 有 **补签卡** 机制（点白色背景圆点补签）
- 2026-09-27 账号快照：分享率 6.183 / 上传 21.466 TB / 下载 3.472 TB / **电力值 2,688,370.9** / 当前活动 335 / 邀请 0(0) / 做种 1

## 四、踩坑记录

- `plugin_sign-in.php` / `signin.php` 均 **404** → 签到入口就是 `/attendance.php`
- 首页里跟签到相关的链接只有：`[签到已得N, 补签卡: M]` → `attendance.php`；`电力值 ...` → `mybonus.php`
- 探测时必须先用浏览器穿 CF，**不要用 curl 断言站点特征**（curl 只会看到 403 挑战页，什么字段都读不到）
