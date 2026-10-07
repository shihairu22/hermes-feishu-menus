/* 飞书控制台 · 建版本并发布（自建应用免审核，版本状态立即变 2）
 *
 * 用法（由你的 AI 助手在**已登录的** open.feishu.cn 应用管理页执行，
 *       且必须在上一步 console-apply-menu.js 成功之后）：
 *   把本文件整体贴进页面的 JS 执行入口。返回的 published=true 才算成功。
 *
 * 版本号：默认自动取历史最大版本 +1（补丁位）；想指定就把下面 FORCED_VERSION 的
 *         占位符换成 '1.2.3'。说明文案同理，替换 CHANGELOG 的占位符。
 */
(async () => {
  const CID = (location.pathname.match(/(cli_[A-Za-z0-9]+)/) || [])[1];
  if (!CID) return 'ERR_NO_CLIENT_ID: 请先打开应用管理页（URL 形如 /app/cli_xxxx/...）再执行';

  const FORCED_VERSION = '__VERSION__';
  const CHANGELOG = '__CHANGELOG__';

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

  // ── 1) 读版本列表，推算下一个版本号 ─────────────────────────────
  let nextVer = FORCED_VERSION;
  if (!nextVer || nextVer.indexOf('__') === 0) {
    const listRaw = await post('/developers/v1/app_version/list/' + CID, {});
    let best = [0, 0, 0];
    try {
      const j = JSON.parse(listRaw);
      const vs = (j.data && j.data.versions) || [];
      vs.forEach(v => {
        const m = String(v.appVersion || '').match(/^(\d+)\.(\d+)\.(\d+)$/);
        if (!m) return;
        const t = [Number(m[1]), Number(m[2]), Number(m[3])];
        if (t[0] > best[0] || (t[0] === best[0] && (t[1] > best[1] || (t[1] === best[1] && t[2] > best[2])))) best = t;
      });
    } catch (e) { /* 列表读不到就退回 1.0.0 */ }
    nextVer = best[0] + '.' + best[1] + '.' + (best[2] + 1);
  }

  // ── 2) 建版本 ────────────────────────────────────────────────
  const create = await post('/developers/v1/app_version/create/' + CID, {
    clientId: CID,
    appVersion: nextVer,
    changeLog: CHANGELOG,
    remark: '',
    autoPublish: false,
    visibleSuggest: {},
    blackVisibleSuggest: {}
  });

  let vid = null;
  try {
    const j = JSON.parse(create);
    vid = (j.data && (j.data.versionId || j.data.id)) || null;
  } catch (e) { return 'CREATE_PARSE_ERR:' + String(create).slice(0, 300); }
  if (!vid) return 'CREATE_NO_VID:' + String(create).slice(0, 300);

  // ── 3) 提交发布 ──────────────────────────────────────────────
  const commit = await post('/developers/v1/publish/commit/' + CID + '/' + vid, {
    clientId: CID,
    versionId: String(vid),
    is_full_release: true
  });

  let isOk = null;
  try { isOk = JSON.parse(commit).data.isOk; } catch (e) { /* 忽略 */ }

  return JSON.stringify({
    clientId: CID,
    appVersion: nextVer,
    versionId: vid,
    published: isOk === true,
    commit_raw: String(commit).slice(0, 300)
  }, null, 1);
})()
