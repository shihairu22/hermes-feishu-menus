---
name: pthome
description: PTHOME (pthome.net) 登录 + 签到：NexusPHP + Cloudflare 挑战，纯黑文字验证码
---

# PTHOME（`www.pthome.net`）

NexusPHP 影视站（PT/下载/电影/蓝光电影），**前置 Cloudflare JS 挑战**。
凭据**与馒头一致**（`PTUSER`），从 M-Team 的 `.env` 读取。无 2FA。

- 登录尝试：**10 次**（`[10] 次连续登录失败将导致你的IP地址被禁用! 你还有 [10] 次尝试机会`）。

## 1. Cloudflare 挑战 —— curl 过不去，必须用 Camoufox

```bash
curl -I https://www.pthome.net/index.php
# HTTP/2 403   cf-mitigated: challenge   →  “Just a moment...”
```

Camoufox（`os="windows"`, `humanize=True`）实测 **5 秒过挑战**，拿到 `cf_clearance`。
持久档案：`~/.pt-sessions/pthome-login-session`。

## 2. 登录

```
POST https://www.pthome.net/takelogin.php
  username      用户名
  password      密码
  imagestring   图形验证码
  imagehash     隐藏字段（与验证码图配套）
  scode         两步验证码（未开 2FA 时留空）
  securelogin / ssl / trackerssl   高级选项（SSL）
```

脚本：`scripts/pthome_login.py`（两阶段：先导出验证码 → `CAPTCHA_READY` → 轮询 `/tmp/pthome_captcha_answer.txt`，支持写 `RELOAD` 换一张；提交前硬校验用户名/密码长度/验证码；页面内 JS 提交）。

成功判据：跳到 `index.php` 且出现 `欢迎回来, PTUSER [退出]`。

## 3. 验证码（150×40，与 OpenCD 同款）

主色：

| 颜色 | 含义 |
|---|---|
| `RGB(228,228,228)` | 浅灰背景 |
| **`RGB(0,0,0)`** | **文字（纯黑，约 774 px）** |
| `RGB(185,205,159)` / `RGB(231,151,115)` 等 | 彩色噪点 |

分离：`a.sum(axis=2) < 200` → 只剩文字；**记得把图像四周的黑色边框也剔掉**（边框占约 390 px，会把列投影切成一整段）。

### ⚠️ 这条很重要：净化图 + 视觉模型 比「草率点阵判读」更准

实测 6 位验证码（实际 `NEM6C9`）：
- 我的**点阵草读**得到 `HEHOC8`（前两位就错了）
- **视觉模型在「去噪去边框、放大 6 倍」的净化图上读 `NEM6C9` —— 完全正确**，服务器接受

所以：点阵只有在**逐字符切分 + 谨慎判读**时才有裁决力；拿整图粗扫出的点阵结论，不要压过净化图上的视觉结果。两者不一致时，优先信视觉（验证码错通常不扣次数，可以再验一次）。

## 4. 签到：GET `/attendance.php`

首页用户栏的 **「签到得魔力」** 指向 `attendance.php`；**打开即自动签**（与 HDHome 同机制，无需表单/验证码）。

实测（2026-09-26）：

```
签到成功 这是您的第 1249 次签到，已连续签到 194 天，本次签到获得 70 个魔力值。
魔力值 643,293.5 → 643,363.5（+70）
用户栏出现「(签到已得70)」
```

规则：首次 +5；每次额外 +1 至 20 封顶；连续 10/20/30/40 天分别额外 +10/+20/+30/+40（不累计）。

**判据**：`body` 出现「签到成功」+ 用户栏 `(签到已得N)` + 魔力值增长。

## 5. 状态基线（2026-09-26）

- `PTUSER`｜魔力值 643,363.5｜做种积分 1,455,782.5｜邀请 0/0
- 分享率 24.135｜上传 147.997 TB｜下载 6.132 TB｜H&R 0/0｜流量排名 102 / 745
- 第 1249 次签到，连续 194 天
