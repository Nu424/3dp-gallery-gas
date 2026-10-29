// getThumbnails（スマホで読めなかった画像を data URL で返す）のテスト
'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { setupEnv, plain } = require('./fakes');

const META = JSON.stringify({ author: '山田', purpose: '固定具', status: '使用中', tags: [] });
const b64 = (s) => Buffer.from(s, 'utf8').toString('base64');
const thumbUrl = (name) => 'data:image/png;base64,' + b64('thumb-of-' + name);

/**
 * 作品フォルダを1つ作り、ファイルIDを名前で引けるようにして返す。
 * files: { 名前: addFile の opts }
 */
function addItem(env, name, files, meta = META) {
  const folder = env.drive.addFolder(name, env.itemsId);
  if (meta !== null) env.drive.addFile(folder, 'meta.json', meta);
  const ids = {};
  Object.keys(files).forEach((n) => { ids[n] = env.drive.addFile(folder, n, files[n].content || 'img-' + n, files[n]); });
  return ids;
}

const call = (env, ids, large) => plain(env.ctx.getThumbnails(ids, large));

// ---------------------------------------------------------------------------
test('getThumbnails：縮小画像を data URL で返す。写真も読める', () => {
  const env = setupEnv();
  const a = addItem(env, '20250101_a', { 'thumb.png': {}, 'photo_1.jpg': {} });
  env.ctx.syncNow();
  const r = call(env, [a['thumb.png'], a['photo_1.jpg']]);
  assert.deepEqual(r, { [a['thumb.png']]: thumbUrl('thumb.png'), [a['photo_1.jpg']]: thumbUrl('photo_1.jpg') });
  assert.deepEqual(env.drive.byteReads, []); // 元のファイルは読まない
});

test('getThumbnails：large は 2MB 以下なら元のファイル、超えたら縮小画像', () => {
  const env = setupEnv();
  const a = addItem(env, '20250101_a', { 'thumb.jpg': { content: 'jpeg-body' }, 'photo_big.jpg': { size: 2 * 1024 * 1024 + 1 } });
  env.ctx.syncNow();
  const r = call(env, [a['thumb.jpg'], a['photo_big.jpg']], true);
  assert.equal(r[a['thumb.jpg']], 'data:image/jpeg;base64,' + b64('jpeg-body'));
  assert.equal(r[a['photo_big.jpg']], thumbUrl('photo_big.jpg'));
  assert.deepEqual(env.drive.byteReads, [a['thumb.jpg']]);
});

test('getThumbnails：取れない件だけ null（縮小画像なし・読み込み失敗・一覧に無いID・要対応の作品）', () => {
  const env = setupEnv();
  const a = addItem(env, '20250101_a', { 'thumb.png': {}, 'photo_none.png': { thumbnail: null }, 'photo_err.png': {}, 'base.stl': {} });
  const bad = addItem(env, '20250102_b', { 'thumb.png': {} }, JSON.stringify({ author: '', purpose: '', status: '' }));
  env.ctx.syncNow();
  env.drive.getByIdErrors[a['photo_err.png']] = 'Service error: Drive';
  const r = call(env, [a['thumb.png'], a['photo_none.png'], a['photo_err.png'], a['base.stl'], bad['thumb.png'], 'nosuchid']);
  assert.deepEqual(r, {
    [a['thumb.png']]: thumbUrl('thumb.png'),
    [a['photo_none.png']]: null,
    [a['photo_err.png']]: null,
    [a['base.stl']]: null,     // 画像として一覧に出していないファイルは読まない
    [bad['thumb.png']]: null,  // 要対応の作品の画像も読まない
    nosuchid: null
  });
  assert.equal(env.drive.thumbReads.includes(a['base.stl']), false);
  assert.equal(env.drive.thumbReads.includes(bad['thumb.png']), false);
  assert.equal(env.logs.length, 1); // 失敗はログに残す
});

test('getThumbnails：1回10件まで。ID らしくない値と重複は除く。空や配列以外は空のオブジェクト', () => {
  const env = setupEnv();
  const files = {};
  for (let i = 0; i < 12; i++) files['photo_' + String(i).padStart(2, '0') + '.png'] = {};
  const a = addItem(env, '20250101_a', files);
  env.ctx.syncNow();
  const ids = Object.values(a);
  const r = call(env, [ids[0], ids[0], '../x', 123, null].concat(ids.slice(1)));
  assert.deepEqual(Object.keys(r), ids.slice(0, 10));
  assert.equal(env.drive.thumbReads.length, 10);
  assert.deepEqual(call(env, []), {});
  assert.deepEqual(call(env, 'abc'), {});
  assert.deepEqual(call(env, undefined), {});
});

test('getThumbnails：6時間キャッシュし、2回目は Drive を読まない（縮小と large は別）', () => {
  const env = setupEnv();
  const a = addItem(env, '20250101_a', { 'thumb.png': {} });
  env.ctx.syncNow();
  const id = a['thumb.png'];
  const first = call(env, [id]);
  assert.equal(env.drive.thumbReads.length, 1);
  assert.deepEqual(env.cache.state.puts, [{ values: { ['thumb:S:' + id]: first[id] }, sec: 21600 }]);

  assert.deepEqual(call(env, [id]), first);
  assert.equal(env.drive.thumbReads.length, 1);

  call(env, [id], true); // large は別のキー
  assert.deepEqual(env.drive.byteReads, [id]);
  assert.equal(env.cache.state.store.has('thumb:L:' + id), true);
});

test('getThumbnails：100KB を超える data URL はキャッシュしない。キャッシュが壊れていても返す', () => {
  const env = setupEnv();
  const big = 'x'.repeat(90 * 1024); // base64 にすると 100KB を超える
  const a = addItem(env, '20250101_a', { 'thumb.png': { content: big, size: big.length }, 'photo_s.png': {} });
  env.ctx.syncNow();
  const r = call(env, [a['thumb.png'], a['photo_s.png']], true);
  assert.ok(r[a['thumb.png']].length > 100000);
  assert.deepEqual([...env.cache.state.store.keys()], ['thumb:L:' + a['photo_s.png']]);

  env.cache.state.failGet = true;
  assert.equal(call(env, [a['photo_s.png']], true)[a['photo_s.png']], r[a['photo_s.png']]);
});

test('getThumbnails：シートが無ければすべて null', () => {
  const env = setupEnv();
  const a = addItem(env, '20250101_a', { 'thumb.png': {} });
  assert.deepEqual(call(env, [a['thumb.png']]), { [a['thumb.png']]: null });
  assert.equal(env.drive.thumbReads.length, 0);
});
