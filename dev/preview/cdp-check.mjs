// ヘッドレス Chrome を DevTools プロトコル（CDP）で動かし、プレビューの状態を実時間で調べる（Node v20、依存なし）。
// --virtual-time-budget では IntersectionObserver の通知が最初の数回しか届かず、スクロール後や
// 描き直し後の画像の頼み方を確かめられないため、こちらを使う。
// 使い方：node --experimental-websocket dev/preview/cdp-check.mjs "<index.html のクエリ。& の代わりに ; でもよい>" [幅,高さ] [待つミリ秒] [スクショ.png]
//   例  node --experimental-websocket dev/preview/cdp-check.mjs "scenario=many;view=list;scroll=bottom" 1400,900 4000 out/shots/x.png
// 出力（JSON）：getThumbnails の呼び出し（data-thumb-calls）、同時実行の最大、待っている画像の数、blob: の画像の数など。
// 例  THEN="document.querySelector('.card:nth-child(3)').click()" node --experimental-websocket dev/preview/cdp-check.mjs "scenario=many"
// 環境変数 PAGE で out/ の別のページを開ける（例 PAGE=frame-390.html で "src=scenario%3Dmany"。このとき数値は iframe の外なので空）
// drive.google.com は 127.0.0.1:9 に向けて、すぐ失敗させる（ネットワークの待ちで結果が揺れないように）。
import { spawn } from 'node:child_process';
import { mkdtempSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const [query = 'scenario=many', size = '1400,900', waitMs = '4000', shot] = process.argv.slice(2);
const [w, h] = size.split(',').map(Number);
const CHROME = process.env.CHROME || 'C:/Program Files/Google/Chrome/Application/chrome.exe';
const here = dirname(fileURLToPath(import.meta.url));
// Windows では node が .cmd 経由のことがあり、& が cmd に解釈されるので、区切りは ; でもよい（& に直す）
const page = pathToFileURL(join(here, 'out', process.env.PAGE || 'index.html')).href + '?' + query.replace(/;/g, '&');
const port = 9300 + Math.floor(Math.random() * 500);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const chrome = spawn(CHROME, ['--headless=new', '--disable-gpu', '--remote-debugging-port=' + port,
  '--user-data-dir=' + mkdtempSync(join(tmpdir(), 'cdp-')), '--host-resolver-rules=MAP drive.google.com 127.0.0.1:9',
  '--window-size=' + w + ',' + h, 'about:blank'], { stdio: 'ignore' });
try {
  let targets;
  for (let i = 0; i < 50 && !targets; i++) {
    try { targets = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json(); } catch (_) { await sleep(100); }
  }
  const ws = new WebSocket(targets.find((t) => t.type === 'page').webSocketDebuggerUrl);
  await new Promise((r) => ws.addEventListener('open', r, { once: true }));
  let seq = 0;
  const waiting = new Map();
  ws.addEventListener('message', (ev) => {
    const m = JSON.parse(ev.data);
    if (m.id && waiting.has(m.id)) { waiting.get(m.id)(m); waiting.delete(m.id); }
  });
  const send = (method, params = {}) => new Promise((r) => { const id = ++seq; waiting.set(id, r); ws.send(JSON.stringify({ id, method, params })); });
  await send('Page.enable');
  await send('Page.navigate', { url: page });
  await sleep(Number(waitMs));
  // 環境変数 THEN に JS を書くと、待った後にそれを実行し、もう一度同じだけ待つ（描き直し・スクロールの後を調べる用）
  if (process.env.THEN) { await send('Runtime.evaluate', { expression: process.env.THEN }); await sleep(Number(waitMs)); }
  const res = await send('Runtime.evaluate', { returnByValue: true, expression: `(() => {
    const d = document.documentElement.dataset;
    const imgs = [...document.querySelectorAll('img')];
    return {
      calls: JSON.parse(d.thumbCalls || '[]'),
      maxParallel: Number(d.thumbMaxParallel || 0),
      vh: innerHeight,
      scroll: d.scroll ? JSON.parse(d.scroll) : null,
      note: d.note ? JSON.parse(d.note) : undefined,   // THEN の中で document.documentElement.dataset.note に JSON を入れると出る
      waiting: imgs.filter((i) => i.dataset.wait).map((i) => i.dataset.key),
      blobImgs: imgs.filter((i) => (i.getAttribute('src') || '').startsWith('blob:')).length,
      dataImgsFromServer: imgs.filter((i) => /^data:image\\/[^,]*;base64,/.test(i.getAttribute('src') || '')).length,
      hero: (() => { const i = document.querySelector('.hero img'); return i ? { key: i.dataset.key, src: (i.getAttribute('src') || '').slice(0, 30), wait: !!i.dataset.wait, ok: i.complete && i.naturalWidth > 0 } : (document.querySelector('.hero svg') ? 'icon' : null); })()
    };
  })()` });
  const v = res.result.result.value || { calls: [] };
  console.log(JSON.stringify({ ...v, calls: undefined }));
  v.calls.forEach((c, i) => console.log(`  call${i + 1} ${c.large ? "L" : "S"} ` + c.ids.map((id, j) => id.replace("preview-", "") + "@" + c.tops[j]).join(" ")));
  if (shot) {
    const img = await send('Page.captureScreenshot', { format: 'png' });
    writeFileSync(resolve(shot), Buffer.from(img.result.data, 'base64'));
  }
  ws.close();
} finally {
  chrome.kill();
}
