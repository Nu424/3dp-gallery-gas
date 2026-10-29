"""実機確認用のテスト作品フォルダを dev/sample-items/out/ に作る（標準ライブラリのみ）。
できたフォルダをテスト用 items/ にそのまま置いて同期を試す。"""
import json, struct, zlib
from pathlib import Path

OUT = Path(__file__).parent / "out"

def png(path, w, h, rgb):
    # 単色の PNG を書く（サムネイル表示の確認用）
    raw = b"".join(b"\x00" + bytes(rgb) * w for _ in range(h))
    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    data = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) \
        + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")
    path.write_bytes(data)

def item(name, meta, files=(), thumb=None, photo=None, raw_meta=None):
    d = OUT / name
    d.mkdir(parents=True, exist_ok=True)
    if raw_meta is not None:
        (d / "meta.json").write_text(raw_meta, encoding="utf-8")
    elif meta is not None:
        (d / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    for f in files:
        (d / f).write_text("dummy\n", encoding="utf-8")
    if thumb:
        png(d / "thumb.png", 300, 200, thumb)
    if photo:
        png(d / "photo_使用中.png", 200, 200, photo)

# 1. 正常：画像・写真・各形式あり（BOM 付き meta.json も兼ねる）
item("20250612_テスト_流路セルホルダー", None, ["holder.f3d", "holder.step", "base.stl", "clip.stl"],
     thumb=(224, 122, 46), photo=(79, 134, 198),
     raw_meta="﻿" + json.dumps({"author": "テスト", "purpose": "表示確認用の正常な作品", "status": "使用中",
                                     "tags": ["テスト", "顕微鏡"], "note": ["BOM 付きの meta.json。", "写真が1枚ある。"]}, ensure_ascii=False, indent=2))
# 2. 正常：画像なし（アイコン表示の確認）、note が文字列、タグにカンマ
item("20240101_テスト_画像なし", {"author": "テスト", "purpose": "画像が無いときのアイコン表示", "status": "参考",
     "tags": ["テスト", "カンマ,入り"], "note": "1行目\n2行目"}, ["part.stl"])
# 3. 数式と誤解されうる note（レビュー S4 の確認）
item("20230505_テスト_数式っぽいメモ", {"author": "テスト", "purpose": "- で始まる用途", "status": "引退",
     "tags": ["テスト"], "note": ["- ハイフンで始まる行", "=1+1", "+81 で始まる行", "@で始まる行"]}, ["x.stl"], thumb=(91, 158, 106))
# 4. 要対応になるべきもの
item("20260722_テスト_必須が空", {"author": "", "purpose": "", "status": "使用中"}, ["a.stl"])
item("20260723_テスト_状態が選択肢外", {"author": "テスト", "purpose": "状態の検査", "status": "使ってる"})
item("20260724_テスト_壊れたJSON", None, raw_meta='{"author": "テスト", "purpose": ')
item("テスト_日付なし", {"author": "テスト", "purpose": "フォルダ名の検査", "status": "参考"})
item("20260725_テスト_metaなし", None, ["only.stl"])
# 5. 無視されるべきもの
item("_テスト_無視される", {"author": "テスト", "purpose": "先頭 _ は無視", "status": "参考"})
print("作成:", OUT)
