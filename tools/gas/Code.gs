/**
 * 3Dプリント作品ギャラリー  Code.gs
 * =============================================================================
 * このファイルの役割
 *   1. 同期：Drive の items/ にある作品フォルダを読み、スプシ（シート items）に写す
 *   2. Webアプリのサーバー側：doGet（画面を返す）、getGalleryData（一覧を返す）、
 *      syncNow / resyncItem（画面のボタンから呼ばれる同期）
 *   3. スプシのメニュー（onOpen）と初期設定（setup）
 *
 * 大前提
 *   - 作品フォルダ（meta.json を含む）が唯一の正。シートはその写しで、壊れても
 *     「ギャラリー → 全部作り直す」で元に戻せる。だからシートは手で編集しない。
 *   - 外部ライブラリ・拡張サービスは使わない（コピペで動かすため）。
 *
 * 読み方
 *   - 「設定」          … 変えたくなりそうな値はすべてここ
 *   - 「純粋な関数」     … Drive やシートに触らない。Node のテスト（dev/gas-test）で検証済み
 *   - 「Drive / シートの読み書き」以降 … GAS の API を呼ぶ部分
 *   - 名前が _ で終わる関数は GAS の非公開関数（画面やメニューから直接は呼べない）
 *
 * 設定の都合で var を使っている箇所がある。テストから値を差し替えられるようにするため。
 * =============================================================================
 */


// =============================================================================
// 設定
// =============================================================================

/** 作品一覧を書くシートの名前 */
var SHEET_NAME = 'items';

/**
 * 状態（meta.json の status）の選択肢。ここを変えれば検査も変わる。
 * この値と必須キーは fingerprint に含めているので、変えると次の同期で全作品が読み直される。
 */
var STATUS_CHOICES = ['使用中', '参考', '引退'];

/** meta.json の必須キー（どれも空でない文字列であること） */
var REQUIRED_META_KEYS = ['author', 'purpose', 'status'];

/** シートの列。順番を変えたら「全部作り直す」を実行する */
var HEADERS = [
  'folder_id', 'folder_name', 'date', 'name',
  'author', 'purpose', 'status', 'tags', 'note',
  'thumb_id', 'files', 'fingerprint', 'error', 'synced_at'
];

/**
 * 1回の同期に使う時間の目安（ミリ秒）。GAS の実行時間上限は6分なので、
 * シートへの書き込みの余裕を残して約4.5分で区切り、続きは次の実行に回す。
 */
var SYNC_TIME_BUDGET_MS = 4.5 * 60 * 1000;

/** 時間切れのとき、続きを始めるまでの待ち時間（トリガー・メニュー起動のときだけ使う） */
var CONTINUE_AFTER_MS = 60 * 1000;

/** 同期の二重実行を防ぐロックを待つ時間（ミリ秒） */
var LOCK_WAIT_MS = 5000;

/** 毎日の自動同期を走らせる時刻（0〜23時。実際はこの1時間のどこか） */
var DAILY_SYNC_HOUR = 4;

/** 作品フォルダの中のファイル名の決まり */
var META_FILE_NAME = 'meta.json';
var THUMB_FILE_NAMES = ['thumb.png', 'thumb.jpg', 'thumb.jpeg']; // この順に探す
var PHOTO_PREFIX = 'photo_';
var IGNORE_PREFIX = '_'; // この文字で始まるフォルダは同期しない（_template など）

/** 画像とみなす拡張子（mimeType が image/ でない場合の予備判定） */
var IMAGE_EXTENSIONS = ['png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp'];

/** Drive のショートカットの mimeType（作品のファイルとしては扱わない） */
var SHORTCUT_MIME_TYPE = 'application/vnd.google-apps.shortcut';

/** スクリプトプロパティのキー。ユーザーが設定するのは ITEMS_FOLDER_ID だけ */
var PROP_ITEMS_FOLDER_ID = 'ITEMS_FOLDER_ID';
var PROP_RESUME_AFTER = 'SYNC_RESUME_AFTER';        // 内部用：時間切れで止まった位置
var PROP_LAST_FULL_SYNC = 'SYNC_LAST_COMPLETED_AT'; // 内部用：最後に全件を見終えた時刻

/** トリガーから呼ばれる関数の名前（関数名を変えたらここも変える） */
var DAILY_HANDLER = 'dailySync';
var CONTINUE_HANDLER = 'continueSync';

/** シートの見出しに付けるメモと、シート保護の説明 */
var HEADER_NOTE = 'このシートは同期で上書きされます。編集は各作品フォルダの meta.json で';
var PROTECTION_DESCRIPTION = '同期で上書きされるシート（編集は meta.json で）';

/** 画面に出す決まり文句 */
var MSG_PERMISSION = '同期には items フォルダとスプシの編集権限が必要です';
var MSG_LOCKED = '別の同期が実行中です。少し待ってからもう一度押してください';

/** Webアプリの題名 */
var APP_TITLE = '3Dプリント作品ギャラリー';


// =============================================================================
// 純粋な関数（Drive やシートに触らない）
//   入力から出力が決まるので、Node のテストで細かく確かめている。
// =============================================================================

