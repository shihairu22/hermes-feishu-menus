# 飞书菜单全家桶（Hermes 技能包）

**给你的 Hermes 飞书机器人装上一套界面。** 中文悬浮菜单 + 中文快捷命令 + 可点选的交互卡片，装完在飞书里直接用。

Hermes 原生的飞书机器人只会收发文本 —— 命令得背、参数得敲。这个包把输入框上方变成菜单栏：点一下就等于发一条中文命令；`/model` 这类需要选参数的，直接弹**可点选的卡片**。

一份包、三层能力，**本地部分全自动**，全程只有一步需要你本人：在飞书开放平台控制台扫一次码。

```
点悬浮菜单  →  飞书发出对应文本（如「📊面板」）  →  Hermes 网关命中快捷命令 / 插件拦截  →  回文字或交互卡片
```

## 它解决什么

| 原来 | 装完之后 |
|---|---|
| 得记住 `/status`、`/new`、`/model <名字>` 这些命令和参数 | 点悬浮菜单「📊面板」「💬新会话」，或点卡片选模型 |
| 回复是纯文本，状态要自己拼 | 状态 / 会话 / 任务 / 设置 / 运维 出结构化卡片，可翻页、可局部刷新 |
| 每个操作都要打字 | 5 组 23 项菜单覆盖日常操作，56 条中文快捷命令兜底 |

## 它给你什么

| 组成 | 落点 | 是否需要人工 |
|---|---|---|
| 控制台悬浮菜单：**5 组 / 23 项**（📊面板 · 💬会话 · 🎯任务 · ⚙️设置 · 🔧运维） | 飞书开放平台控制台 | 需要**扫一次码** |
| 中文快捷命令 `quick_commands`：**56 条**（`/状态` `/新会话` `/时间` …） | `$HERMES_HOME/config.yaml` | 全自动 |
| 插件 `feishu-menu-bridge`：悬浮菜单文本 → 交互卡片 | `$HERMES_HOME/plugins/` | 全自动 |
| 插件 `feishu-model-picker`：`/model` 点选器卡片 | `$HERMES_HOME/plugins/` | 全自动 |
| 实测手册：`SKILL.md` + `references/`（卡片局部刷新、配色、翻页…） | 给 AI 助手读 | — |

## 三步跑起来

```bash
# ① 取包 + 拷进技能库
git clone https://github.com/shihairu22/hermes-feishu-menus.git
mkdir -p ~/.hermes/skills/social-media
cp -r hermes-feishu-menus ~/.hermes/skills/social-media/feishu-menus

# ② 本地安装：两个插件 + 中文快捷命令（无需扫码）
bash ~/.hermes/skills/social-media/feishu-menus/scripts/install.sh

# ③ 重启网关，让插件真正加载
systemctl restart hermes-gateway      # 或你部署方式对应的命令
```

到飞书里给机器人发 `/model`：**出交互卡片 = 本地部分成功**。

剩下**唯一需要人工的一步**是铺控制台悬浮菜单（官方没有 API，必须登录控制台）——照 `SETUP.md`「第二步」走：你的 AI 助手会把登录二维码取给你扫，扫完之后铺菜单、发布版本全自动。

## 目录

```
feishu-menus/
├── SKILL.md                      # 技能正文（给 AI 助手读的操作手册）
├── README.md                     # 本文件
├── SETUP.md                      # 环境准备 / 三步安装 / 排错
├── SANITIZED.md                  # 去敏说明与自检命令
├── MANIFEST.sha256               # 全包校验和
├── menu.json                     # 控制台悬浮菜单定义（5 组 23 项）
├── quick_commands.yaml           # 中文快捷命令片段（56 条）
├── references/                   # 深水区实测记录
│   ├── cardkit-partial-update-and-animation.md   # 卡片局部刷新 / 动画边界
│   ├── card-palette-and-verified-components.md   # 卡头配色 + 可用组件清单
│   └── paging-and-card-inventory.md              # 翻页机制 + 卡片清单 + 重启姿势
├── scripts/
│   ├── install.sh                        # ★ 一键本地安装（插件 + 快捷命令）
│   ├── install-feishu-menu-bridge.sh     # 单装「菜单桥」插件
│   ├── install-feishu-model-picker.sh    # 单装「模型点选器」插件
│   ├── apply-quick-commands.py           # 把 quick_commands.yaml 合并进 config.yaml
│   ├── build-console-snippet.py          # 生成控制台可粘贴的 JS 片段
│   ├── console-apply-menu.js             # 控制台：读菜单 → 写菜单 → 回读复核
│   ├── console-publish.js                # 控制台：建版本 → 提交发布
│   ├── check-assets-sync.sh              # assets ⇄ 线上插件一致性对账
│   ├── feishu-model-picker-selftest.py   # 插件离线自测（7 项，纯标准库）
│   └── skill_zh_autofill.py              # 把技能卡里没中文化的说明一次补齐（可选）
└── assets/
    ├── feishu-menu-bridge/       # 菜单桥插件源码（4 个文件 + SHA256SUMS）
    └── feishu-model-picker/      # 点选器插件源码（3 个文件 + SHA256SUMS）
```

