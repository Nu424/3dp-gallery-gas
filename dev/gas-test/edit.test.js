// 画面からの編集（meta.json の書き換え・ファイルのゴミ箱・ファイルの追加）のテスト
'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { setupEnv, plain } = require('./fakes');

const META = (over = {}) => JSON.stringify({ author: '山田', purpose: '固定具', status: '使用中', tags: ['治具'], ...over });
const b64 = (s) => Buffer.from(s, 'utf8').toString('base64');

function addItem(env, name, { meta = META(), extra = [] } = {}) {
  const id = env.drive.addFolder(name, env.itemsId);
  if (meta !== null) env.drive.addFile(id, 'meta.json', meta);
  env.drive.addFile(id, 'base.stl', 'solid');
  extra.forEach((n) => env.drive.addFile(id, n, 'x'));
  return id;
}
const metaOf = (env, folderId) => {
  const f = env.drive.children(folderId, 'file').filter((n) => n.name === 'meta.json' && !n.trashed);
  assert.equal(f.length, 1);
  return JSON.parse(f[0].content);
};
const itemOf = (env, folderId) => plain(env.ctx.getGalleryData()).items.find((i) => i.folderId === folderId);
const issueOf = (env, folderId) => plain(env.ctx.getGalleryData()).issues.find((i) => i.folderId === folderId);
const FIELDS = { author: '佐藤', purpose: '流路セルを固定する', status: '参考', tags: ['顕微鏡', ' 治具 ', '顕微鏡', ''], note: ['M3ネジで固定。', '', '2行目\n3行目  '] };

// ---------------------------------------------------------------------------
test('cleanMetaFields：空白・空・重複を除き、note の改行は行に分ける。型の違うものは空', () => {
  const { ctx } = setupEnv();
  assert.deepEqual(plain(ctx.cleanMetaFields(FIELDS)), {
    author: '佐藤', purpose: '流路セルを固定する', status: '参考', tags: ['顕微鏡', '治具'], note: ['M3ネジで固定。', '2行目', '3行目'],
  });
  assert.deepEqual(plain(ctx.cleanMetaFields({ author: 1, tags: 'a', note: [1, 'x'] })), { author: '', purpose: '', status: '', tags: [], note: ['x'] });
  assert.deepEqual(plain(ctx.cleanMetaFields(null)), { author: '', purpose: '', status: '', tags: [], note: [] });
});

test('mergeMetaText：知らないキー（fusion_id）と並びを残し、無いキーは後ろに足す。検査は checkMeta', () => {
  const { ctx } = setupEnv();
  const r = plain(ctx.mergeMetaText({ fusion_id: 'urn:x', status: '使用中', author: '山田', extra: [1] }, FIELDS));
  assert.deepEqual(r.errors, []);
  assert.deepEqual(Object.keys(JSON.parse(r.text)), ['fusion_id', 'status', 'author', 'extra', 'purpose', 'tags', 'note']);
  assert.equal(JSON.parse(r.text).fusion_id, 'urn:x');
  assert.ok(r.text.endsWith('}\n'));
  assert.match(r.text, /\n {2}"author": "佐藤"/);   // 2文字の字下げ（人が読める形）
  const bad = plain(ctx.mergeMetaText({}, { author: '', purpose: 'p', status: '保管中' }));
  assert.deepEqual(bad.errors, ['「author」が空です', '「status」は 使用中 / 参考 / 引退 のどれかにしてください（今は「保管中」）']);
});

test('parseMetaObject：空は {}、壊れた JSON と { } でないものは null', () => {
  const { ctx } = setupEnv();
  assert.deepEqual(plain(ctx.parseMetaObject(null)), { obj: {}, error: '' });
  assert.deepEqual(plain(ctx.parseMetaObject('﻿{"a":1}')), { obj: { a: 1 }, error: '' });
  assert.equal(ctx.parseMetaObject('{').obj, null);
  assert.equal(ctx.parseMetaObject('[1]').obj, null);
});