/**
 * フォルダ名 "YYYYMMDD_名前" を日付と名前に分ける。
 * - 日付はカレンダーに実在するかまで確かめる（20250231 はエラー）
 * - "-v2" などの付け足しは名前の一部として扱う
 * @return {{ok:boolean, date:string, name:string, error:string}} date は "YYYY-MM-DD"
 */
function parseFolderName(folderName) {
  var m = /^(\d{8})_(.+)$/.exec(String(folderName));
  if (!m) {
    return { ok: false, date: '', name: '', error: 'フォルダ名が「YYYYMMDD_名前」の形式ではありません' };
  }
  var digits = m[1];
  var y = Number(digits.slice(0, 4));
  var mo = Number(digits.slice(4, 6));
  var d = Number(digits.slice(6, 8));
  if (!isRealDate(y, mo, d)) {
    return { ok: false, date: '', name: m[2], error: 'フォルダ名の日付「' + digits + '」は実在しない日付です' };
  }
  var date = digits.slice(0, 4) + '-' + digits.slice(4, 6) + '-' + digits.slice(6, 8);
  return { ok: true, date: date, name: m[2], error: '' };
}

/** 年・月・日がカレンダーに実在するか（うるう年も考慮） */
function isRealDate(y, mo, d) {
  if (y < 1900 || mo < 1 || mo > 12 || d < 1) return false;
  var dt = new Date(Date.UTC(y, mo - 1, d));
  return dt.getUTCFullYear() === y && dt.getUTCMonth() === mo - 1 && dt.getUTCDate() === d;
}

/** 同期の対象外にするフォルダ名か（先頭が _ ） */
function isIgnoredFolderName(folderName) {
  return String(folderName).indexOf(IGNORE_PREFIX) === 0;
}

/** 先頭の BOM（Windows のメモ帳などが付ける見えない文字）を取り除く */
function stripBom(text) {
  return String(text).replace(/^﻿/, '');
}

/**
 * meta.json の中身（文字列）を検査し、シートに書く形に整える。
 * - 未知のキーはエラーにしない（将来キーを足しても古いコードで壊れないように）
 * - 不備は errors に日本語で並べる。1つでもあればギャラリーには出ず「要対応」になる
 * @return {{meta:{author:string,purpose:string,status:string,tags:string[],note:string[]}, errors:string[]}}
 */
function checkMeta(text) {
  var meta = { author: '', purpose: '', status: '', tags: [], note: [] };
  var errors = [];

  var obj;
  try {
    obj = JSON.parse(stripBom(text));
  } catch (e) {
    errors.push('meta.json を JSON として読めません（カンマや " の過不足を確認してください）');
    return { meta: meta, errors: errors };
  }
  if (obj === null || typeof obj !== 'object' || Array.isArray(obj)) {
    errors.push('meta.json の中身が { } で囲まれていません');
    return { meta: meta, errors: errors };
  }

  // 必須キー：文字列で、空白だけでもないこと
  REQUIRED_META_KEYS.forEach(function (key) {
    var v = obj[key];
    if (v === undefined || v === null) {
      errors.push('meta.json に「' + key + '」がありません');
    } else if (typeof v !== 'string') {
      errors.push('「' + key + '」は文字列で書いてください');
    } else if (v.trim() === '') {
      errors.push('「' + key + '」が空です');
    } else {
      meta[key] = v.trim();
    }
  });

  // status は決まった選択肢のどれか
  if (meta.status && STATUS_CHOICES.indexOf(meta.status) < 0) {
    errors.push('「status」は ' + STATUS_CHOICES.join(' / ') + ' のどれかにしてください（今は「' + meta.status + '」）');
  }

  // tags：任意。書くなら文字列の配列
  if (obj.tags !== undefined && obj.tags !== null) {
    if (isStringArray(obj.tags)) {
      meta.tags = obj.tags.map(function (t) { return t.trim(); }).filter(function (t) { return t !== ''; });
    } else {
      errors.push('「tags」は文字列の配列で書いてください（例: ["顕微鏡", "治具"]）');
    }
  }

  // note：任意。文字列、または文字列の配列（1要素＝1行）
  if (obj.note !== undefined && obj.note !== null) {
    if (typeof obj.note === 'string') {
      meta.note = obj.note === '' ? [] : obj.note.split(/\r?\n/);
    } else if (isStringArray(obj.note)) {
      meta.note = obj.note.slice();
    } else {
      errors.push('「note」は文字列か、文字列の配列で書いてください');
    }
  }

  return { meta: meta, errors: errors };
}

/** 文字列だけからなる配列か */
function isStringArray(v) {
  return Array.isArray(v) && v.every(function (x) { return typeof x === 'string'; });
}

/** ファイル名の拡張子（小文字。無ければ空文字） */
function fileExtension(name) {
  var m = /\.([^.]+)$/.exec(String(name));
  return m ? m[1].toLowerCase() : '';
}

/** 画像ファイルか（mimeType で判定し、だめなら拡張子で） */
function isImageFile(file) {
  if (file.mimeType && String(file.mimeType).indexOf('image/') === 0) return true;
  return IMAGE_EXTENSIONS.indexOf(fileExtension(file.name)) >= 0;
}

