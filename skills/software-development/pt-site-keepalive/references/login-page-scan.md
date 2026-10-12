# 29 站登录页源码级扫描（2026-09-27）

> 方法：纯 HTTP 只读抓取各站登录页，提取表单结构 / 隐藏令牌 / JS 引用 / 防护层。
> 脚本：`scripts/scan_all_login_pages.py`（可重跑）

## 一、防护层分布

**被 Cloudflare 拦（403 Just a moment）—— 8 站**：
Audiences、OurBits、PigGo、UBits、HDDolby、TTG、PTHOME、织梦

**可直连拿到真实登录页 —— 20 站**

> 注：TTG 返回 200 但页面内含 CF 标记（挑战在资源层）；U2 的 `/login.php` 为 404，
> 真实入口是 `/portalbc.php`（旧版）或 `/portal.php`（新版）。

## 二、表单结构对比

| 站点 | form action | 密码字段 | 隐藏字段 |
|---|---|---|---|
| M-Team | `—` | — | — |
| KEEPFRDS | `takelogin.php` | password | — |
| HDSky | `/login.php` | password | imagehash |
| CHDBits | `/login.php` | password | imagehash |
| HDHome | `/login.php` | password | — |
| OpenCD | `/login.php` | password | imagehash |
| 天雪 | `member.php?mod=logging&amp;action=login&amp;loginsubmit=yes&amp;infloat=yes&amp;lssubmit=yes` | password | skfaid,quickforward,handlekey,mod,formhash |
| MonikaDesign | `https://monikadesign.uk/login` | password | _token |
| 朱雀 | `—` | — | — |
| TorrentLeech | `/user/account/login/` | password | — |
| HDFans | `/login.php` | password | secret,secret,imagehash |
| HDU | `/login.php` | password | imagehash,type,sent,type |
| PANDA | `/login.php` | password | secret,secret,imagehash |
| SJTU葡萄 | `takelogin.php` | password | checkcode |
| 大青虫 | `/login.php` | password | secret,secret |
| DiscFan | `/login.php` | — | secret,secret,imagehash,response |
| 冬樱 | `/login.php` | password | secret,secret,imagehash |
| 海棠PT | `/login.php` | password | imagehash |
| SunnyPT | `—` | password | — |

## 三、前端加密 / 挑战机制

| 站点 | 关键词 | JS | 结论 |
|---|---|---|---|
| HDU | bcrypt | — | 密码前端 bcrypt 加密 |
| 大青虫 | challenge, crypto, hmac, sha256 | crypto-js.js | challenge-response |
| DiscFan | challenge, crypto, hmac, sha256 | crypto-js.js | challenge-response（表单无 password 字段）|
| KEEPFRDS | challenge | api.js | Cloudflare Turnstile |

## 四、CSRF / 令牌（meta 标签）

- MonikaDesign：`csrf-token`（标准 Laravel CSRF）
- 朱雀：`x-csrf-token` —— 所有 `/api/*` 请求**必须带此头**（见 `references/zhuque.md`）

## 五、关键结论

1. **9 站使用图形验证码**（表单含 `imagehash`）：HDSky、CHDBits、OpenCD、HDFans、
   HDU、PANDA、DiscFan、冬樱、海棠PT —— 与技能记录一致，验证码流程覆盖完整。
2. **DiscFan 表单无 `password` 字段**，密码由 JS 折进 `response`，印证 challenge-response 判定。
3. **冬樱的“RSA”是误报**：扫描脚本大小写不敏感，把站点名 `WinterSakura` 里的片段当成了 `rsa`；
   实际是明文 POST。**教训：关键词扫描要加词边界，别把品牌名当算法名。**
4. 表单里普遍存在 `securelogin` / `logout` / `ssl` 复选框 —— **一律不勾、不带**。

## 六、原始数据

`~/safeline-research/site_source_scan.json`（含每站 inputs / js / meta / 耗时）
