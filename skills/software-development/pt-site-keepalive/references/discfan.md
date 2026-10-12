# DiscFan（discfan.net）—— 登录 + 签到（已接入例行，第 24 站）

> 结论：**纯 Python（urllib）即可完整登录 + 签到，无需浏览器**。
> 2026-09-27 实测：第 1 轮登录成功、`attendance.php` 打开即自动签到（第 1110 次，连续 15 天，+150 魔力值）。

## 一、站点特征

- 繁体 NexusPHP（`Powered by NexusPHP`），Cloudflare 前置（**无 JS 挑战**，curl 直连可用）
- 域名 `discfan.net`；规则文档在 `wiki.discfan.net`；注册仅限邀请
- 登录：`POST https://discfan.net/takelogin.php`（表单 `#login-form`）
- **challenge-response 认证**（表单含 `input[name="response"]`）
  - 表单字段（DOM 顺序）：`secret`(hidden) / `username` / **`password`（type=password，但没有 name，class=password）** / `two_step_code` / `imagestring` / `imagehash`(hidden) / `logout`(checkbox) / `#submit-btn`(type=button) / reset / `response`(hidden) / passkey
  - JS 流程：点按钮 → `POST /api/challenge`（body `{"username": ...}`）→ 算 response 填入 → `form.submit()`
- 图形验证码：`image.php?action=regimage&imagehash=<32位md5>&secret=`（150×40，**黑字 + 彩色噪点**）
- 尝试次数 **10 次**（`[10] 次連續登錄失敗將導致你的IP位址被禁用! 你還有 [N] 次嘗試機會`）
  - **验证码被判无效 → 不扣次数**（提示「圖片代碼無效！不要返回，圖片代碼已被清除！」）
  - **验证码通过但凭据被拒 → 扣 1 次**（提示「用戶名或密碼不正確！或者你還沒有通過驗證」）
- 签到：`GET /attendance.php` **打开即自动签**（同 HDFans / PANDA / HDHome）；用户栏显示 `[簽到已得150, 補簽卡: 2]`；有补签卡机制
- ⚠️ **本站是繁体站**：早期版 `scripts/nexus_session_checkin.py` 按简体「签到」匹配会误报「未见签到文字」（实测第 1124 次签到 +290 魔力、连续 29 天，页面明明写着「簽到成功」）；**现役脚本已简繁双匹配（源码 L79-83，2026-10-11 核实）**，正常运行即可。判成功仍以页面原文为准（繁体的「簽到成功」同样算），或看签到记录行。
- 登录页另有 **Passkey** 入口（`#passkey_login`）

## 二、★ 关键算法（曾经卡住很久的地方）

站点 JS（`js/common.js`）里那个封装**参数名有欺骗性**：

```javascript
function hmacSha256(key, message) {           // 看起来是 (key, message)
    return CryptoJS.HmacSHA256(message, key).toString(CryptoJS.enc.Hex);   // 实际换了个位置
}
```

登录页调用：`hmacSha256(challengeData.data.challenge, serverSideHash)`

⇒ 代入后 **key = challenge、message = serverSideHash**，即最终等价于：

```python
serverSideHash = sha256(secret + sha256(password))
response       = HMAC_SHA256(key=challenge, msg=serverSideHash)      # ← key 是 challenge！
```

**Python 正确写法**：

```python
chp  = hashlib.sha256(PWD.encode()).hexdigest()
ssh_ = hashlib.sha256((secret + chp).encode()).hexdigest()
resp = hmac.new(challenge.encode(), ssh_.encode(), hashlib.sha256).hexdigest()
```

⚠️ **写反（`hmac.new(ssh_, challenge)`）会得到 64 位 hex、格式完全正常，但服务器一律回「用戶名或密碼不正確」** —— 极易被误判成“账号/密码/ IP 问题”，实测排查了很久。

## 三、★ 验证码请求必须带浏览器 Accept 头

抓图必须用**图片类 Accept**，否则服务器返回的图与提交时校验的答案不匹配，**每次都被判「圖片代碼無效」**：

```python
IMG_ACCEPT = 'image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8'
```

（HTML 页面用 `text/html,application/xhtml+xml,...`；`/api/challenge` 用 `application/json`）

## 四、可复用流程（纯 Python，已验证）

```
1. GET  /login.php                       → 收 imagehash（hidden 字段）+ 建立会话
2. GET  /image.php?action=regimage&imagehash=<IH>&secret=   （必须带 IMG_ACCEPT）
   → 存图 → 打印点阵 → 双路识图 → 写 /tmp/discfan_captcha_answer.txt
3. POST /api/challenge  {"username": "PTUSER"}（JSON，Referer=login.php）
   → 返回 ret=0 / data.challenge(40位) / data.secret(20位)
4. 本地算 response（见第二节）
5. POST /takelogin.php  secret=&username=..&two_step_code=&imagestring=<码>&imagehash=<IH>&response=<64位>
   → 成功：URL 回 index.php / 正文含「歡迎回來, PTUSER」+「退出」
6. GET  /attendance.php  → 打开即签到（正文出现「簽到成功 這是您的第 N 次簽到，已連續簽到 M 天」）
```

现成脚本：`scripts/discfan_login.py`（两阶段等答案文件，自动登录 + 签到 + 保存会话）。

## 五、其他要点

- **会话可保存复用**：脚本用 `http.cookiejar.LWPCookieJar` 存到
  `~/.pt-sessions/state/discfan_cookies.txt`（2026-09-30 从旧目录迁入），下次可先试 cookie（有效就免登录、免验证码）。
- 验证码识图：黑字 + 彩色噪点 → `g < 100` 灰度阈值分离，噪点全消；**打印点阵要覆盖全宽**（只打到 x<130 会漏最后 1～2 个字符，曾误读成 5 位）。
- 字符集：实测出现 **E / D / C / M / F / H / N / B** 等，**6~8 位均有**（本次为 6 位）；NexusPHP 常规排除 `0/O/1/I`，遇到“圆环”优先判 **D** 而非 O/0。
- **双路识图必须一致再提交**：本站在两者分歧时，正确答案往往是视觉模型那一侧（曾经点阵误判 8、实为 6；误判 8、实为 9 —— 单像素的点多为彩色噪点，笔画粗细是 2 像素）。
- 出口：本机为家宽 IPv6（`240e:3a3:...`，CF `loc=CN`），**不需要代理、也不受 IPv6 影响**。
- 探针技巧（零成本）：`POST /api/challenge` 对**存在**的账号返回 `secret` 长度 **20**，对**不存在**的账号返回 **40**（随机假值防枚举）。
- 零成本诊断技巧：验证码故意填错（如 `ZZZZZZ`）提交 **不扣次数**，却能截获真实 POST 数据（确认 JS 是否算出了 response）。