/** 名前順（文字コード順。どの環境でも同じ結果になる）の比較関数 */
function compareByName(a, b) {
  if (a.name < b.name) return -1;
  if (a.name > b.name) return 1;
  return a.id < b.id ? -1 : (a.id > b.id ? 1 : 0);
}

/**
 * 代表画像を選ぶ。thumb.png → thumb.jpg → thumb.jpeg → 名前順で最初の画像。
 * 大文字小文字は区別しない（THUMB.PNG でも可）。
 * @param {Array<{name:string,id:string,mimeType:string}>} files
 * @return {Object|null} 選んだファイル。画像が無ければ null
 */
function pickThumbFile(files) {
  for (var i = 0; i < THUMB_FILE_NAMES.length; i++) {
    var want = THUMB_FILE_NAMES[i];
    var hit = files.filter(function (f) { return String(f.name).toLowerCase() === want; }).sort(compareByName)[0];
    if (hit) return hit;
  }
  var images = files.filter(isImageFile).sort(compareByName);
  return images.length ? images[0] : null;
}

/** 写真（名前が photo_ で始まる画像）を名前順で返す */
function pickPhotoFiles(files) {
  return files.filter(function (f) {
    return String(f.name).toLowerCase().indexOf(PHOTO_PREFIX) === 0 && isImageFile(f);
  }).sort(compareByName);
}

/**
 * fingerprint の元になる文字列。
 * フォルダ名 ＋ 各ファイルの「名前・サイズ・更新日時」。ファイルは並べ替えるので、
 * Drive が返す順番が変わっても同じ値になる。フォルダ名を含めるのは、リネームだけ
 * では中のファイルが変わらないため。
 * @param {Array<{name:string,size:number,updated:number}>} files updated はミリ秒
 */
function fingerprintSource(folderName, files) {
  var lines = files.map(function (f) {
    return [f.name, f.size, f.updated].join('\t');
  }).sort();
  // 検査のルールも含める。ルールを変えたら、中身が同じフォルダも読み直して検査をやり直すため
  var rules = JSON.stringify([STATUS_CHOICES, REQUIRED_META_KEYS]);
  return [rules, String(folderName)].concat(lines).join('\n');
}

/** fingerprint（SHA-256 の16進文字列）。Utilities は計算だけで Drive には触らない */
function computeFingerprint(folderName, files) {
  var bytes = Utilities.computeDigest(
    Utilities.DigestAlgorithm.SHA_256, fingerprintSource(folderName, files), Utilities.Charset.UTF_8);
  return bytesToHex(bytes);
}

/** computeDigest の結果（-128〜127 の配列）を16進文字列に */
function bytesToHex(bytes) {
  return bytes.map(function (b) {
    var v = (b + 256) % 256;
    return (v < 16 ? '0' : '') + v.toString(16);
  }).join('');
}

/**
 * 1作品フォルダの情報から、シート1行分のデータ（列名 → 値）を作る。
 * @param {Object} input
 *   folderId, folderName, fingerprint, syncedAt
 *   files     : [{name,id,size,mimeType,updated}]（ショートカット・ゴミ箱は除去済み）
 *   metaText  : meta.json がちょうど1つのときその中身。それ以外は null
 *   metaReadError : meta.json を読む途中で失敗したときの説明（任意）
 * @return {Object} HEADERS の各列をキーに持つオブジェクト（値はすべて文字列）
 */
function buildRecord(input) {
  var errors = [];

  var parsed = parseFolderName(input.folderName);
  if (!parsed.ok) errors.push(parsed.error);

  var metaCount = input.files.filter(function (f) { return f.name === META_FILE_NAME; }).length;
  var meta = { author: '', purpose: '', status: '', tags: [], note: [] };
  if (metaCount === 0) {
    errors.push('meta.json がありません');
  } else if (metaCount > 1) {
    errors.push('meta.json が' + metaCount + '個あります（1つにしてください）');
  } else if (input.metaReadError) {
    errors.push('meta.json を読めません（' + input.metaReadError + '）');
  } else {
    var checked = checkMeta(input.metaText);
    meta = checked.meta;
    errors = errors.concat(checked.errors);
  }

  var thumb = pickThumbFile(input.files);
  var fileList = input.files.slice().sort(compareByName).map(function (f) {
    return { name: f.name, id: f.id, size: f.size, mimeType: f.mimeType };
  });

  return {
    folder_id: input.folderId,
    folder_name: input.folderName,
    date: parsed.date,
    name: parsed.name,
    author: meta.author,
    purpose: meta.purpose,
    status: meta.status,
    tags: meta.tags.join(', '),
    note: meta.note.join('\n'),
    thumb_id: thumb ? thumb.id : '',
    files: JSON.stringify(fileList),
    fingerprint: input.fingerprint,
    error: errors.join(' / '),
    synced_at: input.syncedAt
  };
}

/** 行データ（オブジェクト）→ シートに書く配列（HEADERS の順） */
function recordToRow(record) {
  return HEADERS.map(function (h) {
    var v = record[h];
    return v === undefined || v === null ? '' : String(v);
  });
}

