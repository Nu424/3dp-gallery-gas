# -*- coding: utf-8 -*-
"""
fusion_export.py — Fusion のクラウド上の f3d を開いて、3Dギャラリー用に書き出すスクリプト

使い方（詳しくは tools/docs の OPERATION.md）
  1. 下の「設定欄」を書き換えて保存する
  2. Fusion の「ユーティリティ → スクリプトとアドイン」でこのスクリプトを選び、実行する
     （初回は「+」→ このフォルダ fusion_export を選んで登録する）

モードは2つ
  モード1（サムネイルのみ）: 対象プロジェクトの f3d を全部開いて画像を撮り、triage.csv（一覧）を作る。
                             triage.csv の rank 列に A/B/C を書いて仕分ける。
                             既存の triage.csv は退避し、記入済みの rank と folder_name は引き継ぐ。
  モード2（フル書き出し）  : triage.csv の rank が A か B の行だけ、作品フォルダを作って
                             f3d / STEP / STL / 3MF / thumb.png / meta.json を書き出す。
  TARGET_NAMES に名前を書くと、どちらのモードもその名前のファイルだけを扱う（モード2では rank を問わない）。

このファイルは標準ライブラリと adsk（Fusion 付属）だけを使う。追加のインストールは要らない。
"""

# =============================================================================
# 設定欄（ここだけ書き換えればよい）
# =============================================================================

# パスの書き方（下のパスの項目に共通）
#   - Windows のパスは r"..." で囲む（\ をそのまま書けるようにするため）。
#   - "~" で始めると、このPCのユーザーのフォルダ（C:\Users\<名前>）を指す。

# -----------------------------------------------------------------------------
# 共通（モード1・モード2の両方で使う）
# -----------------------------------------------------------------------------
# 実行するモード。1 = サムネイルのみ（仕分け用の一覧を作る）、2 = フル書き出し
MODE = 1

# 対象にする Fusion のプロジェクト名のリスト。空のリスト [] なら全プロジェクトが対象。
# 例: PROJECT_NAMES = ["研究室共有", "山田の試作"]（1つだけなら PROJECT_NAMES = "研究室共有" でもよい）
# 対象は Fusion で今選んでいるチーム（データパネル左上のハブ）の中のプロジェクトだけ。
PROJECT_NAMES = []

# 扱うファイルを名前で絞る（Fusion 上のファイル名のリスト）。空のリスト [] なら全部。
# 例: TARGET_NAMES = ["流路セルホルダー", "顕微鏡ステージ"]（1つだけなら TARGET_NAMES = "流路セルホルダー" でもよい）
#   - 名前は完全一致（前後の空白は無視。濁点の表し方の違いもそろえて比べる）。
#   - モード1: 指定した名前のファイルだけ画像を撮る。既存の triage.csv の他の行はそのまま残る。
#   - モード2: triage.csv の中で指定した名前の行だけを書き出す。rank は問わない（空や C でも書き出す）。
#   - 見つからなかった名前は、最後のメッセージとログ（export_log.csv）に出る。
#   - モード2で、同じ名前の行が triage.csv に複数（別のプロジェクトやフォルダの同名ファイル）あれば、全部を書き出し、ログに注意を出す。
TARGET_NAMES = []

# -----------------------------------------------------------------------------
# モード1だけで使う
# -----------------------------------------------------------------------------
# モード1の出力先。triage.csv・サムネイル画像・ログがここに書かれる。
# 空文字 "" なら「ドキュメント\3Dギャラリー_仕分け」（このPCの中。仕分けの作業用なので共有しなくてよい）。
#   「ドキュメント」はエクスプローラーの「ドキュメント」と同じ場所（OneDrive に移している PC では、その移した先）。
#   実際の場所は、終了時のダイアログに出る。
# 共有ドライブに置きたければ書き換えてよい（例 r"G:\共有ドライブ\研究室\3Dギャラリー_仕分け"）。その場合は items の外にする
# （items の中だと作品フォルダと間違えて同期されるため）。
# モード2の TRIAGE_CSV が空のときは、ここの triage.csv を読む。
TRIAGE_DIR = ""

# -----------------------------------------------------------------------------
# モード2だけで使う
# -----------------------------------------------------------------------------
# モード2で読む triage.csv のパス（モード1で作り、rank と folder_name を記入したもの）。
# 空文字 "" なら TRIAGE_DIR の中の triage.csv を読む（ふつうはこのままでよい）。
# スプシで編集した場合は「ファイル → ダウンロード → カンマ区切り形式（.csv）」で保存し、
# TRIAGE_DIR の triage.csv と置き換えるか、ここにそのパスを書く。
TRIAGE_CSV = ""

# モード2の出力先＝ギャラリーの items フォルダ。ここに書き出すと、そのままギャラリーへの登録になる。
#   - Googleドライブ（パソコン版）で見える「共有ドライブ」内の 3Dギャラリー を指す。
#     マイドライブにはしない（卒業で個人のアカウントが消えると、中身ごと消えるため）。
#   - <共有ドライブ名> は研究室の共有ドライブの名前に書き換える（< > ごと消す）。残っていると止まる。
#   - ドライブ文字は G: が多いが、PC によって違う。エクスプローラーで「Google Drive」の文字を確認する。
OUTPUT_DIR = r"G:\共有ドライブ\<共有ドライブ名>\3Dギャラリー\items"

# 書き出す meta.json に最初から入れておく値（全作品に同じ値が入る。空ならあとで各自が記入する）。
#   DEFAULT_AUTHOR: 作成者。例 "山田"
#   DEFAULT_STATUS: 状態。選択肢は "使用中" / "参考" / "引退" のどれか（ギャラリー側 Code.gs の STATUS_CHOICES と同じ）。
#                   選択肢にない値を書くと、同期で「要対応」になる。
#   DEFAULT_TAGS  : タグのリスト。例 ["治具", "PLA"]
# 用途（purpose）は作品ごとに違うので、既定値は持たない（空のまま書き出す）。
DEFAULT_AUTHOR = ""
DEFAULT_STATUS = ""
DEFAULT_TAGS = []

# -----------------------------------------------------------------------------
# 細かい設定（ふつうは変えなくてよい）
# -----------------------------------------------------------------------------
# STL をボディごとに分けるか（モード2）。True = ボディごとに1ファイル（<ボディ名>.stl）、False = 全体で1ファイル（<名前>.stl）
STL_PER_BODY = True

# STL / 3MF のメッシュの細かさ（モード2）。"high"（細かい・ファイル大）/ "medium"（標準）/ "low"（粗い・ファイル小）
MESH_QUALITY = "high"

# サムネイル画像の大きさ（ピクセル。モード1の画像とモード2の thumb.png）。ギャラリーのカードの画像枠がおよそ 3:2（はみ出しは切り取り）
# なので、3:2 にしておくと切れる部分が少ない
THUMB_WIDTH = 1200
THUMB_HEIGHT = 800

# =============================================================================
# ここから下は処理本体。改修するときは tools/docs/DEVELOPMENT.md を先に読む。
# =============================================================================

import csv
import datetime
import io
import json
import os
import re
import traceback
import unicodedata

import adsk.core
import adsk.fusion

# ---------------------------------------------------------------------------
# 定数
# ---------------------------------------------------------------------------
# triage.csv の列。モード1で書き、モード2で読む。列名を変えると両方に効く。
TRIAGE_COLUMNS = [
    "project",       # プロジェクト名
    "folder_path",   # プロジェクト直下からのフォルダ（"a/b"。直下なら空）
    "name",          # Fusion 上のファイル名
    "datafile_id",   # DataFile.id（版に依らないID。モード2で開き直すのに使う）
    "version_id",    # DataFile.versionId（その版のID。モード2で最初に試す。古いCSVには無くてもよい）
    "created",       # 作成日（"YYYY-MM-DD HH:MM"、このPCの時刻）
    "modified",      # 最終更新日（同上）
    "image",         # サムネイル画像のファイル名（TRIAGE_DIR 内）
    "rank",          # 仕分け結果 A/B/C（モード1では空。人が記入する）
    "folder_name",   # 作品フォルダ名の案（YYYYMMDD_名前）。必要なら人が直す
]

TRIAGE_FILENAME = "triage.csv"
TRIAGE_DIR_NAME = "3Dギャラリー_仕分け"   # TRIAGE_DIR が空のときに「ドキュメント」の中に作るフォルダ
LOG_FILENAME = "export_log.csv"
LOG_COLUMNS = ["time", "mode", "name", "result", "detail"]
META_FILENAME = "meta.json"
SOURCE_PREFIX = "Fusion元: "      # 旧版が meta.json の note に入れていた元の場所の見出し。旧版の出力の済み判定にだけ使う
FUSION_ID_KEY = "fusion_id"       # meta.json に入れる DataFile.id のキー（済み判定に使う。同期とギャラリーは無視する）
FUSION_MARKER_FILENAME = "fusion_id.tmp"  # 書き出し中の作品フォルダの目印（中身は datafile_id）。同期は *.tmp を無視する
THUMB_FILENAME = "thumb.png"
EXPORT_RANKS = ("A", "B")          # モード2で書き出すランク
FOLDER_NAME_PATTERN = re.compile(r"^(\d{8})_(.+)$")  # GAS の同期と同じ規則

# ログの result 欄に入れる言葉（後でフィルタしやすいよう固定の語にする）
RESULT_OK = "成功"
RESULT_CHECK = "成功（要目視確認）"
RESULT_FAIL = "失敗"
RESULT_SKIP = "スキップ"
RESULT_NOTE = "注意"

