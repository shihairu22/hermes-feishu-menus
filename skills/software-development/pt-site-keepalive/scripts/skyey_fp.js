// 天雪 skfaid（FingerprintJS Pro v3.3.0）本地求值：Node 里跑它自己的 JS 生成真 token。
// 指纹组件里的浏览器特性用合理常量桩；采集不到的组件会自动记为 error（服务端无法核验真伪）。
// 用法：node /tmp/skyey_fp.js
const fs = require('fs');
const vm = require('vm');

const path = require('path');
const CANDIDATES = [
  path.join(__dirname, 'skyey_skfaid.js'),   // 技能目录持久副本（唯一来源）
];
let code = null;
for (const p of CANDIDATES) {
  try { code = fs.readFileSync(p, 'utf8'); break; } catch (e) {}
}
if (!code) {
  console.error('BUNDLE_MISSING: 未找到 skfaid.js（先让 skyey_http.py --stage1 抓取或补一份 skyey_skfaid.js）');
  process.exit(1);
}

const ua = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36';

function makeStorage() {
  const m = {};
  return {
    getItem: k => (k in m ? m[k] : null),
    setItem: (k, v) => { m[k] = String(v); },
    removeItem: k => { delete m[k]; },
    clear: () => { for (const k of Object.keys(m)) delete m[k]; },
    key: i => Object.keys(m)[i] ?? null,
    get length() { return Object.keys(m).length; },
  };
}

const canvasStub = () => ({
  width: 300, height: 150, style: {}, getContext: () => null,
  toDataURL: () => 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==',
  addEventListener() {}, removeEventListener() {},
});

const documentStub = {
  createElement(tag) {
    if (String(tag).toLowerCase() === 'canvas') return canvasStub();
    if (String(tag).toLowerCase() === 'video') return { canPlayType: () => 'probably', style: {} };
    if (String(tag).toLowerCase() === 'audio') return { canPlayType: () => 'probably', style: {} };
    return { style: {}, setAttribute() {}, appendChild() {}, append() {}, remove() {}, addEventListener() {} };
  },
  createElementNS() { return this.createElement('div'); },
  documentElement: { style: {}, getAttribute: () => null, addEventListener() {} },
  body: { appendChild() {}, append() {}, style: {} },
  head: { appendChild() {} },
  cookie: '',
  referrer: '',
  title: '登录 - 天雪',
  addEventListener() {}, removeEventListener() {},
  querySelector: () => null, querySelectorAll: () => [],
  fonts: { check: () => true, status: 'loaded', ready: Promise.resolve(), addEventListener() {} },
  visibilityState: 'visible',
  hidden: false,
  createTextNode: t => ({ textContent: t }),
};

const windowStub = {};
const sandbox = {
  console,
  setTimeout, clearTimeout, setInterval, clearInterval,
  TextEncoder, TextDecoder, URL, URLSearchParams,
  fetch: () => Promise.reject(new Error('no fetch')),
  atob: s => Buffer.from(s, 'base64').toString('binary'),
  btoa: s => Buffer.from(s, 'binary').toString('base64'),
  performance: { now: () => Date.now() % 1e6, timeOrigin: Date.now(), memory: {} },
  requestIdleCallback: cb => setTimeout(() => cb({ timeRemaining: () => 5, didTimeout: false }), 0),
  requestAnimationFrame: cb => setTimeout(() => cb(Date.now()), 16),
  navigator: {
    userAgent: ua,
    platform: 'Win32',
    language: 'zh-CN',
    languages: ['zh-CN', 'zh', 'en'],
    hardwareConcurrency: 8,
    deviceMemory: 8,
    vendor: 'Google Inc.',
    vendorSub: '',
    productSub: '20030107',
    webdriver: false,
    plugins: { length: 0, item: () => null, namedItem: () => null },
    mimeTypes: { length: 0, item: () => null, namedItem: () => null },
    pdfViewerEnabled: true,
    maxTouchPoints: 0,
    cookieEnabled: true,
    onLine: true,
  },
  screen: { width: 1920, height: 1080, colorDepth: 24, pixelDepth: 24, availWidth: 1920, availHeight: 1040, availLeft: 0, availTop: 0, orientation: { type: 'landscape-primary', angle: 0 } },
  location: { href: 'https://www.skyey2.com/member.php?mod=logging&action=login', protocol: 'https:', host: 'www.skyey2.com', hostname: 'www.skyey2.com', pathname: '/member.php', search: '?mod=logging&action=login', hash: '', origin: 'https://www.skyey2.com' },
  history: { length: 2, state: null, pushState() {}, replaceState() {} },
  localStorage: makeStorage(),
  sessionStorage: makeStorage(),
  indexedDB: undefined,
  openDatabase: undefined,
  document: documentStub,
  screenOrientation: { type: 'landscape-primary', angle: 0 },
  devicePixelRatio: 1,
  innerWidth: 1920, innerHeight: 969, outerWidth: 1920, outerHeight: 1040,
  matchMedia: q => ({ matches: false, media: q, addListener() {}, removeListener() {}, addEventListener() {}, removeEventListener() {} }),
  getComputedStyle: () => ({ getPropertyValue: () => '' }),
  Notification: undefined,
  AudioContext: undefined,
  OfflineAudioContext: undefined,
  webkitOfflineAudioContext: undefined,
  chrome: { runtime: {} },
  evaluationMode: 1,
};

sandbox.window = sandbox;
sandbox.self = sandbox;
sandbox.globalThis = sandbox;
sandbox.top = sandbox;
sandbox.parent = sandbox;
sandbox.frames = sandbox;
sandbox.windowStub = windowStub;

const ctx = vm.createContext(sandbox);
try {
  vm.runInContext(code, ctx, { filename: 'skfaid.js' });
  const p = vm.runInContext('skfaid()', ctx);
  Promise.resolve(p).then(fp => fp.get()).then(res => {
    console.log(JSON.stringify({ skfaId: res.skfaId, version: res.version, confidence: res.confidence && res.confidence.score }, null, 1));
  }).catch(e => {
    console.error('GET_FP_FAIL:', e && (e.stack || e.message || e));
    process.exit(1);
  });
} catch (e) {
  console.error('EVAL_FAIL:', e && (e.stack || e.message || e));
  process.exit(1);
}
