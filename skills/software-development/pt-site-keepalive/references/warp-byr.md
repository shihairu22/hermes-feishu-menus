# BYR（北邮人）走 Cloudflare WARP —— mihomo wireguard 出口

> ⚠️ **【已全部下线】NAS 上这套 WARP 出站（37 个 wireguard + `MASQUE兜底` + `WARP`/`自动选最快` 组 + `byr.pt -> WARP` 规则）已按用户要求整体删除，配置回滚到引入 WARP 之前的原版。**
> 本文件现在只是**研究记录 + mihomo 操作手册**：下面所有「线上配置」描述都已失效，**不要照它去改线上**。
> 原版指纹：**0 个 `type: wireguard` 出站、0 个 `WARP` 组、0 个 `type: masque`**，且 `byr.pt` 规则指向 `V6代理`（该组依赖的二号订阅集长期全挂 ⇒ BYR 走代理不通，**这就是「原版」的真实状态，不是回滚失败**）。回滚做法见 §十。

## 一、为什么要这么干

- BYR 是**纯 IPv6 站点**，按源 IP 拦人：家宽电信 IPv6（`240e::/16` / `2409::/16` / `2408::/16`）一律 **403**（返回 `wengine-auth-failed` 鉴权页）。
- 实测对照：**直连 byr.pt → 403**；**经 WARP → 302 → 登录成功**。
- BYR 回显 `remote_addr = 2a09:bac1:1980:8::208:cb` = **AS13335 Cloudflare** ⇒ BYR 放行 CF 的 IPv6 段。
- BYR 站规（`rules.php`，194 行）**不禁止代理**：「代理 / proxy / VPN / 盒子 / seedbox」零命中；FAQ 2.12 只说明「访问首页返回 403 = 所在网络不能使用 BYRBT」。

> 对照：M-Team 明文禁止代理连 tracker；HDSky 把 VPN/代理当盒子设备。BYR 没有这类条款。

## 二、架构（**历史形态 —— 线上已删除，见文件头**）

```
BYR 请求（byr_http.py，走 http://127.0.0.1:7890）
  → NAS 127.0.0.1 上的 mihomo 容器
  → 规则 DOMAIN-SUFFIX,byr.pt,WARP
  → 策略组 WARP（type: select，默认 自动选最快）
      ├─ 自动选最快   **fallback**  37 个端点全量（粘住第一个可用节点，2026-10-06 05:47 起由 url-test 改）
      └─ DIRECT
  （2026-10-06 05:42 按用户要求**删除**了三个地区组 新加坡/洛杉矶/阿姆斯特丹 —— 37 个出站全部保留，只是不再按地区分可选组）
      └─ DIRECT
  → 37 个 WARP wireguard 出站（AmneziaWG 混淆）
  → Cloudflare anycast → 出口 IPv6 = 2a09:bac1::/32
```

- 组名**全中文**（配置里本来就有 `V6代理`、`二号订阅集`、`自动选最快` 这类中文组名，mihomo 认）。
- 容器：`metacubex/mihomo:Alpha`，`network_mode: host`，挂载 `/path/to/mihomo/mihomo => ~/.config/mihomo`，`external-controller: 0.0.0.0:9090`（secret 写在配置里，长度 8）。容器内二进制在 **`/mihomo`**（不在 PATH 里）。
- ⚠️ **容器名不一定是 `mihomo`**：原容器卡成「假 Up」后是用**救援容器**顶上的，名字叫 `mihomo-rescue`（同一镜像 / 同一配置目录，行为等价）。**每次动手前先 `docker ps --filter name=mihomo` 看清哪个在跑**（★ 2026-10-06 该救援容器已删，当前只剩 `mihomo` 一个）；对卡死的幽灵容器打 `exec` / `logs` / `restart` 会**直接挂住不返回**。旧幽灵容器清干净后名字会回到 `mihomo`。
- 配置文件：`/path/to/mihomo/mihomo/config.yaml` —— **UTF-8 BOM 必须保留**（`EF BB BF`）。
- `byr_http.py` 写死 `PROXIES=http://127.0.0.1:7890`（全 29 站唯一的代理例外），命中上面那条规则 ⇒ 走 WARP。

## 三、WARP 账号

- 用 `warpscout register`（0.16.0）创建：本地生成 X25519 密钥对（**私钥不出本机**）→ 公钥 POST `https://api.cloudflareclient.com/v0a4005/reg`（伪装 Android 客户端）→ 返回 `id` / bearer token / 对端公钥 → 置 `warp_enabled: true` → 写 `warpscout-account.json`。
- **免费、匿名、无邮箱 / 无密码 / 无信用卡 / 无验证码。**
- WARP+（$4.99/月）只加 Argo Smart Routing，**不改变出口 IP 或地区**；BYR 放行的是 CF 的 IP 段，免费档给的完全一样 ⇒ **不要升级**（升级还会改变 CF 网络路径选择，需全部重新验证，收益零风险非零）。
- Zero Trust 免费版出口行为与匿名账号**相同**；egress 选择 / dedicated IP 是 Enterprise 专属；官方不公布 WARP 出口 IP 段 ⇒ 对 BYR 零增益。

