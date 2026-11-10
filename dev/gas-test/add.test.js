// 画面からの作品の追加（置き場・登録・片付け）のテスト
'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { setupEnv, plain } = require('./fakes');

const b64 = (s) => Buffer.from(s, 'utf8').toString('base64');
const FIELDS = { author: '山田', purpose: '流路セルを固定する', status: '使用中', tags: ['顕微鏡'], note: ['M3ネジ×4'] };
const kids = (env, id, kind) => env.drive.children(id, kind).filter((n) => !n.trashed);
const named = (env, name) => kids(env, env.itemsId, 'folder').find((n) => n.name === name);

/** 置き場を作って、ファイルを上げる。{ staging, ids: { 名前: ID } } */
function stage(env, names) {
  const staging = env.ctx.beginUpload().id;
  const ids = {};
  names.forEach((n) => { ids[n] = env.ctx.uploadItemFile(staging, n, '', b64('data-' + n)).id; });
  return { staging, ids };
}

// ---------------------------------------------------------------------------
test('cleanFolderLabel・uniqueFolderName・dedupeNames', () => {
  const { ctx } = setupEnv();
  assert.equal(ctx.cleanFolderLabel('  流路/セル:ホルダー  '), '流路_セル_ホルダー');
  assert.equal(ctx.cleanFolderLabel('a   b'), 'a b');
  assert.equal(ctx.cleanFolderLabel('あ'.repeat(100)).length, 80);
  assert.equal(ctx.cleanFolderLabel('   '), '');
  assert.equal(ctx.uniqueFolderName('20250612_a', ['x']), '20250612_a');
  assert.equal(ctx.uniqueFolderName('20250612_a', ['20250612_a', '20250612_a-v2']), '20250612_a-v3');
  assert.deepEqual(plain(ctx.dedupeNames(['base.stl', 'BASE.stl', 'base.stl', 'lid', 'lid'])), ['base.stl', 'BASE_2.stl', 'base_3.stl', 'lid', 'lid_2']);
});

test('beginUpload：items の直下に _up_ の置き場を作る（同期の対象外）', () => {
  const env = setupEnv();
  const { id } = plain(env.ctx.beginUpload());
  const node = env.drive.nodes.get(id);
  assert.match(node.name, /^_up_\d{14}_[a-z0-9]{1,4}$/);
  assert.deepEqual(node.parents, [env.itemsId]);
  env.ctx.syncNow();
  assert.equal(plain(env.ctx.getGalleryData()).items.length + plain(env.ctx.getGalleryData()).issues.length, 0);
});

test('置き場には同じ名前のファイルを上げられる（別のフォルダから来た base.stl など）', () => {
  const env = setupEnv();
  const { staging } = stage(env, ['base.stl']);
  assert.ok(env.ctx.uploadItemFile(staging, 'base.stl', '', b64('2')).id);
  assert.equal(kids(env, staging, 'file').length, 2);
});

test('registerItems：作業用フォルダに移し、名前を変え、meta.json を書いて、最後にフォルダ名を付ける', () => {
  const env = setupEnv();
  const { staging, ids } = stage(env, ['holder.f3d', 'base.stl', 'IMG_01.png']);
  const r = plain(env.ctx.registerItems(staging, [{
    key: 'g1', name: '流路セルホルダー', date: '2025-06-12', fields: FIELDS, extraMeta: { fusion_id: 'urn:x', author: '無視される' },
    files: [{ id: ids['holder.f3d'], name: 'holder.f3d' }, { id: ids['base.stl'], name: 'base.stl' }, { id: ids['IMG_01.png'], name: 'thumb.png' }],
  }]));
  assert.equal(r.results.length, 1);
  const res = r.results[0];
  assert.equal(res.ok, true, res.error);
  assert.equal(res.key, 'g1');
  assert.equal(res.folderName, '20250612_流路セルホルダー');
  assert.equal(res.entry.item.name, '流路セルホルダー');
  assert.equal(res.entry.item.author, '山田');
  assert.ok(res.entry.item.thumbUrl);
  const dir = named(env, '20250612_流路セルホルダー');
  assert.deepEqual(kids(env, dir.id, 'file').map((n) => n.name).sort(), ['base.stl', 'holder.f3d', 'meta.json', 'thumb.png']);
  const meta = JSON.parse(kids(env, dir.id, 'file').find((n) => n.name === 'meta.json').content);
  assert.equal(meta.fusion_id, 'urn:x');
  assert.equal(meta.author, '山田');
  assert.equal(kids(env, staging, 'file').length, 0);   // 置き場からは移った（送り直していない）
  assert.ok(env.drive.writes.some((w) => w[0] === 'move'));
  assert.ok(!env.drive.writes.some((w) => w[0] === 'copy'));
  // 一覧に出ている
  assert.equal(plain(env.ctx.getGalleryData()).items.length, 1);
  assert.equal(env.lock.state.held, false);
});