test('cleanUploadName：使えない記号を _ に、長すぎる名前は拡張子を残して切る', () => {
  const { ctx } = setupEnv();
  assert.equal(ctx.cleanUploadName('a/b\\c:d*e?.stl'), 'a_b_c_d_e_.stl');
  assert.equal(ctx.cleanUploadName('  base.stl  '), 'base.stl');
  assert.equal(ctx.cleanUploadName('name...'), 'name');
  assert.equal(ctx.cleanUploadName('..'), '');
  assert.equal(ctx.cleanUploadName(''), '');
  const long = ctx.cleanUploadName('あ'.repeat(200) + '.stl');
  assert.equal(long.length, 120);
  assert.ok(long.endsWith('.stl'));
});

// ---------------------------------------------------------------------------
test('updateItemMeta：meta.json を書き換え、一覧に反映した item を返す（fusion_id は残る）', () => {
  const env = setupEnv();
  const id = addItem(env, '20250612_ホルダー', { meta: META({ fusion_id: 'urn:keep' }) });
  env.ctx.syncNow();
  const before = itemOf(env, id);
  const r = plain(env.ctx.updateItemMeta(id, FIELDS, before.fp));
  assert.equal(r.ok, true);
  assert.equal(r.message, '保存しました');
  assert.equal(r.entry.item.author, '佐藤');
  assert.deepEqual(r.entry.item.tags, ['顕微鏡', '治具']);
  assert.notEqual(r.entry.item.fp, before.fp);
  const meta = metaOf(env, id);
  assert.equal(meta.fusion_id, 'urn:keep');
  assert.deepEqual(meta.note, ['M3ネジで固定。', '2行目', '3行目']);
  assert.equal(itemOf(env, id).status, '参考');   // シートも新しい
  assert.equal(env.lock.state.held, false);
});

test('updateItemMeta：読んだあとに誰かが変えていたら、書かずに最新を返す（conflict）', () => {
  const env = setupEnv();
  const id = addItem(env, '20250612_ホルダー');
  env.ctx.syncNow();
  const fp = itemOf(env, id).fp;
  const metaId = env.drive.children(id, 'file').find((n) => n.name === 'meta.json').id;
  env.drive.setContent(metaId, META({ author: '鈴木' }));   // ドライブで直接書き換えられた
  const r = plain(env.ctx.updateItemMeta(id, FIELDS, fp));
  assert.equal(r.ok, false);
  assert.equal(r.conflict, true);
  assert.match(r.message, /ほかの人が先に/);
  assert.equal(r.entry.item.author, '鈴木');
  assert.equal(metaOf(env, id).author, '鈴木');
  // 最新の fp で送り直せば書ける
  assert.equal(env.ctx.updateItemMeta(id, FIELDS, r.entry.item.fp).ok, true);
});

test('updateItemMeta：検査に通らない値は書かない', () => {
  const env = setupEnv();
  const id = addItem(env, '20250612_ホルダー');
  env.ctx.syncNow();
  assert.throws(() => env.ctx.updateItemMeta(id, { ...FIELDS, status: '保管中' }, itemOf(env, id).fp), /保存できません：「status」は/);
  assert.equal(metaOf(env, id).status, '使用中');
  assert.equal(env.lock.state.held, false);
});

test('updateItemMeta：要対応（meta.json が無い）を画面で直すと、meta.json を作って一覧に移る', () => {
  const env = setupEnv();
  const id = addItem(env, '20250612_ホルダー', { meta: null });
  env.ctx.syncNow();
  const issue = issueOf(env, id);
  assert.equal(issue.date, '2025-06-12');
  const r = plain(env.ctx.updateItemMeta(id, FIELDS, issue.fp));
  assert.equal(r.ok, true);
  assert.equal(r.entry.item.name, 'ホルダー');
  assert.equal(metaOf(env, id).author, '佐藤');
  assert.equal(env.drive.writes.filter((w) => w[0] === 'create').length, 1);
});