## 四、端点清单（2026-10-06 扫描 + 逐个实测，全部 0% 丢包且当场能通）

命名规则：`<地区>-<两位序号>`，序号按**实测延迟升序**重排。

| 名字 | 端点:端口 | 实测延迟 |
|---|---|---|
| 新加坡-01 | 8.35.211.207:4500 | 504ms |
| 新加坡-02 | 8.39.125.48:2408 | 506ms |
| 新加坡-03 | 8.39.125.112:2408 | 511ms |
| 新加坡-04 | 8.39.125.61:2408 | 512ms |
| 新加坡-05 | 8.35.211.19:500 | 524ms |
| 新加坡-06 | 8.39.125.209:2408 | 529ms |
| 新加坡-07 | 8.39.125.254:500 | 550ms |
| 新加坡-08 | 8.39.125.184:500 | 568ms |
| 新加坡-09 | 8.39.125.211:2408 | 593ms |
| 新加坡-10 | 8.39.125.142:500 | 616ms |
| 新加坡-11 | 8.39.125.108:500 | 654ms |
| 新加坡-12 | 8.39.125.103:4500 | 1612ms |
| 洛杉矶-01 | 8.39.204.129:500 | 1209ms |
| 洛杉矶-02 | 8.47.69.229:4500 | 1235ms |
| 洛杉矶-03 | 162.159.192.232:500 | 1273ms |
| 洛杉矶-04 | 8.39.214.184:2408 | 1395ms |
| 洛杉矶-05 | 8.39.204.56:2408 | 1402ms |
| 洛杉矶-06 | 8.47.69.62:2408 | 1653ms |
| 洛杉矶-07 | 162.159.192.129:500 | 1768ms |
| 洛杉矶-08 | 8.34.146.14:500 | 2052ms |
| 洛杉矶-09 | 8.34.146.226:4500 | 2288ms |
| 洛杉矶-10 | 8.34.70.50:2408 | 2546ms |
| 阿姆斯特丹-01 | 188.114.99.33:2408 | 1469ms |
| 阿姆斯特丹-02 | 188.114.99.43:4500 | 1522ms |
| 阿姆斯特丹-03 | 188.114.98.149:2408 | 1525ms |
| 阿姆斯特丹-04 | 188.114.97.38:500 | 1562ms |
| 阿姆斯特丹-05 | 188.114.97.36:4500 | 1608ms |
| 阿姆斯特丹-06 | 188.114.96.56:500 | 1646ms |
| 阿姆斯特丹-07 | 188.114.99.137:500 | 1666ms |
| 阿姆斯特丹-08 | 188.114.96.214:500 | 1694ms |
| 阿姆斯特丹-09 | 188.114.99.112:4500 | 1747ms |
| 阿姆斯特丹-10 | 188.114.97.86:500 | 1854ms |
| 阿姆斯特丹-11 | 188.114.97.119:2408 | 1899ms |
| 阿姆斯特丹-12 | 188.114.98.251:500 | 2085ms |
| 阿姆斯特丹-13 | 188.114.98.157:2408 | 2340ms |
| 阿姆斯特丹-14 | 188.114.99.163:4500 | 2412ms |
| 阿姆斯特丹-15 | 188.114.96.243:4500 | 3067ms |

每个出站的公共字段：`type: wireguard`、`ip: 172.16.0.2`、`ipv6: 2606:4700:110:8367:df93:c002:dff1:6891`、`allowed-ips: ['0.0.0.0/0', '::/0']`（**必须含 `::/0`，BYR 是 IPv6-only**）、`persistent-keepalive: 25`、`udp: true`、`remote-dns-resolve: true`、`dns: ['1.1.1.1','1.0.0.1']`、`mtu: 1280`、`amnezia-wg-option`（jc=6 jmin=10 jmax=50 + i1 伪装 iCloud 域名）。

> **延迟两套口径别混**：扫描的「隧道内 ping」是 67–197ms；上表是**经 byr.pt 的完整 HTTPS 健康检查**（建隧道+TLS+HTTP），500ms–3s 是正常的，不是端点变差了。

**端点会漂移** —— 可用性随时间变化。2026-10-06 宽采样 280 探针里 185 可用、20 个被 DPI 中途掐断；70 探针那轮 47 可用、3 个被掐断，`162.159.195.x` 子网当时 30% 丢包。

**三个数字口径完全不同，回答用户时别混着说**：

| 口径 | 含义 |
|---|---|
| **185** | 宽采样 280 探针里**能建立连接**的（扫描口径，最宽松） |
| **145** | 其中 **0% 丢包**的 |
| **70 / 37** | 再逐个跑真实 HTTPS 健康检查**当场应答**的（同一批 145 个里只有 70 个通） |

**185 从来不是「可用节点数」**，只是「扫描时能连上的数」。被问「不是说 185 个可用吗」时按这张表回答。

**地区恒为 3 个**（新加坡 / 洛杉矶 / 阿姆斯特丹）—— 两次不同规模的扫描（70 / 280 探针）结果一致，是 Cloudflare 按本线路 anycast 路由决定的，不是扫描不够。

## 五、运维手册

