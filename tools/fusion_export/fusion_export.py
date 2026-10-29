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
  モード2（フル書き出し）  : triage.csv の rank が A か B の行だけ、作品フォルダを作って
                             f3d / STEP / STL / 3MF / thumb.png / meta.json を書き出す。

このファイルは標準ライブラリと adsk（Fusion 付属）だけを使う。追加のインストールは要らない。
"""

# =============================================================================
# 設定欄（ここだけ書き換えればよい）
# =============================================================================

# 実行するモード。1 = サムネイルのみ（仕分け用の一覧を作る）、2 = フル書き出し
MODE = 1

# モード2の出力先。Googleドライブ（パソコン版）で同期している「3Dギャラリー/items」フォルダを指定する。
# ここに書き出すと、そのままギャラリーへの登録になる。
# Windows のパスは r"..." で囲む（\ をそのまま書けるようにするため）。
OUTPUT_DIR = r"G:\マイドライブ\3Dギャラリー\items"

# モード1の出力先。triage.csv とサムネイル画像がここに書かれる。items の外の作業用フォルダにする。
TRIAGE_DIR = r"C:\Users\自分のユーザー名\Desktop\fusion_triage"

# モード2で読む triage.csv のパス（モード1で作り、rank と folder_name を記入したもの）。
# スプシで編集した場合は「ファイル → ダウンロード → CSV」で保存したものを指定する。
TRIAGE_CSV = r"C:\Users\自分のユーザー名\Desktop\fusion_triage\triage.csv"

# 対象にする Fusion のプロジェクト名のリスト。空のリスト [] なら全プロジェクトが対象。
# 例: PROJECT_NAMES = ["研究室共有", "山田の試作"]
# 対象は Fusion で今選んでいるチーム（データパネル左上のハブ）の中のプロジェクトだけ。
PROJECT_NAMES = []

# STL をボディごとに分けるか。True = ボディごとに1ファイル（<ボディ名>.stl）、False = 全体で1ファイル（<名前>.stl）
STL_PER_BODY = True

# STL / 3MF のメッシュの細かさ。"high"（細かい・ファイル大）/ "medium"（標準）/ "low"（粗い・ファイル小）
MESH_QUALITY = "high"

# サムネイル画像の大きさ（ピクセル）。ギャラリーのカードの画像枠がおよそ 3:2（はみ出しは切り取り）
# なので、3:2 にしておくと切れる部分が少ない
THUMB_WIDTH = 1200
THUMB_HEIGHT = 800

# =============================================================================
# ここから下は処理本体。改修するときは tools/docs/DEVELOPMENT.md を先に読む。
# =============================================================================

import csv
import datetime
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
LOG_FILENAME = "export_log.csv"
LOG_COLUMNS = ["time", "mode", "name", "result", "detail"]
META_FILENAME = "meta.json"
THUMB_FILENAME = "thumb.png"
EXPORT_RANKS = ("A", "B")          # モード2で書き出すランク
FOLDER_NAME_PATTERN = re.compile(r"^(\d{8})_(.+)$")  # GAS の同期と同じ規則

# ログの result 欄に入れる言葉（後でフィルタしやすいよう固定の語にする）
RESULT_OK = "成功"
RESULT_CHECK = "成功（要目視確認）"
RESULT_FAIL = "失敗"
RESULT_SKIP = "スキップ"


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
    """meta.json の note に入れる「Fusion元」の場所。空の部分は詰める。"""
    parts = [p for p in [project, (folder_path or "").strip("/"), name] if p]
    return "/".join(parts)


def build_meta(project, folder_path, name):
    """meta.json の雛形（必須値は空のまま。同期で「未記入」として見えるようにするため）。"""
    return {
        "author": "",
        "purpose": "",
        "status": "",
        "tags": [],
        "note": ["Fusion元: " + source_text(project, folder_path, name)],
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


def write_triage_csv(path, rows):
    """triage.csv を BOM 付き UTF-8 で書く（Excel で開いても文字化けしないように）。"""
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=TRIAGE_COLUMNS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in TRIAGE_COLUMNS})


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
    reader = csv.DictReader(text.splitlines())
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


def select_rows_for_export(rows):
    """モード2で書き出す行を選び、作品フォルダ名を確定する。

    戻り値: (選んだ行のリスト, 注意メッセージのリスト)
      - rank が A/B の行だけ選ぶ
      - folder_name が空なら created と name から作る。書いてあれば使えない文字だけ置き換える
      - 同じフォルダ名が複数あれば2つ目以降に -v2, -v3 を付ける
        （そのままだと2つ目が1つ目の meta.json を見て「済み」と飛ばされてしまうため）
      - 形式外のフォルダ名は書き出すが注意を出す（GAS の同期でエラーになるので直してもらう）
    CSV の行順で番号を振るので、同じ CSV なら再実行しても同じフォルダ名になる。
    """
    selected, warnings, used = [], [], set()
    for r in rows:
        if normalize_rank(r.get("rank")) not in EXPORT_RANKS:
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
    """
    if not wanted:
        return list(all_names), []
    found = [n for n in all_names if n in wanted]
    missing = [n for n in wanted if n not in all_names]
    return found, missing


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
    """
    bodies = []

    def take(body):
        try:
            if body.isSolid and body.isVisible:
                bodies.append(body)
        except Exception:
            pass  # 一時ボディなど、isVisible が取れないものは対象外

    for b in _iter(root_component.bRepBodies):
        take(b)
    for occ in _iter(root_component.allOccurrences):
        try:
            if not occ.isVisible:
                continue
            occ_bodies = occ.bRepBodies
        except Exception:
            continue
        for b in _iter(occ_bodies):
            # 念のため: プロキシになっていなければ自分でプロキシを作る
            try:
                if b.assemblyContext is None:
                    b = b.createForAssemblyContext(occ) or b
            except Exception:
                pass
            take(b)
    return bodies


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

    外部参照があると、書き出しが参照先の古い版になったり、f3d に参照先が含まれなかったり
    しうるので、ログに「要目視確認」と残す。判定は次のどれか:
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


def export_item(app, design, folder, base_name):
    """1作品ぶんの f3d / STEP / STL / 3MF / thumb.png を書き出す。meta.json は書かない（呼び出し側で最後に）。

    方針: 形式ごとに try して、1つ失敗しても残りは出す（手で補えるように）。
    失敗が1つでもあれば例外にまとめて投げ、meta.json を書かせない（再実行でやり直す）。
    戻り値: 補足メッセージのリスト（ボディが無かった等）。
    """
    errors, notes = [], []
    base = sanitize_filename(base_name)

    def attempt(label, func):
        try:
            func()
        except Exception as e:
            errors.append(f"{label}: {e}")
        _do_events()

    attempt("f3d", lambda: export_f3d(design, os.path.join(folder, base + ".f3d")))
    attempt("STEP", lambda: export_step(design, os.path.join(folder, base + ".step")))

    root = design.rootComponent
    bodies = collect_visible_solid_bodies(root)
    if not bodies:
        notes.append("表示中のソリッドボディが無いため STL/3MF なし")
    else:
        if STL_PER_BODY:
            used = set()
            for body in bodies:
                fname = unique_name(sanitize_filename(body.name) + ".stl", used)
                attempt("STL " + fname, lambda b=body, f=fname: export_stl(design, b, os.path.join(folder, f)))
        else:
            attempt("STL", lambda: export_stl(design, root, os.path.join(folder, base + ".stl")))
        attempt("3MF", lambda: export_3mf(design, root, os.path.join(folder, base + ".3mf")))

    attempt("thumb.png", lambda: save_thumbnail(app, os.path.join(folder, THUMB_FILENAME)))

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


def _ensure_dir(path, label):
    if not path:
        raise ValueError(label + " が設定されていません")
    os.makedirs(path, exist_ok=True)


# =============================================================================
# モード1: サムネイルのみ（仕分け用の一覧を作る）
# =============================================================================
def run_mode1(app, ui):
    """対象プロジェクトの f3d を全部開いて画像を撮り、triage.csv を書く。

    方針:
      - 先にファイルを全部列挙してから開く（件数が分かり、進捗が出せる）
      - 開けない・撮れないファイルも行は残す（image が空。仕分けで判断できるように）
      - 既存の triage.csv は上書きせず、日時付きの名前に退避する（記入済みのランクを守るため）
      - キャンセルされたら、そこまでの行で triage.csv を書いて終わる
    """
    _ensure_dir(TRIAGE_DIR, "TRIAGE_DIR")
    log_path = os.path.join(TRIAGE_DIR, LOG_FILENAME)
    projects, missing = list_target_projects(app)
    if missing:
        ui.messageBox("次のプロジェクトが見つかりません（名前を確認してください）:\n" + "\n".join(missing))
        if not projects:
            return

    progress = Progress(ui, "モード1: ファイルを数えています", 1)
    rows, counts = [], {"ok": 0, "fail": 0}
    cancelled = False
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

        # 2) 1件ずつ開いて撮影
        used_folder, used_image = set(), set()
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
            row["folder_name"] = unique_name(make_folder_name(row.get("created"), name), used_folder, "folder")
            image = unique_name(row["folder_name"] + ".png", used_image)
            doc, ours = None, False
            try:
                doc, ours = open_document(app, df)
                get_design(doc)  # デザインでなければここで失敗として記録
                save_thumbnail(app, os.path.join(TRIAGE_DIR, image))
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
        csv_path = os.path.join(TRIAGE_DIR, TRIAGE_FILENAME)
        if rows:
            if os.path.isfile(csv_path):
                os.replace(csv_path, backup_path(csv_path))
            write_triage_csv(csv_path, rows)
        progress.close()

    ui.messageBox(
        "モード1 終了{}\n\n画像を保存: {} 件\n失敗: {} 件\n一覧: {}\n\n"
        "triage.csv の rank 列に A/B/C を書き、必要なら folder_name を直してからモード2を実行してください。"
        .format("（中止）" if cancelled else "", counts["ok"], counts["fail"],
                os.path.join(TRIAGE_DIR, TRIAGE_FILENAME)))


# =============================================================================
# モード2: フル書き出し
# =============================================================================
def run_mode2(app, ui):
    """triage.csv の A/B の行を、作品フォルダとして OUTPUT_DIR に書き出す。

    方針:
      - meta.json があるフォルダは済みとして飛ばす。無ければ（途中で止まった）やり直す
      - meta.json は全部の書き出しが成功したときだけ、最後に書く
      - 1件ずつ try し、失敗してもログに書いて次へ進む
    """
    _ensure_dir(OUTPUT_DIR, "OUTPUT_DIR")
    log_path = os.path.join(OUTPUT_DIR, LOG_FILENAME)
    rows, warnings = select_rows_for_export(read_triage_csv(TRIAGE_CSV))
    for w in warnings:
        append_log(log_path, "", "注意", w, mode=2)
    if not rows:
        ui.messageBox("rank が A か B の行がありません。\n" + TRIAGE_CSV)
        return

    finder = FileFinder(app)
    progress = Progress(ui, "モード2: 書き出し", len(rows))
    counts = {"ok": 0, "check": 0, "fail": 0, "skip": 0}
    cancelled = False
    try:
        for i, row in enumerate(rows):
            if progress.cancelled():
                cancelled = True
                break
            name, folder_name = row.get("name", ""), row["folder_name"]
            label = f"{folder_name}（{name}）"
            progress.update(i, f"{i + 1}/{len(rows)}  {folder_name}")
            folder = os.path.join(OUTPUT_DIR, folder_name)
            if is_done(folder):
                counts["skip"] += 1
                append_log(log_path, label, RESULT_SKIP, "meta.json があるため（書き出し済み）", mode=2)
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
                os.makedirs(folder, exist_ok=True)
                notes = export_item(app, design, folder, name or df.name)
                write_meta_json(folder, build_meta(row.get("project", ""), row.get("folder_path", ""),
                                                   name or df.name))
                notes.insert(0, found_by)
                if refs:
                    notes.insert(1, "外部参照あり: " + ", ".join(refs))
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
        "モード2 終了{}\n\n成功: {} 件\n成功（要目視確認・外部参照あり）: {} 件\n失敗: {} 件\n"
        "スキップ（書き出し済み）: {} 件\n\n詳しくは {} を見てください。失敗した分は、もう一度実行するとやり直します。"
        .format("（中止）" if cancelled else "", counts["ok"], counts["check"], counts["fail"],
                counts["skip"], log_path))


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
