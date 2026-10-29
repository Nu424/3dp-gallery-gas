// Code.gs の純粋な関数（Drive・シートに触らない）のテスト
'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { setupEnv, plain } = require('./fakes');

const { ctx } = setupEnv();

// ---------------------------------------------------------------------------
test('parseFolderName: 正しい形式', () => {
  assert.deepEqual(plain(ctx.parseFolderName('20250612_流路セルホルダー')),
    { ok: true, date: '2025-06-12', name: '流路セルホルダー', error: '' });
});

test('parseFolderName: -v2 は名前の一部', () => {
  const r = ctx.parseFolderName('20250612_流路セルホルダー-v2');
  assert.equal(r.ok, true);
  assert.equal(r.name, '流路セルホルダー-v2');
});

test('parseFolderName: 名前の中の _ はそのまま', () => {
  assert.equal(ctx.parseFolderName('20250612_a_b').name, 'a_b');
});

test('parseFolderName: うるう年', () => {
  assert.equal(ctx.parseFolderName('20240229_x').ok, true);
  assert.equal(ctx.parseFolderName('20250229_x').ok, false);
});

test('parseFolderName: 実在しない日付', () => {
  for (const s of ['20250231_x', '20251301_x', '20250000_x', '20250100_x', '00000101_x']) {
    const r = ctx.parseFolderName(s);
    assert.equal(r.ok, false, s);
    assert.match(r.error, /実在しない日付/, s);
  }
});

test('parseFolderName: 形式違い', () => {
  for (const s of ['2025-06-12_x', '20250612x', '2025061_x', '202506120_x', '20250612_', '流路セル', '', 'x_20250612']) {
    const r = ctx.parseFolderName(s);
    assert.equal(r.ok, false, s);
    assert.match(r.error, /形式ではありません/, s);
  }
});

test('isIgnoredFolderName', () => {
  assert.equal(ctx.isIgnoredFolderName('_template'), true);
  assert.equal(ctx.isIgnoredFolderName('20250101_x'), false);
});

// ---------------------------------------------------------------------------
const goodMeta = {
  author: '山田', purpose: '流路セルを固定する', status: '使用中',
  tags: ['顕微鏡', '治具'], note: ['M3ネジ×4で固定。', '縦向きで刷る。'],
};

test('checkMeta: 正常', () => {
  const r = plain(ctx.checkMeta(JSON.stringify(goodMeta)));
  assert.deepEqual(r.errors, []);
  assert.deepEqual(r.meta, goodMeta);
});

test('checkMeta: BOM 付きでも読める', () => {
  const r = ctx.checkMeta('﻿' + JSON.stringify(goodMeta));
  assert.equal(r.errors.length, 0);
  assert.equal(r.meta.author, '山田');
});

test('checkMeta: 壊れた JSON', () => {
  const r = ctx.checkMeta('{"author": "山田",}');
  assert.equal(r.errors.length, 1);
  assert.match(r.errors[0], /JSON として読めません/);
});

test('checkMeta: オブジェクトでない JSON', () => {
  for (const t of ['[]', '"x"', 'null', '3']) {
    const r = ctx.checkMeta(t);
    assert.match(r.errors[0], /\{ \} で囲まれていません/, t);
  }
});

test('checkMeta: 必須キーの欠落・空文字・空白のみ・型違い', () => {
  const r = plain(ctx.checkMeta(JSON.stringify({ purpose: '', status: '   ' })));
  assert.deepEqual(r.errors, ['meta.json に「author」がありません', '「purpose」が空です', '「status」が空です']);
  const r2 = ctx.checkMeta(JSON.stringify({ author: 3, purpose: 'p', status: '参考' }));
  assert.deepEqual(plain(r2.errors), ['「author」は文字列で書いてください']);
});

test('checkMeta: status が選択肢外', () => {
  const r = ctx.checkMeta(JSON.stringify({ ...goodMeta, status: '現役' }));
  assert.equal(r.errors.length, 1);
  assert.match(r.errors[0], /使用中 \/ 参考 \/ 引退/);
  assert.match(r.errors[0], /現役/);
});

