"""feishu-model-picker 的跨重载守护宿主（keeper）。

为什么要单独一个文件
--------------------
插件模块 ``hermes_plugins.feishu_model_picker`` 每次热重载都会被 ``_evict_modules()``
清掉再 ``exec_module()`` 一份**全新的模块对象**。旧实现里 ``register()`` 每次都新起一条
``_watch`` 守护线程，而那条线程是 ``while True`` 且**不认任何停止标志**：

  * 线程一条条泄漏（实测网关上同时活着 13 条 ``feishu-model-pi``），每条都把上一代的
    模块命名空间（含 ``_PICKERS`` 卡片状态）钉在内存里，永不回收；
  * 补丁标记 ``_MARKER`` / ``_MARKER_LARK`` 是**粘性**的 → 新一代的 ``_try_install()``
    看到标记就返回 True，**不会重装自己的 hook**，于是类属性仍指向第一代的闭包
    → 结果是「改了插件、热重载不生效，必须重启网关」。

本模块的名字（``hermes_plugins._fmp_keeper``）**不在** ``hermes_plugins.<slug>``
前缀下，因此不会被 evict。它承载：

  * 进程内**唯一一条** watcher 线程（跨代存活，不随重载增减）
  * 看门狗线程（watcher 意外死亡时拉起，30 秒心跳）
  * 跨代共享的活状态（``_PICKERS`` 卡片状态、``_PID`` 序号）
  * 每轮从 ``generation`` 取「当前代模块」再调用其 ``_watch_once()``
    → **永远执行最新一代的代码**

设计边界
--------
* 本文件只放**循环机制**，不放业务逻辑。业务逻辑全在被交班的插件模块里，
  所以升级业务代码**不需要重启网关**；本文件自身改动才需要重启网关。
* 线程目标函数属于本模块 → 其 ``__globals__`` 是本模块的字典，**不会**被
  ``_evict_modules()`` 动到，因此线程不会持有旧插件模块的字典（旧模块可被 gc）。
* 不注入任何异步异常；不触碰全局 ``threading.excepthook``。
"""
from __future__ import annotations

import logging
import sys
import threading
import time

logger = logging.getLogger("hermes_plugins.feishu_model_picker")

#: keeper 版本戳：插件侧带同号常量，不一致就重新加载 keeper 模块
#: → 改 keeper.py **不必重启网关**（旧 keeper 的线程会按自我让位退出，共享状态会被搬过来）。
KEEPER_VERSION = 1

WATCHER_NAME = "feishu-model-picker"
WATCHDOG_NAME = "fmp-watchdog"   # 注意：内核线程名只取前 15 字符，两者必须前缀可区分

_SLEEP_SLICE = 0.5      # 分片睡眠粒度：停止/让位在 ≤0.5s 内生效
_WD_INTERVAL = 30.0     # 看门狗心跳
_STOP_CONFIRM = 1.0     # 卸载→停止的确认窗（躲开热重载交班的瞬时窗口）
_NAP_MIN, _NAP_MAX = 0.2, 30.0

# ── 进程级单例状态（本模块不被 evict → 这些名字就是"跨重载"的）──────────
lock = threading.RLock()
state: dict = {}            # 跨代共享的活对象（字典/count 等，由插件模块别名过去）
stop = False                # True = 本代之后不再需要 watcher（卸载/禁用）
generation = None           # 当前代插件模块对象（交班指针）
module_name = ""            # 该模块的 __name__，用于「自我让位」判定
token = 0                   # 代际令牌：旧代的 on_unload 迟到回调不得停掉新代
thread = None               # 唯一 watcher 线程
watchdog = None             # 看门狗线程
rescues = 0                 # 看门狗拉起次数（诊断用）
exit_reason = ""            # watcher 退出原因（诊断用）


def shared(key: str, factory):
    """取/建跨代共享容器（同一 key 恒返回同一对象，跨重载不丢）。"""
    with lock:
        if key not in state:
            state[key] = factory()
        return state[key]


def _watcher_alive() -> bool:
    t = thread
    return t is not None and t.is_alive()


def _watchdog_alive() -> bool:
    t = watchdog
    return t is not None and t.is_alive()


def _generation_valid() -> bool:
    """当前代模块是否仍是 sys.modules 里的那个（否则 keeper 处于"空闲等交班"状态）。"""
    mod = generation
    return mod is not None and sys.modules.get(module_name) is mod


def sleep_sliced(seconds: float) -> None:
    """分片睡眠：让 ``stop`` 能在 ≤0.5s 内生效（不依赖任何异常注入）。"""
    deadline = time.time() + max(0.0, float(seconds))
    while not stop:
        remain = deadline - time.time()
        if remain <= 0:
            return
        time.sleep(min(_SLEEP_SLICE, remain))