### 重新扫描端点
```bash
cd ~/.warp && ./warpscout scan -proto awg -tun-ping -jt 16
```
约 30 秒。关注输出里的 `Working: N/70`、`Torn down: N`，以及末尾「Best endpoint per subnet」表（按隧道内丢包→隧道内 ping 排序）。`-tun-ping` 会标出**握手成功但中途被掐断**的端点，这类必须剔除。

### 换 / 加端点（必须走这套）
**先实测再上线** —— 扫描出的「0% 丢包」只是扫描那一刻，不等于现在还能用。正确顺序：

1. **扫描**拿候选（上一步）。
2. **本地逐个实测**（关键步骤，别跳）：写一个**带 `external-controller`** 的最小配置，把候选全塞进 url-test 组，本地起 `mihomo`，对每组打 `/group/<组名>/delay?url=https%3A%2F%2Fbyr.pt%2F&timeout=10000`，**只保留返回正整数毫秒的**，其余（超时/未应答）全部剔除。参考 `scripts/warp_pretest_endpoints.py`（结果落 `~/.warp/warp_verified.json`）。
3. **建配置**：**文本级替换**，不要整文件 yaml round-trip（会丢注释）。只动两处 —— 顶层 `proxies:` 段整段替换、`WARP` 组及其地区组整段替换。地区组名和出站名用**中文**。参考 `scripts/warp_verified_regions.py`。
4. **校验**：容器内 `ssh nas '/usr/local/bin/docker exec mihomo /mihomo -t -f ~/.config/mihomo/config.yaml.new'`，或本机 `~/.warp/mihomo -t -f <新配置> -d <目录>`（后者先 `unset PYTHONPATH`）。
5. **备份**：`ssh nas "cp -a /path/to/mihomo/mihomo/config.yaml /path/to/mihomo/mihomo/config.yaml.bak-$(date +%Y%m%d-%H%M%S)"`。
6. **上传覆盖 + API 热重载**（不要重启容器）：
   ```bash
   curl -X PUT -H "Authorization: Bearer ***" -H 'Content-Type: application/json' \
     -d '{"path":"","payload":""}' "http://127.0.0.1:9090/configs?force=true"
   ```
   期望 **HTTP 204**。参考 `scripts/warp_apply_verified.py`。
7. **验证**：
   - `GET /proxies/WARP` → `type=Selector`、`now` 非空、候选 = `['自动选最快','DIRECT']`
   - 显式设一次默认：`PUT /proxies/WARP` body `{"name":"自动选最快"}`（cache 里可能残留已删组名）
   - `GET /group/<percent-encoded 中文组名>/delay?url=https%3A%2F%2Fbyr.pt%2F&timeout=10000` → 通过数 / 各节点毫秒
   - `curl -s -o /dev/null -w '%{http_code}' -x http://127.0.0.1:7890 https://byr.pt/` → **302**
   - `byr_http.py --stage1 --stage2` → `msg='登录成功'`

**上线脚本别把「应用 + 全量验证」塞进一个前台命令**：37 个节点 × 4 个组的全量 `/delay` 要跑好几分钟，前台命令会被超时掐断，**而应用其实已经成功**。分两步：先跑「备份 → 容器内校验 → 就位 → 热重载」（快），再单独跑验证；验证慢就丢后台。被掐断后**先查现场再决定要不要重跑** —— `GET /proxies/WARP`、`GET /proxies` 数 WireGuard 出站个数、看 NAS 上 `config.yaml.bak-*` 的时间戳，确认已经上线就别盲目重跑上线脚本。

### 按地区切换 / 固定出口
`WARP` 是 **select** 组，默认 `自动选最快`（跨区自动选最快）。要固定某个地区，用 API 切：
```bash
curl -X PUT -H "Authorization: Bearer ***" -H 'Content-Type: application/json' \
  -d '{"name":"阿姆斯特丹"}' http://127.0.0.1:9090/proxies/WARP
```
可选值：`自动选最快` / `DIRECT`（**地区组已于 2026-10-06 删除**，见八之四）。
- 选择会**持久化**在 mihomo 的 cache 里，重启容器后仍生效；想恢复自动就切回 `自动选最快`。
- ⚠️ **BYR 的登录会话和出口 IP 绑定**：出口 CF IP 一变，会话立刻失效（带 cookie 访问被 302 到 `/login`，页面只剩几百字节）。而 `自动选最快` 是 url-test，**会自己换节点 ⇒ 换 IP ⇒ 掉登录**（实测：5 条 Telegram 连接分别落在 `新加坡-07`/`新加坡-01`/`新加坡-03`，见八之四）。
  → **要长期保持 BYR 登录，就把 `WARP` 钉死在单个出站上**：`PUT /proxies/WARP` body `{"name":"新加坡-19"}`（出站名即 `<地区>-<序号>`）。代价是失去自动故障转移 —— 这是「会话稳定」与「自动选优」之间必须做的取舍，默认应选**会话稳定**。
- 每个地区组自身也是 url-test，组内仍会自动挑最快、自动故障转移。
- 实测延迟（2026-10-06，经 byr.pt 健康检查）：新加坡 ~143ms < 洛杉矶 ~329ms < 阿姆斯特丹 ~401ms。
- 地区组只影响 `DOMAIN-SUFFIX,byr.pt` 走哪个 WARP 出口，**其它站点不受影响**。
- 组名与成员关系（2026-10-06 05:42 后）：`WARP`(select) → `自动选最快`(url-test，37 个 wireguard 出站) / `DIRECT`。地区组已删。

