# 已知债务 · 明确「这轮没修」的结构性项

> 面向**维护者**（自己或接手的人），不是使用说明。
> 来源：2026-10-07 对 `feishu-menu-bridge` / `feishu-model-picker` 的多路只读审计（7 路子代理 + 逐条回源码复核）。
> 同批次的**功能缺陷已全部修复**（见 `CHANGELOG.md` v1.0.2）；这里记录的是**结构性问题**——它们不是 bug，
> 修起来要动大手术、回归风险远大于收益，所以本轮**只记录不动**。动之前请先读完这一页。

## 1. 两个 `keeper.py` 约 95% 逐字复制，且已经漂移

- `assets/feishu-menu-bridge/keeper.py` 与 `assets/feishu-model-picker/keeper.py` 是同一份代码的两份拷贝：
  `KEEPER_VERSION` 分别是 **2** 和 **1**，`WATCHER_NAME` / `WATCHDOG_NAME` 不同，跨代共享容器名不同。
- **为什么不合并**：keeper 的语义是「进程内唯一一条 watcher 线程 + 看门狗 + 跨代共享容器」，
  两个插件**同时**加载时必须各有一份独立的 `KEEPER_NAME` / 线程名，合并成一个共享模块会引入
  「谁的名字、谁的 token、谁收养谁」的新耦合；而这两份代码的差异恰好就在这些身份字段上。
- **代价**：改一处 bug 要改两遍，忘了就分叉。**最低成本纪律**：改任一份 keeper.py 时，
  同时 `grep` 另一份里的同名函数，逐行确认是否也要改；改完把两边的 `KEEPER_VERSION` 各自 +1
  （插件侧的 `_KEEPER_VERSION` 必须同步，否则契约校验会拒绝加载 —— 见 v1.0.2 的 #15 修复）。

## 2. 单一 `_CODE_V` 统管 7+ 个补丁族，5 套防重范式并存

- 同一个 `_CODE_V` 决定：批处理改写、忙线拦截、分发器拦截、卡片路由、出卡卡化、已处理卡、回执抑制、PT 静音窗、
  lark builder 钩子 是否重装。
- 防重/升版机制有 **5 套**并存：`_mk()` + 类标记、`_mk()` + 函数标记、`_hermes_orig` 包装链、
  `_Guard` 数值版本位、`_stamp_value()` 代际戳。
- **风险**：升版纪律靠人记。**改了补丁逻辑却忘了 `_CODE_V += 1`，热重载后旧包装继续生效，表现为「改了没用」**。
- **为什么不重构成一套**：这 5 套分别对付不同的对象（类属性 / 实例属性 / 闭包 / 跨模块函数），
  统一成一套要引入中间抽象层，反而更容易在某条路径上静默失效。**当前纪律**：改「卡片 / 点击 / 补丁」逻辑，
  一律 `_CODE_V += 1`，并在 CHANGELOG 里写明。

## 3. `config.yaml` 被 7 处手写正则各解析一遍

- 读 `display.busy_input_mode`、`quick_commands`、`base_url`、`api key`、人格预设等，各自写一套
  `re.search(r"(?m)^\s*xxx:")`。
- **风险**：上游 Hermes 改了配置缩进 / 字段名 / 换成 YAML 多行风格，这些正则**静默失配**（返回默认值，不报错）。
- **为什么不修**：插件在网关进程里跑，**不能**依赖 `ruamel.yaml`（那是网关引导流程注入的，
  裸 shell / 短命 CLI 进程里 import 会失败）；改成「一次解析成 dict 再取字段」需要自建一个极小的
  YAML 子集解析器，工作量与风险都不小。**当前纪律**：每次改正则，去 `SETUP.md` 的配置示例上验一遍。

## 4. 零版本约束依赖 9 个上游私有符号

插件用 `getattr` 拿上游的私有成员（`_dispatch_inbound_event`、`_hm_handle_running_session_message`、
`_is_user_authorized_for_source`、`send_final_ledgered`、`resolve_tool_progress`、
`_send_interactive_card` 的关键字参数、`base.send_slash_confirm` 契约、`FeishuAdapter` 的私有方法、
`SessionSource` 字段等）。

- **风险**：上游任一改签名，插件会**静默降级或崩在某条路径上**（不是启动就报错）。
- **为什么不修**：上游没有稳定插件 API，`getattr` + 存在性检查 + 降级路径就是当前唯一可行的接法。
  **缓解**：每处 `getattr` 都配了「取不到 → 记 warning + 走降级」；`_patch_health` 每 5 分钟巡检补丁族存活。
- **升级 Hermes 后的自检**：`grep -c '(v111)' ~/.hermes/logs/agent.log` 与 `_patch_health` 的巡检行。

## 5. 三处菜单分发逻辑各写一份，鉴权策略曾不一致

菜单「点按 → 发卡 / 改写成命令」的逻辑在 **三个地方**各写了一遍：入站钩子（`_on_pre_gateway_dispatch`）、
批处理改写（`_batch_rewrite`）、忙线包装（`_busy_menu_wrapper`）。v1.0.1（F01）只给前两处加了鉴权闸门，
第三处没有 —— 那是 2026-10-07 审计发现的 **F01 结构性根因**。

- **v1.0.2 已补齐**：忙线包装的发卡路径现在也走同一个 `_sender_authorized()`（fail-closed）。
- **仍未合并**：三份逻辑还是三份。抽成单点需要先把三处的入参形态（`event` / `source` / 原始 text / 是否已有适配器）
  统一，改动面覆盖所有点击路径，**回归风险最高的就是这里**，所以留到「有一次完整的端到端点击测试」时再做。

## 6. `scripts/check-assets-sync.sh` 在本机永远报 DRIFT（设计冲突，未修）

该脚本逐文件比 `assets/` 与 `$HERMES_HOME/plugins/` 的 sha256，相等才 OK。但本包的 `assets/` 是**去敏版**
（路径改成 `$HERMES_HOME` / `~`、去掉个人化文案），**必然与线上不一致** → 脚本在本机恒定报 DRIFT，
失去「对账」意义。

- **本轮怎么处理**：同步时**不用这个脚本判定**，改为「同一套补丁脚本分别打到两侧 + 两侧各自 `py_compile` +
  语义护栏（`grep` 关键修复标记）」。
- **正确的修法**（未做）：让脚本比对「去敏变换后的 live」而不是原始 live —— 需要一个与去敏规则同步维护的
  归一化函数；在去敏规则还在变之前，这个归一化函数本身就是新的漂移源。

## 7. 其它已确认但**故意不修**的小项

- **`_patch_health` 的巡检族不全**：`lark` / `dispatcher` / `ws` 三族不在巡检内（v1.0.2 修了「全 None 判据不可达」
  的死代码，但没扩族）。扩族会把 `healthy` 语义变复杂，容易产生假警报，故留观。
- **斜杠确认卡两层实现**：本地 `adapter.py` 补丁（+129 行）与插件自身包裹重复，本地 send 路径是死代码，
  而插件点击路径硬依赖本地专属符号。属于「上游补丁 vs 插件」的边界问题，改它要同时动 `adapter.py`，不在本包范围内。
- **两份技能枚举 / 两份 markdown 清洗 / 三份「读 base_url + key」**：重复实现，但每份的容错策略不同，
  合并会把「宽容失败」和「严格校验」混在一起，收益低于风险。