test('checkMeta: 値の前後の空白は落とす', () => {
  const r = ctx.checkMeta(JSON.stringify({ ...goodMeta, author: ' 山田 ', status: '引退 ' }));
  assert.equal(r.errors.length, 0);
  assert.equal(r.meta.author, '山田');
  assert.equal(r.meta.status, '引退');
});

test('checkMeta: tags の型違い', () => {
  for (const tags of ['顕微鏡', ['a', 1], { a: 1 }, 5]) {
    const r = ctx.checkMeta(JSON.stringify({ ...goodMeta, tags }));
    assert.equal(r.errors.length, 1, JSON.stringify(tags));
    assert.match(r.errors[0], /tags/);
  }
});

test('checkMeta: tags は省略・null・空配列でもよい。空文字の要素は捨てる', () => {
  const { tags, ...noTags } = goodMeta;
  assert.deepEqual(plain(ctx.checkMeta(JSON.stringify(noTags)).meta.tags), []);
  assert.deepEqual(plain(ctx.checkMeta(JSON.stringify({ ...goodMeta, tags: null })).meta.tags), []);
  assert.deepEqual(plain(ctx.checkMeta(JSON.stringify({ ...goodMeta, tags: [' a ', '', 'b'] })).meta.tags), ['a', 'b']);
});

test('checkMeta: note は文字列・配列どちらでもよい', () => {
  assert.deepEqual(plain(ctx.checkMeta(JSON.stringify({ ...goodMeta, note: '1行目\n2行目' })).meta.note), ['1行目', '2行目']);
  assert.deepEqual(plain(ctx.checkMeta(JSON.stringify({ ...goodMeta, note: '' })).meta.note), []);
  assert.deepEqual(plain(ctx.checkMeta(JSON.stringify({ ...goodMeta, note: ['a', 'b'] })).meta.note), ['a', 'b']);
  const { note, ...noNote } = goodMeta;
  const r = ctx.checkMeta(JSON.stringify(noNote));
  assert.equal(r.errors.length, 0);
  assert.deepEqual(plain(r.meta.note), []);
});

test('checkMeta: note の型違い', () => {
  for (const note of [3, ['a', 2], { a: 'b' }, true]) {
    const r = ctx.checkMeta(JSON.stringify({ ...goodMeta, note }));
    assert.equal(r.errors.length, 1, JSON.stringify(note));
    assert.match(r.errors[0], /note/);
  }
});

test('checkMeta: 未知のキーは許容', () => {
  const r = ctx.checkMeta(JSON.stringify({ ...goodMeta, printer: 'X1', version: 2 }));
  assert.equal(r.errors.length, 0);
});

test('checkMeta: 複数の不備をまとめて返す', () => {
  const r = ctx.checkMeta(JSON.stringify({ author: '', status: 'x', tags: 'a' }));
  assert.equal(r.errors.length, 4); // author 空, purpose 無し, status 選択肢外, tags 型違い
});

// ---------------------------------------------------------------------------
const f = (name, id, mimeType) => ({ name, id: id || name, size: 1, mimeType: mimeType || '' });

test('pickThumbFile: thumb.png を最優先', () => {
  const files = [f('a.jpg', 'a', 'image/jpeg'), f('thumb.jpg', 'tj', 'image/jpeg'), f('thumb.png', 'tp', 'image/png')];
  assert.equal(ctx.pickThumbFile(files).id, 'tp');
});

test('pickThumbFile: thumb.jpg → thumb.jpeg の順', () => {
  assert.equal(ctx.pickThumbFile([f('thumb.jpeg', 'x'), f('thumb.jpg', 'y')]).id, 'y');
  assert.equal(ctx.pickThumbFile([f('thumb.jpeg', 'x'), f('a.png', 'a', 'image/png')]).id, 'x');
});

test('pickThumbFile: 大文字の THUMB.PNG も可', () => {
  assert.equal(ctx.pickThumbFile([f('a.png', 'a', 'image/png'), f('THUMB.PNG', 'T')]).id, 'T');
});

