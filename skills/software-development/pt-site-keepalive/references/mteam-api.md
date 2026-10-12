# M-Team API 逆向分析（2026-09-28）

> 来源：`static.m-team.cc/static/js/main.36d6a5a5.js`（webpack minified）
> 方法：下载全部 33 个 JS 资源 → 正则定位 `interceptors.request` 与签名生成函数
> 原始文件：`~/safeline-research/mteam-js/`（4.7 MB）

## 一、★ 签名算法（已完整还原）

在 `main.js` 中找到签名生成函数（源码用数组 join 混淆参数名）：

```javascript
const L = (e, t) => {                       // e = url, t = method
    const n = {},
          s = o.Ay.env.secret,              // ★ 密钥（运行时注入，不在 JS 里）
          r = Date.now(),                   // ★ 毫秒时间戳
          a = b.parse("".concat(o.Ay.env.server).concat(e)).path || "",
          i = "".concat(t, "&").concat(a, "&").concat(r);
    n[["_","t","i","m","e","s","t","a","m","p"].join("")] = r;
    n[["_","s","g","i","n"].join("")] = y.hmacSHA1(i, s);
    return n;
};
```

**等价形式**：

```
_sgin      = HMAC-SHA1(message, secret)
message    = method + "&" + path + "&" + timestamp
_timestamp = Date.now()          # 毫秒
secret     = 站点 env.secret     # 运行时配置
```

示例（实测捕获的请求）：
```
GET /api/system/unix
message = "GET&/api/system/unix&1790562405309"
→ https://api2.m-team.cc/api/system/unix?_sgin=<base64>&_timestamp=1790562405309
```

## 二、请求头机制（axios request interceptor）

```javascript
T.interceptors.request.use((e => {
    e.baseURL = o.Ay.env.server;
    const t = o.Ay.env.version || "";
    let n = t.includes("-") ? t.substring(0, t.indexOf("-")).replaceAll(/\./g,"")
                            : t.replaceAll(/\./g,"");
    const s = n + "0";
    if (!e.fetchOptions || !e.fetchOptions.missHeader) {
        e.headers.ts         = Math.floor(Date.now() / 1e3);   // 秒级时间戳
        e.headers.visitorId  = f.xi.visitorId || localStorage.visitorId || "";
        e.headers.version    = t;
        e.headers.webVersion = s;
        const n1 = localStorage.getItem("auth");  if (n1) e.headers.authorization = n1;
        const r1 = localStorage.getItem("did");   if (r1) e.headers.did = r1;
    }
    return e;
}), (e => Promise.reject(e)));
```

- **`authorization`** 来自 `localStorage.auth`（登录令牌，登录后写入）
- **`did`** 来自 `localStorage.did`
- **`visitorId`** 来自 `localStorage.visitorId`
- **`webVersion`** = 版本号去点号后拼 `"0"`
- ★ **`missHeader: true` 的请求会跳过所有上述头** → 这类接口**免签名**，
  很可能是启动引导类接口（如 `POST /api/system/sysConf`）→ 可用于无签名获取站点配置

## 三、已知 API 端点（实测捕获）

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/system/sysConf` | 站点配置（疑似免签名引导接口） |
| GET | `/api/system/unix` | 服务器时间（带 `_sgin` + `_timestamp`） |

**API 域名（两个）**：
- `api.m-team.cc`
- `api2.m-team.cc`（实测观测到 `unix` 走这里）

**静态资源域名**：`static.m-team.cc/static/js/`（webpack 分包：
`main.<hash>.js` + `user.<hash>.chunk.js` + 31 个 `vendors-*.js`）

## 四、★★ 实测更正：`_sgin` 对已认证请求**不是必需的**

用浏览器（已登录档案）直接 `fetch`，**只带以下头、不带 `_sgin`**：

```
Content-Type: application/json
ts:         <秒级时间戳>          ← Math.floor(Date.now()/1000)
visitorId:  <localStorage.visitorId>
did:        <localStorage.did>
authorization: <localStorage.auth>   ← 登录 JWT（eyJ...）
```

实测结果（2026-09-28）：

| 请求 | 结果 |
|---|---|
| `POST /api/member/profile` `{}` | **200 成功**，返回完整用户数据 |
| `POST /api/system/sysConf` `{}` | **200 成功**，返回站点配置 |
| `POST /api/system/getConf` `{}` | 200 |

**结论**：签名（`_sgin`）属于前端 axios 拦截器的行为，服务端对已认证请求不强制校验；
因此**无需逆出 `env.secret` 就能调用接口**。

### ★ 另一个坑：官方文档写 GET，实际要 POST

`/api/system/getConf`、`/api/member/profile` 用 **GET 会报**
`{"code":1,"message":"Request method 'GET' is not supported"}` —— **必须用 POST**，
且 body 传 `{}`（`Content-Type: application/json`）。这与 `wiki.m-team.cc/api`
文档描述不一致（文档自己声明「請求資料格式 json/form 可能與實際不符」）。

### 登录态与档案

- M-Team 的**有效登录档案**现在是 `~/.pt-sessions/mteam-session`（2026-09-30 把旧目录里的有效档案迁入此处、
  替换掉原来的过期副本；`scripts/mteam_login.py` 的 PROFILE 已同步更新）。做扫描/探测时用这一份。
- `localStorage` 关键键：`auth`（JWT）、`did`、`visitorId`、`apiHost`（= `https://api.m-team.cc/api`）、
  `lastCheckTime`，以及 React Redux 的 `persist:user` / `persist:torrent` / `persist:persist`。
- `sysConf` 返回的站点配置项（实测）：`SITE_NAME`、`CLOSE_WEB`、`OPEN_FUNBOX`、`BET_MAXLOSS`、
  `ORDER_DONATE_CONFIG`、`SUBTITLE_TRANSLATE_PRICE`、`EXT_FORUM`/`EXT_FORUM_URL`、
  `OPEN_INVITE_REGISTER`、`OPEN_REGISTER`、`OPEN_SHOUTBOX`、`SHOW_HOTMOVIES`、`HOME_SHOW_POLLS`。

## 五、★ 合规提醒（重要）

M-Team 官方 Wiki（`wiki.m-team.cc/api`）**明确禁止第三方工具用 cookie 存取接口**：

> 「API KEY 開放後，若發現第三方工具仍以 cookie 存取接口，不排除停用帳號。」

因此：
- **正式自动化请走官方 x-api-key**（控制台 → 实验室 → 存取令牌），完全合规。
- 本逆向**仅用于理解实现原理**（用户明确表示「只是研究好奇」），
  不代表建议用签名方式刷接口。
- 速率上限（官方建议）：下载种子 1000/天、100/小时；`/torrent/detail` 100/小时；
  `/torrent/search` 1000/24 小时。

## 五、复现步骤

```bash
# 1. 取 JS 清单（来自浏览器流量扫描的结果）
python3 -c "import json;d=json.load(open('~/safeline-research/apis/M-Team.json'));print('\n'.join(d['assets_js']))"

# 2. 下载全部 JS
cd ~/safeline-research/mteam-js
# （脚本见会话记录：按 assets_js 逐个 curl 到本地）

# 3. 定位签名函数
grep -oh 'T\.interceptors\.request\.use(.\{2900\}' *.js | head -1

# 4. 定位签名生成（源码里参数名被 join 混淆）
grep -o '\["_","s","g","i","n"\]' *.js
```
