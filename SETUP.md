# 环境准备与安装验证

## 系统要求

- **Hermes Agent**：`hermes` 命令在 PATH；已连通**飞书渠道**并能收发消息。
- **飞书自建应用**：你自己在飞书开放平台建的（应用管理里能拿到 `cli_` 开头的 App ID），已开「机器人」能力、已订阅长连接事件。权限清单见 `SKILL.md` 第二节。
- **Python 3.11+**：本包的插件与脚本**只用标准库**，不需要额外 pip 安装。
- **bash** 与 `sha256sum`（安装脚本与对账脚本要用）。
- 可选：Pillow、ffmpeg、中文字体 —— 只有做「用量波形 GIF」那部分才需要。

## 目录约定

- 所有路径默认 `~/.hermes`，可用环境变量 **`HERMES_HOME`** 覆盖。
- 插件安装位置：`$HERMES_HOME/plugins/<插件名>/`
- 技能位置：`$HERMES_HOME/skills/<分类>/feishu-menus/`

---

## 第一步：本地安装（全自动，不用扫码）

```bash
# 1) 拷技能目录
mkdir -p ~/.hermes/skills/social-media
cp -r feishu-menus ~/.hermes/skills/social-media/

# 2) 一键装：两个插件 + 中文快捷命令
bash ~/.hermes/skills/social-media/feishu-menus/scripts/install.sh

# 3) 重启网关（插件只在网关**启动那一刻**读 plugins.enabled，reload 不一定够）
systemctl restart hermes-gateway      # 或你部署方式对应的命令
```

`install.sh` 做三件事，全程可重复运行：

1. 拷 `assets/feishu-menu-bridge/` → `$HERMES_HOME/plugins/feishu-menu-bridge/`，并 `hermes plugins enable`
2. 拷 `assets/feishu-model-picker/` → `$HERMES_HOME/plugins/feishu-model-picker/`，并 `hermes plugins enable`
3. 把 `quick_commands.yaml`（56 条中文快捷命令）**合并**进 `$HERMES_HOME/config.yaml`

第 3 步是**文本级、块内合并**：只动 `quick_commands:` 那一块，文件其余部分字节不变；已存在的同名命令**不覆盖**；写之前自动备份成 `config.yaml.bak-<时间戳>`；写完用 `hermes config get quick_commands` 回读复核。

想先看会改什么：

```bash
python3 scripts/apply-quick-commands.py --dry-run   # 只打印，不写
python3 scripts/apply-quick-commands.py --force     # 同名命令也用本包的值覆盖
```

装完到飞书里给机器人发 `/model`：**出交互卡片 = 本地部分成功**。

---

## 第二步：铺控制台悬浮菜单（唯一需要人工的一步：扫一次码）

飞书**没有**提供自定义菜单的开放 API，只能登录控制台改。这一步由**你的 AI 助手**在浏览器里代劳，人只需要扫一次码。

> ⚠️ **顺序很重要**：必须**先做完第一步（插件已在网关里生效）再发布菜单**。菜单项发出去的就是名字本身（带 emoji 的 `✨新会话` 也照发），如果插件还没加载，点菜单名会直接落进模型。

给助手的操作顺序：

1. **用带持久化 profile 的浏览器**打开 `https://open.feishu.cn/app`。
   （经验：会话态要能跨命令存活，否则每次都被重置回空白页，逼着反复扫码。）
2. 页面会把登录二维码画在 `canvas` 上。取出来发给用户：
   ```js
   document.querySelector('canvas').toDataURL('image/png')   // → base64 → 存 PNG → 发给用户
   ```
   ⚠️ **取完码不要再碰那个标签页**：重导航/刷新会作废「待确认」的扫码会话。用户手机上若弹「确认登录」，要点确认。
3. 登录后进入**你的应用**，URL 形如 `https://open.feishu.cn/app/cli_xxxx/...`。
   （控制台会话 **20–30 分钟**过期，后面几步要一口气做完。）
4. **铺菜单**——生成可直接粘贴执行的片段：
   ```bash
   python3 scripts/build-console-snippet.py apply
   ```
   把输出**整段**贴进该页面的 JS 执行入口。
   ⚠️ 片段是 `async` 的，**执行时必须等它返回（await / awaitPromise），不能同步取值**——否则拿到空串，误判成失败。
   它会：先读当前菜单留底 → 写入 `menu.json` 的 5 组 23 项 → 再回读复核。返回的 JSON 里应满足：
   - `after.groups` = `["📊面板","💬会话","🎯任务","⚙️设置","🔧运维"]`
   - `after.leaves` = `23`
   - `before` 是你原来的菜单（**想回滚就把它写回去**）
