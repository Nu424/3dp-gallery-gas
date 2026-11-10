// 関連リンク（links シート）のテスト：URL への変換、行の読み方、setup での用意、getGalleryData の links
'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { setupEnv, plain } = require('./fakes');

test('linkTargetUrl：URL はそのまま、Drive の ID は open?id=、それ以外は空', () => {
  const { ctx } = setupEnv();
  assert.equal(ctx.linkTargetUrl('https://docs.google.com/document/d/1AbCdEf/edit'), 'https://docs.google.com/document/d/1AbCdEf/edit');
  assert.equal(ctx.linkTargetUrl('  http://example.com/a  '), 'http://example.com/a');
  assert.equal(ctx.linkTargetUrl('1AbCdEfGhIjKlMn_-'), 'https://drive.google.com/open?id=1AbCdEfGhIjKlMn_-');
  assert.equal(ctx.linkTargetUrl('javascript:alert(1)'), '');
  assert.equal(ctx.linkTargetUrl('short'), '');
  assert.equal(ctx.linkTargetUrl(''), '');
  assert.equal(ctx.linkTargetUrl(null), '');
  assert.equal(ctx.linkTargetUrl('https://example.com/a b'), '');
});

test('parseLinkRows：決まった key は1つずつ、知らない key はその他、URL にならない行は捨てる', () => {
  const { ctx } = setupEnv();
  const out = plain(ctx.parseLinkRows([
    ['manual', '', 'https://docs.google.com/document/d/1AbCdEf/edit', ''],
    ['Manual', '別の説明書', 'https://example.com/2', ''],          // 同じ key の2行目は使わない（大文字小文字は区別しない）
    ['', '印刷のルール', 'https://example.com/print', 'メモ'],
    ['printer', 'プリンターの予約', '1AbCdEfGhIjK', ''],              // 知らない key はその他
    ['fusion', 'Fusion', '', ''],                                     // target が空
    ['repo', 'GitHub', 'javascript:alert(1)', ''],                    // URL でない
  ]));
  assert.deepEqual(out, [
    { key: 'manual', label: '使い方の説明書', url: 'https://docs.google.com/document/d/1AbCdEf/edit' },
    { key: '', label: '印刷のルール', url: 'https://example.com/print' },
    { key: '', label: 'プリンターの予約', url: 'https://drive.google.com/open?id=1AbCdEfGhIjK' },
  ]);
});

/** 3Dギャラリー/tools/docs と tools/fusion_export、items/_template を置く */
function addToolsTree(env) {
  // 本物の Drive の ID は長い（linkTargetUrl は10文字以上を ID とみなす）。偽物の ID も長くする
  const shortId = env.drive.newId.bind(env.drive);
  env.drive.newId = (prefix) => shortId(prefix) + 'AbCdEfGh';
  const root = env.drive.nodes.get(env.itemsId).parents[0];
  const tools = env.drive.addFolder('tools', root);
  const docs = env.drive.addFolder('docs', tools);
  const readme = env.drive.addFile(docs, 'README.md', '# readme');
  const operation = env.drive.addFile(docs, 'OPERATION.md', '# op');
  const fusion = env.drive.addFolder('fusion_export', tools);
  const template = env.drive.addFolder('_template', env.itemsId);
  return { readme, operation, fusion, template };
}

test('setup：links シートを作り、Drive で見つけた場所を初期値に書く', () => {
  const env = setupEnv();
  const ids = addToolsTree(env);
  const msg = env.ctx.setup();
  assert.match(msg, /シート「links」：6行を足しました/);
  const sheet = env.ss.getSheetByName('links');
  assert.deepEqual(sheet.cells[0], ['key', 'label', 'target', 'memo']);
  const byKey = {};
  sheet.cells.slice(1).forEach((r) => { byKey[r[0]] = r[2]; });
  assert.deepEqual(byKey, {
    manual: ids.readme, admin: ids.operation, fusion: ids.fusion, template: ids.template, items: env.itemsId, repo: '',
  });

  // getGalleryData の links：target が空の repo は出ない。items は（偽物の ID が短く URL にならないので）
  // ITEMS_FOLDER_ID からの予備が末尾に付く
  const data = plain(env.ctx.getGalleryData());
  assert.deepEqual(data.links.map((l) => l.key), ['manual', 'admin', 'fusion', 'template', 'items']);
  assert.equal(data.links[0].url, 'https://drive.google.com/open?id=' + ids.readme);
});

test('setup をもう一度実行しても、書き換えた行は上書きせず、消した key の行だけ足す', () => {
  const env = setupEnv();
  addToolsTree(env);
  env.ctx.setup();
  const sheet = env.ss.getSheetByName('links');
  sheet.cells[1][2] = 'https://docs.google.com/document/d/1AbCdEf/edit';   // manual を Google ドキュメントに
  sheet.cells.splice(6, 1);                                                 // repo の行を消す
  sheet.cells.push(['', '印刷のルール', 'https://example.com/print', '']);
  const msg = env.ctx.setup();
  assert.match(msg, /シート「links」：1行を足しました/);
  assert.equal(sheet.cells[1][2], 'https://docs.google.com/document/d/1AbCdEf/edit');
  assert.deepEqual(sheet.cells[sheet.cells.length - 1].slice(0, 2), ['repo', 'ソースコード（GitHub）']);
  assert.match(env.ctx.setup(), /シート「links」：確認しました/);
});

test('setup：tools が無くても止まらず、見つからないものは空で書く', () => {
  const env = setupEnv();
  env.ctx.setup();
  const byKey = {};
  env.ss.getSheetByName('links').cells.slice(1).forEach((r) => { byKey[r[0]] = r[2]; });
  assert.equal(byKey.manual, '');
  assert.equal(byKey.fusion, '');
  assert.equal(byKey.template, '');
  assert.equal(byKey.items, env.itemsId);
});

test('getGalleryData：links シートが無くても items フォルダのリンクは出る', () => {
  const env = setupEnv();
  const data = plain(env.ctx.getGalleryData());
  assert.deepEqual(data.links, [{ key: 'items', label: 'items フォルダ', url: 'https://drive.google.com/drive/folders/' + env.itemsId }]);
});

test('getGalleryData：links シートが読めなくても一覧は返す', () => {
  const env = setupEnv();
  env.ctx.setup();
  const realGet = env.ss.getSheetByName.bind(env.ss);
  env.ss.getSheetByName = (name) => { if (name === 'links') throw new Error('Service error'); return realGet(name); };
  const data = plain(env.ctx.getGalleryData());
  assert.equal(data.links.length, 1);
  assert.equal(data.links[0].key, 'items');
});