test('pickThumbFile: thumb が無ければ名前順で最初の画像', () => {
  const files = [f('model.stl', 's', 'model/stl'), f('photo_b.jpg', 'b', 'image/jpeg'), f('photo_a.png', 'a', 'image/png')];
  assert.equal(ctx.pickThumbFile(files).id, 'a');
});

test('pickThumbFile: mimeType が無くても拡張子で画像と判定', () => {
  assert.equal(ctx.pickThumbFile([f('x.stl', 's'), f('z.JPG', 'z')]).id, 'z');
});

test('pickThumbFile: 画像が無ければ null', () => {
  assert.equal(ctx.pickThumbFile([f('meta.json', 'm', 'application/json'), f('x.stl', 's')]), null);
  assert.equal(ctx.pickThumbFile([]), null);
});

test('pickPhotoFiles: photo_ で始まる画像だけ、名前順', () => {
  const files = [f('photo_b.jpg', 'b', 'image/jpeg'), f('thumb.png', 't', 'image/png'),
    f('photo_a.png', 'a', 'image/png'), f('photo_memo.txt', 'm', 'text/plain')];
  assert.deepEqual(plain(ctx.pickPhotoFiles(files).map((x) => x.id)), ['a', 'b']);
});

// ---------------------------------------------------------------------------
test('fingerprint: ファイルの順番に依存しない', () => {
  const a = { name: 'a.stl', size: 10, updated: 1 };
  const b = { name: 'meta.json', size: 20, updated: 2 };
  assert.equal(ctx.computeFingerprint('20250101_x', [a, b]), ctx.computeFingerprint('20250101_x', [b, a]));
});

test('fingerprint: フォルダ名・サイズ・更新日時・ファイル追加で変わる', () => {
  const files = [{ name: 'a.stl', size: 10, updated: 1 }];
  const base = ctx.computeFingerprint('20250101_x', files);
  assert.match(base, /^[0-9a-f]{64}$/);
  assert.notEqual(ctx.computeFingerprint('20250101_y', files), base);
  assert.notEqual(ctx.computeFingerprint('20250101_x', [{ ...files[0], size: 11 }]), base);
  assert.notEqual(ctx.computeFingerprint('20250101_x', [{ ...files[0], updated: 2 }]), base);
  assert.notEqual(ctx.computeFingerprint('20250101_x', [...files, { name: 'photo_1.jpg', size: 1, updated: 1 }]), base);
});

test('fingerprint: 検査のルール（状態の選択肢）を変えると変わる', () => {
  const files = [{ name: 'a.stl', size: 10, updated: 1 }];
  const base = ctx.computeFingerprint('20250101_x', files);
  const saved = ctx.STATUS_CHOICES;
  try {
    ctx.STATUS_CHOICES = ['使用中', '参考', '引退', '修理中'];
    assert.notEqual(ctx.computeFingerprint('20250101_x', files), base);
  } finally {
    ctx.STATUS_CHOICES = saved;
  }
});

test('bytesToHex: 負の値も正しく', () => {
  assert.equal(ctx.bytesToHex([0, 15, 16, 127, -128, -1]), '000f107f80ff');
});

// ---------------------------------------------------------------------------
const FILES = [
  { name: 'meta.json', id: 'm1', size: 100, mimeType: 'application/json', updated: 1 },
  { name: 'thumb.png', id: 't1', size: 200, mimeType: 'image/png', updated: 1 },
  { name: 'photo_2.jpg', id: 'p2', size: 300, mimeType: 'image/jpeg', updated: 1 },
  { name: 'photo_1.jpg', id: 'p1', size: 300, mimeType: 'image/jpeg', updated: 1 },
  { name: 'base.stl', id: 's1', size: 400, mimeType: 'model/stl', updated: 1 },
];

function record(overrides = {}) {
  return ctx.buildRecord({
    folderId: 'F1', folderName: '20250612_流路セルホルダー', files: FILES,
    metaText: JSON.stringify(goodMeta), fingerprint: 'fp', syncedAt: '2026-10-30T10:00:00+09:00',
    ...overrides,
  });
}