# 外部参照の取り込み（breakLink）を繰り返す上限。入れ子1段ごとに1周するので、普通は数周で終わる
BREAK_LINK_MAX_ROUNDS = 20


# =============================================================================
# 純粋な関数（Fusion を使わない部分）
#   名前づけ・CSV・行の選別・スキップ判定・meta.json の生成をここにまとめる。
#   dev/fusion-test のテストで検証しているので、直したらテストも走らせる。
# =============================================================================

# Windows / Mac / Googleドライブでファイル名に使えない文字。制御文字も含めて "_" に置き換える。
_INVALID_CHARS = re.compile(r'[\\/:*?"<>|\x00-\x1f\x7f]')
# Windows で予約されているファイル名（拡張子を付けても使えない）
_RESERVED_NAMES = {"CON", "PRN", "AUX", "NUL"} | {f"COM{i}" for i in range(1, 10)} | {f"LPT{i}" for i in range(1, 10)}
DEFAULT_NAME = "無題"


def sanitize_filename(name):
    """ファイル名・フォルダ名に使えない文字を "_" に置き換える。

    方針: 日本語はそのまま残す（計画書で日本語可としている）。消すのではなく置き換えるのは、
    元の名前との対応が目で追えるようにするため。末尾の空白とドットは Windows で消されて
    名前がずれるので取り除く。空になったら「無題」。
    """
    s = unicodedata.normalize("NFC", str(name or ""))
    s = _INVALID_CHARS.sub("_", s)
    s = s.strip().rstrip(". ")
    if not s:
        return DEFAULT_NAME
    if s.split(".")[0].upper() in _RESERVED_NAMES:
        s = "_" + s
    return s


def epoch_to_text(epoch):
    """UNIX時刻（秒）を "YYYY-MM-DD HH:MM"（このPCのタイムゾーン）にする。不正なら空文字。

    DataFile.dateCreated / dateModified は UNIX 時刻（秒）で返る（公式リファレンスで確認）。
    """
    try:
        if epoch is None or int(epoch) <= 0:
            return ""
        return datetime.datetime.fromtimestamp(int(epoch)).strftime("%Y-%m-%d %H:%M")
    except (TypeError, ValueError, OverflowError, OSError):
        return ""


def date_part(created_text):
    """created 列の文字列から "YYYYMMDD" を取り出す。取れなければ空文字。

    created 列は人がスプシで触ることがあるので、"2025-06-12 10:00" のほか
    "2025/6/12" "20250612" も受け付ける。日付として実在するかも確かめる。
    """
    s = (created_text or "").strip()
    m = re.match(r"^(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})", s) or re.match(r"^(\d{4})(\d{2})(\d{2})", s)
    if not m:
        return ""
    try:
        d = datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return ""
    return d.strftime("%Y%m%d")


def make_folder_name(created_text, name):
    """作成日と名前から作品フォルダ名の案 "YYYYMMDD_名前" を作る。

    日付が取れないときは "00000000_名前" にして、仕分けのときに人が直す前提にする
    （GAS 側は実在しない日付をエラーにするので、直し忘れが「要対応」に出る）。
    """
    return (date_part(created_text) or "00000000") + "_" + sanitize_filename(name)


def is_valid_folder_name(folder_name):
    """フォルダ名が "YYYYMMDD_名前" の形式で、日付が実在するか。"""
    m = FOLDER_NAME_PATTERN.match(folder_name or "")
    return bool(m) and date_part(m.group(1)) == m.group(1)


def unique_name(name, used, style="file"):
    """名前の重複を避ける。used（小文字で保持する集合）に登録してから返す。

    style="file"  : "body.stl" → "body_2.stl" → "body_3.stl"（拡張子の前に番号）
    style="folder": "20250612_治具" → "20250612_治具-v2" → "-v3"（計画書の命名規則）
    Windows とGoogleドライブは大文字小文字を区別しないことがあるので、比較は小文字で行う。
    """
    if style == "file":
        stem, ext = os.path.splitext(name)
        candidates = (name if n == 1 else f"{stem}_{n}{ext}" for n in range(1, 10000))
    else:
        candidates = (name if n == 1 else f"{name}-v{n}" for n in range(1, 10000))
    for cand in candidates:
        if cand.lower() not in used:
            used.add(cand.lower())
            return cand
    raise ValueError("名前の重複を解消できません: " + name)


def source_text(project, folder_path, name):
    """旧版が meta.json の note に入れていた「Fusion元」の場所。空の部分は詰める（旧版の出力の済み判定用）。"""
    parts = [p for p in [project, (folder_path or "").strip("/"), name] if p]
    return "/".join(parts)


def _as_tags(tags):
    """タグの既定値をリストにそろえる。文字列1つが書かれていても受ける。空の要素は落とす。"""
    if isinstance(tags, str):
        tags = [tags]
    try:
        return [str(t).strip() for t in (tags or []) if str(t).strip()]
    except TypeError:
        return []


def build_meta(fusion_id, author=None, status=None, tags=None):
    """meta.json の雛形。

    note は空の配列（Fusion の場所は入れない。ギャラリーに出てしまうため）。
    代わりに fusion_id（DataFile.id。版・名前・置き場所が変わっても同じ）を入れ、済み判定に使う。
    未知のキーは同期でもギャラリーでも無視されるので、画面には出ない。
    author / status / tags は省略すると設定欄の DEFAULT_* を使う。purpose は作品ごとに違うので常に空
    （必須値が空なら、同期で「未記入」として見える）。
    """
    return {
        "author": (DEFAULT_AUTHOR if author is None else author) or "",
        "purpose": "",
        "status": (DEFAULT_STATUS if status is None else status) or "",
        "tags": _as_tags(DEFAULT_TAGS if tags is None else tags),
        "note": [],
        FUSION_ID_KEY: fusion_id or "",
    }


def meta_json_text(meta):
    """meta.json の中身の文字列。日本語をそのまま読めるよう ensure_ascii=False、インデント2。"""
    return json.dumps(meta, ensure_ascii=False, indent=2) + "\n"


def write_meta_json(folder, meta):
    """meta.json を書く。完了の目印なので、一時ファイルに書いてから置き換える。

    途中で止まっても「中途半端な meta.json があるのに完了扱い」にならないようにするため。
    """
    path = os.path.join(folder, META_FILENAME)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(meta_json_text(meta))
    os.replace(tmp, path)
    return path


def is_done(folder):
    """作品フォルダが書き出し済みか。meta.json があれば完了（最後に書くので）。"""
    return os.path.isfile(os.path.join(folder, META_FILENAME))


def write_marker(folder, fusion_id):
    """書き出しの最初に、作品フォルダへ目印 fusion_id.tmp（中身は datafile_id）を書く。

    途中で止まったフォルダ（meta.json が無い）が、どの作品のものかを次の実行で見分けるため。
    名前が *.tmp なので、GAS の同期は無視する（ギャラリーに出ない）。完了したら remove_marker で消す。
    """
    with open(os.path.join(folder, FUSION_MARKER_FILENAME), "w", encoding="utf-8", newline="\n") as f:
        f.write((fusion_id or "").strip() + "\n")


def read_marker(folder):
    """目印 fusion_id.tmp の中身（datafile_id）を返す。無い・読めない・空なら None。"""
    try:
        with open(os.path.join(folder, FUSION_MARKER_FILENAME), encoding="utf-8-sig") as f:
            value = f.read().strip()
    except (OSError, UnicodeDecodeError):
        return None
    return value or None


def remove_marker(folder):
    """目印を消す。消せなくても害は無い（判定は meta.json が先）ので、エラーにしない。"""
    try:
        os.remove(os.path.join(folder, FUSION_MARKER_FILENAME))
    except OSError:
        pass


def folder_state(folder, fusion_id, source=""):
    """出力先フォルダの状態を返す。

      "new"        : フォルダが無い（新しく作る）
      "partial"    : フォルダはあるが meta.json が無い（途中で止まった。やり直す）。
                     目印 fusion_id.tmp がこの行の datafile_id と一致するか、目印が無いとき。
                     目印が無いときに使ってよいのは、triage.csv どおりの名前（-v2 などでない）だけ。
                     それは resolve_output_folder が判断する
      "done"       : meta.json の fusion_id がこの行の datafile_id と一致（書き出し済み）。
                     旧版の出力（fusion_id が無い）は、note の「Fusion元: <source>」行が一致すれば done
      "done_no_id" : meta.json はあるが fusion_id が無い（手で消した、手作りの同名フォルダ、旧版の出力で
                     「Fusion元」行が無いか違う）。同じ作品かどうか分からないが（Fusion で名前や場所を変えただけかも
                     しれない）、重複して書き出すより飛ばすほうが害が少ないので、済み扱いで飛ばす
      "conflict"   : fusion_id が違う＝別の作品、meta.json が読めない、または途中のフォルダの目印が別の作品。
                     触らずに -v2 などへ書く
    meta.json は人が記入していくので、fusion_id と note の「Fusion元」行のほかは問わない。
    meta.json があれば目印は見ない（完了後に目印が消せずに残っていても害が無いように）。
    """
    meta_path = os.path.join(folder, META_FILENAME)
    if not os.path.isfile(meta_path):
        if not os.path.isdir(folder):
            return "new"
        mark = read_marker(folder)
        return "partial" if mark is None or mark == (fusion_id or "").strip() else "conflict"
    try:
        with open(meta_path, encoding="utf-8-sig") as f:
            meta = json.load(f)
    except Exception:
        return "conflict"
    if not isinstance(meta, dict):
        return "conflict"
    saved_id = meta.get(FUSION_ID_KEY)
    saved_id = saved_id.strip() if isinstance(saved_id, str) else ""
    if saved_id:
        return "done" if saved_id == (fusion_id or "").strip() else "conflict"
    # 旧版の出力: note の「Fusion元」行で照合する
    note = meta.get("note")
    lines = [note] if isinstance(note, str) else note if isinstance(note, list) else []
    head = SOURCE_PREFIX.strip()  # "Fusion元:"
    sources = [x.strip()[len(head):].strip() for x in lines if isinstance(x, str) and x.strip().startswith(head)]
    if sources and (source or "").strip() in sources:
        return "done"
    # 旧版の行が違う・無い: fusion_id が無いので同じ作品か言い切れない。重複して書き出すより飛ばす
    return "done_no_id"