## 常用命令

```bash
bash scripts/install.sh                             # 一键装：插件 + 快捷命令
python3 scripts/apply-quick-commands.py --dry-run   # 只看会往 config.yaml 加什么
python3 scripts/build-console-snippet.py apply      # 生成「铺菜单」JS
python3 scripts/build-console-snippet.py publish    # 生成「建版本+发布」JS
python3 scripts/feishu-model-picker-selftest.py     # 插件离线自测
bash scripts/check-assets-sync.sh                   # assets ⇄ 线上插件对账
python3 scripts/skill_zh_autofill.py --stats        # 看技能卡还有多少条说明没中文化
python3 scripts/skill_zh_autofill.py                # 一次补齐（走你自己配置的模型）
sha256sum -c MANIFEST.sha256                        # 校验本包完整性
```

## 谁适合用

- 已经跑着 Hermes、并且接了飞书渠道，觉得纯文本交互太费手的人。
- 想照着一份**实测过**的笔记自己改卡片的人 —— `references/` 里记的都是踩过的坑和验过的组件清单。

**不适合**：没跑 Hermes 的人（这包依赖 Hermes 网关与插件机制）；想「零人工全自动装完」的人（控制台扫码那一步绕不开，原因见下）。

## 能力边界（先说清楚，省得白折腾）

- **控制台菜单没有官方 API**：改菜单必须登录飞书开放平台控制台。无设备登录时只能由人**扫一次码**（助手可以代取二维码发给你，但扫码那一下必须本人）。控制台会话 **20–30 分钟**过期，扫完要一口气干完。
- **菜单发布后客户端约 5 分钟才同步**，别以为没生效就反复发布。
- **两个插件是「运行期打补丁」式实现**：`feishu-menu-bridge` 包装的是 Hermes 适配器的**内部私有方法**（`FeishuAdapter._dispatch_inbound_event`、`GatewayRunner._hm_handle_running_session_message`）。**Hermes 版本差得远就会失效**——装完务必按 `SETUP.md`「第三步」的三条硬证据验一遍。
- **权限与事件订阅仍需在控制台做**：应用身份权限清单见 `SKILL.md` 第二节；「卡片回传交互」回调在「事件与回调」里订阅（**长连接模式同样需要**）。不订阅，卡片点不动。
- **卡片渲染效果只能真机确认**：接口返回 `code=0` 只代表服务端收下了，不代表客户端画出来了。
- **卡片做不到连续动画**：图表组件每次被更新都会重新挂载，视觉上永远是「转圈 → 硬切」（已实测，见 `references/cardkit-partial-update-and-animation.md`，别再花时间试）。
- **`🌱PT` 卡片是只读的**：它读 `$PT_SESSIONS_DIR`（默认 `~/.pt-sessions`）下的两个 JSON 文件渲染签到明细，**不发起签到**，卡片上也**没有**「全部签到」按钮（那条命令得对接你自己的签到脚本）。没有数据文件时卡片照常打开、显示 `? 站 · 尚无记录`。文件格式见 `SETUP.md`「PT 卡的数据来源」。
- 部分操作需要**重启或热加载 Hermes 网关**的权限。

## 依赖与降级（装之前先知道）

插件**不依赖任何第三方库**（纯标准库），但有几处会读**本机 Hermes 的文件**。缺了不会崩，只会降级 —— 下表是实测结果，不是推断：