### 回滚
`scp` 回 `.bak` 文件 + 再热重载一次。

## 六、坑（都踩过）

- **端点不是越多越好 —— 数量本身会把容器拖死**：实测把 37 → **70** 个 wireguard 出站后，mihomo 进程死亡、容器被 Docker 守护进程卡成「假 Up」（处置见 NAS 维护手册的「容器假 Up 卡死」一节）。70 个出站 × 每个自带 `remote-dns-resolve` × `lazy: false` 的 url-test 组健康检查 = 周期性几十路并发握手。**加端点要小步走**（4 → 13 → 37 都稳），没经过时间考验的规模不要推。
- **同一个生产配置上别连续叠改动**：改组类型 → 加兜底节点 → 再调参，这样一轮轮叠上去，新故障的症状会和上一层改动的后遗症几乎一样，因果被互相掩盖、定位成本成倍涨（本轮就是这么把一次「兜底节点被当主力」拖成一次通道中断的）。**每加一层先让它单独跑一段、确认稳了再动下一层；用户说「最小改动」时就真的只改一处。**
- **别对多节点组反复打全量 `/group/<名>/delay`**：每次调用都会触发**整组**健康检查，短时间内连打几次就是一次健康检查风暴。要全量验证就一次打完、落盘结果，别在诊断循环里反复调用。

- **热重载后立刻诊断会看到「经代理 000」** —— 这是过渡期：依赖订阅的 `proxy-providers` 在重新下载，瞬间为空。**等一会儿重跑就自愈**，不要急着重启容器。
- **热重载 ≈ 1 分钟代理中断**（含走代理的 Telegram）。挑时间做。
- **`tracker.byr.pt` 裸请求 403 不代表被封** —— 那是 BYR 的 `wengine-auth-failed` 鉴权页（没带 passkey）；带上 passkey 立刻 200。
- **mihomo 策略组的 `url` 对 `use:` 引入的 proxy-providers 不生效**（官方文档明示）⇒ `V6代理` 组（`use: [二号订阅集]`）健康检查一直空转，49 个节点全超时也不报警。这是 BYR 当初挂掉的根因之一。
- **不要动 `V6代理` 组和其余 126 条规则**；byr.pt 那条规则排在 `DOMAIN-KEYWORD,tracker,DIRECT` **之前**，顺序不能改。
- **NAS 上的 `curl` 自身是坏的**（对任何站都 `HTTP=000 / 0.000000s` 秒失败），Python 裸连正常 ⇒ NAS 上 curl 的一切结论作废。
- **NAS 的 SSH 非交互会话 PATH 里没有 `docker`** —— `ssh nas "docker ps"` 报 `command not found`。真路径是 **`/usr/local/bin/docker`**（软链到 `/var/packages/ContainerManager/target/usr/bin/docker`），校验配置直接在容器里跑 `ssh nas '/usr/local/bin/docker exec mihomo /mihomo -t -f ~/.config/mihomo/config.yaml'`。
- **本地测 mihomo API 必须显式配 `external-controller`** —— 只配 `mixed-port` 的话，请求会打到**代理端口**上，代理对 `GET /proxies`、`/group/.../delay` 一律回 **400 Bad Request**，极易误判成「API 坏了 / 组名有问题」。踩过两次。
- **API 路径里的中文组名必须百分号编码** —— `/group/%E6%96%B0%E5%8A%A0%E5%9D%A1/delay` 正常 200；直接塞原始 UTF-8 会失败（Python `http.client` 拒绝非 ASCII 请求行，是客户端限制不是 mihomo 的）。用 `urllib.parse.quote(名字)`。
- **中文组名本身完全可用**，配置里本来就有 `V6代理`、`二号订阅集`、`自动选最快`；`GET /proxies` 里中文名正常返回，`PUT /proxies/WARP` 的 body 是 JSON 更不受影响。只有 **emoji 会踩坑**（此构建 API 认不出带 emoji 的节点名，`/proxies/<emoji名>/delay` 404）。
- **`mihomo -t` 要在有 pyyaml 的环境跑**，且先 `unset PYTHONPATH`（终端会话的 PYTHONPATH 指向 Hermes 的 python3.14 site-packages，会遮蔽项目 venv）。
- **测 MTProto 必须先暖机**：先跑一次 HTTPS 请求把隧道建起来，否则首次 CONNECT 会失败，误判成「WARP 到不了 Telegram」。

## 七、实测数据（2026-10-06）