test('buildRecord: 正常な作品の行', () => {
  const r = plain(record());
  assert.equal(r.folder_id, 'F1');
  assert.equal(r.date, '2025-06-12');
  assert.equal(r.name, '流路セルホルダー');
  assert.equal(r.author, '山田');
  assert.equal(r.status, '使用中');
  assert.equal(r.tags, '["顕微鏡","治具"]');
  assert.equal(r.note, 'M3ネジ×4で固定。\n縦向きで刷る。');
  assert.equal(r.thumb_id, 't1');
  assert.equal(r.error, '');
  assert.equal(r.fingerprint, 'fp');
  const files = JSON.parse(r.files);
  assert.deepEqual(files.map((x) => x.name), ['base.stl', 'meta.json', 'photo_1.jpg', 'photo_2.jpg', 'thumb.png']);
  assert.deepEqual(Object.keys(files[0]), ['name', 'id', 'size']);
  assert.deepEqual(Object.keys(r), plain(ctx.HEADERS));
});

test('buildRecord: meta.json が無い / 複数 / 読み取り失敗', () => {
  const noMeta = FILES.filter((x) => x.name !== 'meta.json');
  assert.equal(record({ files: noMeta, metaText: null }).error, 'meta.json がありません');
  const dup = [...FILES, { name: 'meta.json', id: 'm2', size: 1, mimeType: 'application/json', updated: 1 }];
  assert.match(record({ files: dup, metaText: null }).error, /meta.json が2個あります/);
  assert.match(record({ metaText: null, metaReadError: 'boom' }).error, /meta.json を読めません（boom）/);
});

test('buildRecord: フォルダ名と meta の不備をまとめて error に', () => {
  const r = record({ folderName: '2025-06-12_x', metaText: '{"author":"a"}' });
  assert.match(r.error, /形式ではありません/);
  assert.match(r.error, /purpose/);
  assert.match(r.error, / \/ /);
  assert.equal(r.author, 'a'); // 読めたところはシートに出す
});

test('recordToRow / rowToRecord は往復で同じ', () => {
  const r = plain(record());
  const row = plain(ctx.recordToRow(r));
  assert.equal(row.length, ctx.HEADERS.length);
  assert.deepEqual(plain(ctx.rowToRecord(row)), r);
});

test('rowToRecord: 日付として返ったセルを文字列に直す', () => {
  const row = plain(ctx.recordToRow(record()));
  row[2] = new Date(Date.UTC(2025, 5, 11, 15)); // JST 2025-06-12 0:00
  assert.equal(ctx.rowToRecord(row).date, '2025-06-12');
});

test('recordToGalleryEntry: 作品', () => {
  const e = plain(ctx.recordToGalleryEntry(plain(record()), { sheetUrl: 'u', sheetGid: 0, rowNumber: 2 }));
  assert.equal(e.issue, undefined);
  const it = e.item;
  assert.deepEqual(Object.keys(it), ['folderId', 'folderName', 'folderUrl', 'date', 'name', 'author', 'purpose',
    'status', 'tags', 'note', 'thumbUrl', 'photos', 'files']);
  assert.equal(it.folderUrl, 'https://drive.google.com/drive/folders/F1');
  assert.deepEqual(it.tags, ['顕微鏡', '治具']);
  assert.deepEqual(it.note, ['M3ネジ×4で固定。', '縦向きで刷る。']);
  assert.equal(it.thumbUrl, 'https://drive.google.com/thumbnail?id=t1&sz=w600');
  assert.deepEqual(it.photos, [
    { name: 'photo_1.jpg', url: 'https://drive.google.com/thumbnail?id=p1&sz=w600' },
    { name: 'photo_2.jpg', url: 'https://drive.google.com/thumbnail?id=p2&sz=w600' },
  ]);
  assert.deepEqual(it.files[0], {
    name: 'base.stl',
    url: 'https://drive.google.com/file/d/s1/view',
    downloadUrl: 'https://drive.google.com/uc?export=download&id=s1',
  });
  assert.equal(it.files.length, 5);
});