def _adopt() -> "threading.Thread | None":
    """收养**本 keeper** 已存在的 watcher 线程（绝不新起第二条）。

    只认 ``__globals__ is globals()`` 的线程：keeper 模块被换版重建时，旧 keeper 的线程
    属于旧字典，交给它自己按「自我让位」退出，而不是收养过来（否则会白等它退出）。
    """
    for t in threading.enumerate():
        tgt = getattr(t, "_target", None)
        if tgt is None or not t.is_alive():
            continue
        if getattr(tgt, "__module__", "") != __name__ or getattr(tgt, "__qualname__", "") != "watch_loop":
            continue
        if getattr(tgt, "__globals__", None) is not globals():
            continue
        return t
    return None


def watch_loop() -> None:
    """唯一 watcher：每轮取「当前代」再跑它的 ``_watch_once()``。"""
    global exit_reason
    while not stop:
        mod = generation
        if mod is None:
            exit_reason = "no-generation"
            return
        # 自我让位：自己那一代已不是 sys.modules 里的当前模块（被替换/被卸载）
        # → 干净退出。这是双保险：即使 on_unload 没跑到也不会变成僵尸。
        if sys.modules.get(module_name) is not mod:
            exit_reason = "superseded"
            return
        try:
            nap = mod._watch_once()
        except Exception:  # 单轮出错不影响线程存活
            logger.debug("[FeishuModelPicker] watcher 单轮异常", exc_info=True)
            nap = 2.0
        try:
            nap = min(max(float(nap), _NAP_MIN), _NAP_MAX)
        except Exception:
            nap = 10.0
        sleep_sliced(nap)


def watchdog_loop() -> None:
    """看门狗：watcher 意外死亡（未捕获异常/被外部杀掉）时拉起一条新的。

    两条不救的规则：
      * 「当前代已失效」不救 —— 模块被卸载/替换后 watcher 是**故意**退出的，救回来只会
        得到一条立刻又退出的线程（还会每 30 秒刷告警）；
      * 连续两轮（默认 60 秒）都没有有效代 → 本 keeper 处于闲置（旧版 keeper 被换版后
        就是这种状态），自行收摊退出，等下一次 boot 再起。
    """
    global rescues, thread
    idle = 0
    while not stop:
        sleep_sliced(_WD_INTERVAL)
        if stop:
            return
        if not _generation_valid():
            idle += 1
            if idle >= 2:
                return
            continue
        idle = 0
        if _watcher_alive():
            continue
        with lock:
            t = _adopt()
            if t is None:
                t = threading.Thread(target=watch_loop, name=WATCHER_NAME, daemon=True)
                t.start()
            thread = t
            rescues += 1
        logger.warning("[FeishuModelPicker] watcher 已死，看门狗重新拉起（第 %d 次）", rescues)


def boot(mod) -> int:
    """交班 + 确保线程在位。微秒级返回（插件加载有 10 秒硬超时，这里绝不等待）。

    返回本次交班的代际令牌，交给 ``on_unload`` 回调做代际感知的停止。
    """
    global stop, generation, module_name, token, thread, watchdog, exit_reason
    with lock:
        stop = False
        exit_reason = ""
        generation = mod
        module_name = getattr(mod, "__name__", "") or module_name
        token += 1
        my_token = token
        if not _watcher_alive():
            t = _adopt()
            if t is None:
                t = threading.Thread(target=watch_loop, name=WATCHER_NAME, daemon=True)
                t.start()
            thread = t
        if not _watchdog_alive():
            wd = threading.Thread(target=watchdog_loop, name=WATCHDOG_NAME, daemon=True)
            watchdog = wd
            wd.start()
    return my_token


def request_stop(my_token: int) -> None:
    """代际感知的停止：只有「当前代」的卸载回调才能停线程，且要等过交班窗口。

    热重载的顺序是 unload（dispose 旧注册）→ load（新代 register）。若在 unload 当场就置
    ``stop``，两条线程可能恰好在交班前退出，于是每次重载都白换一条线程。这里改成
    **延迟确认**：1 秒内若有新代交班（token 变了），说明只是热重载，什么都不做；
    否则才是真的卸载/禁用，停线程。
    """
    def _confirm() -> None:
        global stop
        time.sleep(_STOP_CONFIRM)
        with lock:
            if my_token == token:
                stop = True

    threading.Thread(target=_confirm, name="fmp-stop-confirm", daemon=True).start()


def status() -> dict:
    """诊断快照（给插件模块的诊断串用）。"""
    mod = generation
    return {
        "watcher": _watcher_alive(),
        "watchdog": _watchdog_alive(),
        "rescues": rescues,
        "token": token,
        "exit_reason": exit_reason,
        "generation": getattr(mod, "__name__", "") if mod is not None else "",
    }