- 直连 `byr.pt` → **403**；经代理 → **302 / 0.74s**（37 端点版本；13 端点版 0.57s；4 端点版 1.40–2.85s）。
- v6 上线后热重载 **HTTP 204**，容器仍 `Up`（未重启）；`WARP` = Selector，`now=自动选最快`；`自动选最快` 37 成员、`now=新加坡-07`。
- 健康检查（当时含地区组）：`自动选最快` **29/29 通**（最快 141ms）、`新加坡` 8/8（143ms）、`洛杉矶` 6/6（329ms）、`阿姆斯特丹` 12/12（401ms）。
- 上线前本地实测：60 个 0% 丢包候选里 **37 个当场能通**（新加坡 12 / 洛杉矶 10 / 阿姆斯特丹 15），另 23 个 8 秒内无应答 → **全部剔除**。
- 登录保活 `byr_http.py --stage1 --stage2`：HTTP 200 `msg='登录成功'`、cookie 4 个、`index.php` 200 len=94421、欢迎语含 `Extreme User`、分享率 8,111.15、上传 9.766 TiB。
- 回归：`github.com` 200、`google.com/generate_204` 204、`baidu` 200。
- **MTProto 测试**（本地 mihomo `MATCH,WARP`，发 abridged + `req_pq_multi`，检查 nonce 回显）：DC1/DC2/DC4/DC5 × 端口 443 和 80 **全部收到有效 resPQ**，0.1–0.6s；对照走 NAS 代理 0.2–1.7s ⇒ **WARP 完全能承载 Telegram**。

## 八、未落地 / 边界

- **BT（transmission）走 WARP 未做，且不建议做**：transmission 的代理设置是**全局**的，NAS 上有 4391 个种子 / 54 个 tracker 域名，一开代理其余 28 站 tracker 会被一起塞进代理 ⇒ 踩其他站的代理红线。唯一可行是**专用实例**（只装这 12 个 BYR 种子 + 独立代理），但 announce 上报的是 CF 的 IP 而非家庭真实 IP，「可连接」会变「否」，只能靠出站上传；是否触发 BYR 防作弊**未知**。
- **mihomo 规则按域名匹配**，`DOMAIN-SUFFIX,byr.pt,WARP` 只覆盖 tracker 的 HTTP 请求；**BT peer 之间的裸 IP 连接匹配不到规则，会掉进 `MATCH`**。真要解决需加 `IP-CIDR,2001:da8::/32,WARP`（CERNET 整段走 WARP）+ BT 客户端指向 `127.0.0.1:7890`。
- NAS 的 transmission4.0 里有 **12 个 BYR 种子**（2026-06-05/07 加的辅种，announce 全是 `tracker.byr.pt`），**活动时间戳全是 0 —— 从来没跑起来过**（和「家里连 BYR 403」完全吻合）。
- **给 Telegram 挂 WARP 技术上可行（已实测），但没做**：需要加 Telegram 的 IP 段规则（`91.108.4.0/22`、`149.154.160.0/20` 等，域名规则盖不住 DC 的裸 IP），要再热重载一次；而且 Hermes 自己发 Telegram 也走这个代理，改它等于动自己的传话通道。

## 八之二、WARP 深挖研究（2026-10-06 第二轮）

### 协议两条腿（Cloudflare 官方文档口径）
- **WireGuard**（当前在用）：入口 `162.159.193.0/24` + `2606:4700:100::/48`，默认 UDP 2408，回退 500 / 1701 / 4500；消费级 1.1.1.1 另有 `162.159.192.0/24`。
- **MASQUE**（HTTP/3 + QUIC，官方客户端 2025 起默认）：入口 `162.159.197.0/24` + `2606:4700:102::/48`，默认 **UDP 443**，回退 500/1701/4500/4443/8443/8095 + **TCP 443**（h2）。
- MASQUE 的价值：UDP 被封时能退到 **TCP 443（长得像 HTTPS）**。mihomo **v1.19.20+ 支持** `type: masque`（`network: quic | h2 | h3-l4proxy`），NAS 容器（alpha-9f053c4）支持。

### 实测：usque 匿名注册 → mihomo masque 节点
- `usque register` **匿名注册**（无需团队令牌；交互问 ToS，用 `printf 'y\n' | ./usque register`），产出 `config.json`（ECDSA 私钥、`endpoint_pub_key`、`ipv4/ipv6`、`endpoint_v4=162.159.198.2`、`endpoint_h2_v4`）。
- 转 mihomo 节点：PEM **去掉头尾标识和换行**、`ip: <ipv4>/32`、`ipv6: <ipv6>/128`、`mtu: 1280`、`udp: true`、`sni: consumer-masque.cloudflareclient.com`。
- **QUIC 模式（UDP 443）实测完全可用**：`warp=on`、github 200、出口 `104.28.220.209`。
- **h2 模式（TCP 443）实测失败**：`connection reset by peer`（该线对 TCP 443 会被重置）。
- ⚠️ mihomo 已知未修 bug **#3227**：TUN(gVisor) + MASQUE + url-test 健康检查失败 → ChaCha20 忙自旋、CPU 1300%+。**别在 TUN 模式堆 MASQUE 节点 + url-test**。

### 出口真相（最重要，回答「WARP 能不能当梯子」用这条）
- **所有端点的出口都 geo 定位在中国**：`104.28.220.209`（ipinfo → 南京 / 江苏 / AS13335 Cloudflare），trace 一律 `loc=CN`；IPv6 出口是 `2a09:bac1:*` / `2a09:bac5:*`。
- **出口 IP 是共享的**：10 个成功样本里 7 个共用同一个出口 IP，且跨地区（SIN / LAX / AMS）相同 ⇒ **地区只决定入口路径（colo），不改变出口身份**。
- ⇒ **WARP 不是「海外梯子」**，它是一个 geo 在中国的 Cloudflare IP：对 BYR / 国内站有用，对「假装在国外」无用。要真海外出口得走 CF Workers（edgetunnel 那类，见教程调研）。

