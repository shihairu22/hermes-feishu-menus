# 大青虫（`cyanbug.net`）

NexusPHP，**带 challenge-response 认证 → 必须用 Camoufox**（纯脚本 POST 会被服务端挂起）。2026-09-27 接入，例行第 23 站。

> **2026-09-28 二次验证**：算法已完全破解（见下），但用纯 Python 复现时，
> `POST takelogin.php` **稳定卡死到超时**（实测 `exit=124`，40 秒无响应），
> 而同一算法在浏览器里执行则正常。**确认是站点对脚本 POST 的 tarpit 反爬，不是算法问题。**
> → 结论：**大青虫保持 Camoufox 方案，不要再尝试纯脚本**。实验脚本已删除。

## 站点特征

- Cloudflare 承载，国内可达（1 秒内），**无 CF 挑战**
- **无图形验证码** → Camoufox 可全自动（不需人工识图）
- ⚠️ **只有 10 次连续登录失败机会**
- 登录按钮是 `type=button`（由 JS 接管提交，不是普通 submit）

## 认证机制（重要，下次别再从 curl 摸索）

1. JS 先 `POST /api/challenge`，body 是 JSON `{"username":"<用户名>"}`，返回：
   `{"ret":0,"data":{"challenge":"<40位hex>","secret":"<20位字母>"}}`
2. 计算：
   ```
   clientHashedPassword = sha256_hex(password)
   serverSideHash       = sha256_hex(secret + clientHashedPassword)
   response             = hmac_sha256(key=challenge, message=serverSideHash)
   ```
   来自站点自己的 `js/common.js`：
   ```javascript
   function sha256(message) { return CryptoJS.SHA256(message).toString(CryptoJS.enc.Hex); }
   function hmacSha256(key, message) { return CryptoJS.HmacSHA256(message, key).toString(CryptoJS.enc.Hex); }
   ```
   **注意 `hmacSha256` 的参数顺序是 (key, message)**（与 CryptoJS 原生相反，容易搞错）
3. 把 `response` 加入表单提交

**实测：即使按上面算法带上 `response`，纯脚本 POST `takelogin.php` 仍然挂住不返回**（GET 正常、站点本身健康）→ 所以正式流程**直接用 Camoufox**让浏览器自己走完整流程，不要徒手实现。

## 登录（Camoufox）

```bash
cd /tmp && MTEAM_NO_DELAY=1 xvfb-run -a --server-args="-screen 0 1280x900x24" \
  ~/.pt-sessions/venv/bin/python scripts/cyanbug_login.py
```

- `Camoufox(headless=False, os="windows", humanize=True, persistent_context=True, user_data_dir="~/.pt-sessions/bug-login-session")`
- 填 `#login-form input[name=username]` 与 `input[name=password]`，然后点 **`#login-form input[type="button"]`**（该按钮是 type=button，由站点 JS 处理；别指望 form.submit）
- 等 ~7 秒，判定 URL 到 `index.php` 且页面含「欢迎/退出」

### 两个必知的坑

1. `page.wait_for_selector('#login-form')` 会因“元素存在但不可见”**超时 30s** → 改用 `page.wait_for_selector('input[name="username"]', state="attached")`
2. 脚本被 timeout/kill 后会留下**残余 camoufox-bin + Xvfb 进程与 profile 锁**（`~/.pt-sessions/bug-login-session/lock`、`.parentlock`），使下一次启动“导航 60s 超时”（站点其实好好的）
   → 修复：`killall -q camoufox-bin; killall -q Xvfb` + `rm -f` 那两个锁文件（**用 killall 而非 `pkill -f`**，后者会杀掉自己的 shell）

## 账号现状（2026-09-27 实测）

| 项 | 值 |
|---|---|
| 分享率 | 5.078 |
| 上传 / 下载 | 15.471 TB / 3.047 TB |
| 魔力值 | 2,518,134.9 |
| 邀请 | 21 |
| 签到 | 第 1138 次，连续 10 天，本次得 3000 魔力值（补签卡 5）|

## 签到

- `GET /attendance.php` → **打开即自动签到**（页面出现「签到成功 这是您的第 N 次签到，已连续签到 X 天，本次签到获得 Y 个魔力值」）
- 用户栏显示 `[签到已得 N, 补签卡: M]`；首页那个 `[签到已得…]` 链接就指向 `attendance.php`
- `mybonus.php` 是魔力值兑换页（200，含“签到”字样但不是签到页）；`qiandao.php` 是 404

## 脚本

`scripts/cyanbug_login.py` —— Camoufox 单阶段（无验证码，一次跑完登录 + 账号信息 + 签到）。