/** シートから読んだ配列 → 行データ（オブジェクト）。セルの値は文字列にそろえる */
function rowToRecord(row) {
  var record = {};
  HEADERS.forEach(function (h, i) {
    record[h] = cellToText(row[i], h);
  });
  return record;
}

/**
 * セルの値を文字列に。列は書式「書式なしテキスト」で書くので普通は文字列が返るが、
 * 誰かが書式を変えると日付が Date で返ることがあるので、念のため直す。
 */
function cellToText(v, header) {
  if (v === undefined || v === null) return '';
  if (Object.prototype.toString.call(v) === '[object Date]') {
    if (isNaN(v.getTime())) return '';
    if (header === 'date') {
      // シートが日付と解釈した場合はスプシのタイムゾーンの 0 時になっている
      return Utilities.formatDate(v, Session.getScriptTimeZone(), 'yyyy-MM-dd');
    }
    return v.toISOString();
  }
  return String(v);
}

/** Drive の URL の組み立て（画面との約束どおり） */
function driveFolderUrl(id) { return 'https://drive.google.com/drive/folders/' + id; }
function driveFileUrl(id) { return 'https://drive.google.com/file/d/' + id + '/view'; }
function driveDownloadUrl(id) { return 'https://drive.google.com/uc?export=download&id=' + id; }
function driveThumbnailUrl(id) { return 'https://drive.google.com/thumbnail?id=' + id + '&sz=w600'; }

/** カンマ区切り → 配列（空は除く） */
function splitTags(text) {
  return String(text || '').split(',').map(function (t) { return t.trim(); }).filter(function (t) { return t !== ''; });
}

/** 改行区切り → 配列（空文字なら空配列） */
function splitNote(text) {
  var s = String(text || '');
  return s === '' ? [] : s.split(/\r?\n/);
}

/** files 列（JSON）を読む。壊れていたら空配列 */
function parseFilesCell(text) {
  try {
    var v = JSON.parse(String(text || '[]'));
    return Array.isArray(v) ? v : [];
  } catch (e) {
    return [];
  }
}

/**
 * 行データ → 画面用データ。error が空なら作品（item）、あれば要対応（issue）。
 * @param {Object} record rowToRecord の結果
 * @param {{sheetUrl:string, sheetGid:number, rowNumber:number}} where 行へのリンク用
 * @return {{item:Object}|{issue:Object}}
 */
function recordToGalleryEntry(record, where) {
  var folderUrl = driveFolderUrl(record.folder_id);
  if (record.error) {
    return {
      issue: {
        folderName: record.folder_name,
        problem: record.error,
        url: folderUrl,
        rowUrl: sheetRowUrl(where.sheetUrl, where.sheetGid, where.rowNumber)
      }
    };
  }
  var files = parseFilesCell(record.files);
  return {
    item: {
      folderId: record.folder_id,
      folderName: record.folder_name,
      folderUrl: folderUrl,
      date: record.date,
      name: record.name,
      author: record.author,
      purpose: record.purpose,
      status: record.status,
      tags: splitTags(record.tags),
      note: splitNote(record.note),
      thumbUrl: record.thumb_id ? driveThumbnailUrl(record.thumb_id) : null,
      photos: pickPhotoFiles(files).map(function (f) {
        return { name: f.name, url: driveThumbnailUrl(f.id) };
      }),
      files: files.map(function (f) {
        return { name: f.name, url: driveFileUrl(f.id), downloadUrl: driveDownloadUrl(f.id) };
      })
    }
  };
}

/** スプシの特定の行へのリンク（#gid=..&range=A行） */
function sheetRowUrl(sheetUrl, gid, rowNumber) {
  var base = String(sheetUrl).split('#')[0];
  return base + '#gid=' + gid + '&range=A' + rowNumber;
}

/** シートに書く順番：フォルダ名順（同名ならID順） */
function sortRecords(records) {
  return records.slice().sort(function (a, b) {
    return compareByName({ name: a.folder_name, id: a.folder_id }, { name: b.folder_name, id: b.folder_id });
  });
}

/**
 * 同期の結果を画面に出す文に。
 * @param {{done:boolean, checked:number, updated:number, removed:number}} r
 * @param {string} mode 'web'（画面のボタン）/ 'menu'（スプシのメニュー）/ 'trigger'
 */
function buildSyncMessage(r, mode) {
  var counts = r.checked + '件を確認、' + r.updated + '件を更新' + (r.removed ? '、' + r.removed + '件を削除' : '');
  if (r.done) return '同期しました（' + counts + '）';
  if (mode === 'web') return '途中まで同期しました（' + counts + '）。もう一度押すと続きから再開します';
  return '途中まで同期しました（' + counts + '）。続きは1分ほどで自動的に再開します';
}

/** 現在時刻（ミリ秒）。テストで時計を進めるために関数にしてある */
function nowMs() {
  return Date.now();
}

/** 同期時刻の文字列（スクリプトのタイムゾーン付き ISO 形式。例 2026-10-29T09:12:00+09:00） */
function nowIso_() {
  return Utilities.formatDate(new Date(nowMs()), Session.getScriptTimeZone(), "yyyy-MM-dd'T'HH:mm:ssXXX");
}