def resolve_output_folder(base_dir, folder_name, fusion_id, source, reserved):
    """書き出し先のフォルダ名を決める。戻り値: (フォルダ名, 状態, 避けたフォルダ名のリスト)

    候補は folder_name, folder_name-v2, -v3 …。出力先にある候補をすべてと、その次の空き1つまでを
    先に調べてから決める（途中で決めると、後ろにある自分の完了済みを見落として重複して書き出すため）。
      1. fusion_id が一致する完了済み（done）があれば、番号に関わらずそれを選ぶ
      2. 無ければ、番号の小さい順に最初の「使える」候補を選ぶ。次の候補は使えない（飛ばす）:
         - conflict（別の作品の完了済み、読めない meta.json、目印が別の作品の途中のフォルダ）
         - -v2 以降で、目印 fusion_id.tmp の無い途中のフォルダ（誰のものか分からない。
           triage.csv の他の行が CSV 内の重複処理で使った名前かもしれない）
         - -v2 以降で reserved にある名前（triage.csv の他の行が使うフォルダ名。小文字）
    選んだ名前は reserved に足す（後の行と取り合わないように）。
    避けたフォルダ名のリストは、選んだ候補より前の conflict（ログの注意に使う）。
    再実行しても同じ順に調べるので、前回 -v2 に書いた作品は -v2 で「done」と判定され、番号が変わらない。
    名前の比較は大文字小文字を区別しない（Windows と Googleドライブに合わせる）。
    """
    try:
        existing = {n.lower(): n for n in os.listdir(base_dir)}
    except OSError:
        existing = {}
    prefix = folder_name.lower() + "-v"
    last = 1  # 出力先にある候補の最大の番号
    for low in existing:
        rest = low[len(prefix):] if low.startswith(prefix) else ""
        if re.fullmatch(r"[0-9]+", rest):
            last = max(last, int(rest))

    avoided, choice = [], None
    for n in range(1, 10000):
        if n > last and choice is not None:
            break
        cand = folder_name if n == 1 else f"{folder_name}-v{n}"
        actual = existing.get(cand.lower(), cand)  # 出力先にあれば、その実際の名前（大文字小文字）
        path = os.path.join(base_dir, actual)
        state = folder_state(path, fusion_id, source)
        if state == "partial" and n > 1 and read_marker(path) is None:
            state = "conflict"
        if state == "done":
            reserved.add(actual.lower())
            return actual, state, avoided
        if choice is not None:
            continue  # 後ろに自分の完了済みが無いかだけ見る
        if n > 1 and cand.lower() in reserved:
            continue
        if state == "conflict":
            avoided.append(actual)
            continue
        choice = (actual, state, list(avoided))
    if choice is None:
        raise ValueError("空いているフォルダ名が見つかりません: " + folder_name)
    reserved.add(choice[0].lower())
    return choice


def write_triage_csv(path, rows):
    """triage.csv を BOM 付き UTF-8 で書く（Excel で開いても文字化けしないように）。"""
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=TRIAGE_COLUMNS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in TRIAGE_COLUMNS})


def can_overwrite(path):
    """既存のファイルを書き換えられるか（Excel などで開いたままだと書けない）。無ければ True。

    読み書きの形（r+b）で開いてみるだけで、中身は変えない。
    """
    if not os.path.isfile(path):
        return True
    try:
        with open(path, "r+b"):
            pass
        return True
    except OSError:
        return False


def fallback_triage_path(path, now=None):
    """triage.csv を書けなかったときの書き先 "triage_new_YYYYMMDD_HHMMSS.csv" を返す。"""
    now = now or datetime.datetime.now()
    stem, ext = os.path.splitext(path)
    return f"{stem}_new_{now.strftime('%Y%m%d_%H%M%S')}{ext}"


def save_triage_csv(path, rows, now=None):
    """モード1の最後に triage.csv を書き直す。既存のものは日時付きの名前に退避してから書く。

    戻り値: (書いたパス, 書けなかった理由。書けたら空文字)
    撮影中に Excel などで開かれて書けなかったら、結果を失わないよう triage_new_<日時>.csv に書く。
    """
    try:
        if os.path.isfile(path):
            os.replace(path, backup_path(path, now))
        write_triage_csv(path, rows)
        return path, ""
    except OSError as e:
        alt = fallback_triage_path(path, now)
        write_triage_csv(alt, rows)
        return alt, str(e)