| 卡 / 功能 | 依赖 | 缺了会怎样（实测） |
|---|---|---|
| 全部 **23 项菜单** | 插件 + 重启网关 | **23/23 全部命中**（10 项转成内置命令、13 项出卡片） |
| 🎭人格 / 📜命令表 | Hermes 安装目录里的 `hermes_cli/personality.py`、`hermes_constants.py`、`hermes_cli/commands.py` | **自动探测**，见下方说明；全都找不到才会降级（人格 14→0 个内置、命令表 67→23 条） |
| 🧠推理 | 插件自带档位表 | 不受影响 |
| 🩺状态 / 📈用量 / 🔍洞察 | `$HERMES_HOME/state.db` | 任何 Hermes 都有；无数据时显示空值 |
| 📈用量 的**波形块** | `$HERMES_HOME/tools/wave_shared.py` + `usage_wave.py` | 显示一行「波形块未启用」提示（**不再静默留白**），卡片其余部分正常 |
| 🌱PT | `$PT_SESSIONS_DIR/state/*.json` | 显示 `? 站 · 尚无记录` |
| 🖥系统 | 本机实时读数 | 不受影响 |

**关于 Hermes 安装位置：** 插件不再写死 `/usr/local/lib/hermes-agent`，而是按顺序自动探测 ——

1. 环境变量 `HERMES_AGENT_DIR`（设了且存在就用它，尊重你的选择）
2. 已装好的 `hermes_cli` 包位置（插件就跑在 Hermes 进程里，这条路最可靠）
3. `sys.path` 里含 `hermes_cli/personality.py` 的目录
4. 常见安装位置（`/usr/local/lib/hermes-agent`、`/opt/hermes-agent`、`~/.local/share/hermes-agent`、`~/hermes-agent`）
5. 都没有才退回历史默认值

所以 **pipx / venv / `~/.local` 安装同样能直接跑**，不必手动设环境变量；只有在非常规布局下才需要显式指定。

> 用量卡的**波形块**依赖本机 `tools/` 下两个工具文件（**不在本包里**，属于可选增强）。没有就是那行提示，卡片不会报错。

## 技能卡的中文说明是怎么来的

技能卡里「按钮下方那一行」是中文的，来源**三层，按优先级**：

1. **你自己技能自带的说明** —— 你的 `SKILL.md` 写的是中文，卡片就显示中文（多数情况命中这层，零成本）
2. **包内静态表** `skill_zh.json`（66 条）—— 覆盖常见/上游技能，离线、零成本，装完就有
3. **自动补译** —— 前两层都没有、且原文不是中文的，插件用**你自己配置的模型**译成一行中文，
   结果存 `$HERMES_HOME/state/skill_zh_auto.json`，之后一直复用

**自动补译的行为**（都是实测过的）：

- **不阻塞**：卡片立刻渲染，翻译在后台线程里做 —— 永远不会让你等模型
- **一次 20 条**：每打开一次技能卡补一批，几轮下来就齐了；卡上会显示「⏳ 另有 N 条说明还没中文化」
- **想一次补齐**：`python3 scripts/skill_zh_autofill.py`（`--dry-run` 先看要译哪些，`--stats` 看还剩多少）
- **成本**：约 250 token/条，走你自己的额度。95 个技能大约 2.5 万 token（一次性）
- **幂等**：已译过的不再送模型；想强制重译某条，把它从 `state/skill_zh_auto.json` 删掉再跑
- **失败静默**：模型不可用/超时就保留原文，不写坏缓存、不影响其他功能
- **关掉**：设环境变量 `FMB_SKILL_ZH_AUTO=0` 后重启网关

> 人格卡不走这套 —— 14 个内置人格的中文说明是**插件自带**的，装完就是中文；
> 对方自建的人格会显示原始英文说明（**不编造翻译**）。

## 常见问题

**装完菜单没出现？**
菜单发布后客户端要几分钟同步；先确认控制台里版本已发布、且订阅了「卡片回传交互」。仍不行就按 `SETUP.md`「第三步」逐条验。

**`/model` 没出卡片？**
插件没被加载。重启网关后重试，再跑 `python3 scripts/feishu-model-picker-selftest.py` 看插件本身是否正常。

**点菜单会误发消息吗？**
悬浮菜单的机制就是**发一条文本**（这是飞书侧设计，不是本包的取巧），网关再把它接住。本包里唯一「点了会发命令」的按钮已经拆掉了 —— `🌱PT` 卡只剩「🔄 刷新」。

**升级 Hermes 之后失效了？**
见上面「运行期打补丁」那条。这是本包最大的脆弱点，`SETUP.md` 给了验证方法。

**包里有没有我的数据？**
没有。这是**去敏分发版**：不含作者的家目录路径、应用 ID / 会话 ID、密钥、站点清单。详见 `SANITIZED.md`（含可自行运行的自检命令）。

## 许可

MIT，见 `LICENSE`。