// =============================================================================
// エラーの扱い
//   画面に出すメッセージは日本語の Error で投げる。想定外の例外は、権限不足らしければ
//   決まり文句に言い換え、それ以外は「同期に失敗しました」を付けて投げ直す。
// =============================================================================

/** 画面にそのまま出してよいエラー */
function userError_(message) {
  var e = new Error(message);
  e.userFacing = true;
  return e;
}

/** 例外を画面向けの Error にする */
function toUserError_(e) {
  if (e && e.userFacing) return e;
  var msg = String(e && e.message ? e.message : e);
  if (/permission|not have access|access denied|権限|アクセス/i.test(msg)) {
    return userError_(MSG_PERMISSION);
  }
  return userError_('同期に失敗しました：' + msg);
}

/** fn を実行し、失敗したら画面向けの Error にして投げる */
function withUserErrors_(fn) {
  try {
    return fn();
  } catch (e) {
    throw toUserError_(e);
  }
}

/**
 * 同期の二重実行を防ぐ。スクリプト全体で1つのロックを取り、取れなければ投げる。
 * 誰が実行しても（閲覧者・トリガー・メニュー）同じロックを使う。
 */
function withSyncLock_(fn) {
  var lock = LockService.getScriptLock();
  if (!lock.tryLock(LOCK_WAIT_MS)) throw userError_(MSG_LOCKED);
  try {
    return fn();
  } finally {
    lock.releaseLock();
  }
}


// =============================================================================
// Drive の読み取り
// =============================================================================

/** スクリプトプロパティ ITEMS_FOLDER_ID のフォルダを開く。設定漏れ・誤りはわかる言葉で投げる */
function getItemsFolder_() {
  var id = PropertiesService.getScriptProperties().getProperty(PROP_ITEMS_FOLDER_ID);
  if (!id) {
    throw userError_('スクリプトプロパティ「' + PROP_ITEMS_FOLDER_ID + '」が設定されていません。' +
      'Apps Script の「プロジェクトの設定 → スクリプト プロパティ」に items フォルダのIDを入れてください');
  }
  try {
    return DriveApp.getFolderById(id);
  } catch (e) {
    throw userError_('items フォルダ（ID: ' + id + '）を開けません。' +
      'ITEMS_FOLDER_ID が正しいか、そのフォルダを見る権限があるかを確認してください');
  }
}

/**
 * items/ 直下の作品フォルダを並べる（名前順）。
 * ゴミ箱の中・先頭が _ のフォルダは除く。key は「名前＋ID」で、続きの位置の保存に使う。
 * @return {Array<{folder:Folder, id:string, name:string, key:string}>}
 */
function listItemFolders_(itemsFolder) {
  var list = [];
  var it = itemsFolder.getFolders();
  while (it.hasNext()) {
    var folder = it.next();
    if (folder.isTrashed()) continue;
    var name = folder.getName();
    if (isIgnoredFolderName(name)) continue;
    var id = folder.getId();
    list.push({ folder: folder, id: id, name: name, key: folderKey(name, id) });
  }
  return list.sort(function (a, b) { return a.key < b.key ? -1 : (a.key > b.key ? 1 : 0); });
}

/** 続きの位置を表すキー。同名フォルダがあっても順番が決まるようにIDを足す */
function folderKey(name, id) {
  return name + '\u0000' + id;
}

/**
 * 作品フォルダ直下のファイルを並べる。サブフォルダは見ない（作品フォルダはフラットの約束）。
 * ゴミ箱の中とショートカットは除く。
 * @return {Array<{name,id,size,mimeType,updated,file}>}
 */
function listFolderFiles_(folder) {
  var files = [];
  var it = folder.getFiles();
  while (it.hasNext()) {
    var f = it.next();
    if (f.isTrashed()) continue;
    var mimeType = f.getMimeType();
    if (mimeType === SHORTCUT_MIME_TYPE) continue;
    files.push({
      name: f.getName(),
      id: f.getId(),
      size: f.getSize(),
      mimeType: mimeType,
      updated: f.getLastUpdated().getTime(),
      file: f
    });
  }
  return files;
}

/**
 * 作品フォルダ1つを同期し、行データを返す。
 * fingerprint が前回と同じなら meta.json は読まずに前回の行をそのまま返す（速さのため）。
 * @param {{folder:Folder, id:string, name:string}} entry
 * @param {Object|undefined} previous 前回の行データ
 * @param {boolean} force true なら fingerprint が同じでも読み直す
 * @return {{record:Object, changed:boolean}}
 */
function syncOneFolder_(entry, previous, force, syncedAt) {
  var files = listFolderFiles_(entry.folder);
  var fingerprint = computeFingerprint(entry.name, files);
  if (!force && previous && previous.fingerprint === fingerprint) {
    return { record: previous, changed: false };
  }

  var metaFiles = files.filter(function (f) { return f.name === META_FILE_NAME; });
  var metaText = null;
  var metaReadError = '';
  if (metaFiles.length === 1) {
    try {
      metaText = metaFiles[0].file.getBlob().getDataAsString('UTF-8');
    } catch (e) {
      metaReadError = String(e && e.message ? e.message : e);
    }
  }

  var record = buildRecord({
    folderId: entry.id,
    folderName: entry.name,
    files: files,
    metaText: metaText,
    metaReadError: metaReadError,
    fingerprint: fingerprint,
    syncedAt: syncedAt
  });
  return { record: record, changed: true };
}