def read_triage_csv(path):
    """triage.csv を読み、行の辞書のリストを返す。

    BOM の有無どちらも受ける（utf-8-sig は BOM が無くても読める）。
    Excel の「CSV（コンマ区切り）」で保存し直すと Shift_JIS(cp932) になるので、
    UTF-8 で読めなければ cp932 で読み直す。列名の前後の空白は取り除く。
    """
    with open(path, "rb") as f:
        raw = f.read()
    for enc in ("utf-8-sig", "cp932"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ValueError("triage.csv の文字コードが読めません（UTF-8 で保存し直してください）")
    # セル内の改行（備考欄など）を壊さないよう、newline="" の StringIO で csv に渡す
    reader = csv.DictReader(io.StringIO(text, newline=""))
    rows = []
    for r in reader:
        rows.append({(k or "").strip(): (v or "").strip() if isinstance(v, str) else "" for k, v in r.items()})
    header = [(x or "").strip() for x in (reader.fieldnames or [])]
    missing = [c for c in ("project", "name", "datafile_id", "rank") if c not in header]
    if missing:
        raise ValueError("triage.csv に必要な列がありません: " + ", ".join(missing))
    return rows


def normalize_rank(rank):
    """rank 列を正規化する。全角の "Ａ" や小文字の "a"、前後の空白も A として扱う。"""
    return unicodedata.normalize("NFKC", rank or "").strip().upper()


def select_rows_for_export(rows, ignore_rank=False):
    """モード2で書き出す行を選び、作品フォルダ名を確定する。

    戻り値: (選んだ行のリスト, 注意メッセージのリスト)
      - rank が A/B の行だけ選ぶ。ignore_rank=True（TARGET_NAMES で名前を指定したとき）は rank を問わない
      - datafile_id が空の行は選ばず、注意を出す（済み判定に使う fusion_id が決まらず、
        重複して書き出したり別の作品と取り違えたりしうるため。モード1で撮り直せば入る）
      - folder_name が空なら created と name から作る。書いてあれば使えない文字だけ置き換える
      - 同じフォルダ名が複数あれば2つ目以降に -v2, -v3 を付ける
        （そのままだと2つ目が1つ目の meta.json を見て「済み」と飛ばされてしまうため）
      - 形式外のフォルダ名は書き出すが注意を出す（GAS の同期でエラーになるので直してもらう）
    CSV の行順で番号を振るので、同じ CSV なら再実行しても同じフォルダ名になる。
    """
    selected, warnings, used = [], [], set()
    for r in rows:
        if not ignore_rank and normalize_rank(r.get("rank")) not in EXPORT_RANKS:
            continue
        if not (r.get("datafile_id") or "").strip():
            warnings.append(f"「{r.get('name', '')}」は datafile_id が空のため書き出しません"
                            "（済み判定ができないため。モード1で撮り直すと入ります）")
            continue
        fn = (r.get("folder_name") or "").strip()
        fn = sanitize_filename(fn) if fn else make_folder_name(r.get("created"), r.get("name"))
        unique = unique_name(fn, used, style="folder")
        if unique != fn:
            warnings.append(f"フォルダ名の重複を避けるため「{fn}」→「{unique}」にしました")
        if not is_valid_folder_name(unique):
            warnings.append(f"フォルダ名「{unique}」は YYYYMMDD_名前 の形式ではありません（同期でエラーになります）")
        out = dict(r)
        out["folder_name"] = unique
        selected.append(out)
    return selected, warnings


def select_projects(all_names, wanted):
    """対象プロジェクト名を選ぶ。戻り値: (対象の名前リスト, 見つからなかった名前リスト)

    wanted が空なら全部。名前の打ち間違いに気づけるよう、見つからない名前も返す。
    wanted に文字列1つが書かれていても、その名前1つとして扱う（部分一致にしない）。
    """
    wanted = as_name_list(wanted)
    if not wanted:
        return list(all_names), []
    found = [n for n in all_names if n in wanted]
    missing = [n for n in wanted if n not in all_names]
    return found, missing


def normalize_name(name):
    """TARGET_NAMES の照合用に名前をそろえる（前後の空白を除き、NFC 正規化）。

    NFC にするのは、Mac で付けた名前などで「が」が「か＋濁点」の2文字になっていても一致させるため。
    全角・半角や大文字小文字は区別する（別の名前として付けられることがあるため）。
    """
    return unicodedata.normalize("NFC", str(name or "")).strip()


def as_name_list(value):
    """設定欄の名前のリスト（TARGET_NAMES・PROJECT_NAMES）をリストにそろえる。

    文字列1つが書かれていたら [その文字列] にする（そのままだと1文字ずつに割られてしまうため）。
    None と空文字は空のリスト。
    """
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    try:
        return list(value)
    except TypeError:
        return [value]


def duplicate_names(items, name_of=lambda x: x):
    """同じ名前（normalize_name でそろえて比べる）が複数あるものを [(名前, 数), ...] で返す（最初に出た順）。

    モード2で TARGET_NAMES の名前の行が triage.csv に複数（別のプロジェクトやフォルダの同名ファイル）あるとき、
    全部書き出すことをログで知らせるのに使う。
    """
    counts = {}
    for it in items:
        key = normalize_name(name_of(it))
        if key:
            counts[key] = counts.get(key, 0) + 1
    return [(k, c) for k, c in counts.items() if c > 1]


def select_by_names(items, wanted, name_of=lambda x: x):
    """items のうち、名前（name_of(item)）が wanted のどれかと一致するものを選ぶ。

    戻り値: (選んだもののリスト（items の順）, 見つからなかった名前のリスト（wanted の順・書いたまま）)
    wanted が空なら全部を返す。照合は normalize_name をかけたうえで完全一致。
    同じ名前のファイルが複数あれば全部選ぶ（プロジェクトやフォルダが違う同名ファイル）。
    wanted に文字列1つが書かれていても、その名前1つとして扱う（as_name_list）。
    """
    wanted = as_name_list(wanted)
    if not wanted:
        return list(items), []
    keys = {normalize_name(w) for w in wanted if normalize_name(w)}
    selected, hit = [], set()
    for it in items:
        key = normalize_name(name_of(it))
        if key in keys:
            selected.append(it)
            hit.add(key)
    missing, seen = [], set()
    for w in wanted:
        key = normalize_name(w)
        if key and key not in hit and key not in seen:
            seen.add(key)
            missing.append(w.strip() if isinstance(w, str) else str(w))
    return selected, missing


def names_in_use(old_rows, ids_this_run):
    """モード1で、今回撮らない既存の行が使っている folder_name と image の名前（小文字の集合）を返す。

    戻り値: (フォルダ名の集合, 画像名の集合)
    今回撮る行の名前案や画像のファイル名がこれと重なると、残す行の画像を上書きしてしまうので、避けるのに使う。
    今回撮る行（datafile_id が ids_this_run にある行）の名前は、撮り直しで同じ名前を使ってよいので含めない。
    """
    folders, images = set(), set()
    for r in old_rows:
        if (r.get("datafile_id") or "").strip() in ids_this_run:
            continue
        for key, bucket in (("folder_name", folders), ("image", images)):
            value = (r.get(key) or "").strip()
            if value:
                bucket.add(value.lower())
    return folders, images


def merge_triage_rows(old_rows, new_rows):
    """モード1で、既存の triage.csv の行（old_rows）に今回撮った行（new_rows）を合わせる。

    方針（記入済みの仕分けを消さないため）:
      - datafile_id が同じ既存の行があれば、その行の位置に新しい行を入れる。
        rank と folder_name は既存の行の値を引き継ぐ（既存が空なら新しい行の値）
      - 今回撮れなかった（image が空の）ときは、既存の行の image を残す（前回の画像はフォルダに残っている）
      - 今回撮らなかった既存の行はそのまま残す（TARGET_NAMES で絞ったとき・キャンセルしたとき・
        Fusion から消えたファイル）
      - 既存に無い新しい行は最後に足す（既存の行の並びは、人がスプシで並べ替えたものかもしれないので変えない）
    datafile_id が空の行は照合できないので、どちらも別の行として残す。
    同じ datafile_id の既存の行が複数あれば、最初の行に入れ、残りはそのまま残す。
    入力は書き換えない。
    """
    new_by_id = {}
    for r in new_rows:
        fid = (r.get("datafile_id") or "").strip()
        if fid and fid not in new_by_id:
            new_by_id[fid] = r  # ID が空・2つ目以降の重複は照合しない
    merged, used = [], set()
    for old in old_rows:
        fid = (old.get("datafile_id") or "").strip()
        if fid and fid in new_by_id and fid not in used:
            used.add(fid)
            row = dict(new_by_id[fid])
            for key in ("rank", "folder_name"):
                if (old.get(key) or "").strip():
                    row[key] = old[key]
            if not (row.get("image") or "").strip() and (old.get("image") or "").strip():
                row["image"] = old["image"]
            merged.append(row)
        else:
            merged.append(dict(old))
    for r in new_rows:
        fid = (r.get("datafile_id") or "").strip()
        if fid in used and new_by_id.get(fid) is r:
            continue  # 既存の行の位置に入れた
        merged.append(dict(r))
    return merged


_AUTO = object()  # documents_dir の既定（このPCに合った取り方を使う）


def documents_dir(get_known_folder=_AUTO, home=None):
    """「ドキュメント」フォルダの場所を返す。

    OneDrive にドキュメントを移している PC では、~\\Documents がエクスプローラーの「ドキュメント」と
    違う場所になることがある。そこで Windows では Known Folder（FOLDERID_Documents）を
    _known_documents_folder で取る。
      get_known_folder: 場所を返す関数。既定は Windows なら _known_documents_folder、それ以外は無し
      home            : 取れなかったときの元（既定はユーザーのフォルダ）
    関数が無い・例外を出す・空を返したときは <home>\\Documents にする。
    """
    if get_known_folder is _AUTO:
        get_known_folder = _known_documents_folder if os.name == "nt" else None
    if get_known_folder is not None:
        try:
            path = get_known_folder()
            if isinstance(path, str) and path.strip():
                return path.strip()
        except Exception:
            pass
    return os.path.join(home or os.path.expanduser("~"), "Documents")


def _known_documents_folder():
    """Windows の SHGetKnownFolderPath で「ドキュメント」の場所を取る（ctypes。標準ライブラリだけ）。失敗は例外。"""
    import ctypes
    from ctypes import wintypes

    class GUID(ctypes.Structure):
        _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD), ("Data3", wintypes.WORD),
                    ("Data4", ctypes.c_ubyte * 8)]

    # FOLDERID_Documents = {FDD39AD0-238F-46AF-ADB4-6C85480369C7}
    folder_id = GUID(0xFDD39AD0, 0x238F, 0x46AF,
                     (ctypes.c_ubyte * 8)(0xAD, 0xB4, 0x6C, 0x85, 0x48, 0x03, 0x69, 0xC7))
    shell32 = ctypes.WinDLL("shell32")
    ole32 = ctypes.WinDLL("ole32")
    shell32.SHGetKnownFolderPath.argtypes = [ctypes.POINTER(GUID), wintypes.DWORD, wintypes.HANDLE,
                                             ctypes.POINTER(ctypes.c_void_p)]
    shell32.SHGetKnownFolderPath.restype = ctypes.c_long
    ole32.CoTaskMemFree.argtypes = [ctypes.c_void_p]
    ole32.CoTaskMemFree.restype = None
    buf = ctypes.c_void_p()
    hr = shell32.SHGetKnownFolderPath(ctypes.byref(folder_id), 0, None, ctypes.byref(buf))
    try:
        if hr != 0 or not buf.value:
            raise OSError("SHGetKnownFolderPath が失敗しました（HRESULT {}）".format(hr))
        return ctypes.wstring_at(buf.value)
    finally:
        if buf.value:
            ole32.CoTaskMemFree(buf)


def resolve_paths(mode, triage_dir, triage_csv, output_dir, documents=None):
    """設定欄のパスを解決し、問題を調べる。戻り値: ({"triage_dir", "triage_csv", "output_dir"}, 問題のリスト)

      - "~" はユーザーのフォルダに展開する。前後の空白は除く
      - triage_dir が空なら「ドキュメント」の中の 3Dギャラリー_仕分け。
        documents は「ドキュメント」の場所（テスト用。省略すると documents_dir() で取る）
      - triage_csv が空なら triage_dir の中の triage.csv
      - モード1は OUTPUT_DIR を調べない（未設定でも動く）
      - モード2は OUTPUT_DIR を調べる。<共有ドライブ名> の残りを止めるのは
        OUTPUT_DIR だけ（Googleドライブ上でなければならないのはここだけなので）
    """
    def clean(p):
        p = (p or "").strip()
        return os.path.expanduser(p) if p else ""

    tdir, tcsv, odir = clean(triage_dir), clean(triage_csv), clean(output_dir)
    if not tdir:
        tdir = os.path.join(documents or documents_dir(), TRIAGE_DIR_NAME)
    if not tcsv:
        tcsv = os.path.join(tdir, TRIAGE_FILENAME)
    problems = []
    if mode == 2:
        problem = check_setting_path(odir, "OUTPUT_DIR")
        if problem:
            problems.append(problem)
    return {"triage_dir": tdir, "triage_csv": tcsv, "output_dir": odir}, problems


