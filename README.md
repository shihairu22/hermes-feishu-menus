# 飞书菜单全家桶（Hermes 技能包）

装到你自己那台跑 Hermes 的机器上，飞书里就会长出一套**中文悬浮菜单 + 中文快捷命令 + 可点选的交互卡片菜单**——和作者在用的那套同款。

## 它给你什么

| 组成 | 落点 | 是否需要人工 |
|---|---|---|
| 控制台悬浮菜单：**5 组 / 23 项**（📊面板 · 💬会话 · 🎯任务 · ⚙️设置 · 🔧运维） | 飞书开放平台控制台 | 需要**扫一次码** |
| 中文快捷命令 `quick_commands`：**56 条**（`/状态` `/新会话` `/时间` …） | `$HERMES_HOME/config.yaml` | 全自动 |
| 插件 `feishu-menu-bridge`：悬浮菜单文本 → 交互卡片 | `$HERMES_HOME/plugins/` | 全自动 |
| 插件 `feishu-model-picker`：`/model` 点选器卡片 | `$HERMES_HOME/plugins/` | 全自动 |
| 实测手册：`SKILL.md` + `references/`（卡片局部刷新、配色、翻页…） | 给 AI 助手读 | — |

链路：**点悬浮菜单 → 飞书发出一条文本（如「📊面板」）→ Hermes 网关命中快捷命令 / 插件拦截 → 回复文字或交互卡片。**

## 三步跑起来

```bash
# ① 拷进技能库
mkdir -p ~/.hermes/skills/social-media
cp -r feishu-menus ~/.hermes/skills/social-media/

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
│   └── feishu-model-picker-selftest.py   # 插件离线自测（7 项，纯标准库）
└── assets/
    ├── feishu-menu-bridge/       # 菜单桥插件源码（4 个文件 + SHA256SUMS）
    └── feishu-model-picker/      # 点选器插件源码（3 个文件 + SHA256SUMS）
```

## 常用命令

```bash
bash scripts/install.sh                       # 一键装：插件 + 快捷命令
python3 scripts/apply-quick-commands.py --dry-run   # 只看会往 config.yaml 加什么
python3 scripts/build-console-snippet.py apply      # 生成「铺菜单」JS
python3 scripts/build-console-snippet.py publish    # 生成「建版本+发布」JS
python3 scripts/feishu-model-picker-selftest.py     # 插件离线自测
bash scripts/check-assets-sync.sh                   # assets ⇄ 线上插件对账
sha256sum -c MANIFEST.sha256                        # 校验本包完整性
```

## 能力边界（先说清楚，省得白折腾）

- **控制台菜单没有官方 API**：改菜单必须登录飞书开放平台控制台。无设备登录时只能由人**扫一次码**（助手可以代取二维码发给你，但扫码那一下必须本人）。控制台会话 **20–30 分钟**过期，扫完要一口气干完。
- **菜单发布后客户端约 5 分钟才同步**，别以为没生效就反复发布。
- **两个插件是「运行期打补丁」式实现**：`feishu-menu-bridge` 包装的是 Hermes 适配器的**内部私有方法**（`FeishuAdapter._dispatch_inbound_event`、`GatewayRunner._hm_handle_running_session_message`）。**Hermes 版本差得远就会失效**——装完务必按 `SETUP.md`「第三步」的三条硬证据验一遍。
- **权限与事件订阅仍需在控制台做**：应用身份权限清单见 `SKILL.md` 第二节；「卡片回传交互」回调在「事件与回调」里订阅（**长连接模式同样需要**）。不订阅，卡片点不动。
- **卡片渲染效果只能真机确认**：接口返回 `code=0` 只代表服务端收下了，不代表客户端画出来了。
- **卡片做不到连续动画**：图表组件每次被更新都会重新挂载，视觉上永远是「转圈 → 硬切」（已实测，见 `references/cardkit-partial-update-and-animation.md`，别再花时间试）。
- **`🌱PT` 卡片是只读的**：它读 `$PT_SESSIONS_DIR`（默认 `~/.pt-sessions`）下的两个 JSON 文件渲染签到明细，**不发起签到**，卡片上也**没有**「全部签到」按钮（那条命令得对接你自己的签到脚本）。没有数据文件时卡片照常打开、显示 `? 站 · 尚无记录`。文件格式见 `SETUP.md`「PT 卡的数据来源」。
- 部分操作需要**重启或热加载 Hermes 网关**的权限。

## 怎么用这份技能

- **用 Hermes**：整个目录拷进 `~/.hermes/skills/<分类>/feishu-menus/`，助手会在相关任务时自动加载 `SKILL.md`。
- **不用 Hermes**：`SKILL.md` + `references/` 本身就是一份可读的操作手册；`assets/` 里的插件是标准 Hermes 本地插件，手工拷贝也能用。
