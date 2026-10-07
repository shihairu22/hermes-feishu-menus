/* 飞书控制台 · 铺悬浮菜单（读 → 写 → 回读复核）
 *
 * 用法（由你的 AI 助手在**已登录的** open.feishu.cn 应用管理页执行）：
 *   1) 打开  https://open.feishu.cn/app/<你的 clientId>/...  （URL 里必须带 cli_ 开头的 app id）
 *   2) 把本文件整体贴进页面的 JS 执行入口（控制台/DevTools/浏览器的 js 执行工具）
 *   3) 返回的 JSON 里 afterGroups / afterLeaves 应与 menu.json 一致
 *
 * 下面 `const MENU =` 处的占位符会被 scripts/build-console-snippet.py 自动替换成
 * menu.json 的内容；也可以自己手动把 menu.json 的内容粘进去（注意保持合法 JSON）。
 */
(async () => {
  const CID = (location.pathname.match(/(cli_[A-Za-z0-9]+)/) || [])[1];
  if (!CID) return 'ERR_NO_CLIENT_ID: 请先打开应用管理页（URL 形如 /app/cli_xxxx/...）再执行';

  const MENU = __MENU_JSON__;

  const post = async (url, body) => {
    const r = await fetch(url, {
      method: 'POST',
      headers: {
        'content-type': 'application/json;charset=UTF-8',
        'x-csrf-token': window.csrfToken || '',
        'X-Requested-With': 'XMLHttpRequest'
      },
      body: JSON.stringify(body)
    });
    return await r.text();
  };

  const summarize = (txt) => {
    try {
      const j = JSON.parse(txt);
      const d = j.data || {};
      const cfg = d.botMenuConfig || [];
      return {
        code: j.code,
        groups: cfg.map(g => g.defaultName),
        leaves: cfg.reduce((n, g) => n + ((g.childNodes || []).length), 0)
      };
    } catch (e) {
      return { parse_error: String(e), raw: String(txt).slice(0, 300) };
    }
  };

  // 1) 先读（留底，便于回滚）
  const before = await post('/developers/v1/robot/' + CID, {});

  // 2) 写。注意：body 只包 {menu:{...}}，且 menu 里必须带完整 botMenuConfig
  const write = await post('/developers/v1/robot/update_changed/' + CID, { menu: MENU });

  // 3) 回读复核
  const after = await post('/developers/v1/robot/' + CID, {});

  return JSON.stringify({
    clientId: CID,
    before: summarize(before),
    write_result: String(write).slice(0, 400),
    after: summarize(after)
  }, null, 1);
})()
