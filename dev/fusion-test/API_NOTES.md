# Fusion API 照合メモ（fusion_export.py）

2026-10-30 に Autodesk 公式 API リファレンスと照合した（第2ラウンドで `Occurrence.breakLink` と BreakLink サンプルを追加照合）。後で `tools/docs/DEVELOPMENT.md` に転記する。

- リファレンスの URL は `https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/<名前>.htm`。**ページ名に名前空間の接頭辞（`core_` / `fusion_`）が付く形に変わっている**。計画書にある旧 URL（`.../files/ExportManager.htm` など接頭辞なし）は 404 になる。下の表は新しい URL。
- 実機では未確認。「確信度」は、リファレンスに明記されているかどうかで付けた（高＝明記、中＝明記はないが記述から推定、低＝推測）。

## 使っている API

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
| `Occurrence.breakLink()` | R5: 自分で開いたドキュメントで、外部参照の配置をローカルに取り込んでから f3d を書き出す（`break_external_links`） | `isReferencedComponent` が true の配置について、リンクを切り、その配置が参照する**ローカルな Component を作る**（取り込んだ後は `occurrence.component` で取れる）。戻り値 bool（成功で true）。**外部参照でない配置に呼ぶと失敗する**。2017年9月に追加。入れ子の扱い・取り込み後に他のオカレンス（プロキシ）が無効になるかは明記なし → 周ごとに `allOccurrences` を取り直し、1つずつ try。False・例外は次の周で試し直し、進まなくなるか上限 `BREAK_LINK_MAX_ROUNDS`（20 周）で止める。残ったものを「取り込めなかった」としてログ（要目視確認）に出す | 高（仕様）／中（入れ子） | [fusion_Occurrence_breakLink](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/fusion_Occurrence_breakLink.htm) |
| BreakLink サンプル | 取り込みの書き方の手本 | サンプルは `rootComponent.occurrences`（最上位だけ）を**先にリストへ集めてから** `isReferencedComponent` のものに `breakLink()` を呼ぶ。理由は「リンクを切るとコレクションが変わり、回しながらだと問題が起きる」とコメントにある。こちらは入れ子にも対応するため `allOccurrences` を使い、同じく先にリストへ集めてから処理する。サンプルは保存しない（こちらも `close(False)` で破棄） | 高 | [BreakLink_Sample](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/BreakLink_Sample.htm) |
| `UserInterface.createProgressDialog()` / `ProgressDialog.show(title, message, min, max, delay)` / `.isCancelButtonShown` / `.cancelButtonText` / `.progressValue` / `.maximumValue` / `.message` / `.wasCancelled` / `.hide()` | 進捗 | すべて確認 | 高 | [core_ProgressDialog](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/core_ProgressDialog.htm), [core_ProgressDialog_show](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/core_ProgressDialog_show.htm) |
| `UserInterface.messageBox(text)` | まとめの表示 | 確認 | 高 | [core_UserInterface_messageBox](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/core_UserInterface_messageBox.htm) |
| `adsk.doEvents()` | 画面を固めない | Python モジュールの関数。リファレンスのページは見つけられなかった（広く使われている） | 中 | — |
| `.manifest`（`"autodeskProduct": "Fusion"`, `"type": "script"` ほか） | 登録用 | ユーザーマニュアルで形式を確認。`id` は未使用で空でもよい。フォルダ名と .py/.manifest の名前を揃える | 高 | [WritingDebugging_UM](https://help.autodesk.com/cloudhelp/ENU/Fusion-360-API/files/WritingDebugging_UM.htm) |

## 確信が持てない点（実機で確認すること、優先度順）

1. **`Data.findFileById` でどの ID が引けるか**。モード2のログの detail「取得: …」を見る。`version_id` で常に引けるなら `datafile_id` と再走査は保険のまま残してよい。`datafile_id` でしか引けない／再走査ばかりなら、試す順（`lookup_candidates`）を見直す。古い triage.csv（version_id 列なし）は datafile_id → 再走査で引く。`?version=N` 付きで引いたとき `latestVersion` が期待どおり最新版を返すかも確認する。
2. **オカレンス内ボディ（プロキシ）を STL 書き出ししたとき、組立上の位置で出るか**。リファレンスでは `Occurrence.bRepBodies` はプロキシを返すとあるが、STL の座標に変換が反映されるかは明記なし。多部品のアセンブリで、ボディごとの STL をスライサーに並べて確認する。
3. **ルート単位の STL（STL_PER_BODY=False）と 3MF に、非表示のボディやサーフェスボディが含まれるか**。含まれるなら、表示中ボディだけを対象にする実装に変える。
4. **外部参照の取り込み（R5）**。実機確認（Fusion 2705.1.15）で、外部参照を含むデザインの f3d は開くと中身が空だった（STEP/STL は出ていた）。API の Fusion アーカイブ書き出しは参照先を含まず、参照先を含む本物の f3z は API では作れない（Autodesk フォーラムの回答）。そこで自分で開いたドキュメントに限り `breakLink()` で取り込んでから f3d を書き出すようにした。実機で確かめること: (a) 書き出した f3d を開いて中身（参照先の形状）が入っているか、(b) 入れ子の参照（参照先の中にさらに参照）も取り込めるか、ログの「外部参照 N 件を取り込んで f3d を書き出し」の N が配置の数と合うか、(c) 取り込み後に `close(False)` で閉じたとき、保存を問うダイアログが出ないか・クラウドの元ファイルに新しい版ができていないか（データパネルの版の履歴で確認）、(d) 取り込みの前に出す STEP/STL/3MF/サムネイルが今までどおりか、(e) 元々開いていたドキュメントのときは取り込まずに「成功（要目視確認）」になるか。外部参照の判定（`isReferencedComponent` / `documentReferences` / `hasChildReferences`）が実際に立つかも見る。
5. **開いた直後のサムネイルが真っ白・描画途中にならないか**。`doEvents` を数回挟んでいるが足りなければ回数を増やすか、`time.sleep` を足す。ViewCube の向きが変えられているデータで斜め視点がばらつかないか。
6. **`DataFolder.dataFiles` / `dataFolders` が初回アクセスで全部そろうか**（クラウドからの遅延読み込みで件数が欠けないか）。モード1の件数を Fusion のデータパネルの件数と比べる。
7. **`DataFile.versions` の dateCreated が「最初の版」まで取れるか**、そして大量ファイルで遅くないか。遅ければ最新版の `dateCreated` だけにする。
8. `Documents.open` がすでに開いているファイルに対して何を返すか（実装では事前に `app.documents` を見て、開いていれば閉じない扱いにしている）。外部参照の子ドキュメントが裏で開かれたまま残らないか。
9. `fileExtension` の値（`"f3d"` か大文字か）と、外部参照を含むデザインも `f3d` で列挙されるか。
10. 確認した Fusion のバージョン（`app.version`）を DEVELOPMENT.md に記録する。

## 第2ラウンドで照合した箇所（2026-10-30）

- `break_external_links`: 上の `Occurrence.breakLink()` と BreakLink サンプルに合わせた（先にリストへ集める、`isReferencedComponent` が true のものだけに呼ぶ、戻り値 bool を見る）。
- `export_item` の順番を STEP → STL → 3MF → thumb.png → 取り込み → f3d に変えた。取り込みは自分で開いたドキュメントのときだけ（`open_document` の「自分で開いたか」）で、閉じるのは従来どおり `Document.close(False)`（変更を捨てて閉じる。リファレンスで確認済み）。
- `Component.allOccurrences` は「階層を問わず全オカレンス」を返す（照合済み）。取り込みでコレクションが変わるので、周ごとに取り直している。
- meta.json の `fusion_id` には triage.csv の `datafile_id`（= `DataFile.id`、版に依らない lineage ID。照合済み）を入れる。モード2で `version_id` から引いて最新版に替えても `id` は同じ系列のはずだが、明記はない（中）。
- 新たに呼ぶ Fusion API は `Occurrence.breakLink()` だけ。設定欄の既定 `TRIAGE_DIR` は `os.path.expanduser("~")` + `Documents`（Python の標準ライブラリ。Windows では `%USERPROFILE%`）。OneDrive でドキュメントを移している PC では、エクスプローラーの「ドキュメント」と別の場所（`C:\Users\<名前>\Documents`）になりうる。