### 稳定性纪律（新增）
- **同一把 WARP 密钥同时在两处握手会互相影响**：用同一把私钥在本地复测 37 个端点只通 10 个（当时 NAS 正持有同样的 37 条隧道），而一小时前单独测是全通。要本地复测就先停 NAS 那条、或**另注册一个账号**。
- **一个账号 = 一个设备**（wgcf 文档：WARP+ 最多绑 5 设备）。
- 端点可用性随时间漂移，**上线前必须实测**（§五）。

## 八之三、Telegram 走 WARP（2026-10-06 上线）

**配置改动（字节级 2 行）**：在 `rules:` 段第一条 `DOMAIN-SUFFIX,byr.pt,WARP` **之后**插入：
```yaml
  - GEOIP,telegram,WARP                                # Telegram IP 段 -> WARP
  - GEOSITE,telegram,WARP                              # Telegram 即时通讯 -> WARP
```
- 原配置本来就有 `GEOIP,telegram,聊天软件` / `GEOSITE,telegram,聊天软件`（第 2824/2826 行），插到它们前面即生效，后面两条成死规则（无害）。
- **不要动 `聊天软件` 组** —— 它是个 select 大杂烩（还管 Twitter / IG / FB / WhatsApp / Signal…），改它会把社媒全部改道。
- 插入位置必须在 `GEOIP,cn,DIRECT` 之前（Telegram IP 非 CN，理论上不冲突，但放最前面最稳）。

**配置文件格式**：`/path/to/mihomo/mihomo/config.yaml` = **UTF-8 BOM + LF**（**不是 CRLF**，别搞错）；编辑必须按字节做、保留 BOM。

**上线动作**：`scp` 拉回 → 字节插入 → 备份 `config.yaml.bak-<ts>` → 上传 `.new` → 容器内 `docker exec mihomo-rescue /mihomo -t -f ~/.config/mihomo/config.yaml.new` → `mv` 就位 → `PUT /configs?force=true`（HTTP 204）→ 验证。脚本：`scratch/nas_tg_apply.py`。

**验证方法（决定性）**：
1. `GET /rules` → 应有 `GeoIP,telegram -> WARP` / `GeoSite,telegram -> WARP`。
2. 经 NAS 代理（127.0.0.1:7890）打真 MTProto `req_pq_multi` → 4 个 DC × 443 全回 resPQ。
3. **`GET /connections`** → 看 Telegram 目标 IP 的 `chains` 应为 `['新加坡-01','自动选最快','WARP']`、`rule` 为 `GeoIP/telegram`。**这是唯一能证明「真的走了 WARP」的方法**（只看 curl 通不通会骗人）。

**实测结果（2026-10-06 05:36）**：4/4 DC 通；活动连接链路 `新加坡-01 → 自动选最快 → WARP`；byr.pt 302/0.65s、google 204/0.45s、github 200/7.3s；容器未重启。
**回滚**：`cp config.yaml.bak-20261006-053636 config.yaml` + 热重载。

**注意**：WARP 组是 `url-test`（37 节点自动选最快），**每次切节点会断掉 Telegram 现有连接**（客户端会重连，但有瞬断）。要彻底稳定就把 `WARP` 钉死单节点（如 `新加坡-01`），代价是失去自动故障转移。

## 八之四、组结构精简 + 切节点实锤（2026-10-06 05:42）

**用户要求（原话）**：「最小改动，把warp的地区分组删了吧」

**改动**：删除三个地区组 `新加坡`/`洛杉矶`/`阿姆斯特丹`（58 行）+ `WARP` 组里的 3 行引用。**37 个 wireguard 出站全部保留**，只是不再有按地区分的可选组。
- `WARP`(select) 候选 → `['自动选最快','DIRECT']`
- 删除前已确认：**没有任何规则引用地区组**（全文件 grep 只命中 WARP 组里那 3 行 + 组定义本身）→ 安全。
- 备份 `config.yaml.bak-20261006-054216`；容器内 `mihomo -t` rc=0；热重载 HTTP 204；容器未重启。
- 验证：地区组 API 全部 404 ✓；byr.pt 302/0.50s、google 204/1.5s ✓。
- 脚本：`scratch/nas_del_regions.py`。