test('registerItems：同じフォルダ名があれば -v2。1つ失敗してもほかは登録する', () => {
  const env = setupEnv();
  env.drive.addFolder('20250612_ホルダー', env.itemsId);
  const { staging, ids } = stage(env, ['a.stl', 'b.stl']);
  const r = plain(env.ctx.registerItems(staging, [
    { key: 'g1', name: 'ホルダー', date: '2025-06-12', fields: FIELDS, files: [{ id: ids['a.stl'], name: 'a.stl' }] },
    { key: 'g2', name: 'ふた', date: '2025-02-31', fields: FIELDS, files: [{ id: ids['b.stl'], name: 'b.stl' }] },
    { key: 'g3', name: 'ふた', date: '2025-02-01', fields: { ...FIELDS, purpose: '' }, files: [{ id: ids['b.stl'], name: 'b.stl' }] },
    { key: 'g4', name: '', date: '2025-02-01', fields: FIELDS, files: [{ id: ids['b.stl'], name: 'b.stl' }] },
    { key: 'g5', name: 'ふた', date: '2025-02-01', fields: FIELDS, files: [] },
  ]));
  assert.deepEqual(r.results.map((x) => [x.key, x.ok]), [['g1', true], ['g2', false], ['g3', false], ['g4', false], ['g5', false]]);
  assert.equal(r.results[0].folderName, '20250612_ホルダー-v2');
  assert.match(r.results[1].error, /実在しない日付/);
  assert.match(r.results[2].error, /説明に直すところがあります：「purpose」が空です/);
  assert.match(r.results[3].error, /名前を入れてください/);
  assert.match(r.results[4].error, /ファイルがありません/);
  assert.ok(kids(env, staging, 'file').some((n) => n.name === 'b.stl'));   // 失敗した分は置き場に残る
});

test('registerItems：置き場に無いファイル（よその作品のファイル）は使えない', () => {
  const env = setupEnv();
  const other = env.drive.addFolder('20250101_よそ', env.itemsId);
  const otherFile = env.drive.addFile(other, 'secret.stl', 'x');
  const { staging } = stage(env, []);
  const r = plain(env.ctx.registerItems(staging, [{ key: 'g1', name: 'a', date: '2025-01-02', fields: FIELDS, files: [{ id: otherFile, name: 'x.stl' }] }]));
  assert.equal(r.results[0].ok, false);
  assert.match(r.results[0].error, /上げたファイルが見つかりません/);
  assert.deepEqual(env.drive.nodes.get(otherFile).parents, [other]);
});

test('registerItems：同じ名前になるファイルは _2 を付ける。meta.json という名前は断る', () => {
  const env = setupEnv();
  const { staging, ids } = stage(env, ['x1', 'x2', 'x3']);
  const r = plain(env.ctx.registerItems(staging, [{ key: 'g1', name: 'a', date: '2025-01-02', fields: FIELDS, files: [{ id: ids.x1, name: 'base.stl' }, { id: ids.x2, name: 'base.stl' }] }]));
  assert.equal(r.results[0].ok, true);
  assert.deepEqual(r.results[0].entry.item.files.map((f) => f.name), ['base.stl', 'base_2.stl', 'meta.json']);
  const r2 = plain(env.ctx.registerItems(staging, [{ key: 'g2', name: 'b', date: '2025-01-02', fields: FIELDS, files: [{ id: ids.x3, name: 'meta.json' }] }]));
  assert.match(r2.results[0].error, /meta.json はファイルとしては登録できません/);
});

test('registerItems：移せない（投稿者）ときはコピーする。やり直しても二重にならない', () => {
  const env = setupEnv();
  const { staging, ids } = stage(env, ['a.stl', 'b.stl']);
  env.drive.denyWrite[ids['a.stl']] = 'Insufficient permissions for the specified parent.';   // 移動できない
  const work = { key: 'g1', name: 'a', date: '2025-01-02', fields: FIELDS, files: [{ id: ids['a.stl'], name: 'a.stl' }, { id: ids['b.stl'], name: 'b.stl' }] };
  const r = plain(env.ctx.registerItems(staging, [work]));
  assert.equal(r.results[0].ok, true, r.results[0].error);
  assert.ok(env.drive.writes.some((w) => w[0] === 'copy'));
  const dir = named(env, '20250102_a');
  assert.deepEqual(kids(env, dir.id, 'file').map((n) => n.name).sort(), ['a.stl', 'b.stl', 'meta.json']);
});