5. **发布版本**（自建应用免审核，状态立即生效）：
   ```bash
   python3 scripts/build-console-snippet.py publish --changelog "同步悬浮菜单结构"
   ```
   贴进页面执行，返回 `"published": true` 才算成功。版本号默认自动取历史最大版本 +1。
6. **补两件控制台的事**（脚本不代劳，见 `SKILL.md` 第二节）：
   - 「权限管理」→ 开通应用身份权限（tenant_access_token）清单；
   - 「事件与回调」→ 订阅**「卡片回传交互」**（**长连接模式同样需要**；不订阅卡片点不动）。
7. 等约 **5 分钟**客户端同步，然后到飞书里点悬浮菜单试。

---

## 第三步：验证（别只看 CLI 输出）

`hermes plugins list` 里那行 `[Xxx] registered` 来自 CLI 进程，**不代表网关加载了**。三条硬证据：

1. **日志落点**：插件日志写在 `~/.hermes/logs/agent.log`，**不进 journald**。查该进程启动时刻之后的 `hook installed ... (vN)` 行，行尾版本号 `(vN)` 就是「已加载的真源」。
2. **线程证据（最硬）**：`for t in /proc/<网关pid>/task/*; do cat $t/comm; done | sort | uniq -c` 里出现 `feishu-model-pi` + `fmp-watchdog` ＝ 插件模块已 import 且 `register()` 已跑（内核线程名只取前 15 字符）。
3. **版本/哈希**：`ps -o lstart= -p <pid>` 的启动时刻必须**晚于**插件文件的 mtime。

功能验证：飞书里发 `/model`（点选器）、点悬浮菜单的「📊面板」（菜单桥）。两者都出卡片即全链路通。

---

## 关于解释器

Hermes 网关上常并存两套 Python，本包已按此设计：

- **插件与网关**：跑在 Hermes 自己的运行时里。
- **离线脚本**（自测 / 对账 / 片段生成）：系统 `python3` 即可，本包脚本只用标准库。

> 如果你把脚本改去读 `config.yaml`，注意 `ruamel.yaml` 这类依赖**只在走过 Hermes 引导流程的网关进程里可见**，裸 shell 里 import 会失败。

### 插件读 Hermes 自带模块的两个默认路径

菜单桥插件为了做「人格卡」「推理档位」「命令表」，要**静态解析 Hermes 自带的几个模块**（人格表、常量、命令注册表）。默认按**系统级安装**的布局找：

| 环境变量 | 默认值 | 用途 |
|---|---|---|
| `HERMES_AGENT_DIR` | `/usr/local/lib/hermes-agent` | 读 `hermes_cli/personality.py`、`hermes_constants.py`、`hermes_cli/commands.py` |
| `HERMES_PYTHON` | `/usr/bin/python3` | 起子进程跑 `tools/usage_wave.py`（用量波形图） |

**如果你的 Hermes 不是装在这两个位置**（pipx、venv、容器、自定义前缀），在 `$HERMES_HOME/config.yaml` 或网关的 systemd unit 里把这两个变量指到你自己的路径，然后重启网关。不设的话，**菜单、快捷命令、卡片点击都正常**，只有「人格卡 / 推理档位 / 命令表 / 用量波形」这四块会读到空。

确认方法：到飞书里点「🎭人格」「🧠推理」「📜命令表」——有内容就是找对了。

### PT 卡的数据来源

悬浮菜单里的 `🌱PT` 卡**只读、不发起签到**。它读一个目录，默认 `~/.pt-sessions`，可用环境变量 `PT_SESSIONS_DIR` 覆盖：

| 文件 | 格式 | 用途 |
|---|---|---|
| `state/sites.json` | 字符串数组，如 `["站点甲", "站点乙"]` | 卡面「🌐 站点」格的总数 |
| `state/checkin_runs.json` | `{"runs": [ {"date": "…", "ok": N, "ended": "…", "sites": [ {"site": "…", "status": "ok\|fail\|skip", "note": "…", "time": "…"} ]} ]}` | 取**最后一条** run 渲染明细；`status` 用 `ok` / `fail` / `skip` |
| `state/checkin_live.json`（可选） | `{"started": <unix 秒>, "hb": <unix 秒>}` | 见下面「签到静音窗」 |

两个文件都没有时，卡片照常打开，显示 `? 站 · 尚无记录`——**不报错，也没有任何按钮会把消息误送进模型**。

