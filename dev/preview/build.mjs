// プレビューのビルド（Node v20、依存なし）。
// tools/gas/index.html の include('guide') を guide.html で置き換え、
// google.script.run の偽物（サンプルデータを返す）を注入して dev/preview/out/index.html を出す。
// 使い方：node dev/preview/build.mjs
// 場面の切り替え：out/index.html?scenario=empty | error | partial | syncfail | readonly（canSync:false）| status（未知の状態あり）
//                 | many（作品30件）| thumbfail（getThumbnails が失敗する）
//                 | heic（作品30件。large=true の返事がブラウザで表示できない画像 → 画面は S で頼み直す）
// プレビュー専用の指定（ヘッドレス Chrome の --screenshot で、操作した後の状態を撮るため）：
//   &view=list|gallery    読み込み後に表示方法を切り替える
//   &select=<folderId>    読み込み後にその作品を選ぶ
//   &click=<CSSセレクタ>  読み込み後にその要素を押す（例 .card .tag で、カードの中のタグを押す）
//   &scroll=end           一覧の最後の作品が見えるところまでスクロールする（PC は一覧の枠、スマホ幅はページ）
//   &blobfail=1           URL.createObjectURL が壊れた blob: の URL を返す（本物の GAS で blob: が表示できない場合の再現）
//   &scroll=bottom        一覧の枠とページを、どちらも一番下までスクロールする
// 撮るときは --virtual-time-budget=5000 を付ける（読み込みの待ち時間を進めるため）。
// getThumbnails の呼び出しは <html data-thumb-calls="[...]"> に残す（--dump-dom で確かめる用）。
//   各呼び出しは { ids, large, tops }。tops は呼ばれた時点での、その画像の <img> の上端の位置（画面の上から。px）。
//   あわせて data-thumb-max-parallel（同時に返事待ちだった最大数）と data-thumb-vh（画面の高さ）を残す。
// 実時間での確かめ（IntersectionObserver を含む）は dev/preview/cdp-check.mjs（使い方はそのファイルの先頭）。
// あわせて out/frame-390.html（390px 幅の iframe に入れて撮るための入れ物）も出す。
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { SAMPLE_DATA, MORE_ITEMS } from './sample-data.js';

const here = dirname(fileURLToPath(import.meta.url));
const gasDir = join(here, '..', '..', 'tools', 'gas');
const indexHtml = readFileSync(join(gasDir, 'index.html'), 'utf8');
const guideHtml = readFileSync(join(gasDir, 'guide.html'), 'utf8');

// GAS のテンプレート構文 include('guide') を guide.html の中身に置き換える
const includeTag = "<?!= include('guide') ?>";
if (!indexHtml.includes(includeTag)) throw new Error('index.html に ' + includeTag + ' が見つかりません');
const withGuide = indexHtml.replace(includeTag, () => guideHtml);
// 置き換えのあとに GAS のテンプレート構文が残っていないこと
if (/<\?/.test(withGuide)) throw new Error('テンプレート構文 <? が残っています');