test('updateItemMeta：meta.json が壊れていたら、元の文字列を返して確かめる。overwriteBroken なら書き直す', () => {
  const env = setupEnv();
  const id = addItem(env, '20250612_ホルダー', { meta: '{"author": "山田", ' });
  env.ctx.syncNow();
  const fp = issueOf(env, id).fp;
  const r = plain(env.ctx.updateItemMeta(id, FIELDS, fp));
  assert.equal(r.ok, false);
  assert.equal(r.broken, '{"author": "山田", ');
  assert.equal(env.drive.writes.length, 0);
  const r2 = plain(env.ctx.updateItemMeta(id, FIELDS, fp, true));
  assert.equal(r2.ok, true);
  assert.equal(metaOf(env, id).author, '佐藤');
});

test('updateItemMeta：meta.json が2つあるときは書かない', () => {
  const env = setupEnv();
  const id = addItem(env, '20250612_ホルダー');
  env.drive.addFile(id, 'meta.json', META());
  env.ctx.syncNow();
  assert.throws(() => env.ctx.updateItemMeta(id, FIELDS, issueOf(env, id).fp), /meta.json が2個あります/);
});

test('書き込みは items の直下の作品フォルダだけ（_ で始まる・よその・ゴミ箱のフォルダは断る）', () => {
  const env = setupEnv();
  const tpl = addItem(env, '_template');
  const other = env.drive.addFolder('よそ', null);
  env.drive.addFile(other, 'meta.json', META());
  const trashed = addItem(env, '20250101_消した');
  env.drive.trash(trashed);
  assert.throws(() => env.ctx.updateItemMeta(tpl, FIELDS, ''), /このフォルダには書き込めません/);
  assert.throws(() => env.ctx.updateItemMeta(other, FIELDS, ''), /items の直下にありません/);
  assert.throws(() => env.ctx.updateItemMeta(trashed, FIELDS, ''), /items の直下にありません/);
  assert.throws(() => env.ctx.updateItemMeta('nope', FIELDS, ''), /見つかりません/);
  assert.equal(env.drive.writes.length, 0);
});

test('updateItemMeta：Drive に書く権限が無ければ、わかる文で返す', () => {
  const env = setupEnv();
  const id = addItem(env, '20250612_ホルダー');
  env.ctx.syncNow();
  const metaId = env.drive.children(id, 'file').find((n) => n.name === 'meta.json').id;
  env.drive.denyWrite[metaId] = 'Access denied: DriveApp.';
  assert.throws(() => env.ctx.updateItemMeta(id, FIELDS, itemOf(env, id).fp), /作品フォルダを書き換える権限がありません/);
});

// ---------------------------------------------------------------------------
test('trashItemFile：ファイルをゴミ箱へ移し、一覧から消えた item を返す', () => {
  const env = setupEnv();
  const id = addItem(env, '20250612_ホルダー', { extra: ['lid.stl'] });
  env.ctx.syncNow();
  const lid = env.drive.children(id, 'file').find((n) => n.name === 'lid.stl').id;
  const r = plain(env.ctx.trashItemFile(id, lid));
  assert.equal(r.message, '「lid.stl」をゴミ箱に移しました');
  assert.deepEqual(r.entry.item.files.map((f) => f.name), ['base.stl', 'meta.json']);
  assert.equal(env.drive.nodes.get(lid).trashed, true);
});

test('trashItemFile：meta.json・よその作品のファイルは断る。投稿者（ゴミ箱の権限なし）はわかる文', () => {
  const env = setupEnv();
  const a = addItem(env, '20250612_a');
  const b = addItem(env, '20250613_b');
  env.ctx.syncNow();
  const metaA = env.drive.children(a, 'file').find((n) => n.name === 'meta.json').id;
  const stlB = env.drive.children(b, 'file').find((n) => n.name === 'base.stl').id;
  const stlA = env.drive.children(a, 'file').find((n) => n.name === 'base.stl').id;
  assert.throws(() => env.ctx.trashItemFile(a, metaA), /meta.json は消せません/);
  assert.throws(() => env.ctx.trashItemFile(a, stlB), /この作品のフォルダにありません/);
  env.drive.denyTrash[stlA] = 'Insufficient permissions for the specified parent.';
  assert.throws(() => env.ctx.trashItemFile(a, stlA), /コンテンツ管理者/);
  assert.equal(env.drive.nodes.get(stlA).trashed, false);
});