**签到静音窗（可选）**：`checkin_live.json` 存在且新鲜时，插件会把飞书的**工具进度显示整体关掉**，并把后台任务完成提示**暂存、等签到结束后合并补发**。它是给「一次签到要跑好几分钟、期间刷屏」的场景降噪用的。接法：你的签到脚本开始时写 `{"started": <now>, "hb": <now>}`、每几分钟刷新 `hb`，结束时删掉该文件。不写这个文件的话这一块永远不触发，其它功能不受影响。

> 卡片上**没有**「全部签到 / 只看失败」按钮——那两个按钮原本发的是**一条文本命令**，接收方网关上没有这条快捷命令也没有对应技能，点下去会落进模型当普通聊天，所以本包已把它们换成「🔄 刷新」。

确认方法：到飞书里点「🌱PT」——出现卡片（哪怕写着 `? 站`）就说明菜单桥、卡片渲染、点击链路全通。

## 一致性对账

`assets/` 是**产物**——由作者本机的 live 插件经生成器产出（去敏 + 分发覆盖）。
不再需要人肉对齐两份，也不会因为「改了线上忘了同步回包」而漂移：

```bash
python3 scripts/sanitize-live-to-assets.py --write   # 从 live 重生成 assets
python3 scripts/sanitize-live-to-assets.py --check   # 只比对（改了 live 没重生成 → exit 1）
bash scripts/check-assets-sync.sh                    # 生成器对账 + 两层校验和 + 语义护栏
python3 scripts/regen-sums.py                        # 重算内层 SHA256SUMS → 外层 MANIFEST
python3 scripts/scan-leaks.py --history              # 泄漏扫描（工作区 + 全历史）
```

**改了插件后的正确顺序**：改 live → `--write` 重生成 → `regen-sums.py` 重算两层 → `scan-leaks.py` 扫一遍 → 提交。

生成器把差异分成两类，都写在 `scripts/sanitize-live-to-assets.py` 的规则表里、逐条有名字：

- `sanitize:` —— 纯个人/本机标识 → 中性值（行为不变）；
- `overlay:` —— **有意的分发版功能差异**（不是去敏）。目前只有 PT 卡那条：删掉两个会误触的按钮。

CI（`.github/workflows/ci.yml`）只做它**做得到**的事：语法检查、两层校验和、泄漏扫描、产物里不许出现宿主家目录的绝对路径。
它**不**重生成 assets——CI runner 上没有作者的 live 插件，那项核对只能在作者本机跑（就是上面的 `check-assets-sync.sh`）。

## 回滚

- **插件**：`rm -rf $HERMES_HOME/plugins/feishu-menu-bridge`（或 `feishu-model-picker`），再从 `config.yaml` 的 `plugins.enabled` 里删掉，重启网关。
- **快捷命令**：`$HERMES_HOME/config.yaml.bak-<时间戳>` 覆盖回去。
- **控制台菜单**：`console-apply-menu.js` 返回的 `before` 就是改前的菜单，把它作为 `menu` 写回 `POST /developers/v1/robot/update_changed/<clientId>` 即可，然后同样建版本 + 发布。

## 常见问题

- **`/model` 回的是文字列表** → `send_model_picker` 没挂上：查 `plugins.enabled` 是否含该插件，再看日志里有没有 `lark builder hook installed`。
- **点悬浮菜单没反应 / 回了原文** → 菜单桥插件没生效：查日志有没有 `FeishuMenuBridge` 的行；多半是网关没重启，或 Hermes 版本与插件不匹配（见 README「能力边界」）。
- **卡片发出来点不动** → 飞书开放平台后台「事件与回调」是否订阅了「卡片回传交互」（**长连接模式同样需要**）。
- **点按后回「未知命令 /card」** → 点击穿到了官方通用路径，见 `SKILL.md`「四层拦截」一节；多半是新按钮载荷键没加进插件的键白名单。
- **卡片不原地更新、另收到一条文字** → `message_id` 为空，或更新接口失败（看日志 warning）。
- **`health UNHEALTHY: {...'batch': None...}`** → 多是**假警报**：短命 CLI 进程（`hermes plugins list/doctor`）和仪表盘进程都会 import 插件但不连平台，家族自然全 None。先确认读数出自哪个进程再判读，别追。
- **重载 ≠ 插件被加载** → 网关只在**启动那一刻**读 `plugins.enabled`。启用新插件后只 reload 可能没进网关，必要时重启。
