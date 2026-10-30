# 開発手引き（DEVELOPMENT）

**この文書は誰向けか**：コードを改修する人（と、改修を頼まれたAIエージェント）。4ファイルの役割、画面とサーバーの約束、スプシの列、**データ仕様（このリポジトリでの正）**、仕様を変えるときに直す箇所、動作確認の手順、Fusionスクリプトの構成をまとめています。AIに改修を頼む方法は [AI_GUIDE.md](AI_GUIDE.md) にあります。

## 目次

1. [構成と4ファイルの役割](#構成と4ファイルの役割)
2. [Code.gs の関数](#codegs-の関数)
3. [画面とサーバーの約束](#画面とサーバーの約束)
4. [スプシの列](#スプシの列)
5. [データ仕様](#データ仕様)
6. [データ仕様を変えるときに直す箇所](#データ仕様を変えるときに直す箇所)
7. [ローカルでの動作確認](#ローカルでの動作確認)
8. [本番での確認手順](#本番での確認手順)
9. [Fusionスクリプトの構成](#fusionスクリプトの構成)
10. [Fusion API 照合表](#fusion-api-照合表)
11. [確認したFusionのバージョン](#確認したfusionのバージョン)

---

## 構成と4ファイルの役割

方針：外部ライブラリ・GASの拡張サービスは使わない。コピペ（4ファイル＝`Code.gs` `index.html` `guide.html` `appsscript.json` の貼り付け＋スクリプトプロパティ1つ）で動くことを守る。

```
3dp-gallery-gas/（リポジトリ）
├── docs/               計画書・作業計画・画面モック（設計の記録。Driveには置かない）
├── tools/              ← 中身を丸ごと Drive の 3Dギャラリー/tools/ にコピーする
│   ├── gas/            Code.gs, index.html, guide.html, appsscript.json
│   ├── fusion_export/  fusion_export.py, fusion_export.manifest
│   ├── items_template/_template/   meta.json, README.txt（Drive の items/ へコピーする雛形）
│   └── docs/           この文書たち
└── dev/                ローカル検証用（リポジトリにだけあり、Drive には置かない）
```

| ファイル | 役割 |
| --- | --- |
| `tools/gas/Code.gs` | サーバー側。同期処理、`doGet`、画面から呼ぶ関数、トリガー、スプシのメニュー、`setup()` |
| `tools/gas/index.html` | 画面（一覧と詳細）。見た目とブラウザ側の処理はすべてここ。`<?!= include('guide') ?>` で `guide.html` を読み込む。GASとの境目は `loadData` / `syncNow` / `resyncItem` と、画像の取り直し（`getThumbnails`）だけ |
| `tools/gas/appsscript.json` | GASの設定ファイル（マニフェスト）。`oauthScopes`（`drive.readonly` / `spreadsheets` / `script.scriptapp` / `script.container.ui`）で許可の範囲を絞り、`webapp`（`executeAs: USER_ACCESSING`、`access: DOMAIN`）を決める。エディタでは「プロジェクトの設定」で表示をオンにして編集する。貼り方は [SETUP.md](SETUP.md#4つ目appsscriptjson-を置き換える許可の範囲を絞る) |
| `tools/gas/guide.html` | 「作品を追加する」パネルの本文（HTMLの断片）。文章の修正はこのファイルだけで済む。構成は、用意するものの順の段（1 3Dデータ → 2 meta.json → 3 フォルダ → 4 同期）で、各段に「手でやる」「自動でやる」の枠（`.way` の `data-way`）を置き、段ごとの切り替え（`.way-seg`）で片方だけ見せる。切り替えは全段で連動し（`.sheet-body` の `data-way`。`setGuideWay`）、押した切り替えの画面上の位置を保つ。PC は2つの枠を同じ升に重ねて見せない方を `visibility:hidden` にし、切り替えても段の高さが変わらない。960px 以下は余白が大きくなるので `display:none`（位置の保持だけで、ずれを抑える）。AIに渡すプロンプトは `#ai-prompt` の1か所にまとめてある（計画書の版から改訂済み。こちらが正）。**スクリプトレット（`<?` で始まる構文）は書かない** |

`Code.gs` は上から「設定」→「純粋な関数」→「エラーの扱い」→「Driveの読み取り」→「シートの読み書き」→「同期の本体」→「画面から呼ばれる関数」→「トリガー」→「スプシのメニューと初期設定」の順に並んでいる。変えたくなる値は先頭の「設定」にある。関数名の末尾が `_` のものは非公開（画面やメニューから直接呼べない）。テストから差し替えるため、一部の設定は `var` で宣言されている。

## Code.gs の関数

### 純粋な関数（Drive・シートに触らない。Nodeのテストで検証済み）

| 関数 | 内容 |
| --- | --- |
| `parseFolderName(folderName)` | `YYYYMMDD_名前` を日付と名前に分ける。日付の実在を検査 |
| `isRealDate` / `isIgnoredFolderName` / `isIgnoredFileName` / `stripBom` | 日付の実在判定／先頭 `_` の判定／無視するファイル（`*.tmp`）の判定／BOM除去 |
| `checkMeta(text)` | `meta.json` の文字列を検査し、整形した meta とエラー配列を返す |
| `isStringArray` / `fileExtension` / `isImageFile` / `compareByName` | 補助 |
| `pickThumbFile(files)` / `pickPhotoFiles(files)` | 代表画像の選択／`photo_` の写真の選択 |
| `fingerprintSource` / `computeFingerprint` / `bytesToHex` | 指紋の元文字列と SHA-256（`Utilities` は計算のみ） |
| `buildRecord(input)` | 1作品フォルダの情報から、シート1行分（列名→値）を作る |
| `recordToRow` / `rowToRecord` / `cellToText` | 行データ⇄シート配列 |
| `recordToGalleryEntry(record, where)` | 行データ→画面用の item または issue |
| `splitTags` / `splitNote` / `parseFilesCell` / `sortRecords` / `sheetRowUrl` / `truncateText` | 補助。`splitTags` は JSON 配列を読み、古いカンマ区切りも読める。`truncateText` はセル上限での切り詰め |
| `deletionGuardMessage(existing, found, toRemove)` | 消えた行の削除を見送るべきかの判断（理由の文、無ければ空） |
| `isPermissionError` / `isNotFoundError` | 例外が権限不足／見つからないらしいかの判定 |
| `driveFolderUrl` / `driveFileUrl` / `driveDownloadUrl` / `driveThumbnailUrl` | URLの組み立て |
| `buildSyncMessage(r, mode)` | 同期結果の文（mode: web / menu / trigger） |
| `normalizeThumbIds(ids, max)` / `galleryImageIds` / `thumbCacheKey` / `blobToDataUrl` / `isBrowserImageMime` | 画像の取り直し：IDの整理（重複除去・上限件数）／一覧に出ている画像のIDの集合／キャッシュのキー／data URL 化／ブラウザで出せる画像形式か |
| `nowMs` / `nowIso_` | 現在時刻（テストで差し替え） |

### I/O（Drive・シート・Properties・Lock・Trigger に触る）

| 関数 | 内容 |
| --- | --- |
| `getItemsFolder_()` | `ITEMS_FOLDER_ID` のフォルダを開く。設定漏れ・誤りはわかる言葉で投げる |
| `listItemFolders_` / `listFolderFiles_` / `syncOneFolder_` / `isDirectChildOf_` / `whyNotSyncTarget_` | フォルダ・ファイルの列挙（ゴミ箱・ショートカット・`*.tmp` を除く）、1フォルダの同期、一覧に無いフォルダの理由の説明 |
| `getOrCreateSheet_` / `ensureHeader_` / `readRecords_` / `writeRecords_` / `protectSheet_` | シートの読み書き。列は「書式なしテキスト」。1回で読み、まとめて書く。`writeRecords_` は新しい行で上書きしてから余りを消す（書き込み失敗でシートが空にならないように） |
| `assertCanWriteSheet_` / `canEditSpreadsheet_` | 同期の前にスプシへ書けるか確かめる（書けなければ `MSG_PERMISSION`）／編集権限の有無（`getGalleryData` の `canSync`） |
| `runSync_(options)` | 同期の本体（時間切れの区切り、続きの位置の保存、ロック） |
| `resyncItem_(folderId)` | 1作品だけの再同期 |
| `withSyncLock_` / `userError_` / `toUserError_` / `withUserErrors_` | ロックとエラーの言い換え |
| `runSyncFromTrigger_` / `scheduleContinuation_` / `deleteTriggersFor_` / `ensureDailyTrigger_` | トリガー |
| `runSyncFromMenu_(rebuild)` | メニューからの同期 |

### 公開関数（画面・メニュー・トリガーから呼ばれる）

| 関数 | 呼び出し元 | 内容 |
| --- | --- | --- |
| `doGet()` | Webアプリ | `index` を評価して返す |
| `include(name)` | `index.html` | 別のHTMLファイルを差し込む |
| `getGalleryData()` | 画面 | 一覧を返す（シートを読むだけ） |
| `syncNow()` | 画面の「今すぐ同期」 | 同期（続きのトリガーは作らない） |
| `resyncItem(folderId)` | 詳細の「この作品だけ再同期」 | 1件の再同期 |
| `getThumbnails(ids, large)` | 画面（Driveの画像URLが読めなかったとき） | 画像を data URL で返す（下の「画像の取り直し」） |
| `dailySync()` / `continueSync()` | トリガー | 毎日の同期／時間切れの続き |
| `onOpen()` | スプシを開いたとき | メニュー「ギャラリー」を追加 |
| `menuSyncNow` / `menuRebuild` / `menuSetup` | メニュー | 今すぐ同期／全部作り直す／初期設定 |
| `setup()` | メニュー・エディタ | 初期設定（何度実行しても同じ状態） |

設計上の要点：

- **時間切れ対策**：名前順に処理し、約4.5分（`SYNC_TIME_BUDGET_MS`）で区切る。続きの位置を `SYNC_RESUME_AFTER`（スクリプトプロパティ、内部用）に保存し、メニュー・トリガー経由なら1分後の1回限りトリガーで再開。消えたフォルダの行の削除は全件を見終えた回だけ。全件完了時に `SYNC_LAST_COMPLETED_AT` を記録（画面の「最終同期」）。
- **二重実行**：`LockService.getScriptLock()`（待ち5秒）。続きのトリガー（`continueSync`）がロックを取れなかったときは、1分後にもう一度挑戦する。
- **同期前の権限確認**：`runSync_` / `resyncItem_` はまず `assertCanWriteSheet_` でスプシに書けるかを試し、無ければすぐ「同期にはスプシの編集権限が必要です（items フォルダは閲覧できれば足ります）」を返す（`items/` は閲覧でよい。Drive のスコープは `drive.readonly`）。
- **削除の安全装置**：全件を見終えたとき、`items/` で見つかったフォルダが0件なのに既存の行がある、または既存の行が `DELETE_GUARD_MIN_ROWS`（10）以上で半数超を消すことになる場合は、削除を見送ってメッセージを返し、完了時刻も更新しない。「全部作り直す」には効かない。
- **セル上限**：1セル50000文字（`CELL_CHAR_LIMIT`）。超える値は切り詰めて `error` に理由を残す（作品は要対応になる）。
- **指紋**：フォルダ名＋各ファイルの名前・**ID**・サイズ・更新日時＋**検査ルール（`STATUS_CHOICES` と `REQUIRED_META_KEYS`）**。ルールを変えると次の同期で全作品が読み直される。
- **ユーザーが設定するスクリプトプロパティは `ITEMS_FOLDER_ID` のみ**。`SYNC_RESUME_AFTER` と `SYNC_LAST_COMPLETED_AT` はコードが管理する。
- **シートの列順や追加列を変えたら**「全部作り直す」が必要（`HEADERS` の変更）。

## 画面とサーバーの約束

画面（`index.html`）はサーバーを `google.script.run` 経由で4つの関数（`getGalleryData` / `syncNow` / `resyncItem` / `getThumbnails`）だけ呼ぶ。失敗時は日本語のメッセージ入りの `Error` が投げられ、`withFailureHandler` の `err.message` で表示される。

### `getGalleryData()` の戻り値

```js
{
  syncedAt: "2026-10-30T04:12:00+09:00" | null,  // 最後に全件を見終えた時刻（削除を見送った回は更新されない）。未同期なら null
  sheetUrl: "https://docs.google.com/spreadsheets/d/…/edit",
  statuses: ["使用中", "参考", "引退"],           // STATUS_CHOICES（並び順どおり。画面の状態の選択肢）
  canSync: true | false,                          // スプシの編集権限があるか。false なら画面は同期ボタンを無効にする
  items: [ {                                      // error が空の行
    folderId, folderName, folderUrl,
    date: "2025-06-12", name: "流路セルホルダー",
    author, purpose, status,                      // status は statuses のどれか
    tags: ["顕微鏡", "治具"],
    note: ["M3ネジ×4で固定。", …],               // 1要素＝1行
    thumbUrl: "https://drive.google.com/thumbnail?id=…&sz=w600" | null,
    photos: [ { name, url } ],                    // photo_ で始まる画像（サムネイルURL）
    files:  [ { name, url, downloadUrl } ]        // フォルダ内の全ファイル
  } ],
  issues: [ {                                     // error がある行（「要対応」）
    folderId /* 「再同期」ボタンで resyncItem に渡す */,
    folderName, problem /* error 列の文 */,
    url /* Driveのフォルダ */, rowUrl /* スプシの該当行 */
  } ]
}
```

`getGalleryData` の失敗は日本語のメッセージ入りの `Error`（権限不足なら「一覧を読み込めません。スプシを閲覧する権限があるか確認してください」）。画面は `statuses` を使い、items にだけある未知の状態もグレーの破線枠（`st-other`）で表示する（色が付くのは既知の3種）。

URLの形：サムネイル `…/thumbnail?id=<id>&sz=w600`、ファイル `…/file/d/<id>/view`、ダウンロード `…/uc?export=download&id=<id>`、フォルダ `…/drive/folders/<id>`。画像が読めないときは、下の「画像の取り直し」を1回試し、それでもだめなら `index.html` 側でフォルダIDから決めた形と色のアイコンに差し替える。

### 画像の取り直し `getThumbnails(ids, large)`

スマホのブラウザは、GAS の iframe の中から drive.google.com の画像を読むときに Cookie を送らないため、サムネイルURLが失敗する（2026-10-30 の実機確認。PC の Chrome では出る）。そこで画面は、URL で読めなかった画像をサーバーに頼む。

```js
getThumbnails(["<ファイルID>", …], large) → { "<ファイルID>": "data:image/png;base64,…" | null }
```

サーバー側（`Code.gs`）：

- 1回に最大10件（`THUMB_BATCH_MAX`）。`large=true` は2件まで（`THUMB_LARGE_BATCH_MAX`。元のファイルは大きいので）。超えた分は戻り値に入らない。
- 通常は `getThumbnail()`（Driveの縮小画像。幅220px程度）。`large=true`（詳細の大きな画像）は、MIME が `image/png`・`image/jpeg`・`image/gif`・`image/webp`（`THUMB_LARGE_MIME_TYPES`、判定は `isBrowserImageMime`）で 2MB（`THUMB_LARGE_MAX_BYTES`）以下のときだけ元のファイル。HEIC・TIFF などブラウザで出せない形式や、大きいものは縮小画像。
- **一覧に出ている作品の代表画像と写真のIDしか読まない**（それ以外は null）。**キャッシュを引く前に**シートを1回読んで一覧で絞るので、一覧から外れたIDはキャッシュにあっても null。キャッシュ（`CacheService.getScriptCache()`、6時間）は利用者全員で共有なので、絞らないと、見る権限の無い人にキャッシュ経由で渡ってしまうため。100KB を超える値はキャッシュしない。
- 1件の失敗は、その件だけ null にする。
- 新しい許可（スコープ）は要らない（`drive.readonly` で足りる）。

画面側（`index.html`）：

- 頼むのは、**画面に見えている画像とその 200px 先まで**だけ（IntersectionObserver。見張りの枠は、PC は各ペイン、960px 以下はページ）。同時実行は2本まで（`THUMB_PARALLEL`）で、残りは順番待ち（`pumpThumbs`）。送る前に画面から離れたものは取り消す。取り込み済み・順番待ち・返事待ちのものは頼み直さない。縮小画像は10件、大きな画像は2件ずつ分けて呼ぶ。
- 一度サーバーで取れた端末では、以降 URL を試さず最初からサーバーに頼む（ちらつきを減らすため）。
- 返ってきた data URL は Blob にして `blob:` の URL で表示する（1キーにつき1回だけ作る。描き直しの innerHTML を短くするため）。`blob:` の画像が表示できなければ（GAS の iframe の制限に備えて）、その端末では以降 data URL で表示する（`useDataUrl`。そのため data URL の文字列も持つ）。data URL でも表示できないときだけ、次の項目に進む。
- 大きな画像が表示できなければ、一度だけ縮小画像で頼み直す。それも表示できなければ形のアイコンにし、以降は頼み直さない。

見張りの枠は、PC は各ペイン、960px 以下は一覧がページで、重ねた詳細はその要素自身。960px 以下の詳細は閉じている間も `overflow-y:auto`（`display:none`）なので、開け閉めで枠は変わらない。

### 幅の段階と、スマホの重なり（第3ラウンド）

| 幅 | 配置 |
| --- | --- |
| 1280px 以上 | 3列（絞り込み・一覧・詳細）。**主な利用環境なので、見た目を変えるときは慎重に** |
| 961〜1279px | 3列。絞り込みは最初だけたたむ（`filtersOpen` の初期値が `(min-width:1280px)`）。利用者が開け閉めしたら、それを保つ |
| 960px 以下 | 1列。ヘッダーは1行で上に固定し、ボタンは絵だけにする（名前は `.btn-text` で読み上げる）。その下に検索欄と「絞り込み」ボタンを固定する。一覧のカードは2列。要対応の帯は1行にたたむ（`state.issuesOpen`） |

960px 以下の重なりは3つ（絞り込みシート・詳細・作品を追加するパネル）で、`applyLayers` が一手に扱う。dialog の属性、後ろの `inert`、body のスクロールの固定と復元（`setScrollLock`）を受け持つ。

- 絞り込みシートは PC と**同じ DOM**。`.f-sheet` は PC では `display:contents`（見た目に影響しない）、960px 以下では下からの全画面シートになる。部品を二重に持たない。
- 詳細は右から全画面で重なる。開くとフォーカスは「← 一覧」へ移り、閉じると押したカードかリストの行へ戻る。Esc で閉じる。Tab は中で回る。
- 960px をまたいだら（`onNarrowChange`）、重なりを解き、見張りを作り直す。

### 作品へのリンクと「戻る」

画面は `google.script.run` の4関数のほかに、`google.script.history`（`push` / `replace` / `setChangeHandler`）と `google.script.url.getLocation` を使う。`Code.gs` の `doGet` は変えていない。`google.script.history` には back が無いので、閉じるときは `window.history.back()` を呼ぶ。

- 開いている重なりは `state.layer` の1つだけ（null・`guide`・`sheet`・`detail`）。別のものを開くと、前のものは閉じる。開け閉めは `openLayer(kind, id, fromHistory)` と `closeLayer(fromHistory)` だけで行う。
- 履歴の状態は `histLayer`（今の段に積んでいる重なり。null なら一覧の段）の1つ。段は一覧の段の上に**高々1つ**。state は `{overlay:'detail', item}`（URL は `?item=<フォルダID>`）、`{overlay:'sheet'}`、`{overlay:'guide'}`。
- 960px 以下で開くとき：積んでいなければ push、積んでいれば replace（載せ替え）。積み重ねると、一覧に戻るまで何度も「戻る」を押すことになるため。
- PC では push しない。作品を選ぶと replace で `?item=` を替える（積んでいる段があれば、その state のまま）。幅を広げても `state.layer` と段は残す（狭く戻すとまた重なる）。最初の作品を自動で選んだときは URL を変えない。
- 画面の操作で閉じるとき（×・← 一覧・n件を表示・Esc）：積んでいれば `history.back()`。600ms 待っても返事が無ければ `replace(null, {})` にする（空振りは1回で済む）。返事待ちの間に開いた重なりは、返事が来てから push し、待ち時間を過ぎたら捨てる（`backWait`）。積んでいない詳細を閉じたときは `replace(null, {})` で `?item=` を外す。
- 「戻る」「進む」（`setChangeHandler`）：来た段に overlay があれば、その重なりを開く。無い段なら、積んでいたときだけ閉じる（遅れて届いた返事で、あとから開いた重なりを閉じないため）。自分の back への返事は無視する。
- `?item=` で始まったとき：960px 以下では `replace(null, {})` で一覧の段を作ってから詳細を push する（「戻る」1回で一覧、2回でアプリの外）。PC では選ぶだけ。一覧に無い ID なら `replace(null, {})` で外す。
- **`USE_HISTORY_PUSH = false`** にすると push しなくなる（`?item=` の replace だけ）。GAS の iframe で back が効かないと分かったとき用で、「戻る」で閉じる機能は無くなる。
- プレビューでは `&histdelay=<ms>`（「戻る」の知らせを遅らせる）と `&backfail=1`（back を効かなくする）で不調を再現できる。筋書きの再現は `dev/preview/out/hist-m3.sh`。

アクセシビリティ：カードとリストの行は全体が1つのボタンで、`aria-labelledby` が名前、`aria-describedby` が用途・状態・日付を指す。リストの行のフォーカス枠は内側に描く（`.list` の `overflow:hidden` で切れるため）。

### `syncNow()` / `resyncItem(folderId)` の戻り値

```js
{ done: true | false, message: "同期しました（12件を確認、2件を更新）" }
```

- `done: false` は時間切れで途中まで。画面は `message` を警告色で出し、ボタンを押せる状態に戻す（もう一度押すと続きから）。
- `resyncItem` の `message` は「『名前』を再同期しました」「…直すところがあります：<error>」「一覧から外しました（理由）」など。
- どちらも、ロックが取れなければ「別の同期が実行中です…」、権限不足なら「同期にはスプシの編集権限が必要です（items フォルダは閲覧できれば足ります）」、その他は「同期に失敗しました：…」の `Error` を投げる。
- `syncNow` の `message` には、削除を見送った場合の注意（「…行の削除を見送りました」）が付くことがある。

## スプシの列

シート名 `items`。1行目が見出し（メモ「編集は meta.json で」）。2行目以降が1作品1行。列順は `Code.gs` の `HEADERS`。すべて「書式なしテキスト」。

| 列 | 内容 |
| --- | --- |
| `folder_id` | 作品フォルダのID（行の主キー） |
| `folder_name` | フォルダ名そのまま |
| `date` | フォルダ名から分解した日付（`YYYY-MM-DD`）。分解できなければ空 |
| `name` | フォルダ名から分解した名前 |
| `author` / `purpose` / `status` | `meta.json` から |
| `tags` | **JSON 配列**の文字列（`["顕微鏡","治具"]`。タグ名にカンマがあっても割れない）。タグが無ければ空。古いカンマ区切りも読める |
| `note` | 改行区切りの文字列 |
| `thumb_id` | 代表画像のファイルID（無ければ空） |
| `files` | フォルダ内ファイルのJSON配列 `[{name,id,size}]`（名前順。**mimeType は保存しない**。ショートカット・ゴミ箱・`*.tmp` を除く）。画面は拡張子で種類を分ける |
| `fingerprint` | SHA-256 の16進。差分判定用（フォルダ名、各ファイルの名前・ID・サイズ・更新日時、検査ルールから計算） |
| `error` | 不備の内容（` / ` 区切り）。**空ならギャラリーに表示、あれば要対応**。セル上限での切り詰めもここに記録 |
| `synced_at` | その行を最後に更新した時刻（ISO形式） |

---

## データ仕様

**このリポジトリでのデータ仕様の正はこの章です。** ほかの文書・`guide.html`・`_template`・Fusionスクリプトは、ここに合わせる（変更時の直し方は次の章）。

### フォルダ配置と命名

```
3Dギャラリー/
└── items/
    ├── 20250612_流路セルホルダー/
    ├── 20250903_ステージ用スペーサー/
    └── _template/          ← 先頭が _ のフォルダは同期しない
```

- 1作品＝1フォルダ。**中身はフラット**（サブフォルダは見ない）。
- フォルダ名は `YYYYMMDD_名前`（正規表現 `^(\d{8})_(.+)$`）。日付は**モデルの作成日**（不明なら大体でよい。登録日ではない）で、**カレンダーに実在すること**（1900年以降。20250231 はエラー）。
- 名前は日本語可。`/` `\` `:` などファイル名に使えない記号は避ける。
- 同じ日付・同じ名前が重なったら末尾に `-v2` などを付ける（`-v2` は名前の一部として扱われる）。
- 日付と名前はフォルダ名から取る。**`meta.json` には書かない**。
- **同期の対象外**：`items/` 直下の、先頭が `_` のフォルダ／ゴミ箱の中のフォルダ／ショートカット／フォルダ以外のファイル。作品フォルダ内では、ゴミ箱の中・ショートカット・`*.tmp`（`IGNORE_FILE_EXTENSIONS`。Fusion書き出しの一時ファイルなど）を無視する。

### フォルダの中身

| ファイル | 要否 | 内容 |
| --- | --- | --- |
| `meta.json` | **必須** | 作品情報（下記）。ちょうど1つ |
| `thumb.png` / `thumb.jpg`（`.jpeg`） | 推奨 | ギャラリーの代表画像。この順に探し（大文字小文字は無視）、無ければフォルダ内の名前順で最初の画像を使う |
| `*.f3d` | 推奨 | Fusionの元データ。編集用の正本 |
| `*.step` | 推奨 | Fusion以外のCADでも開ける保険。履歴（スケッチ・寸法拘束）は消える |
| `*.stl` / `*.3mf` | 推奨 | 印刷用。部品が複数なら `base.stl`, `lid.stl` のように並べる（Fusionスクリプトは `コンポーネント名_ボディ名.stl`） |
| `photo_*.jpg` / `photo_*.png` | 任意 | 使用中の様子など。名前が `photo_` で始まる画像が詳細の写真欄に並ぶ（名前順） |
| その他 | 任意 | 図面PDFなど。詳細のファイル一覧に出る |

### meta.json

| キー | 要否 | 型 | 内容 |
| --- | --- | --- | --- |
| `author` | 必須 | 文字列 | 作った人 |
| `purpose` | 必須 | 文字列 | 何のための部品か（一行） |
| `status` | 必須 | 文字列 | `使用中` / `参考` / `引退` のいずれか |
| `tags` | 任意 | 文字列の配列 | 絞り込み用（装置名、種類など） |
| `note` | 任意 | 文字列、または文字列の配列 | 上記以外すべて。配列なら1要素＝1行、文字列なら改行で行に分ける |
| `fusion_id` | 任意（Fusion書き出しが入れる。**手で書かない**） | 文字列 | Fusion の `DataFile.id`（版・名前・置き場所が変わっても同じ）。`fusion_export.py` が書き出し済みかを判定するための印。同期は未知のキーとして無視するので、スプシにもギャラリーの画面にも出ない（`meta.json` の中にだけ残る）。書き出しの最中は、作品フォルダに同じ ID を入れた目印 `fusion_id.tmp` も置かれる（完了で消える。同期は `*.tmp` を無視する） |

```json
{
  "author": "山田",
  "purpose": "流路セルを顕微鏡ステージに固定する",
  "status": "使用中",
  "tags": ["顕微鏡", "治具"],
  "note": ["M3ネジ×4で固定。", "縦向きで刷らないと爪が折れる。", "v2で穴径を0.2mm拡大。"],
  "fusion_id": "urn:adsk.wipprod:dm.lineage:xxxxxxxxxxxxxxxxxxxxxx"
}
```

`fusion_id` はFusion書き出しスクリプトが入れる（手で作った作品には無い）。人が `meta.json` を埋め直すときも、既存のキーはそのまま残す（消すと再実行で飛ばされ、書き換えると別の作品として `-v2` に書かれる。判定の詳細は「Fusionスクリプトの構成」）。

絞り込み・並び替えに使う情報だけを項目にし、それ以外は `note` に寄せる。`note` を配列でも書けるのは、手書きで `\n` を打つ手間を省くため。

### 検査ルール

不備のある作品はギャラリーに出さず、`error` 列に理由を記録する（メッセージは [OPERATION.md](OPERATION.md#エラーメッセージ一覧) に一覧）。検査は `Code.gs` の `parseFolderName` / `buildRecord` / `checkMeta`。

- フォルダ名が形式に合う／日付が実在する
- `meta.json` がちょうど1つある（0個・複数個はエラー）
- UTF-8 の JSON として読め（先頭のBOMは除去してから読む）、トップレベルが `{ }`
- `author` `purpose` `status` が**空でない文字列**（前後の空白は除去）
- `status` が `STATUS_CHOICES` のどれか
- `tags` を書くなら文字列の配列（各要素は前後の空白除去、空は捨てる）
- `note` を書くなら文字列か文字列の配列
- 1セル50000文字を超える値は切り詰め、`error` に記録する（`files` の一覧が収まらない場合も要対応）
- **未知のキーはエラーにしない**（将来キーを足しても、古いコードで壊れないように）

---

## データ仕様を変えるときに直す箇所

データ仕様（状態の選択肢、キー、ファイル名の規則など）を変えるときは、次を**すべて**そろえる。1つでも漏れると、画面の説明と実際の検査が食い違う。

| 変えること | 直す箇所 |
| --- | --- |
| 状態の選択肢（例：「保管中」を足す） | `Code.gs` の `STATUS_CHOICES`（検査と指紋に効き、`getGalleryData` の `statuses` として画面にも渡る）／`index.html` の状態の色（既知の3種の色対応。`DEFAULT_STATUSES` は `statuses` が無いときの予備。色が無い新しい状態はグレーの破線枠で出る）／`guide.html` の表（`status` の行）と `#ai-prompt` の status の文／`_template/README.txt`／`fusion_export.py` は status を `DEFAULT_STATUS`（既定は空）で出すので、選択肢を変えたら設定欄のコメントの選択肢も直す／**この文書のデータ仕様** |
| 必須キーを足す・外す | `Code.gs` の `REQUIRED_META_KEYS` と `checkMeta`（キーごとの検査）／`guide.html` の meta 例・キー一覧・`#ai-prompt`／`_template/meta.json` と `README.txt`／`fusion_export.py` の `build_meta` の雛形（`fusion_id` は済み判定に使うので、外さない）／この文書。**古い作品が一斉に要対応にならないか**を考える（必須にするなら既存作品を直す手間が出る。基本は任意キーとして足す） |
| 任意キーを足す | `checkMeta`（型の検査と整形）／シートの列を足すなら `HEADERS`・`buildRecord`・`recordToGalleryEntry`（そして「全部作り直す」）／`getGalleryData` の戻り値を変えるなら `index.html`／`guide.html`／`_template`／`build_meta`／この文書 |
| フォルダ名の形式 | `Code.gs` の `parseFolderName`／`fusion_export.py` の `FOLDER_NAME_PATTERN`・`make_folder_name`・`is_valid_folder_name`・`date_part`／`guide.html`／`_template/README.txt`／この文書 |
| 代表画像・写真の規則 | `Code.gs` の `THUMB_FILE_NAMES`・`PHOTO_PREFIX`・`pickThumbFile`・`pickPhotoFiles`／`fusion_export.py` の `THUMB_FILENAME`／`guide.html`／この文書 |
| 新しいGoogleサービスを使う（スコープが増える） | コードを変えたら、`appsscript.json` の `oauthScopes` に必要なスコープを足す（足さないと実行時に権限エラー。足すと閲覧者の許可画面の内容が広がるので最小限に）／[SETUP.md](SETUP.md) の `appsscript.json` の説明 |
| 同期の対象外にする条件 | `Code.gs` の `IGNORE_PREFIX`・`IGNORE_FILE_EXTENSIONS`・`listItemFolders_`・`listFolderFiles_`／`guide.html`／この文書 |

あわせて：

- 該当するテスト（`dev/gas-test`、`dev/fusion-test`）を直して、通ることを確認する。
- `tools/` の控え（Drive上の `3Dギャラリー/tools/`）を差し替える。
- Apps Script に貼り直し（`appsscript.json` を変えたらそれも）、「デプロイを管理」で新バージョンを出す（[SETUP.md](SETUP.md#更新するとき新しいデプロイとデプロイを管理の違い)）。
- 検査ルール（`STATUS_CHOICES`、`REQUIRED_META_KEYS`）を変えると、指紋が変わって次の同期で全作品が自動的に読み直される。

---

## ローカルでの動作確認

`dev/` は**リポジトリにだけあり、Driveには置かない**。Node.js v20以上（依存パッケージなし）と、Fusionスクリプト用に Python 3 を使う。リポジトリのルートで実行する。

| 対象 | コマンド | 内容 |
| --- | --- | --- |
| `Code.gs` | `cd dev/gas-test && node --test` | `Code.gs` を Node で読み込み、偽の `DriveApp` / `SpreadsheetApp` / `PropertiesService` などで検証する。純粋な関数（フォルダ名、検査、指紋など）と、同期の通し（追加・変更・削除・リネーム・時間切れからの再開・二重実行・1件再同期・`getGalleryData`・`setup`・`getThumbnails`） |
| `fusion_export.py` | `python -m unittest discover -s dev/fusion-test -v` | 偽の `adsk` を差し込んで import し、Fusionを要しない部分（命名、CSV、行の選別、名前での絞り込み、triage.csv の引き継ぎ、パスの解決、済み判定、meta.json の生成、外部参照の判定）と、`break_external_links` を偽のオカレンスでテストする |
| 画面 | `node dev/preview/build.mjs` | `index.html` の `include('guide')` を `guide.html` で置き換え、`google.script.run` の偽物（サンプルデータを返す）を注入して `dev/preview/out/index.html` を出す。ブラウザで開いて見た目を確認する |

プレビューの場面は URL の `?scenario=` で切り替えられる：`out/index.html?scenario=empty`（作品ゼロ）、`error`（読み込み失敗）、`partial`（時間切れ）、`syncfail`（同期失敗）、`readonly`（同期できない人）、`status`（未知の状態）、`many`（30件。画像の取り直しを含む）、`thumbfail`（取り直しも失敗）、`heic`（大きな画像が表示できず縮小画像で取り直す）。画像の取り直し（IntersectionObserver）は `--virtual-time-budget` のスクショでは途中で止まるので、実時間で調べる `node --experimental-websocket dev/preview/cdp-check.mjs "scenario=many;view=list" 1400,900 5000 [shot.png]` で確かめる（Windows ではクエリの区切りに `;` を使う。手順は `THEN`〜`THEN6` で続けられ、`STEP_SHOTS=1` で手順ごとに撮る。`FRAME=1` で 390px の iframe の中を操作し、`"@size 幅,高さ"` で大きさを変える。出力には pageY・フォーカス・履歴（`data-hist`）が出る。プレビューの `&item=<フォルダID>` と、`google.script.history` / `url` の偽物（pushState と popstate で再現）もある。第3ラウンドの一式は `dev/preview/out/shots-m3.sh` で撮り直せる。1400px の見た目を比べるときは、実時間で撮ったもの同士で比べる。`--virtual-time-budget` で撮ったものは毎回少しずつ変わるので、比べるのには使えない。また、drive.google.com は Chrome の `--host-resolver-rules` で 127.0.0.1:9 に向けてすぐ失敗させる）。読み込み後の操作もクエリで指定できる（プレビュー専用）：`&view=list|gallery`、`&select=<folderId>`、`&click=<CSSセレクタ>`、`&scroll=end|bottom`。スマホ幅は `out/frame-390.html?src=<クエリ>` で 390px の iframe に入れて見る。サンプルデータは `dev/preview/sample-data.js`。GASのテンプレート構文が残っているとビルドが失敗する。

ローカルで確かめられないこと：GAS実環境での動作（許可画面、共有ドライブ上の挙動、実行時間）、Driveのサムネイル表示（ブラウザのCookie制限）、Fusion APIの実際の挙動。これらは次の「本番での確認」と、Fusionの実機で確かめる。

## 本番での確認手順

AIや他の人が直したコードは、本番に出す前にテスト環境で確かめる。

1. **スプシごとコピーしてテスト環境を作る**：本番のスプシを「ファイル → コピーを作成」する（コピーに GAS も付く）。
2. **コピー側の GAS に変更したコードを貼る**（`appsscript.json` を変えた場合は、コピー側でもマニフェストの表示をオンにして置き換える）。コピー側の「プロジェクトの設定 → スクリプト プロパティ」で `ITEMS_FOLDER_ID` を**テスト用フォルダ**（本番の `items/` ではない、テスト作品だけを入れた別フォルダ）のIDにする。コピーではスクリプトプロパティが引き継がれないことがあるので、必ず確かめる。
3. スプシのメニュー「ギャラリー → 今すぐ同期」でテスト用フォルダを同期し、シートの内容（変更した列・`error`）を確認する。`setup()` は必須ではない（同期が見出しを作る）。実行した場合は、コピー側に毎日のトリガーが登録されるので、確認後にエディタの「トリガー」から削除する。
4. エディタの「デプロイ → デプロイをテスト」の URL（最新コードが動く）で画面を確認する。一覧、絞り込み、詳細、要対応、「作品を追加する」パネル、PC幅とスマホ幅。
5. 問題なければ**本番のGASに貼り替え**、「デプロイ → デプロイを管理」で新バージョンを出す。URLが変わっていないことを確認する。
6. 本番で「今すぐ同期」と画面表示を確認する。
7. `tools/gas/` の控えを差し替え、この文書を更新する。

---

## Fusionスクリプトの構成

`tools/fusion_export/fusion_export.py` 1本（＋`fusion_export.manifest`）。Fusion の「スクリプトとアドイン」に**フォルダごと**登録する。**フォルダ名と `.py` / `.manifest` の名前をそろえる**（`fusion_export`）。標準ライブラリと `adsk`（Fusion付属）だけを使う。使い方は [OPERATION.md](OPERATION.md#fusion書き出しの運用)。

構成（上から）：

| 区画 | 内容 |
| --- | --- |
| 設定欄 | 「共通 → モード1だけ → モード2だけ → 細かい設定」の順。共通：`MODE` `PROJECT_NAMES` `TARGET_NAMES`／モード1だけ：`TRIAGE_DIR`（既定は空＝ローカルの `ドキュメント\3Dギャラリー_仕分け`。「ドキュメント」は Known Folder で取る）／モード2だけ：`TRIAGE_CSV`（既定は空＝`TRIAGE_DIR\triage.csv`）`OUTPUT_DIR` `DEFAULT_AUTHOR` `DEFAULT_STATUS` `DEFAULT_TAGS`／細かい設定：`STL_PER_BODY` `MESH_QUALITY` `THUMB_WIDTH/HEIGHT`。Googleドライブ上でなければならず、`<共有ドライブ名>` の書き換えが要るのはモード2の `OUTPUT_DIR` だけ |
| 定数 | `TRIAGE_COLUMNS`、ファイル名（`TRIAGE_DIR_NAME` は `TRIAGE_DIR` が空のときのフォルダ名）、`FUSION_ID_KEY`（`"fusion_id"`）、`FUSION_MARKER_FILENAME`（書き出し中の目印 `"fusion_id.tmp"`）、`SOURCE_PREFIX`（旧版の「Fusion元: 」。互換用）、`BREAK_LINK_MAX_ROUNDS`、ランク（`EXPORT_RANKS = ("A","B")`）、ログの result の語、`FOLDER_NAME_PATTERN`（GASの同期と同じ規則） |
| 純粋な関数 | `sanitize_filename` `epoch_to_text` `date_part` `make_folder_name` `is_valid_folder_name` `unique_name` `source_text` `build_meta` `meta_json_text` `write_meta_json` `is_done` `write_marker` `read_marker` `remove_marker` `folder_state` `resolve_output_folder` `check_setting_path` `write_triage_csv` `can_overwrite` `fallback_triage_path` `save_triage_csv` `read_triage_csv` `normalize_rank` `select_rows_for_export` `select_projects` `normalize_name` `as_name_list` `duplicate_names` `select_by_names` `names_in_use` `merge_triage_rows` `documents_dir`（Windows では `_known_documents_folder` を使う。ctypes） `resolve_paths` `external_ref_outcome` `lookup_candidates` `append_log` `backup_path` `collect_visible_solid_bodies`（`[(ボディ, STLの名前の元), …]` を返す） `break_external_links`（Fusion のオブジェクトを受けるが、`count`/`item` と属性だけで判断するので偽物でテストできる） |
| Fusionを使う関数 | `list_target_projects` `walk_f3d_files` `first_created_epoch` `FileFinder` `open_document` `close_document` `is_modified` `get_design` `save_thumbnail` `export_f3d/step/stl/3mf` `find_external_references` `export_item` `Progress` |
| 純粋な関数の役割（第2ラウンドで追加） | `resolve_paths`：`~` の展開、`TRIAGE_CSV` が空なら `TRIAGE_DIR\triage.csv`、モードごとの設定の検査（`<共有ドライブ名>` の残りを止めるのは `OUTPUT_DIR` だけ。第4ラウンドで、使うパスに制御文字があれば止める検査を追加＝r の付け忘れで `\3` `\t` が化けた場合。`\U` などは読み込み時の SyntaxError になり、ここでは拾えない）。`normalize_name`：前後の空白を除いて NFC 正規化。`select_by_names`：名前で絞り、見つからなかった名前も返す。`merge_triage_rows`：モード1の再実行で既存の行に合わせる。`names_in_use`：今回撮らない行が使う `folder_name` と画像名（撮り直す行の名前案が衝突しないように）。`external_ref_outcome`：ログを「要目視確認」にするかと注記を決める。`break_external_links`：外部参照の取り込み。（第2ラウンドのレビュー対応で追加）`write_marker` / `read_marker` / `remove_marker`：書き出し中の目印 `fusion_id.tmp`。`as_name_list`：設定欄の名前のリストに文字列1つが書かれていたら `[s]` にする。`duplicate_names`：同じ名前の行の数。`can_overwrite`：`triage.csv` を書き換えられるか（`r+b` で開いてみる）。`save_triage_csv`：退避して書き、書けなければ `fallback_triage_path`（`triage_new_日時.csv`）に書く。`documents_dir`：「ドキュメント」の場所（失敗時は `~\Documents`） |
| 実行 | `run_mode1` `run_mode2` `run(context)`（Fusionが呼ぶ入口） |

設計の決まり：

- 純粋な関数は Fusion を要しないので `dev/fusion-test` で検証する。Fusion を使う部分は薄く保つ。
- `triage.csv` は BOM 付きUTF-8で書き、読むときは BOM の有無・Shift_JIS(cp932) のどれも受ける。モード1の再実行では既存の `triage.csv` を `triage_日時.csv` に退避する。
- 完了の目印は **`meta.json` を最後に書くこと**。`meta.json` は一時ファイル（`.tmp`）に書いてから置き換える（`.tmp` は同期が無視する）。
- 済み判定は `folder_state`。`meta.json` の **`fusion_id`**（`DataFile.id`）とこの行の `datafile_id` を照合する。`note` には何も入れない（空の配列。Fusion の場所を入れるとギャラリーに出てしまうため）。`fusion_id` は版・名前・置き場所が変わっても同じなので、Fusion 側で整理し直しても追跡できる。分岐は次のとおり。

  | 出力先フォルダの状態 | `folder_state` | 動き |
  | --- | --- | --- |
  | フォルダが無い | `new` | 新しく作る |
  | フォルダはあるが `meta.json` が無く、目印 `fusion_id.tmp` がこの行の `datafile_id` と一致 | `partial` | 自分が途中で止まったフォルダ。やり直す（そのフォルダに書く） |
  | 同上で、目印が無い | `partial`（`-v2` 以降は `conflict` 扱い） | 目印を書く前の版で止まったフォルダなど。`triage.csv` どおりの名前（n=1）なら従来どおり自分のものとしてやり直す。`-v2` 以降は誰のものか分からない（CSV 内の重複処理で他の行が使った名前かもしれない）ので、`resolve_output_folder` が避ける |
  | 同上で、目印が別の `datafile_id` | `conflict` | 他の作品の途中のフォルダ。取らない |
  | `fusion_id` が一致 | `done` | 済み。スキップ（ログに「スキップ」、ダイアログは「書き出し済み」） |
  | `fusion_id` がある、だが違う | `conflict` | 別の作品。上書きせず `resolve_output_folder` が `-v2`、`-v3` … の空きを探して書き、ログに「注意」を残す |
  | `meta.json` が読めない・`{ }` でない | `conflict` | 同上（手作りの同名フォルダなど） |
  | `fusion_id` が無く、`note` に旧版の「Fusion元: …」行がある | `done` / `done_no_id` | 旧版の出力との互換。行の場所が今回の行（`source_text`）と一致すれば `done`。違えば、Fusion で名前や場所を変えただけかもしれず同じ作品か言い切れないので、`done_no_id`（重複して書き出すより飛ばす） |
  | `fusion_id` も「Fusion元」行も無い | `done_no_id` | 念のためスキップ。手で消した・手作りの同名フォルダ・旧版以前の出力は、同じ作品か分からないが、重複して書き出すより飛ばすほうが害が少ないため。ログの `detail` に「fusion_id が無いため念のためスキップ（同じ作品なら fusion_id を戻すかフォルダを消してから再実行。別の作品なら triage.csv の folder_name を変える）」。終了時のダイアログでは「スキップ（fusion_id なし・未確認）」として、書き出し済みのスキップとは分けて数える |

  `meta.json` があれば目印は見ない（完了後に目印を消せずに残っていても害が無い）。目印は書き出しの最初（`os.makedirs` の直後）に `write_marker` で書き、`meta.json` を書いたら `remove_marker` で消す（消せなくてもエラーにしない）。名前が `*.tmp` なので同期は無視する。

- **書き出し先の決め方**（`resolve_output_folder`）：候補は `folder_name`、`-v2`、`-v3` …。出力先にある候補をすべて（`os.listdir` で一番大きい番号を見る）と、その次の空き1つまでを**先に調べてから**決める。
  1. `fusion_id` が一致する `done` があれば、番号に関わらず（`reserved` にある名前でも）それを選ぶ。途中で決めると、後ろにある自分の完了済みを見落として重複して書き出すため。
  2. 無ければ、番号の小さい順に最初の使える候補。`conflict`・`-v2` 以降の目印の無い `partial`・`-v2` 以降で `reserved`（`triage.csv` の他の行が使う名前）にあるものは飛ばす。
  
  これで、CSV 内の重複処理で B が `X-v2` になって失敗し（途中）、A が `X-v3` で完了したあと、`TARGET_NAMES=[A]` で再実行しても、A は B の途中の `X-v2` を取らずに `X-v3` で済みと判定される（再実行で番号が変わらない。テスト `TestMode2Renumber`）。済み（`done` / `done_no_id`）で飛ばすときは、避けたフォルダがあっても「…に書き出します」の注意は出さない。

  `datafile_id` が空の行は、`fusion_id` が決まらないので `select_rows_for_export` が選ばず、警告（ログの「注意」）を出す。書き出し直したいときは、人が作品フォルダを消してから再実行する（`meta.json` だけ消すと、`triage.csv` どおりの名前のフォルダは `partial` になって同じ場所に書き直される。`-v2` 以降のフォルダは目印が無いので避けられ、別の番号に書かれる。フォルダごと消すのが確実）。`meta.json` は人が記入していくので、照合に使うのは `fusion_id`（と旧版の「Fusion元」行）だけで、ほかのキーは問わない。
- 設定欄のパスに `< >` が残っていたら `check_setting_path` が実行を止める。
- 1件ごとに `try/except` し、`export_log.csv` に記録して次へ進む。`adsk.doEvents()` と進捗ダイアログ（キャンセル可）で画面を固めない。
- 形式ごと（f3d / STEP / STL / 3MF / thumb）に try し、1つ失敗しても残りを出す。失敗があれば `meta.json` を書かず、その作品を失敗にする。
- モード2は、`version_id` → `datafile_id` → 対象プロジェクトの再走査の順でファイルを探し、ログの `detail` に「取得: …」と残す。古い版で引けたら `latestVersion` に替える。
- STL は、ルートと全オカレンスの「表示中のソリッドボディ」を対象にし、ファイル名はルート直下ならボディ名、オカレンス内なら `コンポーネント名_ボディ名`（`Occurrence.component.name`）。重複は `_2` などで避ける。`STL_PER_BODY = False` で1ファイルにまとめる。
- `meta.json` の雛形（`build_meta`）は、`author` / `status` / `tags` に設定欄の `DEFAULT_AUTHOR` / `DEFAULT_STATUS` / `DEFAULT_TAGS` を入れ（既定は空）、`purpose` は作品ごとに違うので常に空、`note` は空の配列、`fusion_id` に `datafile_id` を入れる。`DEFAULT_STATUS` が選択肢外だと、同期で「要対応」になる。
- **`TARGET_NAMES`**（空なら全部）：`select_by_names` が `normalize_name`（前後の空白を除き NFC 正規化）をかけて完全一致で選ぶ。同名のファイルは全部選び、見つからない名前は最後のメッセージとログ（「注意」）に出す。`TARGET_NAMES` と `PROJECT_NAMES` に文字列1つが書かれていたら、`as_name_list` が `[s]` にする（そのままだと1文字ずつに割られ、`PROJECT_NAMES` では部分一致になってしまうため）。モード2で、指定した名前の行が `triage.csv` に複数ある（別のプロジェクトやフォルダの同名ファイル）ときは、全部書き出し、`duplicate_names` で数えてログに「注意」を出す。モード1は指定した名前のファイルだけ画像を撮り、モード2は `triage.csv` から指定した名前の行だけを書き出す（指定＝書き出すと決めたことなので、`rank` は問わない）。
- **モード1の再実行**：既存の `triage.csv` を `triage_日時.csv` に退避したうえで、`merge_triage_rows` が `datafile_id` の同じ行の `rank` と `folder_name` を引き継ぐ（既存の行の位置に新しい行を入れる。今回撮らなかった行・Fusion から消えたファイルの行もそのまま残し、新しいファイルは最後に足す）。一部だけ撮り直しても、記入済みの仕分けは消えない。今回撮れなかった行は、前回の `image` を残す。`names_in_use` は、残す行が使う `folder_name` と画像名を、撮り直す行の名前案が避けるために使う。
- **`triage.csv` を Excel で開いたまま**：Excel が開いているファイルは、書き換えも名前の変更（退避の `os.replace`）もできない（`PermissionError`）。最後に書けないと撮影の結果が全部失われるので、モード1は撮影の前に `can_overwrite`（既存の `triage.csv` を `r+b` で開いてみる）で確かめ、書けなければ撮らずに「Excel などで開いていたら閉じてください」と止める（例外ではなくメッセージ）。撮影の途中で開かれて最後に書けなかったときは、`save_triage_csv` が `triage_new_日時.csv` に書き、ログ（「注意」）と終了時のダイアログで案内する。テストは Windows で、Excel と同じく共有を読み取りだけに絞って開く（`CreateFileW`）ことで再現している。
- **設定欄のパス**：`resolve_paths` が解決する。`TRIAGE_DIR` の既定は空で、空ならローカルの `ドキュメント\3Dギャラリー_仕分け`（仕分けの作業用で、共有しなくてよい）。「ドキュメント」は `documents_dir` が決める。OneDrive にドキュメントを移している PC では `~\Documents` がエクスプローラーの「ドキュメント」と違う場所になることがあるので、Windows では Known Folder（`SHGetKnownFolderPath`、`FOLDERID_Documents`）を ctypes で取り（`_known_documents_folder`）、失敗・空なら `~\Documents` にする。取得の関数は引数で差し替えられるので、失敗時の扱いはテストで確かめている。実際の場所は終了時のダイアログの「一覧」に出る。`TRIAGE_CSV` は既定が空で、空なら `TRIAGE_DIR\triage.csv` を読む。`<共有ドライブ名>` が残っていると止めるのは、モード2の `OUTPUT_DIR` だけ（モード1は `OUTPUT_DIR` が未設定でも動く）。
- **外部参照**：API の Fusion アーカイブ書き出しは参照先を含まず、外部参照のあるデザインの f3d は中身が空になる（実機で確認。上の「確認したFusionのバージョン」）。そこで `export_item` は **STEP → STL → 3MF → thumb.png → 取り込み（`before_f3d`）→ f3d** の順で書き出す。STEP/STL/3MF/サムネイルは取り込まなくても参照先ごと出ることを実機で確かめてあり、取り込みが失敗したり、取り込みで部品が置き換わって先に集めたボディ（プロキシ）が無効になったりしても、それらに影響しないようにするため。取り込みは**自分で開いたドキュメントに限り**、`break_external_links` が `Occurrence.breakLink()` で行う（対象を先にリストへ集めてから呼び、入れ子は `isReferencedComponent` が無くなるまで周回する。1周で1つも取り込めなければ止め、上限は `BREAK_LINK_MAX_ROUNDS` 周）。保存せずに `close(False)` で閉じるので、クラウド上の元データは変わらない。元々開いていたドキュメントは書き換えないので、取り込まずに書き出す。
- **ログの判定**（`external_ref_outcome`）：外部参照が無い、または全部取り込めた（自分で開いたドキュメント）→「成功」（detail に「外部参照 N 件を取り込んで f3d を書き出し」）。次のどれかなら「成功（要目視確認）」：元々開いていたドキュメントで取り込まなかった／取り込めなかった配置が残った／印は立っているのに取り込める配置が無かった。いずれも f3d に参照先が入っていない可能性があるため。
- **既知の制約**：API では、参照先を含む本物の f3z は作れない（Autodesk のフォーラムでも同じ回答）。取り込んだ f3d は、参照先がローカルのコンポーネントとして入った単体のデータになり、元の参照のつながり（参照先を直すと反映される関係）は失われる。つながりを保った形で残したいなら、Fusion の UI から f3z で書き出す（手作業）。
- 元々開いていたドキュメントに未保存の変更があるとき（`Document.isModified`）は、その状態で書き出し、ログの `detail` に注記する。サムネイルは `isSmoothTransition = False` で視点移動のアニメーション途中を撮らない。
- 公式リファレンスの URL は、ページ名に名前空間の接頭辞（`core_` / `fusion_`）が付く形に変わっている（旧形式の接頭辞なしは 404）。

## Fusion API 照合表

2026-10-30 に Autodesk 公式 API リファレンス（`https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/<名前>.htm`）と照合した。**実機では未確認。** 確信度は、リファレンスに明記されているか（高＝明記、中＝明記はないが記述から推定、低＝推測）で付けた。

| API | 使い方 | 照合結果 | 確信度 | URL |
| --- | --- | --- | --- | --- |
| `Application.get()` / `.userInterface` / `.activeDocument` / `.activeViewport` / `.documents` / `.data` | 入口 | 存在を確認 | 高 | [core_Application](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/core_Application.htm) |
| `Data.dataProjects` | 対象プロジェクトの列挙 | 「アクティブなハブ」のプロジェクトだけを返す | 高 | [core_Data](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/core_Data.htm) |
| `DataProject.name` / `.rootFolder` | | 確認 | 高 | [core_DataProject](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/core_DataProject.htm) |
| `DataFolder.dataFolders` / `.dataFiles` / `.name` | 再帰でたどる | `dataFiles` はフォルダ以外の全アイテム（f3d 以外も含む） | 高 | [core_DataFolder](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/core_DataFolder.htm) |
| `DataFiles.asArray()` / `DataFolders.asArray()` | コレクションをまとめて取る | 2021年4月追加。「現在の一覧」を返す。無い版では `count`/`item` にフォールバック | 高 | [core_DataFiles_asArray](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/core_DataFiles_asArray.htm) |
| `DataFile.fileExtension` | `"f3d"` で絞る | 拡張子を返す。大文字小文字は不明なので `lower()` で比較 | 中 | [core_DataFile](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/core_DataFile.htm) |
| `DataFile.dateCreated` / `.dateModified` | 作成日・更新日 | **UNIX 時刻（秒）**、uinteger。**dateCreated はその版の作成日**（保存のたびに新しい版＝新しい日付） | 高 | [core_DataFile_dateCreated](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/core_DataFile_dateCreated.htm), [core_DataFile_dateModified](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/core_DataFile_dateModified.htm) |
| `DataFile.versions` | 最初の作成日を出す（全版の dateCreated の最小値） | DataFiles を返す。「他の版」とあるので自分を含むか不明 → 自分も足して最小を取る | 中 | [core_DataFile_versions](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/core_DataFile_versions.htm) |
| `DataFile.id` / `.versionId` | triage.csv の `datafile_id` / `version_id` | `id` は `urn:adsk.wipprod:dm.lineage:...`（版に依らない）、`versionId` は `urn:...:fs.file:vf...?version=N`（その版）。属性名 `versionId` をリファレンスで確認 | 高 | [core_DataFile](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/core_DataFile.htm) |
| `DataFile.latestVersion` | version_id で古い版が引けたとき最新版に差し替える | 「最新版を返す。自分が最新なら同じものを返すことがある」 | 高 | [core_DataFile](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/core_DataFile.htm) |
| `Data.findFileById(id)` | モード2で開き直す | 見つからなければ null。**引数の例は版付きID（fs.file:vf...?version=N）。`?version=` を省くと最新版**とある。lineage ID を受けるかは明記なし → **version_id → datafile_id → 対象プロジェクトの再走査** の順で試し、どれで引けたかを export_log.csv の detail に「取得: version_id」などと残す。version_id で引けて古い版だったら `latestVersion` に替え、「→最新版」と付ける | 中 | [core_Data_findFileById](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/core_Data_findFileById.htm) |
| `DataFile.hasChildReferences` | 外部参照の判定（補助） | 「参照コンポーネントを含むか」 | 高 | [core_DataFile](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/core_DataFile.htm) |
| `Documents.open(dataFile, visible)` | 開く | 戻り値は Document、失敗で null。visible の既定は True | 高 | [core_Documents_open](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/core_Documents_open.htm) |
| `Document.activate()` / `.close(saveChanges)` / `.dataFile` / `.documentReferences` / `.isValid` | 前面化・閉じる・既に開いているかの判定 | `close(False)` は変更があっても破棄して閉じる。コマンドのイベント内では close できない（スクリプトの run からなので該当しない） | 高 | [core_Document](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/core_Document.htm), [core_Document_close](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/core_Document_close.htm) |
| `Document.isModified` | 元々開いていて未保存の変更があるドキュメントを書き出したとき、ログに注記 | 「最後の保存以降に変更されたか」 | 高 | [core_Document](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/core_Document.htm) |
| `FusionDocument.design` / `Design.cast(products.itemByProductType("DesignProductType"))` | Design を取る | `FusionDocument.design` を確認。後者はフォールバック | 高 | [fusion_FusionDocument](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/fusion_FusionDocument.htm) |
| `Viewport.camera`（get/set） | 視点 | **取得はコピー**。変えたら代入し直す必要がある | 高 | [core_Viewport_camera](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/core_Viewport_camera.htm) |
| `Camera.viewOrientation` = `ViewOrientations.IsoTopRightViewOrientation` (7) | 斜め視点 | ViewCube の現在の向きが基準なので、データによって向きが揃わないことがある | 高 | [core_Camera_viewOrientation](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/core_Camera_viewOrientation.htm), [core_ViewOrientations](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/core_ViewOrientations.htm) |
| `Camera.isFitView` / `Viewport.fit()` / `Viewport.refresh()` | 全体表示 | 確認 | 高 | [core_Camera_isFitView](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/core_Camera_isFitView.htm), [core_Viewport_fit](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/core_Viewport_fit.htm) |
| `Camera.isSmoothTransition` | 視点を一瞬で切り替える（アニメーション途中で撮らない） | true でアニメーション、false で即時。Viewport から取った Camera では既定 false だが、明示的に false を設定 | 高 | [core_Camera](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/core_Camera.htm) |
| `Viewport.saveAsImageFile(filename, width, height)` | PNG 保存 | 戻り値 bool。形式は拡張子から。指定サイズで再描画 | 高 | [core_Viewport_saveAsImageFile](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/core_Viewport_saveAsImageFile.htm) |
| `Design.exportManager` / `ExportManager.execute(options)` | 書き出し | 戻り値 bool | 高 | [fusion_ExportManager](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/fusion_ExportManager.htm), [fusion_ExportManager_execute](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/fusion_ExportManager_execute.htm) |
| `createFusionArchiveExportOptions(filename, geometry=None)` | f3d | **引数は (ファイル名, 対象)**。対象省略でルート全体 | 高 | [fusion_ExportManager_createFusionArchiveExportOptions](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/fusion_ExportManager_createFusionArchiveExportOptions.htm) |
| `createSTEPExportOptions(filename, geometry=None)` | STEP | 同上 | 高 | [fusion_ExportManager_createSTEPExportOptions](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/fusion_ExportManager_createSTEPExportOptions.htm) |
| `createSTLExportOptions(geometry, filename="")` | STL | **引数は (対象, ファイル名) で f3d/STEP と逆**。対象は BRepBody / Occurrence / Component | 高 | [fusion_ExportManager_createSTLExportOptions](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/fusion_ExportManager_createSTLExportOptions.htm) |
| `STLExportOptions.isBinaryFormat` / `.meshRefinement` / `.unitType` | バイナリ・精度・mm | `unitType` の既定はデザインの単位なので mm（`DistanceUnits.MillimeterDistanceUnits` = 0）に固定 | 高 | [fusion_STLExportOptions](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/fusion_STLExportOptions.htm), [fusion_DistanceUnits](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/fusion_DistanceUnits.htm) |
| `MeshRefinementSettings` High=0 / Medium=1 / Low=2 | 設定 MESH_QUALITY | 確認 | 高 | [fusion_MeshRefinementSettings](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/fusion_MeshRefinementSettings.htm) |
| `createC3MFExportOptions(geometry, filename="")` / `C3MFExportOptions.meshRefinement` | 3MF | 引数は (対象, ファイル名)。unitType は無い | 高 | [fusion_ExportManager_createC3MFExportOptions](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/fusion_ExportManager_createC3MFExportOptions.htm), [fusion_C3MFExportOptions](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/fusion_C3MFExportOptions.htm) |
| `Component.bRepBodies` / `.allOccurrences` | ボディ収集 | `allOccurrences` は階層を問わず全オカレンス（読み取り専用リスト） | 高 | [fusion_Component_allOccurrences](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/fusion_Component_allOccurrences.htm) |
| `Occurrence.bRepBodies` | オカレンス内のボディ | **ボディのプロキシを返す**（ルートから見た位置） | 高 | [fusion_Occurrence_bRepBodies](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/fusion_Occurrence_bRepBodies.htm) |
| `Occurrence.isVisible` / `.isReferencedComponent` / `.name` | 表示判定・外部参照判定 | `isReferencedComponent` は「外部のコンポーネントを参照しているか」 | 高 | [fusion_Occurrence_isVisible](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/fusion_Occurrence_isVisible.htm), [fusion_Occurrence_isReferencedComponent](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/fusion_Occurrence_isReferencedComponent.htm) |
| `Occurrence.component` | ボディごと STL の名前を「コンポーネント名_ボディ名」にする | 「このオカレンスが参照するコンポーネント」 | 高 | [fusion_Occurrence](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/fusion_Occurrence.htm) |
| `BRepBody.isSolid` / `.isVisible` / `.name` / `.assemblyContext` / `.createForAssemblyContext(occ)` | 対象ボディの選別とプロキシ化 | `isVisible` は親の非表示も含めた最終結果。`createForAssemblyContext` はネイティブでなければ null | 高 | [fusion_BRepBody](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/fusion_BRepBody.htm), [fusion_BRepBody_createForAssemblyContext](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/fusion_BRepBody_createForAssemblyContext.htm) |
| `UserInterface.createProgressDialog()` / `ProgressDialog.show(title, message, min, max, delay)` / `.isCancelButtonShown` / `.cancelButtonText` / `.progressValue` / `.maximumValue` / `.message` / `.wasCancelled` / `.hide()` | 進捗 | すべて確認 | 高 | [core_ProgressDialog](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/core_ProgressDialog.htm), [core_ProgressDialog_show](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/core_ProgressDialog_show.htm) |
| `UserInterface.messageBox(text)` | まとめの表示 | 確認 | 高 | [core_UserInterface_messageBox](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/core_UserInterface_messageBox.htm) |
| `adsk.doEvents()` | 画面を固めない | Python モジュールの関数。リファレンスのページは見つけられなかった（広く使われている） | 中 | — |
| `.manifest`（`"autodeskProduct": "Fusion"`, `"type": "script"` ほか） | 登録用 | ユーザーマニュアルで形式を確認。`id` は未使用で空でもよい。フォルダ名と .py/.manifest の名前を揃える | 高 | [WritingDebugging_UM](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/WritingDebugging_UM.htm) |

### 確信が持てない点（実機で確認すること、優先度順）

1. **`Data.findFileById` でどの ID が引けるか**。モード2のログの detail「取得: …」を見る。`version_id` で常に引けるなら `datafile_id` と再走査は保険のまま残してよい。`datafile_id` でしか引けない／再走査ばかりなら、試す順（`lookup_candidates`）を見直す。古い triage.csv（version_id 列なし）は datafile_id → 再走査で引く。`?version=N` 付きで引いたとき `latestVersion` が期待どおり最新版を返すかも確認する。
2. **オカレンス内ボディ（プロキシ）を STL 書き出ししたとき、組立上の位置で出るか**。リファレンスでは `Occurrence.bRepBodies` はプロキシを返すとあるが、STL の座標に変換が反映されるかは明記なし。多部品のアセンブリで、ボディごとの STL をスライサーに並べて確認する。
3. **ルート単位の STL（`STL_PER_BODY=False`）と 3MF に、非表示のボディやサーフェスボディが含まれるか**。含まれるなら、表示中ボディだけを対象にする実装に変える。
4. **外部参照を含むデザインの `.f3d` 書き出し**。第1回の実機で、参照先を含まず中身が空になると分かった。第2ラウンドの対策（取り込んでから書き出す）で、f3d を Fusion で開いて部品が入っているかを確かめる。取り込みが入れ子（参照の中の参照）まで効くか、`breakLink()` が False を返すものが残らないかも見る。
5. **開いた直後のサムネイルが真っ白・描画途中にならないか**。`doEvents` を数回挟んでいるが足りなければ回数を増やすか、`time.sleep` を足す。ViewCube の向きが変えられているデータで斜め視点がばらつかないか。
6. **`DataFolder.dataFiles` / `dataFolders` が初回アクセスで全部そろうか**（クラウドからの遅延読み込みで件数が欠けないか）。モード1の件数を Fusion のデータパネルの件数と比べる。
7. **`DataFile.versions` の dateCreated が「最初の版」まで取れるか**、そして大量ファイルで遅くないか。遅ければ最新版の `dateCreated` だけにする。
8. `Documents.open` がすでに開いているファイルに対して何を返すか（実装では事前に `app.documents` を見て、開いていれば閉じない扱いにしている）。外部参照の子ドキュメントが裏で開かれたまま残らないか。
9. `fileExtension` の値（`"f3d"` か大文字か）と、外部参照を含むデザインも `f3d` で列挙されるか。
10. 確認した Fusion のバージョン（`app.version`）を下の欄に記録する。

## 確認したFusionのバージョン

**確認した Fusion のバージョン：2705.1.15（2026-10-30）**

- モード1・モード2 は動いた。データパネルの件数と triage.csv の行数は一致した。サムネイルは斜めからの全体表示で撮れた。開き方は「取得: version_id」（第一候補）で開けた
- 書き出したファイルは開けた（件数が多く、全部は見ていない）
- 外部参照を含むデザインは、f3d を開くと中身が空だった（STEP/STL は出ていた）。API の Fusion アーカイブ書き出しには参照先が含まれないため。対策は、取り込み（breakLink）をしてから f3d を書き出すこと（第2ラウンド R5）

初回に実機で実行したら、Fusion の「ヘルプ → バージョン情報」（またはスクリプトで `app.version`）の値と確認日、上の「確信が持てない点」の結果をここに書く。APIはFusionの更新で変わることがある。動かなくなったら、まずここに書いたバージョンとの差を疑う。