**顺带抓到的实锤（重要）**：删完后 `GET /connections` 显示 **5 条 Telegram 连接分别走在 `新加坡-07` / `新加坡-01` / `新加坡-03`** —— 说明 `自动选最快` 这个 url-test 组**确实在换节点**（每条连接在建立时锁定当时的节点）。这就是 Telegram 会瞬断、BYR 会话会掉的根源。
- 参数：`interval: 120`、`tolerance: 100`、`lazy: false`（37 个节点延迟 137–3067ms，差得很开，100ms 容差极易触发切换）。
- **更好的修法（2026-10-06 05:47 已落地）**：把 `自动选最快` 从 `url-test` 改成 **`fallback`（自动回退）** —— 粘住第一个可用节点，**只在它真挂了才切**；配 `lazy: true` + `interval: 300`，删掉 `tolerance`。共 4 处改动，**只动这一个组**（订阅里那 18 个 url-test 组未碰）。备份 `config.yaml.bak-20261006-054719`；容器内 `mihomo -t` rc=0；热重载 HTTP 204；容器未重启。脚本 `scratch/nas_fallback.py`。
  - 效果：`type=Fallback`、`now=新加坡-01`（列表第一个活着的，粘住不动）；健康检查 10/10 通（新加坡-01 148ms / 新加坡-07 142ms / 洛杉矶-07 339ms / 阿姆斯特丹-01 383ms）；byr.pt 连测 3 次 302 / 0.5–0.9s。
  - ⚠️ **热重载那一刻会短暂抽风**：这次先出现过一次 `byr.pt 000`、`now` 短暂是 `洛杉矶-07`，几秒后自愈成 `新加坡-01`。**判断 WARP 是否正常必须等 5–10 秒再复测，别拿热重载瞬间的结果下结论。**
  - ⚠️⚠️ **`lazy: true` 是个坑（2026-10-06 05:55 实测踩到）**：`lazy: true` = **没流量时不跑健康检查**，于是热重载后组不知道哪些节点是活的，fallback 会**一路滑到列表最后一个**。当时刚把 `MASQUE兜底` 追加到列表末尾，结果**全部流量被甩到 MASQUE 那条隧道上**，Telegram 长连接反复掉线（用户报「tg 总是失联」），byr.pt 也慢到 4 秒。
    - 实锤：`GET /connections` 里 TG 连接链路 = `['MASQUE兜底','自动选最快','WARP']`。
    - 修法：`lazy` 改回 `false`（保留 `interval: 300`）+ 强制跑一轮 `/group/<组名>/delay` + 验证 `now` 回到某个 wireguard 节点。修后 byr.pt 302/0.5–0.7s。
    - **铁律：往 fallback 组末尾加兜底节点前，先确认 `lazy: false`；`lazy: true` + 末尾兜底节点 = 兜底会被当成主力。**

## 八之五、Telegram 走 WARP 的回退 + MASQUE 兜底节点（2026-10-06 05:52–05:55）

**加了什么**：`MASQUE兜底` 出站（`type: masque`，用 usque 匿名身份，**与 37 个 wireguard 节点不是同一把密钥**），追加到 `proxies:` 末尾 + `自动选最快`(fallback) 列表**末尾**（只有前面全挂才用）。备份 `config.yaml.bak-20261006-055202`；容器内 `mihomo -t` rc=0；热重载 204；单测 `MASQUE兜底 -> {"delay":366}` ✓。

**随后出事**：见上面 `lazy: true` 那个坑 —— TG 被甩到 MASQUE 上，反复失联。

**处置**：
1. **删掉两条 `telegram -> WARP` 规则**（回退到原本的 `聊天软件` 组）—— 脚本 `scratch/nas_revert_tg.py`，备份 `config.yaml.bak-20261006-055346`。
2. `lazy: true` -> `false`（备份见脚本输出）；强制健康检查；`now` 回到 `新加坡-03`。

**结论（重要）**：
- **不要把 Telegram 长期挂 WARP**：握手测试能过（短连接），但 Telegram 是**长连接**，WARP 的 UDP 隧道在国内会抖，长连接撑不住。**BYR 是短请求，适合 WARP；TG 不适合。**
- **MASQUE 兜底节点保留但应闲置**：它在 fallback 列表末尾，只要 37 个 wireguard 里有活的就不会被用。
- 容器内存观测：**146MB(05:05) -> 671MB(05:52) -> 807MB(05:55)**，一轮反复热重载 + 换节点后涨得很快；与 MASQUE 节点无关（加它之前就涨到 671MB）。**下次维护重启容器清一遍，并持续盯。**

## 九、本机留存的物料

> ⚠️ **【2026-10-06 07:15 已全部删除】** 用户决定「删了吧没啥用了」：`~/.warp/`（93M —— warpscout / mihomo 二进制 / usque / 账号 json / 出口明细）与 `~/.hermes/cache/scratch/nas_*.yaml`（含 mihomo secret 的配置快照）已 `rm -rf`，**凭据随目录一起清掉**（warpscout-account.json、usque config.json、warp_final.yaml 全部没了）。
> 下面清单**只作历史参考** —— 想再搞 WARP 得重新下载工具、重新注册账号。技能内 `scripts/warp_*.py` 保留（思路仍有参考价值），但它们引用的 `~/.warp/...` 路径**已不存在**，不能直接跑。