def external_ref_outcome(refs, opened_by_us, broken, failed):
    """外部参照の扱いの結果から、ログの result を「要目視確認」にするかと、detail に足す文を決める。

    戻り値: (要目視確認にするか, 注記（無ければ空文字）)
      refs        : find_external_references の結果（空なら外部参照なし）
      opened_by_us: 自分で開いたドキュメントか（そのときだけ取り込む）
      broken      : breakLink で取り込めた配置の数
      failed      : 取り込めなかった配置の名前のリスト
    取り込めた配置が無いのに外部参照の印があるとき（参照ドキュメントだけがある等）も、
    f3d に参照先が入っていない可能性があるので要目視確認にする。
    """
    if not refs:
        return False, ""
    listed = ", ".join(refs)
    if not opened_by_us:
        return True, f"外部参照あり: {listed}（開いていたドキュメントのため取り込まずに書き出し。f3d に参照先が入っていない可能性）"
    if failed:
        return True, f"外部参照 {broken} 件を取り込んで f3d を書き出し / 取り込めなかった配置: {', '.join(failed)}"
    if broken == 0:
        return True, f"外部参照あり: {listed}（取り込める配置が無かった。f3d に参照先が入っていない可能性）"
    return False, f"外部参照 {broken} 件を取り込んで f3d を書き出し"


def lookup_candidates(row):
    """モード2でファイルを引くときに試すIDを、試す順に [(方法の名前, ID), ...] で返す。

    順番: version_id（版付きID。findFileById のリファレンスの例と同じ形式なので最も確実）
          → datafile_id（版に依らないID。findFileById で引けるかはリファレンスに明記が無い）。
    どちらでも引けなければ、呼び出し側でプロジェクトを再走査する。
    古い triage.csv（version_id 列なし）や空欄の行は、その方法を飛ばす。同じIDは2回試さない。
    """
    out, seen = [], set()
    for method, key in (("version_id", "version_id"), ("datafile_id", "datafile_id")):
        value = (row.get(key) or "").strip()
        if value and value not in seen:
            seen.add(value)
            out.append((method, value))
    return out


