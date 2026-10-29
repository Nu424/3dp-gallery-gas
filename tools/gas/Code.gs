/**
 * 3Dプリント作品ギャラリー  Code.gs
 * =============================================================================
 * このファイルの役割
 *   1. 同期：Drive の items/ にある作品フォルダを読み、スプシ（シート items）に写す
 *   2. Webアプリのサーバー側：doGet（画面を返す）、getGalleryData（一覧を返す）、
 *      syncNow / resyncItem（画面のボタンから呼ばれる同期）、
 *      getThumbnails（スマホで読めなかった画像を data URL で返す）
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
 * 状態（meta.json の status）の選択肢。ここを変えれば検査も変わり、
 * getGalleryData の statuses として画面にも渡る。
 * この値と必須キーは fingerprint に含めているので、変えると次の同期で全作品が読み直される。
 * ほかに直す場所：
 *   - index.html の状態の色（使用中＝黄、参考＝白、引退＝グレー の対応）
 *   - guide.html の説明と AI 用プロンプトの「status は … のいずれか」
 *   - items/_template/README.txt の説明
 *   - fusion_export.py は status を空で書き出すので直さなくてよい
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

/**
 * 画像とみなす拡張子。写真・代表画像の判定に使う（シートの files 列には mimeType を
 * 保存しないので、画面用データでは拡張子だけで判定する）。
 * index.html のファイル分類（「画像」の欄）も同じ一覧にそろえること。
 */
var IMAGE_EXTENSIONS = ['png', 'jpg', 'jpeg', 'gif', 'webp'];

/** 同期で無視するファイルの拡張子（Fusion 書き出しスクリプトの一時ファイルなど） */
var IGNORE_FILE_EXTENSIONS = ['tmp'];

/** Drive のショートカットの mimeType（作品のファイルとしては扱わない） */
var SHORTCUT_MIME_TYPE = 'application/vnd.google-apps.shortcut';

/** スプシの1セルに入る文字数の上限。超えると書き込み全体が失敗するので、行を作る時点で収める */
var CELL_CHAR_LIMIT = 50000;

/**
 * 一覧の欠けに対する安全装置。全件を見終えたとき、既存の行がこの数以上あり、
 * その半数を超える行を消すことになる場合は、削除を見送って知らせる
 * （ITEMS_FOLDER_ID の誤りや権限の問題で一覧が丸ごと消えるのを防ぐ）。
 * 見つかったフォルダが0件なのに既存の行がある場合は、行数に関係なく見送る。
 * 本当に消したいときはメニュー「全部作り直す」を使う。
 */
var DELETE_GUARD_MIN_ROWS = 10;

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
var MSG_PERMISSION = '同期にはスプシの編集権限が必要です（items フォルダは閲覧できれば足ります）';
var MSG_LOCKED = '別の同期が実行中です。少し待ってからもう一度押してください';
var MSG_READ_PERMISSION = '一覧を読み込めません。スプシを閲覧する権限があるか確認してください';
var MSG_DELETE_SKIPPED_EMPTY = 'items フォルダの中が見つからないため、行の削除を見送りました。' +
  'ITEMS_FOLDER_ID と権限を確認してください';
var MSG_DELETE_SKIPPED_MANY = '消えたフォルダが多すぎるため、行の削除を見送りました（{n}行）。' +
  'ITEMS_FOLDER_ID と権限を確認し、問題なければスプシのメニュー「ギャラリー → 全部作り直す」を実行してください';

/** Webアプリの題名 */
var APP_TITLE = '3Dプリント作品ギャラリー';

/**
 * 画像の取り直し（getThumbnails）の決まり。
 * スマホのブラウザは GAS の iframe の中から drive.google.com/thumbnail を読むときに
 * Cookie を送らないため画像が出ない。画面は読めなかった画像だけ、サーバーに data URL で頼む。
 */
var THUMB_BATCH_MAX = 10;                    // 1回に受け付ける件数（これより後ろの ID は戻り値に入らない）
var THUMB_LARGE_MAX_BYTES = 2 * 1024 * 1024; // 詳細の大きな画像で、元のファイルをそのまま返す大きさの上限
var THUMB_CACHE_SECONDS = 6 * 60 * 60;       // キャッシュの保存時間（CacheService の上限の6時間）
var THUMB_CACHE_MAX_CHARS = 100000;          // CacheService の1件の上限（100KB）。余裕を見てこれを超える data URL はキャッシュしない


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