// ---------------------------------------------------------------------------
test('uploadItemFile：作品フォルダに上げる。refreshItem で一覧に出る', () => {
  const env = setupEnv();
  const id = addItem(env, '20250612_ホルダー');
  env.ctx.syncNow();
  const r = plain(env.ctx.uploadItemFile(id, 'photo_使用中.jpg', 'image/jpeg', b64('jpegdata')));
  assert.equal(r.name, 'photo_使用中.jpg');
  assert.equal(r.size, 8);
  assert.equal(itemOf(env, id).photos.length, 0);   // まだ反映していない
  const f = plain(env.ctx.refreshItem(id));
  assert.equal(f.entry.item.photos.length, 1);
});

test('uploadItemFile：同じ名前は断る。replace なら上げてから古い方をゴミ箱へ', () => {
  const env = setupEnv();
  const id = addItem(env, '20250612_ホルダー');
  const old = env.drive.children(id, 'file').find((n) => n.name === 'base.stl').id;
  assert.throws(() => env.ctx.uploadItemFile(id, 'base.stl', 'model/stl', b64('new')), /同じ名前のファイル「base.stl」があります/);
  const r = plain(env.ctx.uploadItemFile(id, 'base.stl', 'model/stl', b64('new'), true));
  assert.notEqual(r.id, old);
  assert.equal(env.drive.nodes.get(old).trashed, true);
  assert.equal(env.drive.nodes.get(r.id).content, 'new');
});

test('uploadItemFile：meta.json・使えない名前・大きすぎるもの・壊れた base64 は断る。名前の記号は _ に', () => {
  const env = setupEnv();
  const id = addItem(env, '20250612_ホルダー');
  assert.throws(() => env.ctx.uploadItemFile(id, 'META.json', 'application/json', b64('{}')), /meta.json は上げられません/);
  assert.throws(() => env.ctx.uploadItemFile(id, '..', '', b64('x')), /この名前のファイルは上げられません/);
  assert.throws(() => env.ctx.uploadItemFile(id, 'a.stl', '', '%%%'), /中身を読めませんでした/);
  env.ctx.UPLOAD_MAX_BYTES = 4;
  assert.throws(() => env.ctx.uploadItemFile(id, 'a.stl', '', b64('12345')), /大きすぎます/);
  env.ctx.UPLOAD_MAX_BYTES = 1024;
  assert.equal(env.ctx.uploadItemFile(id, 'a/b.stl', '', b64('1')).name, 'a_b.stl');
});

test('uploadItemFile：置き換えで古い方をゴミ箱へ移せなければ notReplaced（投稿者）', () => {
  const env = setupEnv();
  const id = addItem(env, '20250612_ホルダー');
  const old = env.drive.children(id, 'file').find((n) => n.name === 'base.stl').id;
  env.drive.denyTrash[old] = 'Insufficient permissions';
  const r = plain(env.ctx.uploadItemFile(id, 'base.stl', '', b64('new'), true));
  assert.equal(r.notReplaced, true);
  assert.equal(env.drive.nodes.get(old).trashed, false);
});

test('refreshItem・updateItemMeta は items をたどり直さない（確かめたフォルダを直接読む）', () => {
  const env = setupEnv();
  const id = addItem(env, '20250612_ホルダー');
  env.ctx.syncNow();
  let listed = 0;
  const real = env.ctx.listItemFolders_;
  env.ctx.listItemFolders_ = (f) => { listed++; return real(f); };
  env.ctx.refreshItem(id);
  env.ctx.updateItemMeta(id, FIELDS, itemOf(env, id).fp);
  assert.equal(listed, 0);
  assert.throws(() => env.ctx.refreshItem(env.drive.addFolder('_template', env.itemsId)), /このフォルダには書き込めません/);
});