test('recordToGalleryEntry: 画像が無ければ thumbUrl は null、tags/note 空は空配列', () => {
  const r = plain(record({ files: FILES.filter((x) => !/\.(png|jpg)$/.test(x.name)),
    metaText: JSON.stringify({ author: 'a', purpose: 'p', status: '参考' }) }));
  const it = ctx.recordToGalleryEntry(r, { sheetUrl: 'u', sheetGid: 0, rowNumber: 2 }).item;
  assert.equal(it.thumbUrl, null);
  assert.deepEqual(plain(it.tags), []);
  assert.deepEqual(plain(it.note), []);
  assert.deepEqual(plain(it.photos), []);
});

test('recordToGalleryEntry: 不備のある行は issue（行へのリンク付き）', () => {
  const r = plain(record({ metaText: '{' }));
  const e = plain(ctx.recordToGalleryEntry(r, {
    sheetUrl: 'https://docs.google.com/spreadsheets/d/SS/edit', sheetGid: 42, rowNumber: 7 }));
  assert.equal(e.item, undefined);
  assert.deepEqual(e.issue, {
    folderId: 'F1',
    folderName: '20250612_流路セルホルダー',
    problem: r.error,
    url: 'https://drive.google.com/drive/folders/F1',
    rowUrl: 'https://docs.google.com/spreadsheets/d/SS/edit#gid=42&range=A7',
  });
});

test('recordToGalleryEntry: files 列が壊れていても落ちない', () => {
  const r = { ...plain(record()), files: 'not json' };
  assert.deepEqual(plain(ctx.recordToGalleryEntry(r, { sheetUrl: 'u', sheetGid: 0, rowNumber: 2 }).item.files), []);
});

test('buildSyncMessage', () => {
  assert.equal(ctx.buildSyncMessage({ done: true, checked: 12, updated: 2, removed: 0 }, 'web'), '同期しました（12件を確認、2件を更新）');
  assert.equal(ctx.buildSyncMessage({ done: true, checked: 3, updated: 0, removed: 1 }, 'web'), '同期しました（3件を確認、0件を更新、1件を削除）');
  assert.match(ctx.buildSyncMessage({ done: false, checked: 2, updated: 2, removed: 0 }, 'web'), /^途中まで同期しました.*もう一度押すと続きから再開します$/);
  assert.match(ctx.buildSyncMessage({ done: false, checked: 2, updated: 2, removed: 0 }, 'menu'), /自動的に再開/);
});

// ---------------------------------------------------------------------------
// レビュー対応で足した振る舞い
// ---------------------------------------------------------------------------

test('tags 列：JSON 配列で保存し、カンマを含むタグも割れない。旧形式（カンマ区切り）も読める', () => {
  const r = plain(record({ metaText: JSON.stringify({ ...goodMeta, tags: ['M3,M4', '治具'] }) }));
  assert.equal(r.tags, '["M3,M4","治具"]');
  const it = ctx.recordToGalleryEntry(r, { sheetUrl: 'u', sheetGid: 0, rowNumber: 2 }).item;
  assert.deepEqual(plain(it.tags), ['M3,M4', '治具']);
  assert.deepEqual(plain(ctx.splitTags('顕微鏡, 治具')), ['顕微鏡', '治具']);
  assert.deepEqual(plain(ctx.splitTags('')), []);
  assert.deepEqual(plain(ctx.splitTags('[壊れ, た')), ['[壊れ', 'た']);
  assert.equal(record({ metaText: JSON.stringify({ ...goodMeta, tags: [] }) }).tags, '');
});

test('写真・代表画像は mimeType の無い files 列（拡張子）でも判定できる', () => {
  const it = ctx.recordToGalleryEntry(plain(record()), { sheetUrl: 'u', sheetGid: 0, rowNumber: 2 }).item;
  assert.equal(it.photos.length, 2);
  assert.deepEqual(plain(ctx.IMAGE_EXTENSIONS), ['png', 'jpg', 'jpeg', 'gif', 'webp']);
});

