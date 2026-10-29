// 偽の Drive / スプシを使った同期の通しテスト
'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { setupEnv, plain } = require('./fakes');

const META = (over = {}) => JSON.stringify({ author: '山田', purpose: '固定具', status: '使用中', tags: ['治具'], ...over });

/** 作品フォルダを1つ作る */
function addItem(env, name, { meta = META(), extra = [] } = {}) {
  const id = env.drive.addFolder(name, env.itemsId);
  if (meta !== null) env.drive.addFile(id, 'meta.json', meta);
  env.drive.addFile(id, 'thumb.png', 'png');
  env.drive.addFile(id, 'base.stl', 'solid');
  extra.forEach((n) => env.drive.addFile(id, n, 'x'));
  return id;
}

function rows(env) {
  return env.ss.getSheetByName('items').dataRows(plain(env.ctx.HEADERS));
}

function names(env) {
  return rows(env).map((r) => r.folder_name);
}

// ---------------------------------------------------------------------------
test('初回同期：全件をシートに書き、画面用データが作れる', () => {
  const env = setupEnv();
  addItem(env, '20250903_スペーサー');
  const a = addItem(env, '20250612_ホルダー', { extra: ['photo_1.jpg'] });
  addItem(env, '20250101_未記入', { meta: JSON.stringify({ author: '', purpose: '', status: '' }) });

  const r = plain(env.ctx.syncNow());
  assert.deepEqual(r, { done: true, message: '同期しました（3件を確認、3件を更新）' });
  assert.deepEqual(names(env), ['20250101_未記入', '20250612_ホルダー', '20250903_スペーサー']);
  assert.equal(env.lock.state.held, false);

  const data = plain(env.ctx.getGalleryData());
  assert.equal(data.sheetUrl, 'https://docs.google.com/spreadsheets/d/SSID/edit');
  assert.match(data.syncedAt, /^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\+09:00$/);
  assert.equal(data.items.length, 2);
  assert.equal(data.issues.length, 1);
  assert.equal(data.issues[0].folderName, '20250101_未記入');
  assert.match(data.issues[0].rowUrl, /#gid=1000&range=A2$/);
  const item = data.items.find((x) => x.folderId === a);
  assert.equal(item.date, '2025-06-12');
  assert.equal(item.photos.length, 1);
  assert.equal(item.files.length, 4);
});

test('変更が無ければ meta.json を読まない', () => {
  const env = setupEnv();
  addItem(env, '20250612_a');
  addItem(env, '20250613_b');
  env.ctx.syncNow();
  assert.equal(env.drive.blobReads.length, 2);
  const before = plain(rows(env));

  env.drive.blobReads.length = 0;
  const r = env.ctx.syncNow();
  assert.equal(r.message, '同期しました（2件を確認、0件を更新）');
  assert.equal(env.drive.blobReads.length, 0);
  assert.deepEqual(plain(rows(env)), before); // synced_at も前回のまま
});

test('写真を1枚足しただけでも拾う', () => {
  const env = setupEnv();
  const id = addItem(env, '20250612_a');
  env.ctx.syncNow();
  env.drive.addFile(id, 'photo_new.jpg', 'jpg');
  const r = env.ctx.syncNow();
  assert.equal(r.message, '同期しました（1件を確認、1件を更新）');
  const item = env.ctx.getGalleryData().items[0];
  assert.deepEqual(plain(item.photos.map((p) => p.name)), ['photo_new.jpg']);
});

test('meta.json を直すと反映され、要対応から消える', () => {
  const env = setupEnv();
  const id = addItem(env, '20250612_a', { meta: '{ broken' });
  env.ctx.syncNow();
  assert.equal(env.ctx.getGalleryData().issues.length, 1);
  const metaId = env.drive.children(id, 'file').find((n) => n.name === 'meta.json').id;
  env.drive.setContent(metaId, META({ status: '参考' }));
  env.ctx.syncNow();
  const data = env.ctx.getGalleryData();
  assert.equal(data.issues.length, 0);
  assert.equal(data.items[0].status, '参考');
});

test('リネーム：同じ行（folder_id）が新しい名前・日付になる', () => {
  const env = setupEnv();
  const id = addItem(env, '20250612_旧名');
  env.ctx.syncNow();
  env.drive.rename(id, '20250701_新名-v2');
  const r = env.ctx.syncNow();
  assert.equal(r.message, '同期しました（1件を確認、1件を更新）');
  const rs = rows(env);
  assert.equal(rs.length, 1);
  assert.equal(rs[0].folder_id, id);
  assert.equal(rs[0].date, '2025-07-01');
  assert.equal(rs[0].name, '新名-v2');
});

test('フォルダ削除・ゴミ箱入り・_ へのリネームで行が消える', () => {
  const env = setupEnv();
  const a = addItem(env, '20250101_a');
  const b = addItem(env, '20250102_b');
  const c = addItem(env, '20250103_c');
  addItem(env, '20250104_d');
  env.ctx.syncNow();
  assert.equal(rows(env).length, 4);

  env.drive.remove(a);
  env.drive.trash(b);
  env.drive.rename(c, '_退避_c');
  const r = env.ctx.syncNow();
  assert.equal(r.message, '同期しました（1件を確認、0件を更新、3件を削除）');
  assert.deepEqual(names(env), ['20250104_d']);
});

test('_ で始まるフォルダ・ゴミ箱のファイル・ショートカットは無視', () => {
  const env = setupEnv();
  const t = env.drive.addFolder('_template', env.itemsId);
  env.drive.addFile(t, 'meta.json', '{}');
  const id = addItem(env, '20250612_a');
  const trashed = env.drive.addFile(id, 'old.stl', 'x');
  env.drive.trash(trashed);
  env.drive.addFile(id, 'link', '', { mimeType: 'application/vnd.google-apps.shortcut' });
  env.ctx.syncNow();
  assert.deepEqual(names(env), ['20250612_a']);
  const files = JSON.parse(rows(env)[0].files).map((x) => x.name);
  assert.deepEqual(files, ['base.stl', 'meta.json', 'thumb.png']);
});

test('meta.json が重複していると要対応になり、中身は読まない', () => {
  const env = setupEnv();
  const id = addItem(env, '20250612_a');
  env.drive.addFile(id, 'meta.json', META());
  env.ctx.syncNow();
  assert.equal(env.drive.blobReads.length, 0);
  const data = env.ctx.getGalleryData();
  assert.equal(data.items.length, 0);
  assert.match(data.issues[0].problem, /meta.json が2個あります/);
});

test('フォルダ名の形式違いも要対応に出る', () => {
  const env = setupEnv();
  addItem(env, '2025-06-12_a');
  addItem(env, '20250231_b');
  env.ctx.syncNow();
  const problems = env.ctx.getGalleryData().issues.map((i) => i.problem);
  assert.match(problems[0], /形式ではありません/);
  assert.match(problems[1], /実在しない日付/);
});

// ---------------------------------------------------------------------------
// 時間切れと再開
// ---------------------------------------------------------------------------

/** nowMs() を呼ぶたびに step ミリ秒進む時計を入れる */
function tickingClock(env, step) {
  let t = Date.UTC(2026, 9, 30);
  env.ctx.nowMs = () => (t += step);
}

test('時間切れ（Web）：途中まで書き、続きのトリガーは作らず、次の押下で続きから。削除は全件見終えた回だけ', () => {
  const env = setupEnv();
  const ids = ['20250101_a', '20250102_b', '20250103_c', '20250104_d', '20250105_e'].map((n) => addItem(env, n));
  env.ctx.syncNow(); // まず全件をシートに載せる
  // 1件を消し、1件を変更しておく
  env.drive.remove(ids[0]);
  env.drive.addFile(ids[4], 'photo_x.jpg', 'x');

  // 1回の同期で2件しか見られない設定：開始 + 各フォルダ前に1回ずつ時計を見る
  env.ctx.SYNC_TIME_BUDGET_MS = 250;
  tickingClock(env, 100);

  const r1 = plain(env.ctx.syncNow());
  assert.equal(r1.done, false);
  assert.match(r1.message, /^途中まで同期しました（2件を確認、0件を更新）。もう一度押すと続きから再開します$/);
  assert.equal(env.script.triggers.length, 0);
  assert.ok(env.props.store.SYNC_RESUME_AFTER.startsWith('20250103_c'));
  assert.equal(rows(env).length, 5, '途中の回では消えたフォルダの行を消さない');

  const r2 = plain(env.ctx.syncNow());
  assert.equal(r2.done, true);
  assert.equal(r2.message, '同期しました（2件を確認、1件を更新、1件を削除）'); // d と e
  assert.equal(env.props.store.SYNC_RESUME_AFTER, undefined);
  assert.deepEqual(names(env), ['20250102_b', '20250103_c', '20250104_d', '20250105_e']);
  const e = rows(env).find((x) => x.folder_name === '20250105_e');
  assert.ok(JSON.parse(e.files).some((x) => x.name === 'photo_x.jpg'));
});

test('時間切れでも syncedAt（全件を見終えた時刻）は途中の回では変わらない', () => {
  const env = setupEnv();
  ['20250101_a', '20250102_b', '20250103_c'].forEach((n) => addItem(env, n));
  env.ctx.SYNC_TIME_BUDGET_MS = 150;
  tickingClock(env, 100);
  assert.equal(env.ctx.syncNow().done, false);
  assert.equal(env.ctx.getGalleryData().syncedAt, null);
  while (!env.ctx.syncNow().done) { /* 続きを最後まで */ }
  assert.notEqual(env.ctx.getGalleryData().syncedAt, null);
  assert.equal(rows(env).length, 3);
});

test('時間切れ（トリガー）：1回限りの続きトリガーを作り、continueSync は自分を消して続ける', () => {
  const env = setupEnv();
  ['20250101_a', '20250102_b', '20250103_c'].forEach((n) => addItem(env, n));
  env.ctx.SYNC_TIME_BUDGET_MS = 150; // 1回1件
  tickingClock(env, 100);

  env.ctx.dailySync();
  assert.equal(rows(env).length, 1);
  assert.deepEqual(env.script.triggers.map((t) => t.spec), [{ handler: 'continueSync', after: 60000 }]);

  env.ctx.continueSync();
  assert.equal(rows(env).length, 2);
  assert.equal(env.script.triggers.length, 1, '続きのトリガーは常に1つだけ');

  env.ctx.continueSync();
  assert.equal(rows(env).length, 3);
  assert.equal(env.script.triggers.length, 0, '終わったら続きのトリガーは残らない');
});

test('ロックが取れないとき：Web はメッセージ付きで投げ、トリガーは静かに終わる', () => {
  const env = setupEnv();
  addItem(env, '20250101_a');
  env.lock.state.busyByOther = true;
  assert.throws(() => env.ctx.syncNow(), { message: '別の同期が実行中です。少し待ってからもう一度押してください' });
  assert.throws(() => env.ctx.resyncItem('x'), { message: '別の同期が実行中です。少し待ってからもう一度押してください' });
  assert.doesNotThrow(() => env.ctx.dailySync());
  assert.equal(env.ss.getSheetByName('items'), null, 'ロックが取れなければ何も触らない');
});

test('書き込み権限が無いと決まり文句に言い換える', () => {
  const env = setupEnv();
  addItem(env, '20250101_a');
  env.ctx.syncNow();
  env.ss.getSheetByName('items').failWrites = true;
  assert.throws(() => env.ctx.syncNow(), { message: '同期にはスプシの編集権限が必要です（items フォルダは閲覧できれば足ります）' });
  assert.throws(() => env.ctx.resyncItem('x'), { message: '同期にはスプシの編集権限が必要です（items フォルダは閲覧できれば足ります）' });
  assert.equal(env.lock.state.held, false, '失敗してもロックは解放される');
});

test('ITEMS_FOLDER_ID が未設定・誤りならわかる言葉で投げる', () => {
  const env = setupEnv({ props: {} });
  assert.throws(() => env.ctx.syncNow(), /ITEMS_FOLDER_ID」が設定されていません/);
  const env2 = setupEnv({ props: { ITEMS_FOLDER_ID: 'nope' } });
  assert.throws(() => env2.ctx.syncNow(), /items フォルダ（ID: nope）を開けません/);
  assert.throws(() => env2.ctx.setup(), /items フォルダ（ID: nope）を開けません/);
});

// ---------------------------------------------------------------------------
// 1件再同期
// ---------------------------------------------------------------------------

test('resyncItem：fingerprint が同じでも読み直す', () => {
  const env = setupEnv();
  const id = addItem(env, '20250612_a');
  env.ctx.syncNow();
  env.drive.blobReads.length = 0;
  const r = plain(env.ctx.resyncItem(id));
  assert.deepEqual(r, { done: true, message: '「20250612_a」を再同期しました' });
  assert.deepEqual(env.drive.blobReads, ['meta.json']);
});

test('resyncItem：新しいフォルダも1件だけ追加できる。不備があれば内容を返す', () => {
  const env = setupEnv();
  addItem(env, '20250101_a');
  env.ctx.syncNow();
  const id = addItem(env, '20250612_b', { meta: META({ status: '現役' }) });
  const r = env.ctx.resyncItem(id);
  assert.match(r.message, /^「20250612_b」を再同期しました。直すところがあります：「status」は/);
  assert.equal(rows(env).length, 2);
});

test('resyncItem：存在しない・_ にリネーム済み・ゴミ箱・items の外なら行を削除', () => {
  const env = setupEnv();
  const a = addItem(env, '20250101_a');
  const b = addItem(env, '20250102_b');
  const c = addItem(env, '20250103_c');
  const d = addItem(env, '20250104_d');
  env.ctx.syncNow();

  env.drive.remove(a);
  assert.match(env.ctx.resyncItem(a).message, /一覧から外しました（フォルダが見つかりません）/);
  env.drive.rename(b, '_b');
  assert.match(env.ctx.resyncItem(b).message, /一覧から外しました（フォルダ名が _ で始まっています）/);
  env.drive.trash(c);
  assert.match(env.ctx.resyncItem(c).message, /ゴミ箱/);
  const other = env.drive.addFolder('other', null);
  env.drive.nodes.get(d).parents = [other];
  assert.match(env.ctx.resyncItem(d).message, /items の直下にありません/);
  assert.equal(rows(env).length, 0);

  assert.match(env.ctx.resyncItem('nope').message, /^同期の対象ではありません/);
});

// ---------------------------------------------------------------------------
// 初期設定・画面・全部作り直す
// ---------------------------------------------------------------------------

test('setup：見出し・メモ・警告のみの保護・毎日トリガー（何度実行しても重複しない）', () => {
  const env = setupEnv();
  const msg = env.ctx.setup();
  assert.match(msg, /items フォルダ：items/);
  env.ctx.setup();
  const sheet = env.ss.getSheetByName('items');
  assert.deepEqual(sheet.cells[0], plain(env.ctx.HEADERS));
  assert.equal(sheet.notes['1,1'], 'このシートは同期で上書きされます。編集は各作品フォルダの meta.json で');
  assert.equal(sheet.protections.length, 1);
  assert.equal(sheet.protections[0]._state.warningOnly, true);
  assert.equal(sheet.frozenRows, 1);
  assert.deepEqual(env.script.triggers.map((t) => t.spec), [{ handler: 'dailySync', everyDays: 1, atHour: 4 }]);
});

test('全部作り直す：データ行を消して全件読み直す（続きの位置も捨てる）', () => {
  const env = setupEnv();
  addItem(env, '20250101_a');
  addItem(env, '20250102_b');
  env.ctx.syncNow();
  // 手で書かれた余計な行と、古い続きの位置
  const sheet = env.ss.getSheetByName('items');
  sheet.cells.push(['junk', 'junk']);
  env.props.store.SYNC_RESUME_AFTER = '20250101_a';
  env.drive.blobReads.length = 0;

  const r = env.ctx.runSync_({ mode: 'menu', rebuild: true });
  assert.equal(r.done, true);
  assert.equal(r.updated, 2);
  assert.equal(env.drive.blobReads.length, 2);
  assert.deepEqual(names(env), ['20250101_a', '20250102_b']);
});

test('getGalleryData：シートが無ければ空', () => {
  const env = setupEnv();
  assert.deepEqual(plain(env.ctx.getGalleryData()), {
    syncedAt: null, sheetUrl: 'https://docs.google.com/spreadsheets/d/SSID/edit',
    statuses: ['使用中', '参考', '引退'], canSync: true, items: [], issues: [] });
});

test('doGet と include', () => {
  const env = setupEnv();
  const out = env.ctx.doGet();
  assert.equal(out.title, '3Dプリント作品ギャラリー');
  assert.equal(out.metas.viewport, 'width=device-width, initial-scale=1');
  assert.deepEqual(env.html.calls, [['template', 'index']]);
  assert.equal(env.ctx.include('guide'), '<!-- guide -->');
});

// ---------------------------------------------------------------------------
// レビュー対応で足した振る舞い
// ---------------------------------------------------------------------------

const MSG_PERMISSION = '同期にはスプシの編集権限が必要です（items フォルダは閲覧できれば足ります）';

test('書き込みが途中で失敗しても、シートの既存の行は消えない', () => {
  const env = setupEnv();
  addItem(env, '20250101_a');
  addItem(env, '20250102_b');
  env.ctx.syncNow();
  const before = plain(rows(env));
  addItem(env, '20250103_c');
  env.ss.getSheetByName('items').failSetValues = true;
  assert.throws(() => env.ctx.syncNow(), /同期に失敗しました/);
  assert.deepEqual(plain(rows(env)), before);
});

test('行が減ったときは余った行だけ消える', () => {
  const env = setupEnv();
  const ids = ['20250101_a', '20250102_b', '20250103_c'].map((n) => addItem(env, n));
  env.ctx.syncNow();
  env.drive.remove(ids[0]);
  env.drive.remove(ids[1]);
  env.ctx.syncNow();
  assert.equal(env.ss.getSheetByName('items').getLastRow(), 2);
  assert.deepEqual(names(env), ['20250103_c']);
});

test('書き込み権限が無ければ Drive を走査する前に止まる', () => {
  const env = setupEnv();
  addItem(env, '20250101_a');
  env.ctx.syncNow();
  env.ss.getSheetByName('items').failWrites = true;
  env.ctx.listItemFolders_ = () => { throw new Error('走査してはいけない'); };
  assert.throws(() => env.ctx.syncNow(), { message: MSG_PERMISSION });
});

test('*.tmp は files に入らない', () => {
  const env = setupEnv();
  addItem(env, '20250101_a', { extra: ['base.stl.tmp'] });
  env.ctx.syncNow();
  assert.ok(!JSON.parse(rows(env)[0].files).some((f) => f.name.endsWith('.tmp')));
});

test('削除の安全装置：フォルダが0件なら行を消さず知らせる。完了時刻も更新しない', () => {
  const env = setupEnv();
  const ids = ['20250101_a', '20250102_b'].map((n) => addItem(env, n));
  env.ctx.syncNow();
  env.props.store.SYNC_LAST_COMPLETED_AT = 'old';
  ids.forEach((id) => env.drive.remove(id));
  const r = env.ctx.syncNow();
  assert.equal(r.done, true);
  assert.match(r.message, /^同期しました（0件を確認、0件を更新）。items フォルダの中が見つからないため、行の削除を見送りました/);
  assert.equal(rows(env).length, 2);
  assert.equal(env.props.store.SYNC_LAST_COMPLETED_AT, 'old');
});

test('削除の安全装置：10行以上で半数超が消えるときは見送る。全部作り直すなら消える', () => {
  const env = setupEnv();
  const ids = Array.from({ length: 10 }, (_, i) => addItem(env, `202501${i + 10}_x`));
  env.ctx.syncNow();
  ids.slice(0, 6).forEach((id) => env.drive.remove(id));
  const r = env.ctx.syncNow();
  assert.match(r.message, /消えたフォルダが多すぎるため、行の削除を見送りました（6行）/);
  assert.equal(rows(env).length, 10);
  const r2 = env.ctx.runSync_({ mode: 'menu', rebuild: true });
  assert.equal(r2.warning, '');
  assert.equal(rows(env).length, 4);
});

test('getGalleryData：statuses・canSync・issues の folderId', () => {
  const env = setupEnv();
  const id = addItem(env, '20250101_a', { meta: '{' });
  env.ctx.syncNow();
  const data = plain(env.ctx.getGalleryData());
  assert.deepEqual(data.statuses, ['使用中', '参考', '引退']);
  assert.equal(data.canSync, true);
  assert.deepEqual(Object.keys(data.issues[0]), ['folderId', 'folderName', 'problem', 'url', 'rowUrl']);
  assert.equal(data.issues[0].folderId, id);
  env.ss.canEdit = false;
  assert.equal(env.ctx.getGalleryData().canSync, false);
});

test('getGalleryData：旧形式（カンマ区切り）の tags 列も読める', () => {
  const env = setupEnv();
  addItem(env, '20250101_a');
  env.ctx.syncNow();
  const sheet = env.ss.getSheetByName('items');
  sheet.cells[1][plain(env.ctx.HEADERS).indexOf('tags')] = '顕微鏡, 治具';
  assert.deepEqual(plain(env.ctx.getGalleryData().items[0].tags), ['顕微鏡', '治具']);
});

test('getGalleryData：スプシを読めなければ日本語で投げる', () => {
  const env = setupEnv();
  env.ss.failRead = true;
  assert.throws(() => env.ctx.getGalleryData(), { message: '一覧を読み込めません。スプシを閲覧する権限があるか確認してください' });
});

test('resyncItem：「見つからない」以外の失敗は投げ直し、行を消さない', () => {
  const env = setupEnv();
  const id = addItem(env, '20250101_a');
  env.ctx.syncNow();
  env.drive.rename(id, '_a'); // 一覧から外れたが、理由を調べる getFolderById が失敗する
  env.drive.getByIdErrors[id] = 'Service error: Drive';
  assert.throws(() => env.ctx.resyncItem(id), { message: '同期に失敗しました：Service error: Drive' });
  assert.equal(rows(env).length, 1);
});

test('continueSync：ロックが取れなければ1分後に再挑戦する。dailySync はしない', () => {
  const env = setupEnv();
  addItem(env, '20250101_a');
  env.lock.state.busyByOther = true;
  env.ctx.dailySync();
  assert.equal(env.script.triggers.length, 0);
  env.ctx.continueSync();
  assert.deepEqual(env.script.triggers.map((t) => t.spec), [{ handler: 'continueSync', after: 60000 }]);
});