/** folder が parentId のフォルダの直下にあるか */
function isDirectChildOf_(folder, parentId) {
  var parents = folder.getParents();
  while (parents.hasNext()) {
    if (parents.next().getId() === parentId) return true;
  }
  return false;
}


// =============================================================================
// シートの読み書き
//   シートは1回で全部読み、メモリ上で更新して、最後にまとめて書く（1行ずつ書くと遅い）。
//   列はすべて「書式なしテキスト」にする。"2025-06-12" が日付に、16進の fingerprint が
//   数値に勝手に変換されるのを防ぐため。
// =============================================================================

/** items シートを返す。無ければ作り、見出しをそろえる（同期・初期設定用） */
function getOrCreateSheet_() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sheet = ss.getSheetByName(SHEET_NAME) || ss.insertSheet(SHEET_NAME);
  ensureHeader_(sheet);
  return sheet;
}

/** 1行目を見出しにする（違っていれば書き直し、メモを付ける） */
function ensureHeader_(sheet) {
  var range = sheet.getRange(1, 1, 1, HEADERS.length);
  var current = range.getValues()[0].map(function (v) { return String(v); });
  if (current.join('\t') !== HEADERS.join('\t')) {
    range.setNumberFormat('@').setValues([HEADERS]);
    range.setNote(HEADER_NOTE);
    range.setFontWeight('bold');
    sheet.setFrozenRows(1);
  }
}

/** データ行（2行目以降）をすべて読む。folder_id が空の行は無視する */
function readRecords_(sheet) {
  var last = sheet.getLastRow();
  if (last < 2) return [];
  var values = sheet.getRange(2, 1, last - 1, HEADERS.length).getValues();
  return values.map(rowToRecord).filter(function (r) { return r.folder_id !== ''; });
}

/** データ行をまとめて書き直す（フォルダ名順） */
function writeRecords_(sheet, records) {
  var last = sheet.getLastRow();
  if (last >= 2) sheet.getRange(2, 1, last - 1, HEADERS.length).clearContent();
  var sorted = sortRecords(records);
  if (sorted.length === 0) return;
  sheet.getRange(2, 1, sorted.length, HEADERS.length)
    .setNumberFormat('@')
    .setValues(sorted.map(recordToRow));
}

/** シートに「警告のみ」の保護をかける（既に保護があれば触らない） */
function protectSheet_(sheet) {
  var existing = sheet.getProtections(SpreadsheetApp.ProtectionType.SHEET);
  if (existing.length > 0) return false;
  // 完全な保護にすると、編集権限のある人が同期できなくなるので「警告のみ」にとどめる
  sheet.protect().setDescription(PROTECTION_DESCRIPTION).setWarningOnly(true);
  return true;
}


// =============================================================================
// 同期の本体
//   1. items/ 直下のフォルダを名前順に並べる（先頭 _ とゴミ箱は除く）
//   2. 前回止まった位置の次から1件ずつ fingerprint を比べ、違えば meta.json を読み直す
//   3. 時間の目安（約4.5分）を超えたら、そこまでをシートに書いて位置を保存し、止める
//   4. 最後まで見終えた回だけ、Drive から消えたフォルダの行を削除し、完了時刻を記録する
//      （途中で止まった回に削除すると、まだ見ていないだけの行を消してしまうため）
// =============================================================================

/**
 * @param {{mode:string, rebuild:boolean}} options
 *   mode    : 'web' / 'menu' / 'trigger'（メッセージの言い回しにだけ使う）
 *   rebuild : true ならシートのデータ行を消してから全件読み直す
 * @return {{done:boolean, checked:number, updated:number, removed:number, message:string}}
 */
function runSync_(options) {
  var mode = options.mode || 'web';
  return withSyncLock_(function () {
    var startedMs = nowMs();
    var props = PropertiesService.getScriptProperties();
    var itemsFolder = getItemsFolder_();
    var sheet = getOrCreateSheet_();

    var byId = {};
    if (options.rebuild) {
      props.deleteProperty(PROP_RESUME_AFTER);
    } else {
      readRecords_(sheet).forEach(function (r) { byId[r.folder_id] = r; });
    }

    var folders = listItemFolders_(itemsFolder);
    var resumeAfter = props.getProperty(PROP_RESUME_AFTER) || '';
    var todo = folders.filter(function (f) { return f.key > resumeAfter; });

    var syncedAt = nowIso_();
    var checked = 0;
    var updated = 0;
    var lastKey = resumeAfter;
    var timedOut = false;
    for (var i = 0; i < todo.length; i++) {
      // 少なくとも1件は進める（毎回0件で終わって先に進まない、を防ぐ）
      if (checked > 0 && nowMs() - startedMs > SYNC_TIME_BUDGET_MS) {
        timedOut = true;
        break;
      }
      var entry = todo[i];
      var result = syncOneFolder_(entry, byId[entry.id], false, syncedAt);
      byId[entry.id] = result.record;
      checked++;
      if (result.changed) updated++;
      lastKey = entry.key;
    }

    var removed = 0;
    if (!timedOut) {
      var alive = {};
      folders.forEach(function (f) { alive[f.id] = true; });
      Object.keys(byId).forEach(function (id) {
        if (!alive[id]) {
          delete byId[id];
          removed++;
        }
      });
    }

    writeRecords_(sheet, Object.keys(byId).map(function (id) { return byId[id]; }));

    if (timedOut) {
      props.setProperty(PROP_RESUME_AFTER, lastKey);
    } else {
      props.deleteProperty(PROP_RESUME_AFTER);
      props.setProperty(PROP_LAST_FULL_SYNC, syncedAt);
    }

    var r = { done: !timedOut, checked: checked, updated: updated, removed: removed };
    r.message = buildSyncMessage(r, mode);
    return r;
  });
}

