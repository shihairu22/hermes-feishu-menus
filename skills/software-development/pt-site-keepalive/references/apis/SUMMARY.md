# 29 站 API / 前端代码总览

> 2026-09-28 扫描 · 数据源：真实浏览器网络流量（22 站有档案）

| 站点 | 技术指纹 | 访问页 | 动态调用 | REST API | JS |
|---|---|---|---|---|---|
| Audiences | jQuery、NexusPHP | 8 | 1 | **0** | 13 |
| CHDBits | jQuery、NexusPHP | 8 | 0 | **0** | 11 |
| DiscFan | jQuery、NexusPHP | 3 | 1 | **0** | 16 |
| HDDolby | jQuery、NexusPHP | 8 | 0 | **0** | 18 |
| HDHome | jQuery、NexusPHP | 8 | 0 | **0** | 11 |
| HDSky | jQuery、NexusPHP | 8 | 1 | **0** | 18 |
| HDU | NexusPHP | 8 | 0 | **0** | 12 |
| KEEPFRDS | jQuery、NexusPHP | 8 | 3 | **0** | 21 |
| M-Team | - | 2 | 4 | **2** | 35 |
| MonikaDesign | Laravel | 8 | 7 | **7** | 6 |
| OpenCD | jQuery、NexusPHP | 8 | 2 | **0** | 15 |
| OurBits | jQuery、NexusPHP | 8 | 7 | **0** | 8 |
| PTHOME | jQuery、NexusPHP | 8 | 0 | **0** | 14 |
| PigGo | jQuery、NexusPHP | 8 | 0 | **0** | 19 |
| TTG | jQuery | 8 | 3 | **0** | 10 |
| U2 | jQuery、NexusPHP | 8 | 0 | **0** | 13 |
| UBits | jQuery、NexusPHP、TNode | 8 | 0 | **0** | 21 |
| 大青虫 | jQuery、NexusPHP | 7 | 0 | **0** | 18 |
| 天雪 | jQuery、Discuz | 8 | 0 | **0** | 13 |
| 朱雀 | Ant Design、TNode | 2 | 7 | **7** | 12 |
| 海棠PT | jQuery、NexusPHP | 2 | 0 | **0** | 10 |
| 织梦 | jQuery、NexusPHP | 8 | 0 | **0** | 20 |

## 关键结论

- **只有极少站点有 REST API**：朱雀（TNode）、MonikaDesign（UNIT3D/Laravel）、
  M-Team（带 `_sgin` 签名）、OurBits（独立域 `api.ourhelp.club`）、
  SunnyPT（Next.js）、BYR（Vue）、PigGo/UBits 的 wiki（Wiki.js GraphQL）。
- **NexusPHP 系（占 71%）没有 REST API**：服务端渲染 PHP，
  「接口」就是 `*.php` 端点（`takelogin.php` / `attendance.php` / `bakatest.php` …）。
- **天雪** 是 Discuz!（`forum.php?mod=…`）。**TTG** 是自研框架（仅 jQuery）。
- 详细数据：`apis/<site>.json`（原始）与 `apis/<site>.md`（可读）。