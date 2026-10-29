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
| `tools/gas/index.html` | 画面（一覧と詳細）。見た目とブラウザ側の処理はすべてここ。`<?!= include('guide') ?>` で `guide.html` を読み込む。GASとの境目は `loadData` / `syncNow` / `resyncItem` の3関数だけ |
| `tools/gas/appsscript.json` | GASの設定ファイル（マニフェスト）。`oauthScopes`（`drive.readonly` / `spreadsheets` / `script.scriptapp` / `script.container.ui`）で許可の範囲を絞り、`webapp`（`executeAs: USER_ACCESSING`、`access: DOMAIN`）を決める。エディタでは「プロジェクトの設定」で表示をオンにして編集する。貼り方は [SETUP.md](SETUP.md#4つ目appsscriptjson-を置き換える許可の範囲を絞る) |
| `tools/gas/guide.html` | 「作品を追加する」パネルの本文（HTMLの断片）。文章の修正はこのファイルだけで済む。AIに渡すプロンプトは `#ai-prompt` の1か所にまとめてある。**スクリプトレット（`<?` で始まる構文）は書かない** |

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

画面（`index.html`）はサーバーを `google.script.run` 経由で3つの関数だけ呼ぶ。失敗時は日本語のメッセージ入りの `Error` が投げられ、`withFailureHandler` の `err.message` で表示される。

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

URLの形：サムネイル `…/thumbnail?id=<id>&sz=w600`、ファイル `…/file/d/<id>/view`、ダウンロード `…/uc?export=download&id=<id>`、フォルダ `…/drive/folders/<id>`。画像が読めないときは `index.html` 側の `onerror` が、フォルダIDから決めた形と色のアイコンに差し替える。

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

```json
{
  "author": "山田",
  "purpose": "流路セルを顕微鏡ステージに固定する",
  "status": "使用中",
  "tags": ["顕微鏡", "治具"],
  "note": ["M3ネジ×4で固定。", "縦向きで刷らないと爪が折れる。", "v2で穴径を0.2mm拡大。"]
}
```

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
| 状態の選択肢（例：「保管中」を足す） | `Code.gs` の `STATUS_CHOICES`（検査と指紋に効き、`getGalleryData` の `statuses` として画面にも渡る）／`index.html` の状態の色（既知の3種の色対応。`DEFAULT_STATUSES` は `statuses` が無いときの予備。色が無い新しい状態はグレーの破線枠で出る）／`guide.html` の表（`status` の行）と `#ai-prompt` の status の文／`_template/README.txt`／`fusion_export.py` は status を空で出すので通常は不要／**この文書のデータ仕様** |
| 必須キーを足す・外す | `Code.gs` の `REQUIRED_META_KEYS` と `checkMeta`（キーごとの検査）／`guide.html` の meta 例・キー一覧・`#ai-prompt`／`_template/meta.json` と `README.txt`／`fusion_export.py` の `build_meta` の雛形／この文書。**古い作品が一斉に要対応にならないか**を考える（必須にするなら既存作品を直す手間が出る。基本は任意キーとして足す） |
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
| `Code.gs` | `cd dev/gas-test && node --test` | `Code.gs` を Node で読み込み、偽の `DriveApp` / `SpreadsheetApp` / `PropertiesService` などで検証する。純粋な関数（フォルダ名、検査、指紋など）と、同期の通し（追加・変更・削除・リネーム・時間切れからの再開・二重実行・1件再同期・`getGalleryData`・`setup`） |
| `fusion_export.py` | `python -m unittest discover -s dev/fusion-test -v` | 偽の `adsk` を差し込んで import し、Fusionを要しない部分（命名、CSV、行の選別、スキップ判定、meta.json の生成）をテストする |
| 画面 | `node dev/preview/build.mjs` | `index.html` の `include('guide')` を `guide.html` で置き換え、`google.script.run` の偽物（サンプルデータを返す）を注入して `dev/preview/out/index.html` を出す。ブラウザで開いて見た目を確認する |

プレビューの場面は URL の `?scenario=` で切り替えられる：`out/index.html?scenario=empty`（作品ゼロ）、`error`（読み込み失敗）、`partial`（時間切れ）、`syncfail`（同期失敗）。サンプルデータは `dev/preview/sample-data.js`。GASのテンプレート構文が残っているとビルドが失敗する。

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
| 設定欄 | `MODE` `OUTPUT_DIR` `TRIAGE_DIR` `TRIAGE_CSV` `PROJECT_NAMES` `STL_PER_BODY` `MESH_QUALITY` `THUMB_WIDTH/HEIGHT` |
| 定数 | `TRIAGE_COLUMNS`、ファイル名、ランク（`EXPORT_RANKS = ("A","B")`）、ログの result の語、`FOLDER_NAME_PATTERN`（GASの同期と同じ規則） |
| 純粋な関数 | `sanitize_filename` `epoch_to_text` `date_part` `make_folder_name` `is_valid_folder_name` `unique_name` `source_text` `build_meta` `meta_json_text` `write_meta_json` `is_done` `folder_state` `resolve_output_folder` `check_setting_path` `write_triage_csv` `read_triage_csv` `normalize_rank` `select_rows_for_export` `select_projects` `lookup_candidates` `append_log` `backup_path` `collect_visible_solid_bodies`（`[(ボディ, STLの名前の元), …]` を返す） |
| Fusionを使う関数 | `list_target_projects` `walk_f3d_files` `first_created_epoch` `FileFinder` `open_document` `close_document` `is_modified` `get_design` `save_thumbnail` `export_f3d/step/stl/3mf` `find_external_references` `export_item` `Progress` |
| 実行 | `run_mode1` `run_mode2` `run(context)`（Fusionが呼ぶ入口） |

設計の決まり：

- 純粋な関数は Fusion を要しないので `dev/fusion-test` で検証する。Fusion を使う部分は薄く保つ。
- `triage.csv` は BOM 付きUTF-8で書き、読むときは BOM の有無・Shift_JIS(cp932) のどれも受ける。モード1の再実行では既存の `triage.csv` を `triage_日時.csv` に退避する。
- 完了の目印は **`meta.json` を最後に書くこと**。済み判定は `folder_state`：`meta.json` の `note` に「Fusion元: <この行の場所>」が一致すれば `done`（飛ばす）、`meta.json` が無ければ `partial`（やり直す）、`meta.json` はあるが元が違う・読めなければ `conflict`（手作りの同名フォルダなど。上書きせず `resolve_output_folder` が `-v2`、`-v3` … の空きを探し、ログに「注意」を残す）。`meta.json` は一時ファイル（`.tmp`）に書いてから置き換える（`.tmp` は同期が無視する）。
- 設定欄のパスに `< >` が残っていたら `check_setting_path` が実行を止める。
- 1件ごとに `try/except` し、`export_log.csv` に記録して次へ進む。`adsk.doEvents()` と進捗ダイアログ（キャンセル可）で画面を固めない。
- 形式ごと（f3d / STEP / STL / 3MF / thumb）に try し、1つ失敗しても残りを出す。失敗があれば `meta.json` を書かず、その作品を失敗にする。
- モード2は、`version_id` → `datafile_id` → 対象プロジェクトの再走査の順でファイルを探し、ログの `detail` に「取得: …」と残す。古い版で引けたら `latestVersion` に替える。
- STL は、ルートと全オカレンスの「表示中のソリッドボディ」を対象にし、ファイル名はルート直下ならボディ名、オカレンス内なら `コンポーネント名_ボディ名`（`Occurrence.component.name`）。重複は `_2` などで避ける。`STL_PER_BODY = False` で1ファイルにまとめる。
- `meta.json` の雛形の `note` に「Fusion元: プロジェクト/フォルダ/名前」を入れる。
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
4. **外部参照を含むデザインの `.f3d` 書き出し**。UI では外部参照を含むと `.f3z` になる。API で `.f3d` 名を指定したときの中身（参照先を含むか）とエラーの有無を確認する。外部参照の判定（`isReferencedComponent` / `documentReferences` / `hasChildReferences`）が実際に立つかも見る。
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