/**
 * 1作品だけ同期し直す（詳細画面の「この作品だけ再同期」）。
 * fingerprint に関係なく meta.json を読み直す。フォルダが無い・ゴミ箱・先頭 _ ・
 * items/ の外に移された場合は、その行を削除する。
 */
function resyncItem_(folderId) {
  return withSyncLock_(function () {
    var itemsFolder = getItemsFolder_();
    var sheet = getOrCreateSheet_();
    var records = readRecords_(sheet);

    var folder = null;
    try {
      folder = DriveApp.getFolderById(String(folderId));
    } catch (e) {
      folder = null;
    }

    var reason = '';
    if (!folder) reason = 'フォルダが見つかりません';
    else if (folder.isTrashed()) reason = 'フォルダがゴミ箱に入っています';
    else if (isIgnoredFolderName(folder.getName())) reason = 'フォルダ名が ' + IGNORE_PREFIX + ' で始まっています';
    else if (!isDirectChildOf_(folder, itemsFolder.getId())) reason = 'フォルダが items の直下にありません';

    if (reason) {
      var rest = records.filter(function (r) { return r.folder_id !== String(folderId); });
      var hadRow = rest.length !== records.length;
      if (hadRow) writeRecords_(sheet, rest);
      return {
        done: true,
        message: hadRow ? '一覧から外しました（' + reason + '）' : '同期の対象ではありません（' + reason + '）'
      };
    }

    var name = folder.getName();
    var entry = { folder: folder, id: folder.getId(), name: name, key: folderKey(name, folder.getId()) };
    var previous = records.filter(function (r) { return r.folder_id === entry.id; })[0];
    var result = syncOneFolder_(entry, previous, true, nowIso_());
    var others = records.filter(function (r) { return r.folder_id !== entry.id; });
    writeRecords_(sheet, others.concat([result.record]));

    var rec = result.record;
    return {
      done: true,
      message: rec.error
        ? '「' + name + '」を再同期しました。直すところがあります：' + rec.error
        : '「' + name + '」を再同期しました'
    };
  });
}


// =============================================================================
// 画面（Webアプリ）から呼ばれる関数
//   google.script.run から呼ぶので、名前の最後に _ を付けない。
// =============================================================================

/** Webアプリの入口。index.html を返す */
function doGet() {
  return HtmlService.createTemplateFromFile('index')
    .evaluate()
    .setTitle(APP_TITLE)
    .addMetaTag('viewport', 'width=device-width, initial-scale=1');
}

/** index.html から <?!= include('guide') ?> で別の html を差し込むため */
function include(name) {
  return HtmlService.createHtmlOutputFromFile(name).getContent();
}

/**
 * 一覧を返す。シートを読むだけで Drive は見ないので速い。
 * error が空の行は items、error がある行は issues（「要対応」）に入れる。
 */
function getGalleryData() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sheet = ss.getSheetByName(SHEET_NAME);
  var syncedAt = PropertiesService.getScriptProperties().getProperty(PROP_LAST_FULL_SYNC) || null;
  var data = { syncedAt: syncedAt, sheetUrl: ss.getUrl(), items: [], issues: [] };
  if (!sheet) return data;

  var last = sheet.getLastRow();
  if (last < 2) return data;
  var values = sheet.getRange(2, 1, last - 1, HEADERS.length).getValues();
  var gid = sheet.getSheetId();
  values.forEach(function (row, i) {
    var record = rowToRecord(row);
    if (!record.folder_id) return;
    var entry = recordToGalleryEntry(record, { sheetUrl: data.sheetUrl, sheetGid: gid, rowNumber: i + 2 });
    if (entry.item) data.items.push(entry.item);
    else data.issues.push(entry.issue);
  });
  return data;
}

/**
 * 画面の「今すぐ同期」。時間切れでも続きのトリガーは作らない
 * （閲覧者のアカウントにトリガーが残らないように）。もう一度押せば続きから。
 * @return {{done:boolean, message:string}}
 */
function syncNow() {
  return withUserErrors_(function () {
    var r = runSync_({ mode: 'web' });
    return { done: r.done, message: r.message };
  });
}

/**
 * 詳細画面の「この作品だけ再同期」。
 * @return {{done:boolean, message:string}}
 */
function resyncItem(folderId) {
  return withUserErrors_(function () {
    return resyncItem_(folderId);
  });
}


// =============================================================================
// トリガー（毎日の同期と、時間切れの続き）
// =============================================================================

