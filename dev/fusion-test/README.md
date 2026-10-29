# fusion-test

`tools/fusion_export/fusion_export.py` の Fusion を要しない部分のテスト（偽の `adsk` を差し込んで import する）。リポジトリのルートで実行する：

```
python -m unittest discover -s dev/fusion-test -v
```
