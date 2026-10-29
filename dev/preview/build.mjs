// プレビューのビルド（Node v20、依存なし）。
// tools/gas/index.html の include('guide') を guide.html で置き換え、
// google.script.run の偽物（サンプルデータを返す）を注入して dev/preview/out/index.html を出す。
// 使い方：node dev/preview/build.mjs
// 場面の切り替え：out/index.html?scenario=empty | error | partial | syncfail | readonly（canSync:false）| status（未知の状態あり）
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { SAMPLE_DATA } from './sample-data.js';

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
  const scenario = new URLSearchParams(location.search).get('scenario') || '';
  const wait = (ms, fn) => setTimeout(fn, ms);
  if (scenario === 'readonly') DATA.canSync = false;
  if (scenario === 'status') { DATA.statuses = ['使用中', '参考', '引退', '検討中']; DATA.items[1].status = '検討中'; }
  const impl = {
    getGalleryData(ok, fail) {
      wait(700, () => {
        if (scenario === 'error') return fail(new Error('スプレッドシートを開けませんでした（プレビュー用の疑似エラー）'));
        if (scenario === 'empty') return ok({ syncedAt: null, sheetUrl: DATA.sheetUrl, items: [], issues: [] });
        ok(JSON.parse(JSON.stringify(DATA)));
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