def append_log(path, name, result, detail="", mode=None, now=None):
    """export_log.csv に1行追記する。新しく作るときだけ BOM と見出しを書く。

    1件ごとに開いて閉じるので、途中で Fusion が落ちてもそこまでのログは残る。
    """
    new = not os.path.isfile(path) or os.path.getsize(path) == 0
    now = now or datetime.datetime.now()
    with open(path, "a", encoding="utf-8-sig" if new else "utf-8", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(LOG_COLUMNS)
        w.writerow([now.strftime("%Y-%m-%d %H:%M:%S"), MODE if mode is None else mode, name, result, detail])


def backup_path(path, now=None):
    """既存ファイルの退避先 "triage_YYYYMMDD_HHMMSS.csv" を返す。"""
    now = now or datetime.datetime.now()
    stem, ext = os.path.splitext(path)
    return f"{stem}_{now.strftime('%Y%m%d_%H%M%S')}{ext}"


def collect_visible_solid_bodies(root_component):
    """STL 用に、表示中のソリッドボディを集める（ルート直下＋全オカレンス）。

    方針:
      - ルートコンポーネント直下のボディはそのまま使う
      - オカレンス（配置されたコンポーネント）のボディは Occurrence.bRepBodies で取る。
        これはルートから見た「プロキシ」を返すので、書き出したときに組立上の位置が反映される
        （コンポーネントの bRepBodies を直接使うと、部品単体の原点の位置で出てしまう）
      - 非表示（電球オフ、親が非表示を含む）と、閉じていない面だけのボディは除く
    allOccurrences は入れ子のオカレンスも含む一覧なので、再帰しなくても全部たどれる。
    同じ部品が複数配置されていれば、配置の数だけボディが出る（それぞれの位置で）。

    戻り値: [(ボディ, STL のファイル名の元), ...]
      ルート直下はボディ名のまま、オカレンス内は「コンポーネント名_ボディ名」（例 lid_Body1）。
      部品ごとに Body1 が並ぶのが普通なので、ボディ名だけでは区別がつかないため。
    """
    bodies = []

    def take(body, prefix):
        try:
            if body.isSolid and body.isVisible:
                bodies.append((body, (prefix + "_" + body.name) if prefix else body.name))
        except Exception:
            pass  # 一時ボディなど、isVisible が取れないものは対象外

    for b in _iter(root_component.bRepBodies):
        take(b, "")
    for occ in _iter(root_component.allOccurrences):
        try:
            if not occ.isVisible:
                continue
            occ_bodies = occ.bRepBodies
        except Exception:
            continue
        try:
            prefix = occ.component.name
        except Exception:
            prefix = getattr(occ, "name", "")
        for b in _iter(occ_bodies):
            # 念のため: プロキシになっていなければ自分でプロキシを作る
            try:
                if b.assemblyContext is None:
                    b = b.createForAssemblyContext(occ) or b
            except Exception:
                pass
            take(b, prefix)
    return bodies


def break_external_links(root_component, max_rounds=None):
    """外部参照している配置（Occurrence）を、breakLink() でこのデザインのローカルなコンポーネントに取り込む。

    戻り値: (取り込めた配置の数, 取り込めなかった配置の名前のリスト)

    方針:
      - 自分で開いたドキュメントにだけ使う（呼び出し側の責任）。保存せずに閉じるので、クラウドの元データは変わらない
      - Autodesk の BreakLink サンプルにならい、対象を先にリストへ集めてから breakLink する
        （取り込むとコレクションが変わり、回しながらだと正しくたどれないため）
      - 入れ子（参照先の中にさらに参照がある）は、親を取り込むまで子は取り込めないことがある。
        そのため allOccurrences を見直しながら、isReferencedComponent のものが無くなるまで周回する。
        1周で1つも取り込めなかったら、それ以上は進まないので止める。上限 max_rounds 周（無限ループ防止）
      - breakLink が False を返す・例外を出すものは、その周では飛ばし、次の周でもう一度試す
        （親が取り込まれて取り込めるようになることがあるため）。最後まで残ったものを「取り込めなかった」とする
    Fusion のオブジェクトを受けるが、判断は count/item と属性だけなので dev/fusion-test で偽物を使って検証している。
    """
    rounds = BREAK_LINK_MAX_ROUNDS if max_rounds is None else max_rounds
    broken = 0

    def referenced():
        found = []
        for occ in _iter(root_component.allOccurrences):
            try:
                if occ.isReferencedComponent:
                    found.append(occ)
            except Exception:
                pass  # 取り込みで無効になった配置など
        return found

    for _ in range(rounds):
        targets = referenced()  # 先にリストへ集める
        if not targets:
            break
        progressed = False
        for occ in targets:
            try:
                if not occ.isReferencedComponent:
                    continue  # 同じ周で親を取り込んだときなどに、もう参照でなくなっている
                if occ.breakLink():
                    broken += 1
                    progressed = True
            except Exception:
                pass  # 次の周で試し直す。最後まで残れば下で「取り込めなかった」に入る
            _do_events()
        if not progressed:
            break

    failed = []
    for occ in referenced():
        try:
            failed.append(occ.name)
        except Exception:
            failed.append("（名前不明）")
    return broken, failed


def _iter(collection):
    """Fusion のコレクション（count と item を持つ）や配列を、普通の for で回せるようにする。

    DataFiles などは asArray()（2021年4月追加）で「今の一覧」をまとめて取れる。
    無ければ count / item で1つずつ取る。リストやタプルはそのまま回す。
    """
    if collection is None:
        return []
    if isinstance(collection, (list, tuple)):
        return list(collection)
    as_array = getattr(collection, "asArray", None)
    if callable(as_array):
        try:
            return list(as_array())
        except Exception:
            pass
    return [collection.item(i) for i in range(collection.count)]


# =============================================================================
# Fusion を使う部分
# =============================================================================

def _ctx():
    """Application と UserInterface を返す。"""
    app = adsk.core.Application.get()
    return app, app.userInterface


def _do_events(n=1):
    """Fusion に画面の更新やキャンセルボタンの処理をさせる（長い処理で画面を固めないため）。"""
    for _ in range(n):
        adsk.doEvents()


# ---------------------------------------------------------------------------
# クラウドのファイルをたどる
# ---------------------------------------------------------------------------
def list_target_projects(app):
    """設定 PROJECT_NAMES に合うプロジェクトを返す。戻り値: (DataProject のリスト, 見つからない名前)

    app.data.dataProjects は「今選んでいるハブ」のプロジェクトだけを返す（公式リファレンス）。
    """
    projects = _iter(app.data.dataProjects)
    names, missing = select_projects([p.name for p in projects], PROJECT_NAMES)
    return [p for p in projects if p.name in names], missing


def walk_f3d_files(project, on_progress=None):
    """プロジェクトのルートフォルダから再帰でたどり、f3d の DataFile を (dataFile, folder_path) で返す。

    folder_path はプロジェクト直下からの "a/b" 形式（直下なら空文字）。
    フォルダの中身はクラウドから読み込むため時間がかかる。フォルダごとに doEvents を挟む。
    on_progress(folder_path) が False を返したら中断する（キャンセル用）。
    """
    results = []
    stack = [(project.rootFolder, "")]
    while stack:
        folder, path = stack.pop()
        if on_progress and on_progress(path) is False:
            break
        _do_events()
        for df in _iter(folder.dataFiles):
            try:
                if (df.fileExtension or "").lower() == "f3d":
                    results.append((df, path))
            except Exception:
                pass
        # 名前順に処理されるよう逆順で積む（スタックなので後に積んだものが先に出る）
        subs = sorted(_iter(folder.dataFolders), key=lambda f: f.name, reverse=True)
        for sub in subs:
            stack.append((sub, (path + "/" + sub.name) if path else sub.name))
    return results


def first_created_epoch(data_file):
    """モデルの最初の作成日（UNIX時刻）を返す。

    DataFile.dateCreated は「そのバージョン」の作成日で、保存するたびに新しくなる
    （公式リファレンスの dateModified の説明）。フォルダ名には最初に作った日を使いたいので、
    全バージョンの dateCreated の最小値を取る。取れなければ最新版の dateCreated。
    """
    epochs = []
    try:
        epochs.append(int(data_file.dateCreated))
    except Exception:
        pass
    try:
        for v in _iter(data_file.versions):
            try:
                epochs.append(int(v.dateCreated))
            except Exception:
                pass
    except Exception:
        pass
    epochs = [e for e in epochs if e > 0]
    return min(epochs) if epochs else 0


class FileFinder:
    """triage.csv の行から DataFile を探す。戻り値: (DataFile または None, 引けた方法)

    順番は lookup_candidates の通り version_id → datafile_id を Data.findFileById で試し、
    だめなら対象プロジェクトを一度だけたどって id / versionId の対応表を作り、そこから引く（"再走査"）。
    引けた方法はログに残す。実機でどれが効くか分かったら、効かない方法を外してよい。

    version_id で引くと「仕分けたときの版」が開く。その後に更新されていても最新を書き出したいので、
    DataFile.latestVersion で最新版に差し替える（引けた方法に「→最新版」と付ける）。
    """

    def __init__(self, app):
        self.app = app
        self._table = None

    def find(self, row):
        df, method = None, ""
        for method, file_id in lookup_candidates(row):
            try:
                df = self.app.data.findFileById(file_id)
            except Exception:
                df = None
            if df:
                break
        if not df:
            ids = [i for _m, i in lookup_candidates(row)]
            if not ids:
                return None, ""
            for file_id in ids:
                df = self._lookup_table(file_id)
                if df:
                    break
            method = "再走査"
        if df:
            try:
                latest = df.latestVersion
                if latest and getattr(latest, "versionId", None) != getattr(df, "versionId", None):
                    df, method = latest, method + "→最新版"
            except Exception:
                pass
        return df, (method if df else "")

    def _lookup_table(self, file_id):
        if self._table is None:
            self._table = {}
            projects, _ = list_target_projects(self.app)
            for p in projects:
                for d, _path in walk_f3d_files(p):
                    for key in (getattr(d, "id", None), getattr(d, "versionId", None)):
                        if key:
                            self._table[key] = d
        return self._table.get(file_id)


# ---------------------------------------------------------------------------
# ドキュメントを開く・閉じる
# ---------------------------------------------------------------------------
def find_open_document(app, data_file):
    """同じファイルがすでに開かれていれば、そのドキュメントを返す（閉じてはいけないもの）。"""
    target = getattr(data_file, "id", None)
    for doc in _iter(app.documents):
        try:
            if doc.dataFile and doc.dataFile.id == target:
                return doc
        except Exception:
            pass  # 未保存のドキュメントは dataFile が無い
    return None


def open_document(app, data_file):
    """DataFile を開く。戻り値: (Document, 自分で開いたか)

    元々開いていたドキュメントは閉じない約束なので、開いていればそれを使い「自分で開いていない」と返す。
    サムネイルを撮るためにビューポートが要るので、見える状態（visible=True）で開いて前面にする。
    """
    doc = find_open_document(app, data_file)
    opened_by_us = False
    if doc is None:
        doc = app.documents.open(data_file, True)
        if doc is None:
            raise RuntimeError("ファイルを開けませんでした（権限が無い、またはクラウドから読み込めない）")
        opened_by_us = True
    try:
        doc.activate()
    except Exception:
        pass
    _do_events(3)  # 読み込み直後の描画を進める
    return doc, opened_by_us


def close_document(doc, opened_by_us):
    """自分で開いたドキュメントだけを、保存せずに閉じる（close(False) は変更を捨てて閉じる）。"""
    if doc is None or not opened_by_us:
        return
    try:
        doc.close(False)
    except Exception:
        pass
    _do_events()


def is_modified(doc):
    """ドキュメントに未保存の変更があるか（Document.isModified）。取れなければ False。"""
    try:
        return bool(doc.isModified)
    except Exception:
        return False


def get_design(doc):
    """ドキュメントから Design（モデルの本体）を取り出す。"""
    design = None
    try:
        design = adsk.fusion.FusionDocument.cast(doc).design
    except Exception:
        design = None
    if not design:
        design = adsk.fusion.Design.cast(doc.products.itemByProductType("DesignProductType"))
    if not design:
        raise RuntimeError("デザインのデータがありません（f3d ではない可能性）")
    return design


# ---------------------------------------------------------------------------
# サムネイル
# ---------------------------------------------------------------------------
def save_thumbnail(app, path):
    """斜め上からの全体表示にして、画像を保存する。

    方針: カメラを「右上手前からの等角（IsoTopRight）」にして isFitView=True で全体を収め、
    念のため fit() も呼ぶ。saveAsImageFile は指定サイズで描き直して保存するので、
    画面の大きさに関係なく同じサイズの画像になる（拡張子 .png から形式が決まる）。
    ViewOrientation は ViewCube の向きが基準なので、ViewCube の「ホーム」を変えている
    データでは向きが揃わないことがある。
    """
    vp = app.activeViewport
    cam = vp.camera  # コピーが返るので、変えたら代入し直す必要がある
    cam.viewOrientation = adsk.core.ViewOrientations.IsoTopRightViewOrientation
    cam.isFitView = True
    cam.isSmoothTransition = False  # 視点移動のアニメーション途中で撮らないよう、一瞬で切り替える
    vp.camera = cam
    _do_events(2)
    vp.fit()
    vp.refresh()
    _do_events(2)
    if not vp.saveAsImageFile(path, THUMB_WIDTH, THUMB_HEIGHT):
        raise RuntimeError("画像の保存に失敗しました")


# ---------------------------------------------------------------------------
# 書き出し
# ---------------------------------------------------------------------------
def _mesh_refinement():
    """設定 MESH_QUALITY を Fusion の値に変える。"""
    m = adsk.fusion.MeshRefinementSettings
    return {"high": m.MeshRefinementHigh, "medium": m.MeshRefinementMedium,
            "low": m.MeshRefinementLow}.get(str(MESH_QUALITY).lower(), m.MeshRefinementHigh)


def _execute(design, options, what):
    """ExportManager.execute を呼び、失敗なら例外にする。"""
    if options is None or not design.exportManager.execute(options):
        raise RuntimeError(what + " の書き出しに失敗しました")


def export_f3d(design, path):
    """Fusion アーカイブ（.f3d）。引数は (ファイル名, 対象) の順。対象省略でルート全体。"""
    _execute(design, design.exportManager.createFusionArchiveExportOptions(path), "f3d")


def export_step(design, path):
    """STEP。引数は (ファイル名, 対象) の順。対象省略でルート全体。"""
    _execute(design, design.exportManager.createSTEPExportOptions(path), "STEP")


def export_stl(design, geometry, path):
    """STL。引数は (対象, ファイル名) の順（f3d/STEP と逆なので注意）。

    単位は mm に固定する（スライサーは mm として読むため。既定はデザインの単位）。
    """
    opts = design.exportManager.createSTLExportOptions(geometry, path)
    if opts is not None:
        opts.isBinaryFormat = True
        opts.meshRefinement = _mesh_refinement()
        opts.unitType = adsk.fusion.DistanceUnits.MillimeterDistanceUnits
    _execute(design, opts, "STL")


def export_3mf(design, geometry, path):
    """3MF。引数は (対象, ファイル名) の順。3MF は形式として単位を持つので単位の指定は無い。"""
    opts = design.exportManager.createC3MFExportOptions(geometry, path)
    if opts is not None:
        opts.meshRefinement = _mesh_refinement()
    _execute(design, opts, "3MF")


def find_external_references(design, doc, data_file):
    """外部参照（他のデザインを部品として挿入している）を探す。見つかった説明のリストを返す。

    API の Fusion アーカイブ書き出しは参照先を含まない（実機で f3d が空になった。第2ラウンドの F4）。
    自分で開いたドキュメントなら break_external_links で取り込んでから f3d を書き出し、
    元々開いていたドキュメントなら取り込まずにログを「要目視確認」にする（external_ref_outcome）。
    判定は次のどれか:
      - Occurrence.isReferencedComponent（その配置が外部のコンポーネントを参照している）
      - Document.documentReferences.count（このドキュメントが直接参照しているドキュメントの数）
      - DataFile.hasChildReferences（クラウド上で子の参照を持っているか）
    """
    found = []
    try:
        for occ in _iter(design.rootComponent.allOccurrences):
            try:
                if occ.isReferencedComponent:
                    found.append(occ.name)
            except Exception:
                pass
    except Exception:
        pass
    if not found:
        try:
            if doc.documentReferences.count > 0:
                found.append("参照ドキュメント %d 件" % doc.documentReferences.count)
        except Exception:
            pass
    if not found:
        try:
            if data_file.hasChildReferences:
                found.append("子の参照あり")
        except Exception:
            pass
    return found


def export_item(app, design, folder, base_name, before_f3d=None):
    """1作品ぶんの STEP / STL / 3MF / thumb.png / f3d を書き出す。meta.json は書かない（呼び出し側で最後に）。

    方針: 形式ごとに try して、1つ失敗しても残りは出す（手で補えるように）。
    失敗が1つでもあれば例外にまとめて投げ、meta.json を書かせない（再実行でやり直す）。
    戻り値: 補足メッセージのリスト（ボディが無かった等）。

    順番: STEP → STL → 3MF → thumb.png → before_f3d() → f3d。
      before_f3d は外部参照の取り込み（breakLink）に使う。f3d は API の書き出しに参照先が含まれないので、
      取り込んでから書き出す必要がある。一方 STEP/STL/3MF/サムネイルは取り込まなくても参照先ごと出ることを
      実機で確かめてある（第2ラウンドの F4）。そこで、それらを先に出し終えてから取り込む。
      こうすると、取り込みが失敗したり、取り込みで部品が置き換わって先に集めたボディ（プロキシ）が
      無効になったりしても、STEP/STL/3MF/サムネイルには影響しない。
    """
    errors, notes = [], []
    base = sanitize_filename(base_name)

    def attempt(label, func):
        try:
            func()
        except Exception as e:
            errors.append(f"{label}: {e}")
        _do_events()

    attempt("STEP", lambda: export_step(design, os.path.join(folder, base + ".step")))

    root = design.rootComponent
    bodies = collect_visible_solid_bodies(root)
    if not bodies:
        notes.append("表示中のソリッドボディが無いため STL/3MF なし")
    else:
        if STL_PER_BODY:
            used = set()
            for body, label in bodies:
                fname = unique_name(sanitize_filename(label) + ".stl", used)
                attempt("STL " + fname, lambda b=body, f=fname: export_stl(design, b, os.path.join(folder, f)))
        else:
            attempt("STL", lambda: export_stl(design, root, os.path.join(folder, base + ".stl")))
        attempt("3MF", lambda: export_3mf(design, root, os.path.join(folder, base + ".3mf")))

    attempt("thumb.png", lambda: save_thumbnail(app, os.path.join(folder, THUMB_FILENAME)))

    if before_f3d is not None:
        attempt("外部参照の取り込み", before_f3d)
    attempt("f3d", lambda: export_f3d(design, os.path.join(folder, base + ".f3d")))

    if errors:
        raise RuntimeError(" / ".join(errors))
    return notes


# ---------------------------------------------------------------------------
# 進捗ダイアログ
# ---------------------------------------------------------------------------
class Progress:
    """キャンセルできる進捗ダイアログ。cancelled() でキャンセルされたかを見る。"""

    def __init__(self, ui, title, maximum):
        self.dlg = ui.createProgressDialog()
        self.dlg.isCancelButtonShown = True
        self.dlg.cancelButtonText = "中止"
        self.dlg.show(title, "準備中…", 0, max(1, maximum), 0)
        _do_events()

    def update(self, value, message, maximum=None):
        if maximum is not None:
            self.dlg.maximumValue = max(1, maximum)
        self.dlg.progressValue = value
        self.dlg.message = message
        _do_events()

    def cancelled(self):
        _do_events()
        return bool(self.dlg.wasCancelled)

    def close(self):
        try:
            self.dlg.hide()
        except Exception:
            pass


def check_setting_path(path, label):
    """設定欄のパスが書き換え済みかを確かめる。問題があれば日本語の説明を返す（無ければ空文字）。"""
    if not path:
        return label + " が設定されていません"
    if "<" in path or ">" in path:
        return label + " の <共有ドライブ名> などの部分を、実際の名前に書き換えてください（< > も消す）"
    return ""


def _resolved_paths(mode):
    """設定欄のパスを解決する（resolve_paths）。問題があれば日本語の説明で止める。"""
    paths, problems = resolve_paths(mode, TRIAGE_DIR, TRIAGE_CSV, OUTPUT_DIR)
    if problems:
        raise ValueError("設定欄を確認してください:\n" + "\n".join(problems))
    return paths


def _missing_names_text(missing):
    """TARGET_NAMES で見つからなかった名前を、最後のメッセージに足す文にする。"""
    if not missing:
        return ""
    return "\n\nTARGET_NAMES のうち見つからなかった名前（{} 件）:\n{}".format(len(missing), "\n".join(missing))


# =============================================================================
# モード1: サムネイルのみ（仕分け用の一覧を作る）
# =============================================================================
def run_mode1(app, ui):
    """対象プロジェクトの f3d を開いて画像を撮り、triage.csv を書く。

    方針:
      - 先にファイルを全部列挙してから開く（件数が分かり、進捗が出せる）
      - TARGET_NAMES があれば、列挙したうち指定した名前のファイルだけを撮る
      - 開けない・撮れないファイルも行は残す（image が空。仕分けで判断できるように）
      - 既存の triage.csv は先に読んでおき、merge_triage_rows で今回の行と合わせる
        （datafile_id が同じ行の rank と folder_name を引き継ぎ、今回撮らなかった行も残す）。
        書く前に、既存の triage.csv は日時付きの名前に退避する（念のため）
      - 撮影の前に triage.csv を書き換えられるか確かめ、書けなければ（Excel で開いたまま等）撮らずに止める。
        撮影中に開かれて最後に書けなかったときは、triage_new_<日時>.csv に書いて案内する（save_triage_csv）
      - キャンセルされたら、そこまでの行で triage.csv を書いて終わる
    """
    paths = _resolved_paths(1)
    triage_dir = paths["triage_dir"]
    os.makedirs(triage_dir, exist_ok=True)
    log_path = os.path.join(triage_dir, LOG_FILENAME)
    csv_path = os.path.join(triage_dir, TRIAGE_FILENAME)
    # 既存の triage.csv は撮る前に読む。読めないまま上書きすると記入済みの仕分けが引き継げないので止める
    old_rows = []
    if os.path.isfile(csv_path):
        try:
            old_rows = read_triage_csv(csv_path)
        except Exception as e:
            raise ValueError("既存の triage.csv が読めないため止めました（記入済みの仕分けを引き継げないため）。\n"
                             "直すか、別の名前に変えてから実行してください。\n{}\n{}".format(csv_path, e))
    # 撮影を始める前に、triage.csv を書き換えられるか確かめる（Excel で開いたままだと、最後に書けず結果を失うため）
    if not can_overwrite(csv_path):
        ui.messageBox("triage.csv に書き込めないため、撮影を始めずに止めました。\n"
                      "Excel などで開いていたら閉じてから、もう一度実行してください。\n" + csv_path)
        return

    projects, missing = list_target_projects(app)
    if missing:
        ui.messageBox("次のプロジェクトが見つかりません（名前を確認してください）:\n" + "\n".join(missing))
        if not projects:
            return

    progress = Progress(ui, "モード1: ファイルを数えています", 1)
    rows, merged, counts = [], [], {"ok": 0, "fail": 0}
    written, write_error = csv_path, ""
    cancelled = False
    missing_names = []
    try:
        # 1) 列挙（クラウドのフォルダを読むので時間がかかる）
        items = []
        for p in projects:
            def on_folder(path, pname=p.name):
                progress.update(0, f"{pname}/{path}  を確認中（{len(items)} 件）")
                return not progress.cancelled()
            for df, path in walk_f3d_files(p, on_folder):
                items.append((p.name, df, path))
            if progress.cancelled():
                cancelled = True
                break
        items, missing_names = select_by_names(items, TARGET_NAMES, name_of=lambda it: it[1].name)
        if cancelled:
            missing_names = []  # 列挙の途中で止めたので、見つからないとは言い切れない
        for n in missing_names:
            append_log(log_path, n, RESULT_NOTE, "TARGET_NAMES の名前が見つかりません", mode=1)

        # 2) 1件ずつ開いて撮影
        #    今回撮らない既存の行の名前は避ける（残す行の画像を上書きしないため）
        ids_this_run = set()
        for _p, df, _path in items:
            try:
                ids_this_run.add(df.id)
            except Exception:
                pass
        used_folder, used_image = names_in_use(old_rows, ids_this_run)
        old_by_id = {}
        for r in old_rows:
            old_by_id.setdefault((r.get("datafile_id") or "").strip(), r)
        for i, (pname, df, path) in enumerate(items):
            if cancelled or progress.cancelled():
                cancelled = True
                break
            name = df.name
            progress.update(i, f"{i + 1}/{len(items)}  {name}", maximum=len(items))
            row = {"project": pname, "folder_path": path, "name": name, "rank": ""}
            try:
                row["datafile_id"] = df.id
                row["version_id"] = df.versionId
                row["created"] = epoch_to_text(first_created_epoch(df))
                row["modified"] = epoch_to_text(df.dateModified)
            except Exception:
                row.setdefault("datafile_id", "")
            # 既存の行に folder_name が記入済みなら、画像の名前もそれに合わせる（撮り直しで同じ画像を置き換える）
            old = old_by_id.get(row["datafile_id"]) if row["datafile_id"] else None
            kept = (old.get("folder_name") or "").strip() if old else ""
            if kept:
                row["folder_name"] = kept
                used_folder.add(kept.lower())
            else:
                row["folder_name"] = unique_name(make_folder_name(row.get("created"), name), used_folder, "folder")
            image = unique_name(sanitize_filename(row["folder_name"]) + ".png", used_image)
            doc, ours = None, False
            try:
                doc, ours = open_document(app, df)
                get_design(doc)  # デザインでなければここで失敗として記録
                save_thumbnail(app, os.path.join(triage_dir, image))
                row["image"] = image
                counts["ok"] += 1
                append_log(log_path, name, RESULT_OK, image, mode=1)
            except Exception as e:
                row["image"] = ""
                counts["fail"] += 1
                append_log(log_path, name, RESULT_FAIL, str(e), mode=1)
            finally:
                close_document(doc, ours)
            rows.append(row)
    finally:
        # 3) 一覧を書く（キャンセルや想定外のエラーでも、そこまでの分は残す）
        #    撮影中に Excel などで開かれて書けなければ、triage_new_<日時>.csv に書く（結果を失わないため）
        if rows:
            merged = merge_triage_rows(old_rows, rows)
            written, write_error = save_triage_csv(csv_path, merged)
            if write_error:
                append_log(log_path, "", RESULT_NOTE,
                           "triage.csv に書けないため {} に書きました: {}".format(os.path.basename(written), write_error),
                           mode=1)
        progress.close()

    kept_rows = len(merged) - len(rows) if rows else len(old_rows)  # 今回撮らずに残した既存の行
    fallback_text = ""
    if write_error:
        fallback_text = ("\n\n※ triage.csv に書けなかったため（Excel などで開いていませんか）、上の一覧に書きました。\n"
                         "triage.csv を閉じてから、元の triage.csv を消すか別名にし、このファイルの名前を triage.csv に"
                         "変えてください。")
    ui.messageBox(
        "モード1 終了{}\n\n画像を保存: {} 件\n失敗: {} 件\n前回の一覧から残した行: {} 件\n一覧: {}{}\n\n"
        "triage.csv の rank 列に A/B/C を書き、必要なら folder_name を直してからモード2を実行してください。{}"
        .format("（中止）" if cancelled else "", counts["ok"], counts["fail"], kept_rows, written, fallback_text,
                _missing_names_text(missing_names)))


# =============================================================================
# モード2: フル書き出し
# =============================================================================
def run_mode2(app, ui):
    """triage.csv の A/B の行（TARGET_NAMES があればその名前の行）を、作品フォルダとして OUTPUT_DIR に書き出す。

    方針:
      - 済み判定は folder_state（meta.json の fusion_id がこの行の datafile_id と一致すれば済み）
      - meta.json が無ければ（途中で止まった）やり直す。書き出しの最初に目印 fusion_id.tmp を書くので、
        途中のフォルダがどの作品のものかは次の実行で分かる（resolve_output_folder が他の作品の途中を取らない）
      - meta.json は全部の書き出しが成功したときだけ、最後に書く。書けたら目印を消す
      - 1件ずつ try し、失敗してもログに書いて次へ進む
      - 外部参照は、自分で開いたドキュメントなら取り込んでから f3d を書き出す（保存はしない）
    """
    paths = _resolved_paths(2)
    output_dir, triage_csv = paths["output_dir"], paths["triage_csv"]
    if not os.path.isfile(triage_csv):
        raise ValueError("triage.csv が見つかりません（先にモード1を実行するか、TRIAGE_CSV / TRIAGE_DIR を確認してください）:\n"
                         + triage_csv)
    os.makedirs(output_dir, exist_ok=True)
    log_path = os.path.join(output_dir, LOG_FILENAME)
    targets = as_name_list(TARGET_NAMES)
    all_rows, missing_names = select_by_names(read_triage_csv(triage_csv), targets,
                                              name_of=lambda r: r.get("name", ""))
    rows, warnings = select_rows_for_export(all_rows, ignore_rank=bool(targets))
    if targets:
        # 同じ名前の行が複数（別のプロジェクトやフォルダの同名ファイル）あれば、全部書き出すことを知らせる
        warnings = ["TARGET_NAMES の「{}」は triage.csv に {} 行あります（別のプロジェクトやフォルダの同名ファイル）。"
                    "すべて書き出します".format(n, c)
                    for n, c in duplicate_names(all_rows, name_of=lambda r: r.get("name", ""))] + warnings
    for n in missing_names:
        append_log(log_path, n, RESULT_NOTE, "TARGET_NAMES の名前が triage.csv にありません", mode=2)
    for w in warnings:
        append_log(log_path, "", RESULT_NOTE, w, mode=2)
    if not rows:
        what = "TARGET_NAMES に合う行" if targets else "rank が A か B の行"
        ui.messageBox("{}がありません。\n{}{}".format(what, triage_csv, _missing_names_text(missing_names)))
        return

    reserved = {r["folder_name"].lower() for r in rows}  # 他の行が使うフォルダ名（空き名探しで避ける）
    finder = FileFinder(app)
    progress = Progress(ui, "モード2: 書き出し", len(rows))
    counts = {"ok": 0, "check": 0, "fail": 0, "skip": 0, "skip_no_id": 0}
    cancelled = False
    try:
        for i, row in enumerate(rows):
            if progress.cancelled():
                cancelled = True
                break
            name = row.get("name", "")
            fusion_id = (row.get("datafile_id") or "").strip()
            source = source_text(row.get("project", ""), row.get("folder_path", ""), name)  # 旧版の出力の照合用
            progress.update(i, f"{i + 1}/{len(rows)}  {row['folder_name']}")
            # 済み判定: meta.json の fusion_id がこの行と一致するときだけ済み。
            # 別の作品の同名フォルダがあれば上書きせず、-v2 などの空き名に書く。
            folder_name, state, avoided = resolve_output_folder(output_dir, row["folder_name"], fusion_id,
                                                                source, reserved)
            label = f"{folder_name}（{name}）"
            folder = os.path.join(output_dir, folder_name)
            # 書き出すときだけ注意を出す（済みで飛ばすときに「書き出します」と出すと紛らわしい）
            if avoided and state not in ("done", "done_no_id"):
                append_log(log_path, label, RESULT_NOTE,
                           "同名のフォルダ（{}）が別の作品のため、{} に書き出します".format("、".join(avoided), folder_name),
                           mode=2)
            if state == "done":
                counts["skip"] += 1
                append_log(log_path, label, RESULT_SKIP, "meta.json があり、同じ作品のため（書き出し済み）", mode=2)
                continue
            if state == "done_no_id":
                counts["skip_no_id"] += 1
                append_log(log_path, label, RESULT_SKIP,
                           "fusion_id が無いため念のためスキップ（同じ作品なら fusion_id を戻すかフォルダを消してから再実行。"
                           "別の作品なら triage.csv の folder_name を変える）", mode=2)
                continue

            doc, ours, found_by = None, False, ""
            try:
                df, how = finder.find(row)
                if not df:
                    raise RuntimeError("Fusion 上でファイルが見つかりません（削除・移動・権限、またはハブ違い）")
                found_by = "取得: " + how
                doc, ours = open_document(app, df)
                design = get_design(doc)
                refs = find_external_references(design, doc, df)
                link = {"broken": 0, "failed": []}

                def break_links(design=design, link=link):
                    # 自分で開いたドキュメントだけ。保存せずに閉じる（close_document）ので元データは変わらない
                    try:
                        link["broken"], link["failed"] = break_external_links(design.rootComponent)
                    except Exception as e:
                        link["failed"] = ["取り込み処理のエラー: {}".format(e)]

                os.makedirs(folder, exist_ok=True)
                write_marker(folder, fusion_id)  # 途中で止まっても、次の実行でこの作品のフォルダと分かるように
                notes = export_item(app, design, folder, name or df.name,
                                    before_f3d=break_links if (refs and ours) else None)
                write_meta_json(folder, build_meta(fusion_id))
                remove_marker(folder)  # 完了。消せなくても害は無い
                notes.insert(0, found_by)
                if not ours and is_modified(doc):
                    notes.append("開いていたドキュメントに未保存の変更があり、その状態で書き出しました")
                check, ref_note = external_ref_outcome(refs, ours, link["broken"], link["failed"])
                if ref_note:
                    notes.insert(1, ref_note)
                if check:
                    counts["check"] += 1
                    append_log(log_path, label, RESULT_CHECK, " / ".join(notes), mode=2)
                else:
                    counts["ok"] += 1
                    append_log(log_path, label, RESULT_OK, " / ".join(notes), mode=2)
            except Exception as e:
                counts["fail"] += 1
                append_log(log_path, label, RESULT_FAIL, " / ".join(x for x in (found_by, str(e)) if x), mode=2)
            finally:
                close_document(doc, ours)
    finally:
        progress.close()

    ui.messageBox(
        "モード2 終了{}\n\n成功: {} 件\n成功（要目視確認・外部参照）: {} 件\n失敗: {} 件\n"
        "スキップ（書き出し済み）: {} 件\nスキップ（fusion_id なし・未確認）: {} 件\n注意: {} 件\n\n"
        "詳しくは {} を見てください。失敗した分は、もう一度実行するとやり直します。{}{}"
        .format("（中止）" if cancelled else "", counts["ok"], counts["check"], counts["fail"],
                counts["skip"], counts["skip_no_id"], len(warnings), log_path,
                "\n「未確認」は同じ作品か確かめられなかったものです（ログの「スキップ」の行に対処の仕方）。"
                if counts["skip_no_id"] else "",
                _missing_names_text(missing_names)))


# =============================================================================
# 入口（Fusion が呼ぶ）
# =============================================================================
def run(context):
    ui = None
    original = None
    try:
        app, ui = _ctx()
        original = app.activeDocument  # 終わったら元の画面に戻すため
        if MODE == 1:
            run_mode1(app, ui)
        elif MODE == 2:
            run_mode2(app, ui)
        else:
            ui.messageBox("設定欄の MODE は 1 か 2 にしてください（今: {}）".format(MODE))
    except Exception:
        if ui:
            ui.messageBox("エラーで止まりました:\n{}".format(traceback.format_exc()))
    finally:
        try:
            if original and original.isValid:
                original.activate()
        except Exception:
            pass