// google.script.run の偽物。場面は URL の ?scenario= で切り替える
const fake = `<script>
/* ===== プレビュー用の google.script.run（本番では GAS が提供する） ===== */
(function () {
  const DATA = ${JSON.stringify(SAMPLE_DATA).replace(/</g, '\\u003c')};
  const MORE = ${JSON.stringify(MORE_ITEMS).replace(/</g, '\\u003c')};
  const params = new URLSearchParams(location.search);
  const scenario = params.get('scenario') || '';
  const wait = (ms, fn) => setTimeout(fn, ms);
  if (scenario === 'many' || scenario === 'heic') DATA.items = DATA.items.concat(MORE);
  // サーバーで取り直した画像の代わり（どの画像か分かるように、IDの末尾と大きさを描く）
  // 本物のサーバーと同じく base64 の data URL で返す
  const serverThumb = (id, large) => 'data:image/svg+xml;base64,' + btoa(
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 240 180"><rect width="240" height="180" fill="#FBE9C8"/>' +
    '<rect x="10" y="10" width="220" height="160" rx="10" fill="none" stroke="#C98A1B" stroke-width="4" stroke-dasharray="10 6"/>' +
    '<text x="120" y="80" text-anchor="middle" font-size="26" font-family="sans-serif" fill="#7A5300">SERVER ' + (large ? 'L' : 'S') + '</text>' +
    '<text x="120" y="118" text-anchor="middle" font-size="16" font-family="sans-serif" fill="#7A5300">' + id.slice(-12) + '</text></svg>');
  // HEIC の代わり：ブラウザが表示できない画像（heic 場面の large=true の返事）
  const undisplayable = 'data:image/heic;base64,AAAAGGZ0eXBoZWljAAAAAG1pZjFoZWlj';
  const thumbCalls = [];
  let inFlight = 0, maxInFlight = 0;
  // 読み込み後の操作（プレビュー専用）。一覧を描いた後に1回だけ行う
  let applied = false;
  function applyPreviewParams() {
    if (applied) return; applied = true;
    const click = (sel) => { const el = document.querySelector(sel); if (el) el.click(); };
    if (params.get('view')) click('[data-view="' + params.get('view') + '"]');
    if (params.get('select')) click('[data-select="' + params.get('select') + '"]');
    if (params.get('click')) click(params.get('click'));   // 任意の要素を押す（CSS セレクタ）
    const scroll = params.get('scroll');
    if (!scroll) return;
    wait(50, () => {
      const main = document.getElementById('main');
      if (scroll === 'end') {
        const box = document.querySelector('.list, .grid');
        if (box && box.lastElementChild) box.lastElementChild.scrollIntoView({ block: 'end' });
      } else {
        main.scrollTop = main.scrollHeight;
        document.scrollingElement.scrollTop = document.scrollingElement.scrollHeight;
      }
      document.documentElement.dataset.scroll = JSON.stringify({ main: main.scrollTop, mainMax: main.scrollHeight - main.clientHeight, page: document.scrollingElement.scrollTop, pageMax: document.scrollingElement.scrollHeight - document.scrollingElement.clientHeight });
    });
  }
  if (params.get('blobfail')) {
    let n = 0;
    URL.createObjectURL = () => 'blob:null/preview-broken-' + (++n);   // 読めない blob: の URL
  }
  if (scenario === 'readonly') DATA.canSync = false;
  if (scenario === 'status') { DATA.statuses = ['使用中', '参考', '引退', '検討中']; DATA.items[1].status = '検討中'; }
  const impl = {
    getGalleryData(ok, fail) {
      wait(700, () => {
        if (scenario === 'error') return fail(new Error('スプレッドシートを開けませんでした（プレビュー用の疑似エラー）'));
        if (scenario === 'empty') return ok({ syncedAt: null, sheetUrl: DATA.sheetUrl, items: [], issues: [] });
        ok(JSON.parse(JSON.stringify(DATA)));
        wait(0, applyPreviewParams);
      });
    },
    getThumbnails(ok, fail, ids, large) {
      const tops = ids.map((id) => {
        const img = document.querySelector('img[data-key="' + id + (large ? ':L' : ':S') + '"]');
        return img ? Math.round(img.getBoundingClientRect().top) : null;
      });
      thumbCalls.push({ ids: ids, large: !!large, tops: tops });
      inFlight++; maxInFlight = Math.max(maxInFlight, inFlight);
      const root = document.documentElement.dataset;
      root.thumbCalls = JSON.stringify(thumbCalls);
      root.thumbMaxParallel = String(maxInFlight);
      root.thumbVh = String(innerHeight);
      wait(300, () => {
        inFlight--;
        if (scenario === 'thumbfail') return fail(new Error('画像を読み込めませんでした（プレビュー用の疑似エラー）'));
        const out = {};
        ids.slice(0, large ? 2 : 10).forEach((id) => {   // 本物と同じく、large は2件・縮小は10件まで
          out[id] = /nothumb/.test(id) ? null : scenario === 'heic' && large ? undisplayable : serverThumb(id, large);
        });
        ok(out);
      });
    },
    syncNow(ok, fail) {
      wait(1000, () => {
        if (scenario === 'syncfail') return fail(new Error('他の同期が実行中です。しばらくしてからやり直してください'));
        DATA.syncedAt = new Date().toISOString();
        if (scenario === 'partial') return ok({ done: false, message: '時間切れのため途中までです（5件を確認、1件を更新）。もう一度押すと続きから進みます' });
        ok({ done: true, message: '同期しました（8件を確認、0件を更新）' });
      });
    },
    resyncItem(ok, fail, folderId) {
      wait(1000, () => {
        if (scenario === 'syncfail') return fail(new Error('フォルダが見つかりません'));
        if (scenario === 'partial') return ok({ done: false, message: '時間切れのため読み直せませんでした' });
        if (folderId === 'id-fanduct-0722') {   // 要対応から一覧に移る
          DATA.issues = [];
          DATA.items.unshift({ folderId, folderName: '20260722_ファンダクト試作', folderUrl: 'https://example.com/preview/folder/fanduct', date: '2026-07-22', name: 'ファンダクト試作', author: '山田', purpose: 'ファンの吸気を整える', status: '使用中', tags: ['試作'], note: [], thumbUrl: null, photos: [], files: [] });
        }
        ok({ done: true, message: '同期しました（1件を確認、0件を更新）' });
      });
    }
  };
  function runner(ok, fail) {
    const r = {
      withSuccessHandler: (f) => runner(f, fail),
      withFailureHandler: (f) => runner(ok, f)
    };
    Object.keys(impl).forEach((name) => {
      r[name] = (...args) => impl[name](ok || (() => {}), fail || ((e) => console.error(e)), ...args);
    });
    return r;
  }
  window.google = { script: { run: runner() } };
})();
</script>
`;
const out = withGuide.replace('</head>', () => fake + '</head>');

const outDir = join(here, 'out');
mkdirSync(outDir, { recursive: true });
writeFileSync(join(outDir, 'index.html'), out, 'utf8');
console.log('出力しました：' + join(outDir, 'index.html') + '（' + out.length + ' 文字）');

// 390px 幅で撮るための入れ物。ヘッドレス Chrome はウィンドウをこの幅まで狭められないので iframe に入れる。
// 使い方：out/frame-390.html?src=<index.html に付けるクエリ>（例 ?src=scenario%3Dmany%26view%3Dlist）
//         ウィンドウは 420x900 程度で撮る。iframe の高さは &h= で変えられる（既定 844）
const frame = `<!doctype html>
<html lang="ja"><head><meta charset="utf-8"><title>390px プレビュー</title>
<style>body{margin:0;padding:8px;background:#555}iframe{display:block;width:390px;border:0;background:#fff}</style></head>
<body><iframe id="f" title="プレビュー"></iframe>
<script>
const p = new URLSearchParams(location.search);
const f = document.getElementById('f');
f.style.height = (p.get('h') || 844) + 'px';
f.src = 'index.html?' + (p.get('src') || '');
</script></body></html>
`;
writeFileSync(join(outDir, 'frame-390.html'), frame, 'utf8');
console.log('出力しました：' + join(outDir, 'frame-390.html'));
