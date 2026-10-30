# CLAUDE.md — 3dp-gallery-gas

研究室の3Dプリント作品ギャラリー。共有ドライブの `items/`（作品フォルダ＝唯一の正）を GAS がスプシに同期し、Web アプリで一覧する。Fusion のクラウドから作品フォルダを一括で書き出すスクリプト付き。概要は `README.md`。

## 最初に読むもの

- `tools/docs/DEVELOPMENT.md`：構成、画面とサーバーの約束、データ仕様（正）、「データ仕様を変えるときに直す箇所」、Fusion API の確認状況。改修の前に必ず読む
- `docs/work-plan.md`：計画と進捗（ラウンドごとの要望・方針・完了条件）。作業の再開はここの「進捗」から
- `HANDOFF.md`：ユーザーに実機で確かめてもらう項目と、その結果

## 構成

| 場所 | 中身 |
| --- | --- |
| `tools/gas/` | GAS の4ファイル（`Code.gs` / `index.html` / `guide.html` / `appsscript.json`）。ユーザーがエディタに貼り付けて使う |
| `tools/fusion_export/` | Fusion のスクリプト（`fusion_export.py` と `.manifest`）。冒頭の設定欄だけを利用者が書き換える |
| `tools/docs/` | 利用者・管理者・改修者向けの文書。共有ドライブにも置かれる |
| `tools/items_template/_template/` | 作品フォルダのひな形 |
| `dev/` | テストとプレビュー（共有ドライブには置かない） |
| `docs/` | 計画書（`plan.md`。初版のまま。差分は HANDOFF の末尾）、作業計画、レビューの記録、モック、README 用の画像 |

## コマンド

```
node --test dev/gas-test                       # Code.gs のテスト（Node 20+、依存なし）
python -m unittest discover -s dev/fusion-test # fusion_export.py のテスト（偽の adsk）
node dev/preview/build.mjs                     # プレビュー dev/preview/out/index.html を作る（?scenario=many など）
```

画面の確認は `dev/preview/cdp-check.mjs`（実時間の Chrome。使い方は DEVELOPMENT.md の「プレビュー」）。PC 1400px とスマホ 390px（`PAGE=frame-390.html FRAME=1`）でスクショを撮って目で見る。`dev/preview/out/` は gitignore（使い捨てのスクショ用スクリプトもここに置く）。

## 守ること（設計上の制約）

- GAS は4ファイルのまま。ファイルの追加・分割、外部ライブラリ、拡張サービスは入れない（コピペで動くことが前提）
- `appsscript.json` の `oauthScopes` を広げない。必要なら理由を添えてユーザーに確認する
- `guide.html` にスクリプトレット（`<?` で始まる構文）を書かない。AI 用の文は `#ai-prompt` の1か所が正
- meta.json の既存キーの意味を変えない。`fusion_id` は済み判定の印（消さない・書き換えない）
- 960px 以下の重なり（詳細・絞り込みシート・追加パネル）と「戻る」の履歴は `state.layer` / `applyLayers` に集約している。個別に hidden や history を触らない
- PC（1280px 以上）の見た目を変える改修は、変える前と見比べてから
- データ仕様を変えたら、DEVELOPMENT.md の「データ仕様を変えるときに直す箇所」を全部直す（Code.gs・guide.html・テスト・文書）

## 作業の進め方

- 要望ごとに `docs/work-plan.md` へラウンドとして追記（要望・方針・完了条件）→ 実装 → テストとスクショ → 文脈を持たない別エージェントで独立レビュー（must/should/could）→ 対処を `docs/review-<日付>-rN.md` に記録 → ユーザーに確かめてほしい項目を `HANDOFF.md` に追記
- コミットは段階ごとに、日本語＋プレフィックス（`feat:` / `fix:` / `docs:`）
- 実機（GAS のデプロイ、Fusion での実行）はユーザーが行う。こちらはローカルで確かめられる所までやり、何を見てほしいかを伝える
- push はユーザーが行う（公開リポジトリ）

## 注意（ハマりどころ）

- **公開リポジトリ**。本物のフォルダID・スプシURL・デプロイURL・共有ドライブ名・人名を書かない（例は `<共有ドライブ名>`・`1AbCdEf…`・架空の人名）。サンプルデータも架空のものだけ
- **シェル経由でファイルを書き換えるとき、`\` が化ける**。Python の通常の文字列やヒアドキュメントで `\3` `\t` を書くと制御文字になる（実際に文書へ混入した）。日本語やバックスラッシュを含む書き換えは、スクリプトをファイルに書いて `python -X utf8` で実行し、文字列は r"..." にする。書いたあとに制御文字が無いか確かめる
- Windows の Python は標準入力を cp932 で読むことがある。日本語を含むスクリプトはヒアドキュメントでなくファイルにする
- Fusion の設定欄のパスは `r"..."`（r を付け忘れると化ける。`\U` などは SyntaxError で起動しない）
- GAS の iframe の中では、スマホは drive.google.com の画像を Cookie なしで読む（失敗する）ので、サーバー経由（`getThumbnails`）で取り直している