/** 毎日の時間トリガーから呼ばれる */
function dailySync() {
  runSyncFromTrigger_();
}

/** 時間切れの続き（1回限りのトリガー）。まず自分のトリガーを消してから続きを行う */
function continueSync() {
  deleteTriggersFor_(CONTINUE_HANDLER);
  runSyncFromTrigger_();
}

/**
 * トリガーから同期する。別の同期が実行中なら何もしない（続きの位置は保存されて
 * いるので、次の実行で拾われる）。時間切れなら続きのトリガーを作る。
 */
function runSyncFromTrigger_() {
  var r;
  try {
    r = runSync_({ mode: 'trigger' });
  } catch (e) {
    if (e && e.message === MSG_LOCKED) {
      Logger.log(MSG_LOCKED);
      return null;
    }
    throw e; // 失敗をトリガーの実行記録（とメール通知）に残す
  }
  if (!r.done) scheduleContinuation_();
  Logger.log(r.message);
  return r;
}

/** 1分後に1回だけ continueSync を呼ぶトリガーを作る（既にあれば作り直す） */
function scheduleContinuation_() {
  deleteTriggersFor_(CONTINUE_HANDLER);
  ScriptApp.newTrigger(CONTINUE_HANDLER).timeBased().after(CONTINUE_AFTER_MS).create();
}

/** 指定した関数を呼ぶトリガーを全部消す */
function deleteTriggersFor_(handlerName) {
  ScriptApp.getProjectTriggers().forEach(function (t) {
    if (t.getHandlerFunction() === handlerName) ScriptApp.deleteTrigger(t);
  });
}

/** 毎日の同期トリガーが無ければ作る。作ったら true */
function ensureDailyTrigger_() {
  var exists = ScriptApp.getProjectTriggers().some(function (t) {
    return t.getHandlerFunction() === DAILY_HANDLER;
  });
  if (exists) return false;
  ScriptApp.newTrigger(DAILY_HANDLER).timeBased().everyDays(1).atHour(DAILY_SYNC_HOUR).create();
  return true;
}


// =============================================================================
// スプシのメニューと初期設定
// =============================================================================

/** スプシを開いたときにメニュー「ギャラリー」を足す（単純トリガー） */
function onOpen() {
  SpreadsheetApp.getUi()
    .createMenu('ギャラリー')
    .addItem('今すぐ同期', 'menuSyncNow')
    .addItem('全部作り直す', 'menuRebuild')
    .addSeparator()
    .addItem('初期設定', 'menuSetup')
    .addToUi();
}

/** メニュー「今すぐ同期」。時間切れなら続きを1分後に自動で再開する */
function menuSyncNow() {
  runSyncFromMenu_(false);
}

/** メニュー「全部作り直す」。データ行を消して全件を読み直す */
function menuRebuild() {
  var ui = SpreadsheetApp.getUi();
  var answer = ui.alert('全部作り直す',
    'シートのデータ行を消して、items フォルダから全件を読み直します。よろしいですか？',
    ui.ButtonSet.OK_CANCEL);
  if (answer !== ui.Button.OK) return;
  runSyncFromMenu_(true);
}

/** メニュー「初期設定」 */
function menuSetup() {
  var ui = SpreadsheetApp.getUi();
  try {
    ui.alert('初期設定', setup(), ui.ButtonSet.OK);
  } catch (e) {
    ui.alert('初期設定できませんでした', toUserError_(e).message, ui.ButtonSet.OK);
  }
}

/** メニューからの同期（結果は画面右下の通知に出す） */
function runSyncFromMenu_(rebuild) {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  try {
    var r = runSync_({ mode: 'menu', rebuild: rebuild });
    if (!r.done) scheduleContinuation_();
    ss.toast(r.message, 'ギャラリー', 10);
    return r;
  } catch (e) {
    var ui = SpreadsheetApp.getUi();
    ui.alert('同期できませんでした', toUserError_(e).message, ui.ButtonSet.OK);
    return null;
  }
}

/**
 * 初期設定。何度実行しても同じ状態になる（トリガーを重複登録しない）。
 * - ITEMS_FOLDER_ID の確認（無い・開けないときはわかる言葉で止める）
 * - シート items と見出し、メモ、「警告のみ」の保護
 * - 毎日の同期トリガー
 * Apps Script のエディタから実行してもよい（その場合は結果がログに出る）。
 * @return {string} 結果の説明
 */
function setup() {
  var itemsFolder = getItemsFolder_();
  var sheet = getOrCreateSheet_();
  sheet.setFrozenRows(1);
  var protectedNow = protectSheet_(sheet);
  var triggerCreated = ensureDailyTrigger_();

  var lines = [
    'items フォルダ：' + itemsFolder.getName(),
    'シート「' + SHEET_NAME + '」：見出しを確認しました' + (protectedNow ? '（警告のみの保護をかけました）' : ''),
    '毎日の同期：' + (triggerCreated ? '登録しました（' + DAILY_SYNC_HOUR + '時台）' : '登録済みです'),
    '続けて「ギャラリー → 今すぐ同期」を実行してください'
  ];
  var message = lines.join('\n');
  Logger.log(message);
  return message;
}