test('セルの上限：ファイルが多すぎると切り詰めて要対応に', () => {
  const many = Array.from({ length: 1200 }, (_, i) => ({
    name: `part_${String(i).padStart(4, '0')}_with_a_rather_long_file_name.stl`, id: 'x'.repeat(33) + i,
    size: 123456, mimeType: 'model/stl', updated: 1 }));
  const r = plain(record({ files: [...FILES, ...many] }));
  assert.ok(r.files.length <= ctx.CELL_CHAR_LIMIT);
  assert.ok(JSON.parse(r.files).length < many.length + FILES.length);
  assert.match(r.error, /ファイルが多すぎて一覧を保存できません（1205個）。フォルダを分けてください/);
});

test('セルの上限：note などが長すぎると切り詰めて error に記録', () => {
  const long = 'あ'.repeat(60000);
  const r = plain(record({ metaText: JSON.stringify({ ...goodMeta, note: long, purpose: long }) }));
  assert.equal(r.note.length, ctx.CELL_CHAR_LIMIT);
  assert.equal(r.purpose.length, ctx.CELL_CHAR_LIMIT);
  assert.match(r.error, /「purpose」が長すぎるため切り詰めました/);
  assert.match(r.error, /「note」が長すぎるため切り詰めました/);
  // recordToRow でも念のため切る
  const row = plain(ctx.recordToRow({ ...r, error: 'e'.repeat(70000) }));
  assert.ok(row.every((v) => v.length <= ctx.CELL_CHAR_LIMIT));
});

test('fingerprint：同名・同サイズ・同時刻でもファイルIDが違えば変わる', () => {
  const a = ctx.computeFingerprint('20250101_x', [{ name: 'a.stl', id: 'A', size: 1, updated: 1 }]);
  const b = ctx.computeFingerprint('20250101_x', [{ name: 'a.stl', id: 'B', size: 1, updated: 1 }]);
  assert.notEqual(a, b);
});

test('isIgnoredFileName：*.tmp は無視', () => {
  assert.equal(ctx.isIgnoredFileName('base.stl.tmp'), true);
  assert.equal(ctx.isIgnoredFileName('X.TMP'), true);
  assert.equal(ctx.isIgnoredFileName('base.stl'), false);
});

test('folderKey はタブ区切り', () => {
  assert.equal(ctx.folderKey('20250101_a', 'ID'), '20250101_a' + String.fromCharCode(9) + 'ID');
});

test('deletionGuardMessage：0件・多すぎるときだけ見送る', () => {
  assert.equal(ctx.deletionGuardMessage(5, 5, 0), '');
  assert.match(ctx.deletionGuardMessage(3, 0, 3), /items フォルダの中が見つからない/);
  assert.equal(ctx.deletionGuardMessage(4, 1, 3), '', '少ない行数なら半数超でも消す');
  assert.equal(ctx.deletionGuardMessage(10, 5, 5), '', 'ちょうど半数は消す');
  assert.match(ctx.deletionGuardMessage(10, 4, 6), /多すぎるため.*（6行）/);
});

test('toUserError_：権限の判定は狭く、「アクセス」単独では当てない', () => {
  const MSG = '同期にはスプシの編集権限が必要です（items フォルダは閲覧できれば足ります）';
  assert.equal(ctx.toUserError_(new Error('You do not have permission to call X')).message, MSG);
  assert.equal(ctx.toUserError_(new Error('この操作を行う権限がありません')).message, MSG);
  assert.equal(ctx.toUserError_(new Error('サーバーへのアクセス中にエラー')).message, '同期に失敗しました：サーバーへのアクセス中にエラー');
  assert.equal(ctx.toUserError_(new Error('x'), { prefix: 'P:' }).message, 'P:x');
});

test('isNotFoundError', () => {
  assert.equal(ctx.isNotFoundError(new Error('No item with the given ID could be found, or you do not have permission to access it.')), true);
  assert.equal(ctx.isNotFoundError(new Error('Service error: Drive')), false);
});