test('registerItems：途中で失敗した作品は _up_ のまま（一覧に出ない）。やり直すと続きから登録できる', () => {
  const env = setupEnv();
  const { staging, ids } = stage(env, ['a.stl', 'b.stl']);
  const work = { key: 'g1', name: 'a', date: '2025-01-02', fields: FIELDS, files: [{ id: ids['a.stl'], name: 'a.stl' }, { id: ids['b.stl'], name: 'b.stl' }] };
  env.drive.denyWrite[ids['b.stl']] = 'Service error: Drive';   // 権限ではない失敗（コピーに逃げない）
  const r = plain(env.ctx.registerItems(staging, [work]));
  assert.equal(r.results[0].ok, false);
  assert.match(r.results[0].error, /作品フォルダに書き込めませんでした/);
  const tmp = kids(env, env.itemsId, 'folder').find((n) => n.name.startsWith('_up_w_'));
  assert.ok(tmp);
  assert.deepEqual(kids(env, tmp.id, 'file').map((n) => n.name), ['a.stl']);
  env.ctx.nowMs = () => env.drive.clock;   // 偽物の時計に合わせる（置き場がまだ新しい＝同期で片付けない）
  env.ctx.syncNow();
  assert.equal(plain(env.ctx.getGalleryData()).items.length, 0);
  assert.equal(plain(env.ctx.getGalleryData()).issues.length, 0);
  delete env.drive.denyWrite[ids['b.stl']];
  const r2 = plain(env.ctx.registerItems(staging, [work]));
  assert.equal(r2.results[0].ok, true, r2.results[0].error);
  assert.equal(kids(env, env.itemsId, 'folder').filter((n) => n.name.startsWith('_up_w_')).length, 0);   // 同じ作業用フォルダを使った
});

test('registerItems：置き場でないフォルダは断る', () => {
  const env = setupEnv();
  const item = env.drive.addFolder('20250101_a', env.itemsId);
  assert.throws(() => env.ctx.registerItems(item, []), /このフォルダには書き込めません/);
});

test('discardUploadedFile・abandonUpload：置き場のファイル・置き場と作業用フォルダをゴミ箱へ。移せなくても失敗にしない', () => {
  const env = setupEnv();
  const { staging, ids } = stage(env, ['a.stl', 'b.stl']);
  assert.deepEqual(plain(env.ctx.discardUploadedFile(staging, ids['a.stl'])), { ok: true });
  assert.equal(env.drive.nodes.get(ids['a.stl']).trashed, true);
  env.drive.denyTrash[ids['b.stl']] = 'Insufficient permissions';
  assert.deepEqual(plain(env.ctx.discardUploadedFile(staging, ids['b.stl'])), { ok: false });
  const work = env.drive.addFolder(env.ctx.workFolderName_(staging, 'g1'), env.itemsId);
  const otherWork = env.drive.addFolder(env.ctx.workFolderName_('zzzzzzzzzz', 'g1'), env.itemsId);
  assert.deepEqual(plain(env.ctx.abandonUpload(staging)), { ok: true });
  assert.equal(env.drive.nodes.get(staging).trashed, true);
  assert.equal(env.drive.nodes.get(work).trashed, true);
  assert.equal(env.drive.nodes.get(otherWork).trashed, false);   // ほかの人の作業用フォルダは触らない
});

test('同期：1日以上たった _up_ のフォルダだけゴミ箱へ（ほかの _ のフォルダは触らない）', () => {
  const env = setupEnv();
  const old = env.ctx.beginUpload().id;
  const tpl = env.drive.addFolder('_template', env.itemsId);
  const created = env.drive.nodes.get(old).created;
  env.ctx.nowMs = () => created + 23 * 3600 * 1000;
  const fresh = env.ctx.beginUpload().id;
  env.drive.nodes.get(fresh).created = created + 22 * 3600 * 1000;   // 22時間あとに作った置き場
  env.ctx.syncNow();
  assert.equal(env.drive.nodes.get(old).trashed, false);
  env.ctx.nowMs = () => created + 25 * 3600 * 1000;
  env.ctx.syncNow();
  assert.equal(env.drive.nodes.get(old).trashed, true);
  assert.equal(env.drive.nodes.get(fresh).trashed, false);
  assert.equal(env.drive.nodes.get(tpl).trashed, false);
});