/** 同期で無視するファイルか（*.tmp など、IGNORE_FILE_EXTENSIONS の拡張子） */
function isIgnoredFileName(fileName) {
  return IGNORE_FILE_EXTENSIONS.indexOf(fileExtension(fileName)) >= 0;
}

/** 先頭の BOM（Windows のメモ帳などが付ける見えない文字）を取り除く */
function stripBom(text) {
  return String(text).replace(/^\uFEFF/, '');
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
 * フォルダ名 ＋ 各ファイルの「名前・ID・サイズ・更新日時」。ファイルは並べ替えるので、
 * Drive が返す順番が変わっても同じ値になる。フォルダ名を含めるのは、リネームだけ
 * では中のファイルが変わらないため。ID を含めるのは、同じ名前・サイズのファイルに
 * 差し替えたときも、シートに保存したファイルIDを新しくするため。
 * @param {Array<{name:string,id:string,size:number,updated:number}>} files updated はミリ秒
 */
function fingerprintSource(folderName, files) {
  var lines = files.map(function (f) {
    return [f.name, f.id, f.size, f.updated].join('\t');
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

  // ファイル一覧（mimeType は保存しない。画面では拡張子で種類を判断する）
  var fileList = input.files.slice().sort(compareByName).map(function (f) {
    return { name: f.name, id: f.id, size: f.size };
  });
  var filesJson = JSON.stringify(fileList);
  if (filesJson.length > CELL_CHAR_LIMIT) {
    // 1セルに収まらない。収まるところまで切り詰め、作品は「要対応」にする
    errors.push('ファイルが多すぎて一覧を保存できません（' + fileList.length + '個）。フォルダを分けてください');
    while (fileList.length > 0 && JSON.stringify(fileList).length > CELL_CHAR_LIMIT) fileList.pop();
    filesJson = JSON.stringify(fileList);
  }

  var record = {
    folder_id: input.folderId,
    folder_name: input.folderName,
    date: parsed.date,
    name: parsed.name,
    author: meta.author,
    purpose: meta.purpose,
    status: meta.status,
    tags: meta.tags.length ? JSON.stringify(meta.tags) : '', // JSON 配列（タグ名にカンマがあっても割れない）
    note: meta.note.join('\n'),
    thumb_id: thumb ? thumb.id : '',
    files: filesJson,
    fingerprint: input.fingerprint,
    error: '',
    synced_at: input.syncedAt
  };

  // 1セルの文字数上限を超える値は切り詰め、何を切ったかを error に残す。
  // 上限を超えたまま書くと、シートへの書き込み全体が失敗して一覧が更新されなくなるため。
  // （tags は切ると JSON として壊れるが、error が付くので画面には出ない）
  ['folder_name', 'name', 'author', 'purpose', 'status', 'tags', 'note'].forEach(function (key) {
    if (record[key].length > CELL_CHAR_LIMIT) {
      record[key] = record[key].slice(0, CELL_CHAR_LIMIT);
      errors.push('「' + key + '」が長すぎるため切り詰めました（' + CELL_CHAR_LIMIT + '文字まで）');
    }
  });
  record.error = truncateText(errors.join(' / '), CELL_CHAR_LIMIT);
  return record;
}

/** 文字列を max 文字までにする */
function truncateText(text, max) {
  var s = String(text);
  return s.length > max ? s.slice(0, max) : s;
}

/**
 * 行データ（オブジェクト）→ シートに書く配列（HEADERS の順）。
 * 念のためここでも1セルの上限で切る（古い行や想定外の値で書き込み全体が失敗しないように）。
 */
function recordToRow(record) {
  return HEADERS.map(function (h) {
    var v = record[h];
    return v === undefined || v === null ? '' : truncateText(v, CELL_CHAR_LIMIT);
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

/**
 * tags 列 → 配列。今の形式は JSON 配列（["顕微鏡","治具"]）。
 * 古い形式（カンマ区切り）も読めるようにしてある。
 */
function splitTags(text) {
  var s = String(text || '').trim();
  if (s.charAt(0) === '[') {
    try {
      var v = JSON.parse(s);
      if (isStringArray(v)) return v;
    } catch (e) {
      // 壊れた JSON はカンマ区切りとして読む
    }
  }
  return s.split(',').map(function (t) { return t.trim(); }).filter(function (t) { return t !== ''; });
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
        folderId: record.folder_id, // 画面の「この作品だけ再同期」で resyncItem に渡す
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

/**
 * getThumbnails に渡された ID を整える。ID らしい形の文字列だけを、重複を除いて
 * 先頭から THUMB_BATCH_MAX 件まで残す（配列でなければ空配列）。
 */
function normalizeThumbIds(ids) {
  if (!Array.isArray(ids)) return [];
  var out = [];
  ids.forEach(function (id) {
    if (typeof id === 'string' && /^[A-Za-z0-9_-]+$/.test(id) && out.indexOf(id) < 0) out.push(id);
  });
  return out.slice(0, THUMB_BATCH_MAX);
}

/**
 * 画面に出している画像のID（一覧に出ている作品の代表画像と写真）を { ID: true } で返す。
 * getThumbnails はこれ以外の ID を読まない。キャッシュは利用者全員で共有するので、
 * 任意のファイルを読ませると、見る権限の無い人にキャッシュ経由で渡ってしまうため。
 */
function galleryImageIds(records) {
  var ids = {};
  records.forEach(function (r) {
    if (r.error) return;
    if (r.thumb_id) ids[r.thumb_id] = true;
    pickPhotoFiles(parseFilesCell(r.files)).forEach(function (f) { ids[f.id] = true; });
  });
  return ids;
}

/** 画像のキャッシュのキー。縮小画像と大きな画像は別に持つ */
function thumbCacheKey(id, large) {
  return 'thumb:' + (large ? 'L:' : 'S:') + id;
}

/** Blob → data URL。Utilities は計算だけで Drive には触らない */
function blobToDataUrl(blob) {
  return 'data:' + (blob.getContentType() || 'image/png') + ';base64,' + Utilities.base64Encode(blob.getBytes());
}

/** シートに書く順番：フォルダ名順（同名ならID順） */
function sortRecords(records) {
  return records.slice().sort(function (a, b) {
    return compareByName({ name: a.folder_name, id: a.folder_id }, { name: b.folder_name, id: b.folder_id });
  });
}

/**
 * 同期の結果を画面に出す文に。
 * @param {{done:boolean, checked:number, updated:number, removed:number, warning:string}} r
 *   warning … 削除を見送ったときなどの注意書き（任意）
 * @param {string} mode 'web'（画面のボタン）/ 'menu'（スプシのメニュー）/ 'trigger'
 */
function buildSyncMessage(r, mode) {
  var counts = r.checked + '件を確認、' + r.updated + '件を更新' + (r.removed ? '、' + r.removed + '件を削除' : '');
  if (r.done) return '同期しました（' + counts + '）' + (r.warning ? '。' + r.warning : '');
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

/** 権限不足の例外らしいか（GAS の英語・日本語のメッセージに出る語で判定） */
function isPermissionError(e) {
  var msg = String(e && e.message ? e.message : e);
  return /permission|not have access|access denied|権限/i.test(msg);
}

/** 「見つからない」例外らしいか（getFolderById の失敗など） */
function isNotFoundError(e) {
  var msg = String(e && e.message ? e.message : e);
  return /could be found|not found|見つかりません|見つからない/i.test(msg);
}

/**
 * 例外を画面向けの Error にする。
 * @param {Object} [texts] 言い換えの文言 { permission: 権限不足のとき, prefix: それ以外の前置き }
 */
function toUserError_(e, texts) {
  texts = texts || {};
  if (e && e.userFacing) return e;
  if (isPermissionError(e)) return userError_(texts.permission || MSG_PERMISSION);
  var msg = String(e && e.message ? e.message : e);
  return userError_((texts.prefix || '同期に失敗しました：') + msg);
}

/** fn を実行し、失敗したら画面向けの Error にして投げる（texts は toUserError_ と同じ） */
function withUserErrors_(fn, texts) {
  try {
    return fn();
  } catch (e) {
    throw toUserError_(e, texts);
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
  return name + '\t' + id; // タブはフォルダ名にまず入らない区切り
}

/**
 * 作品フォルダ直下のファイルを並べる。サブフォルダは見ない（作品フォルダはフラットの約束）。
 * ゴミ箱の中・ショートカット・一時ファイル（*.tmp）は除く。
 * @return {Array<{name,id,size,mimeType,updated,file}>}
 */
function listFolderFiles_(folder) {
  var files = [];
  var it = folder.getFiles();
  while (it.hasNext()) {
    var f = it.next();
    if (f.isTrashed()) continue;
    if (isIgnoredFileName(f.getName())) continue;
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

/**
 * items/ 直下の一覧に無かったフォルダについて、その理由を説明する文を返す。
 * getFolderById が「見つからない」以外の理由で失敗したら投げ直す
 * （権限の問題などで、実際にはあるフォルダの行を消してしまわないように）。
 */
function whyNotSyncTarget_(folderId, itemsFolderId) {
  var folder;
  try {
    folder = DriveApp.getFolderById(folderId);
  } catch (e) {
    if (isNotFoundError(e)) return 'フォルダが見つかりません';
    throw e;
  }
  if (folder.isTrashed()) return 'フォルダがゴミ箱に入っています';
  if (isIgnoredFolderName(folder.getName())) return 'フォルダ名が ' + IGNORE_PREFIX + ' で始まっています';
  if (!isDirectChildOf_(folder, itemsFolderId)) return 'フォルダが items の直下にありません';
  return 'items フォルダの一覧に見つかりません';
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

/**
 * データ行をまとめて書き直す（フォルダ名順）。
 * 先に新しい行で上書きし、そのあと余った行だけを消す。先に全部消してから書くと、
 * 書き込みが失敗したときにシートが空のまま残り、ギャラリーが空になるため。
 */
function writeRecords_(sheet, records) {
  var oldLast = sheet.getLastRow();
  var sorted = sortRecords(records);
  if (sorted.length > 0) {
    sheet.getRange(2, 1, sorted.length, HEADERS.length)
      .setNumberFormat('@')
      .setValues(sorted.map(recordToRow));
  }
  var newLast = sorted.length + 1;
  if (oldLast > newLast) {
    sheet.getRange(newLast + 1, 1, oldLast - newLast, HEADERS.length).clearContent();
  }
}

/**
 * スプシに書けるかを、軽い書き込み（見出しのメモの付け直し）で先に確かめる。
 * Drive を走査してから最後の書き込みで失敗すると時間が無駄になるので、最初に試す。
 */
function assertCanWriteSheet_(sheet) {
  try {
    sheet.getRange(1, 1, 1, HEADERS.length).setNote(HEADER_NOTE);
  } catch (e) {
    throw userError_(MSG_PERMISSION);
  }
}

/**
 * 今の利用者がスプシを編集できるか（画面の「今すぐ同期」ボタンを出すかの判断用）。
 * Spreadsheet.getEditors() は編集権限の無い人が呼ぶと例外になるので、それで見分ける。
 * 判定に失敗したときに同期ボタンが消えると困るので、例外以外は true とする。
 */
function canEditSpreadsheet_(ss) {
  try {
    ss.getEditors();
    return true;
  } catch (e) {
    return false;
  }
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
//      ただし消える行が多すぎるとき（DELETE_GUARD_MIN_ROWS の説明）は削除を見送って知らせる
// =============================================================================

/**
 * 消えたフォルダの行を消してよいか判断する（純粋な関数）。
 * @param {number} existingRows 同期を始めたときにシートにあった行数
 * @param {number} foundFolders 今回 items/ に見つかったフォルダ数
 * @param {number} toRemove     消すことになる行数
 * @return {string} 見送る理由（画面に出す文）。消してよければ空文字
 */
function deletionGuardMessage(existingRows, foundFolders, toRemove) {
  if (toRemove === 0) return '';
  if (foundFolders === 0 && existingRows > 0) return MSG_DELETE_SKIPPED_EMPTY;
  if (existingRows >= DELETE_GUARD_MIN_ROWS && toRemove * 2 > existingRows) {
    return MSG_DELETE_SKIPPED_MANY.replace('{n}', String(toRemove));
  }
  return '';
}

/**
 * @param {{mode:string, rebuild:boolean}} options
 *   mode    : 'web' / 'menu' / 'trigger'（メッセージの言い回しにだけ使う）
 *   rebuild : true ならシートのデータ行を消してから全件読み直す（削除の安全装置も効かせない）
 * @return {{done:boolean, checked:number, updated:number, removed:number, warning:string, message:string}}
 */
function runSync_(options) {
  var mode = options.mode || 'web';
  return withSyncLock_(function () {
    var startedMs = nowMs();
    var props = PropertiesService.getScriptProperties();
    var sheet = getOrCreateSheet_();
    assertCanWriteSheet_(sheet);
    var itemsFolder = getItemsFolder_();

    var byId = {};
    var existingRows = 0;
    if (options.rebuild) {
      props.deleteProperty(PROP_RESUME_AFTER);
    } else {
      readRecords_(sheet).forEach(function (r) { byId[r.folder_id] = r; });
      existingRows = Object.keys(byId).length;
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
    var warning = '';
    if (!timedOut) {
      var alive = {};
      folders.forEach(function (f) { alive[f.id] = true; });
      var gone = Object.keys(byId).filter(function (id) { return !alive[id]; });
      warning = deletionGuardMessage(existingRows, folders.length, gone.length);
      if (!warning) {
        gone.forEach(function (id) { delete byId[id]; });
        removed = gone.length;
      }
    }

    writeRecords_(sheet, Object.keys(byId).map(function (id) { return byId[id]; }));

    if (timedOut) {
      props.setProperty(PROP_RESUME_AFTER, lastKey);
    } else {
      props.deleteProperty(PROP_RESUME_AFTER);
      // 削除を見送った回は「正常に全件を見終えた」とは言えないので、完了時刻を更新しない
      if (!warning) props.setProperty(PROP_LAST_FULL_SYNC, syncedAt);
    }

    var r = { done: !timedOut, checked: checked, updated: updated, removed: removed, warning: warning };
    r.message = buildSyncMessage(r, mode);
    return r;
  });
}

/**
 * 1作品だけ同期し直す（詳細画面の「この作品だけ再同期」）。
 * fingerprint に関係なく meta.json を読み直す。
 * 対象かどうかは、全体の同期と同じく「items/ 直下の一覧（ゴミ箱・先頭 _ を除く）に
 * あるか」で決める。一覧に無ければ行を削除する。理由の説明のために getFolderById も
 * 呼ぶが、「見つからない」以外の失敗（権限など）は投げ直し、行は消さない。
 */
function resyncItem_(folderId) {
  folderId = String(folderId || '');
  return withSyncLock_(function () {
    var sheet = getOrCreateSheet_();
    assertCanWriteSheet_(sheet);
    var itemsFolder = getItemsFolder_();
    var records = readRecords_(sheet);

    var entry = listItemFolders_(itemsFolder).filter(function (f) { return f.id === folderId; })[0];

    if (!entry) {
      var reason = whyNotSyncTarget_(folderId, itemsFolder.getId());
      var rest = records.filter(function (r) { return r.folder_id !== folderId; });
      var hadRow = rest.length !== records.length;
      if (hadRow) writeRecords_(sheet, rest);
      return {
        done: true,
        message: hadRow ? '一覧から外しました（' + reason + '）' : '同期の対象ではありません（' + reason + '）'
      };
    }

    var name = entry.name;
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
 * 戻り値の形は index.html と約束したもの（変えるときは画面側も直す）：
 *   { syncedAt, sheetUrl, statuses, canSync, items: [...], issues: [...] }
 */
function getGalleryData() {
  return withUserErrors_(function () {
    var ss = SpreadsheetApp.getActiveSpreadsheet();
    var sheet = ss.getSheetByName(SHEET_NAME);
    var syncedAt = PropertiesService.getScriptProperties().getProperty(PROP_LAST_FULL_SYNC) || null;
    var data = {
      syncedAt: syncedAt,
      sheetUrl: ss.getUrl(),
      statuses: STATUS_CHOICES.slice(),
      canSync: canEditSpreadsheet_(ss),
      items: [],
      issues: []
    };
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
  }, { permission: MSG_READ_PERMISSION, prefix: '一覧を読み込めませんでした：' });
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

/**
 * 画面が Drive の URL で読めなかった画像を data URL にして返す（スマホ向け。設定の THUMB_* を参照）。
 * - 通常は Drive が作る縮小画像（getThumbnail。幅220px程度）
 * - large=true（詳細の大きな画像）は、元のファイルが画像で THUMB_LARGE_MAX_BYTES 以下ならそのまま、
 *   それより大きければ縮小画像
 * - 一覧に出ている画像の ID だけを読む（galleryImageIds の説明）。それ以外は null
 * - 結果はスクリプトのキャッシュに6時間置く。1件の失敗では全体を落とさず、その件を null にする
 * 新しい権限は要らない（drive.readonly の範囲。CacheService は権限なしで使える）。
 * @param {string[]} ids ファイルID。1回に THUMB_BATCH_MAX 件まで（超えた分は戻り値に入らない）
 * @param {boolean} large 詳細の大きな画像用なら true
 * @return {Object} { ID: data URL または null }
 */
function getThumbnails(ids, large) {
  return withUserErrors_(function () {
    var list = normalizeThumbIds(ids);
    var result = {};
    if (!list.length) return result;
    var big = large === true;
    var cache = CacheService.getScriptCache();
    var cached = {};
    try {
      cached = cache.getAll(list.map(function (id) { return thumbCacheKey(id, big); })) || {};
    } catch (e) {
      cached = {}; // キャッシュが読めなくても Drive から読めばよい
    }

    var missing = [];
    list.forEach(function (id) {
      var hit = cached[thumbCacheKey(id, big)];
      if (hit) result[id] = hit;
      else missing.push(id);
    });
    if (!missing.length) return result;

    var sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(SHEET_NAME);
    var allowed = sheet ? galleryImageIds(readRecords_(sheet)) : {};
    var toCache = {};
    missing.forEach(function (id) {
      result[id] = null;
      if (!allowed[id]) return;
      try {
        result[id] = readThumbDataUrl_(id, big);
      } catch (e) {
        Logger.log('画像を読めませんでした（' + id + '）：' + (e && e.message ? e.message : e));
      }
      if (result[id] && result[id].length <= THUMB_CACHE_MAX_CHARS) toCache[thumbCacheKey(id, big)] = result[id];
    });
    if (Object.keys(toCache).length) {
      try {
        cache.putAll(toCache, THUMB_CACHE_SECONDS);
      } catch (e) {
        // キャッシュに置けなくても、画面には返す
      }
    }
    return result;
  }, { permission: MSG_READ_PERMISSION, prefix: '画像を読み込めませんでした：' });
}

/** 画像1件を data URL で返す（getThumbnails の中身）。縮小画像が無ければ null */
function readThumbDataUrl_(id, large) {
  var file = DriveApp.getFileById(id);
  if (large && file.getSize() <= THUMB_LARGE_MAX_BYTES && String(file.getMimeType()).indexOf('image/') === 0) {
    return blobToDataUrl(file.getBlob());
  }
  var thumb = file.getThumbnail();
  return thumb ? blobToDataUrl(thumb) : null;
}


// =============================================================================
// トリガー（毎日の同期と、時間切れの続き）
//
// 名前の最後に _ を付けていない理由：トリガーやメニューから呼ぶ関数は、エディタの
// 「実行」やトリガー設定画面で選べるよう公開関数にしておく（_ 付きの非公開関数を
// トリガー・メニューから呼べるかは保証されていないため）。その代わり、これらは
// google.script.run からも呼べてしまう。呼ばれても、編集権限が無ければ同期は
// 権限エラーで止まり、menu* は画面の外では getUi() が失敗するだけなので、害は小さい。
// =============================================================================

/** 毎日の時間トリガーから呼ばれる */
function dailySync() {
  runSyncFromTrigger_(false);
}

/**
 * 時間切れの続き（1回限りのトリガー）。まず自分のトリガーを消してから続きを行う。
 * 別の同期が実行中でロックが取れなければ、1分後にもう一度挑戦する。
 */
function continueSync() {
  deleteTriggersFor_(CONTINUE_HANDLER);
  runSyncFromTrigger_(true);
}

/**
 * トリガーから同期する。時間切れなら続きのトリガーを作る。
 * 別の同期が実行中なら、retryOnLock のときだけ続きのトリガーを作り直す
 * （毎日の同期は、実行中の同期が続きを引き受けているはずなので何もしない）。
 */
function runSyncFromTrigger_(retryOnLock) {
  var r;
  try {
    r = runSync_({ mode: 'trigger' });
  } catch (e) {
    if (e && e.message === MSG_LOCKED) {
      Logger.log(MSG_LOCKED);
      if (retryOnLock) scheduleContinuation_();
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
//   menu* と setup も、上の「トリガー」の説明と同じ理由で公開関数にしている。
//   setup を google.script.run から呼ばれた場合、編集権限のある人なら、その人の
//   アカウントに毎日のトリガーが1つできることがある（重複は作らない）。害は小さい。
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