- `~/.warp/warpscout`（0.16.0 二进制）、`~/.warp/mihomo`（v1.19.32 二进制，用于 `-t` 校验和本地实测）
- `~/.warp/warpscout-account.json`（免费 WARP 账号，权限 600）
- `~/.warp/warp_final.yaml`（最初的 4 端点版本，可作字段模板）
- `~/.warp/nas_config_live.yaml`（当前线上 37 端点版本的副本）
- `~/.warp/warp_verified.json`（实测通过名单 + 每个端点的毫秒）
- `~/.warp/warpscout-report-*.txt`（扫描报告，最新一份是宽采样 280 探针）
- `~/.warp/scan_wide.sh` / `scan_wide.out`（宽采样脚本与输出）
- `~/.warp/tg_mtproto.py`（MTProto 穿透测试脚本）
- `~/.warp/usque-dl/` 与 `~/.warp/usque-test/`（usque v4.2.1 + 匿名 MASQUE 账号 `config.json`，权限 600）
- `~/.warp/warp_egress.jsonl`（37 个端点的出口 IP / 国家 / colo 实测明细）
- `~/.hermes/cache/scratch/`：`warp_egress2.py`（出口实测）、`masque_test.py`（mihomo MASQUE 测试）、`nas_health.py`（NAS 侧健康对照）

技能内可复用脚本（`scripts/`）：`warp_scan.sh`（扫描）、`warp_pretest_endpoints.py`（本地逐个实测）、`warp_verified_regions.py`（按实测结果建中文名配置）、`warp_apply_verified.py`（备份→容器内校验→热重载→验证）、`warp_split_regions.py`（纯按地区拆分的旧版）、`warp_build_config.py` / `warp_apply_config.py`（最早的单组版）。

## 十、把一次配置改动整体回滚到「原版」

用户说「删掉 X，恢复原来的」时，**不要凭记忆手写反向改动** —— 按备份指纹挑出改动前的快照整体覆盖。步骤：

1. **列全部备份 + 各自大小**：`ls -la /path/to/mihomo/mihomo/config.yaml*`（备份是历次改动前 `cp` 出来的，文件名带时间戳）。
2. **给每份备份打「特征指纹」，找零特征的那份** = 改动前的原版：
   ```bash
   for f in /path/to/mihomo/mihomo/config.yaml*; do
     printf '%s  wg=%s WARP组=%s masque=%s byr规则=%s 字节=%s\n' "$(basename $f)" \
       "$(grep -c 'type: wireguard' $f)" "$(grep -c '^  - name: "WARP"' $f)" \
       "$(grep -c 'type: masque' $f)" "$(grep -c 'DOMAIN-SUFFIX,byr.pt' $f)" "$(stat -c%s $f)"
   done
   ```
   ⚠️ **以内容指纹为准，不以文件名/时间戳为准**：曾遇到名字写着今天日期、mtime 却是几个月前的备份（`cp` 不带 `-p` 时 mtime 是新值，但历史遗留文件会骗人）。
3. **结构对比，证明差异只有要删的那部分**（拉回本机用 pyyaml 解析，别肉眼扫）：顶层键集合、`proxies` 名字集合、`proxy-groups` 名字集合、`rules` 逐条 diff（尤其关键域名规则的 `proxy` 指向）。本次结论：原版与现版只差「38 个出站 + 2 个组 + 一条规则的指向」，其余 72 组 / 127 条规则完全一致 ⇒ 覆盖安全。**diff 里若还有别的差异，先停下来问用户**，别顺手把无关改动也回滚。
4. **执行**（与上线同一套纪律）：备份当前为 `config.yaml.bak-<ts>-pre-restore` → `cp <原版> config.yaml.new` → 容器内 `mihomo -t -f ~/.config/mihomo/config.yaml.new`（**失败就删掉 `.new`，线上不动**）→ `mv` 就位 → `PUT /configs?force=true`（期望 204）。
5. **双向验证**：①被删的真的没了 —— 对每个组名打 `GET /proxies/<名>`，**404 = 已消失**；数 `type=WireGuard` 出站应为 0；`GET /rules` 看那条域名规则指回了哪个组。②剩下的没坏 —— `curl -x http://127.0.0.1:7890` 打 google / api.telegram.org / 目标站，**等 5–10 秒再复测**（热重载过渡期会先给 `000`）。
6. **如实报告「原版本来就坏的那部分」**：回滚会把之前修好的东西一起还原成坏的状态。这不是回滚失败，这就是原版；要保留修复就得再单独改一次，并让用户明确选择。

> 通用形态：**任何「恢复原来的」= 备份指纹定位原版 + 结构 diff 证明差异可控 + 同套校验/热重载/双向验证**。适用于任何有版本化备份的配置（路由器、NAS、容器）。

### 回滚时的一个附带发现：容器会堆积
顶替过救援容器的服务，`docker ps -a` 里可能同时有 `mihomo` / `mihomo-rescue` / `mihomo-rescue2` —— 用 `docker logs --tail 20 <名>` 看**谁有实时流量日志，谁才是线上那个**（详见 NAS 维护手册的「假 Up」一节）。幽灵容器（假 `Up` / `Created` 占位）清不掉，彻底清只能重启 dockerd（连带几十个容器），属「等用户决定」项。

> **本次结局（2026-10-06 07:15）**：用户**自己**用 `compose.yaml` 重建了 `mihomo` 容器，幽灵容器也一并清掉了 —— 现只剩 `mihomo`（线上）；`mihomo-rescue` 已于 2026-10-06 删除。**结论：这类容器烂摊子用户能自己收拾，助手不要在未授权时去重启 dockerd。**
