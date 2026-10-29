# -*- coding: utf-8 -*-
"""fusion_export.py の Fusion を要しない部分のテスト（Python 3.12 標準 unittest）。

adsk は Fusion の中にしか無いので、sys.modules に偽物を差し込んでから import する。
実行方法は README.md を参照。
"""
import codecs
import csv
import datetime
import importlib.util
import json
import os
import sys
import tempfile
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.normpath(os.path.join(HERE, "..", "..", "tools", "fusion_export", "fusion_export.py"))


# ---------------------------------------------------------------------------
# 偽の adsk（import が通り、定数が参照できるだけの最小限）
# ---------------------------------------------------------------------------
def _install_fake_adsk():
    adsk = types.ModuleType("adsk")
    core = types.ModuleType("adsk.core")
    fusion = types.ModuleType("adsk.fusion")
    adsk.doEvents = lambda: None
    adsk.core = core
    adsk.fusion = fusion

    class Application:
        @staticmethod
        def get():
            raise RuntimeError("テストでは Fusion を使わない")

    core.Application = Application
    core.ViewOrientations = types.SimpleNamespace(IsoTopRightViewOrientation=7)
    fusion.MeshRefinementSettings = types.SimpleNamespace(
        MeshRefinementHigh=0, MeshRefinementMedium=1, MeshRefinementLow=2, MeshRefinementCustom=3)
    fusion.DistanceUnits = types.SimpleNamespace(MillimeterDistanceUnits=0)
    sys.modules["adsk"] = adsk
    sys.modules["adsk.core"] = core
    sys.modules["adsk.fusion"] = fusion


_install_fake_adsk()
# tools/ は Drive へ丸ごとコピーするので、そこに __pycache__ を作らない
sys.dont_write_bytecode = True
_spec = importlib.util.spec_from_file_location("fusion_export", SCRIPT)
fe = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fe)


class TmpDirCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()


# ---------------------------------------------------------------------------
# 名前づけ
# ---------------------------------------------------------------------------
class TestSanitize(unittest.TestCase):
    def test_invalid_chars_replaced(self):
        self.assertEqual(fe.sanitize_filename('a/b\\c:d*e?f"g<h>i|j'), "a_b_c_d_e_f_g_h_i_j")

    def test_japanese_kept(self):
        self.assertEqual(fe.sanitize_filename("流路セルホルダー v2"), "流路セルホルダー v2")

    def test_control_chars(self):
        self.assertEqual(fe.sanitize_filename("a\tb\nc"), "a_b_c")

    def test_trailing_dots_and_spaces(self):
        self.assertEqual(fe.sanitize_filename("  name. . "), "name")

    def test_empty(self):
        self.assertEqual(fe.sanitize_filename(""), "無題")
        self.assertEqual(fe.sanitize_filename(None), "無題")
        self.assertEqual(fe.sanitize_filename(" . "), "無題")

    def test_reserved(self):
        self.assertEqual(fe.sanitize_filename("CON"), "_CON")
        self.assertEqual(fe.sanitize_filename("com1.stl"), "_com1.stl")
        self.assertEqual(fe.sanitize_filename("CONSOLE"), "CONSOLE")


class TestDates(unittest.TestCase):
    def test_epoch_to_text(self):
        epoch = 1749700800  # 2025-06-12 04:00 UTC
        expected = datetime.datetime.fromtimestamp(epoch).strftime("%Y-%m-%d %H:%M")
        self.assertEqual(fe.epoch_to_text(epoch), expected)
        self.assertEqual(fe.epoch_to_text(str(epoch)), expected)

    def test_epoch_invalid(self):
        for v in (None, 0, -5, "abc"):
            self.assertEqual(fe.epoch_to_text(v), "")

    def test_date_part_formats(self):
        self.assertEqual(fe.date_part("2025-06-12 10:00"), "20250612")
        self.assertEqual(fe.date_part("2025/6/3"), "20250603")
        self.assertEqual(fe.date_part("20250612"), "20250612")
        self.assertEqual(fe.date_part(" 2025.06.12 "), "20250612")

    def test_date_part_invalid(self):
        for v in ("", None, "2025-02-30", "abc", "12/06/2025"):
            self.assertEqual(fe.date_part(v), "", v)

    def test_make_folder_name(self):
        self.assertEqual(fe.make_folder_name("2025-06-12 10:00", "流路セル/ホルダー"), "20250612_流路セル_ホルダー")
        self.assertEqual(fe.make_folder_name("", "治具"), "00000000_治具")

    def test_is_valid_folder_name(self):
        self.assertTrue(fe.is_valid_folder_name("20250612_治具"))
        self.assertTrue(fe.is_valid_folder_name("20250612_治具-v2"))
        self.assertFalse(fe.is_valid_folder_name("00000000_治具"))
        self.assertFalse(fe.is_valid_folder_name("2025061_治具"))
        self.assertFalse(fe.is_valid_folder_name("20250612治具"))
        self.assertFalse(fe.is_valid_folder_name(""))


class TestUniqueName(unittest.TestCase):
    def test_file_style(self):
        used = set()
        self.assertEqual(fe.unique_name("body.stl", used), "body.stl")
        self.assertEqual(fe.unique_name("body.stl", used), "body_2.stl")
        self.assertEqual(fe.unique_name("Body.STL", used), "Body_3.STL")  # 大文字小文字は区別しない

    def test_folder_style(self):
        used = set()
        self.assertEqual(fe.unique_name("20250612_治具", used, "folder"), "20250612_治具")
        self.assertEqual(fe.unique_name("20250612_治具", used, "folder"), "20250612_治具-v2")
        self.assertEqual(fe.unique_name("20250612_治具", used, "folder"), "20250612_治具-v3")

    def test_no_extension(self):
        used = {"readme"}
        self.assertEqual(fe.unique_name("readme", used), "readme_2")


# ---------------------------------------------------------------------------
# meta.json
# ---------------------------------------------------------------------------
class TestMeta(TmpDirCase):
    def test_build_meta(self):
        meta = fe.build_meta("研究室共有", "治具/顕微鏡", "ステージ")
        self.assertEqual(meta, {"author": "", "purpose": "", "status": "", "tags": [],
                                "note": ["Fusion元: 研究室共有/治具/顕微鏡/ステージ"]})

    def test_source_text_root_folder(self):
        self.assertEqual(fe.source_text("P", "", "N"), "P/N")
        self.assertEqual(fe.source_text("P", "/a/", "N"), "P/a/N")

    def test_json_text(self):
        text = fe.meta_json_text(fe.build_meta("P", "", "名前"))
        self.assertIn("Fusion元: P/名前", text)          # ensure_ascii=False
        self.assertIn('\n  "author": ""', text)          # インデント2
        self.assertEqual(list(json.loads(text).keys()), ["author", "purpose", "status", "tags", "note"])

    def test_write_and_is_done(self):
        folder = os.path.join(self.tmp, "20250612_x")
        os.makedirs(folder)
        self.assertFalse(fe.is_done(folder))
        fe.write_meta_json(folder, fe.build_meta("P", "", "x"))
        self.assertTrue(fe.is_done(folder))
        self.assertEqual(os.listdir(folder), ["meta.json"])  # 一時ファイルが残らない
        with open(os.path.join(folder, "meta.json"), "rb") as f:
            raw = f.read()
        self.assertFalse(raw.startswith(codecs.BOM_UTF8))
        self.assertEqual(json.loads(raw.decode("utf-8"))["status"], "")

    def test_is_done_missing_folder(self):
        self.assertFalse(fe.is_done(os.path.join(self.tmp, "nope")))


# ---------------------------------------------------------------------------
# CSV
# ---------------------------------------------------------------------------
def _row(**kw):
    base = {"project": "P", "folder_path": "", "name": "n", "datafile_id": "urn:x",
            "version_id": "", "created": "2025-06-12 10:00", "modified": "2025-07-01 09:00", "image": "", "rank": "", "folder_name": ""}
    base.update(kw)
    return base


class TestTriageCsv(TmpDirCase):
    def test_roundtrip_with_bom(self):
        path = os.path.join(self.tmp, "triage.csv")
        rows = [_row(name="流路セル, 改", folder_name="20250612_流路セル"), _row(name='引用"符')]
        fe.write_triage_csv(path, rows)
        with open(path, "rb") as f:
            self.assertTrue(f.read().startswith(codecs.BOM_UTF8))
        back = fe.read_triage_csv(path)
        self.assertEqual(back, rows)

    def test_header_order(self):
        path = os.path.join(self.tmp, "triage.csv")
        fe.write_triage_csv(path, [_row()])
        with open(path, encoding="utf-8-sig") as f:
            self.assertEqual(next(csv.reader(f)), fe.TRIAGE_COLUMNS)

    def test_read_without_bom(self):
        path = os.path.join(self.tmp, "t.csv")
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write("project,folder_path,name,datafile_id,created,modified,image,rank,folder_name\r\n")
            f.write("P,,名前,urn:1,2025-06-12 10:00,,,A,\r\n")
        rows = fe.read_triage_csv(path)
        self.assertEqual(rows[0]["name"], "名前")
        self.assertEqual(rows[0]["rank"], "A")

    def test_read_cp932(self):
        path = os.path.join(self.tmp, "t.csv")
        with open(path, "w", encoding="cp932", newline="") as f:
            f.write("project,name,datafile_id,rank\r\n研究室,治具,urn:1,B\r\n")
        self.assertEqual(fe.read_triage_csv(path)[0]["project"], "研究室")

    def test_read_strips_spaces_and_extra_columns(self):
        path = os.path.join(self.tmp, "t.csv")
        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            f.write(" project , name ,datafile_id,rank,メモ\n P , n ,urn:1, a ,自由記述\n")
        r = fe.read_triage_csv(path)[0]
        self.assertEqual((r["project"], r["name"], r["rank"], r["メモ"]), ("P", "n", "a", "自由記述"))

    def test_read_newline_in_cell(self):
        path = os.path.join(self.tmp, "t.csv")
        fe.write_triage_csv(path, [_row(name="行1" + chr(13) + chr(10) + "行2", rank="A")])
        self.assertEqual(fe.read_triage_csv(path)[0]["name"], "行1" + chr(13) + chr(10) + "行2")

    def test_read_short_row(self):
        path = os.path.join(self.tmp, "t.csv")
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write("project,name,datafile_id,rank,folder_name\nP,n,urn:1\n")
        r = fe.read_triage_csv(path)[0]
        self.assertEqual((r["rank"], r["folder_name"]), ("", ""))

    def test_read_missing_column(self):
        path = os.path.join(self.tmp, "t.csv")
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write("project,name,rank\nP,n,A\n")
        with self.assertRaises(ValueError) as cm:
            fe.read_triage_csv(path)
        self.assertIn("datafile_id", str(cm.exception))


class TestSelectRows(unittest.TestCase):
    def test_rank_filter(self):
        rows = [_row(name="a", rank="A"), _row(name="b", rank="B"), _row(name="c", rank="C"),
                _row(name="d", rank=""), _row(name="e", rank="ａ"), _row(name="f", rank=" b ")]
        selected, _ = fe.select_rows_for_export(rows)
        self.assertEqual([r["name"] for r in selected], ["a", "b", "e", "f"])

    def test_folder_name_filled_from_created(self):
        selected, warnings = fe.select_rows_for_export([_row(name="治具:改", rank="A")])
        self.assertEqual(selected[0]["folder_name"], "20250612_治具_改")
        self.assertEqual(warnings, [])

    def test_user_folder_name_sanitized(self):
        selected, _ = fe.select_rows_for_export([_row(rank="A", folder_name="20240101_a/b")])
        self.assertEqual(selected[0]["folder_name"], "20240101_a_b")

    def test_duplicates_get_v2(self):
        rows = [_row(name="x", rank="A"), _row(name="x", rank="B"), _row(name="y", rank="A", folder_name="20250612_x")]
        selected, warnings = fe.select_rows_for_export(rows)
        self.assertEqual([r["folder_name"] for r in selected], ["20250612_x", "20250612_x-v2", "20250612_x-v3"])
        self.assertEqual(len(warnings), 2)

    def test_invalid_folder_name_warns(self):
        selected, warnings = fe.select_rows_for_export([_row(rank="A", created="", folder_name="")])
        self.assertEqual(selected[0]["folder_name"], "00000000_n")
        self.assertTrue(any("形式" in w for w in warnings))

    def test_input_not_mutated(self):
        rows = [_row(rank="A")]
        fe.select_rows_for_export(rows)
        self.assertEqual(rows[0]["folder_name"], "")


class TestLookup(unittest.TestCase):
    def test_candidates_order(self):
        self.assertEqual(fe.lookup_candidates({"version_id": "urn:v?version=3", "datafile_id": "urn:l"}),
                         [("version_id", "urn:v?version=3"), ("datafile_id", "urn:l")])

    def test_candidates_old_csv_and_blanks(self):
        self.assertEqual(fe.lookup_candidates({"datafile_id": "urn:l"}), [("datafile_id", "urn:l")])
        self.assertEqual(fe.lookup_candidates({"version_id": " ", "datafile_id": "urn:l"}), [("datafile_id", "urn:l")])
        self.assertEqual(fe.lookup_candidates({}), [])
        self.assertEqual(fe.lookup_candidates({"version_id": "x", "datafile_id": "x"}), [("version_id", "x")])

    def test_old_csv_readable(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "t.csv")
            with open(path, "w", encoding="utf-8-sig", newline="") as f:
                f.write("project,folder_path,name,datafile_id,created,modified,image,rank,folder_name\n"
                        "P,,n,urn:l,2025-06-12 10:00,,,A,\n")
            rows, _ = fe.select_rows_for_export(fe.read_triage_csv(path))
            self.assertEqual(fe.lookup_candidates(rows[0]), [("datafile_id", "urn:l")])


class FakeDataFile:
    def __init__(self, lineage, version, latest=None):
        self.id, self.versionId, self._latest = lineage, version, latest

    @property
    def latestVersion(self):
        return self._latest or self


class TestFileFinder(unittest.TestCase):
    def _finder(self, by_id, scan=()):
        app = types.SimpleNamespace(data=types.SimpleNamespace(findFileById=lambda i: by_id.get(i)))
        finder = fe.FileFinder(app)
        saved = (fe.list_target_projects, fe.walk_f3d_files)
        self.scans = 0

        def walk(p, on_progress=None):
            self.scans += 1
            return [(d, "") for d in scan]

        fe.list_target_projects = lambda app: (["P"], [])
        fe.walk_f3d_files = walk
        self.addCleanup(lambda: (setattr(fe, "list_target_projects", saved[0]),
                                 setattr(fe, "walk_f3d_files", saved[1])))
        return finder

    def test_version_id_first(self):
        df = FakeDataFile("urn:l", "urn:v1")
        f = self._finder({"urn:v1": df, "urn:l": FakeDataFile("urn:l", "urn:other")})
        self.assertEqual(f.find({"version_id": "urn:v1", "datafile_id": "urn:l"}), (df, "version_id"))

    def test_version_id_upgraded_to_latest(self):
        latest = FakeDataFile("urn:l", "urn:v2")
        old = FakeDataFile("urn:l", "urn:v1", latest=latest)
        f = self._finder({"urn:v1": old})
        self.assertEqual(f.find({"version_id": "urn:v1", "datafile_id": "urn:l"}), (latest, "version_id→最新版"))

    def test_fallback_to_lineage(self):
        df = FakeDataFile("urn:l", "urn:v1")
        f = self._finder({"urn:l": df})
        self.assertEqual(f.find({"version_id": "urn:v1", "datafile_id": "urn:l"}), (df, "datafile_id"))

    def test_fallback_to_rescan_once(self):
        a, b = FakeDataFile("urn:a", "urn:av"), FakeDataFile("urn:b", "urn:bv")
        f = self._finder({}, scan=[a, b])
        self.assertEqual(f.find({"datafile_id": "urn:a"}), (a, "再走査"))
        self.assertEqual(f.find({"version_id": "urn:bv"}), (b, "再走査"))
        self.assertEqual(f.find({"datafile_id": "urn:zz"}), (None, ""))
        self.assertEqual(self.scans, 1)  # 再走査は1回だけ

    def test_no_ids(self):
        self.assertEqual(self._finder({}).find({}), (None, ""))


class TestFolderState(TmpDirCase):
    def _make(self, name, meta=None, raw=None):
        folder = os.path.join(self.tmp, name)
        os.makedirs(folder)
        if meta is not None:
            fe.write_meta_json(folder, meta)
        if raw is not None:
            with open(os.path.join(folder, "meta.json"), "w", encoding="utf-8") as f:
                f.write(raw)
        return folder

    def test_states(self):
        self.assertEqual(fe.folder_state(os.path.join(self.tmp, "none"), "P/x"), "new")
        self.assertEqual(fe.folder_state(self._make("a"), "P/x"), "partial")
        self.assertEqual(fe.folder_state(self._make("b", fe.build_meta("P", "", "x")), "P/x"), "done")
        self.assertEqual(fe.folder_state(self._make("c", {"note": "Fusion元: P/x"}), "P/x"), "done")  # 文字列の note
        self.assertEqual(fe.folder_state(self._make("d", {"note": ["Fusion元: P/y"]}), "P/x"), "conflict")
        self.assertEqual(fe.folder_state(self._make("e", {"author": "a"}), "P/x"), "conflict")
        self.assertEqual(fe.folder_state(self._make("f", raw="{壊れた"), "P/x"), "conflict")
        self.assertEqual(fe.folder_state(self._make("g", raw="[]"), "P/x"), "conflict")

    def test_done_with_bom_and_edited_note(self):
        folder = self._make("h")
        with open(os.path.join(folder, "meta.json"), "w", encoding="utf-8-sig") as f:
            json.dump({"author": "山田", "note": ["追記", " Fusion元: P/x "]}, f, ensure_ascii=False)
        self.assertEqual(fe.folder_state(folder, "P/x"), "done")

    def test_resolve(self):
        self._make("20250612_x", {"note": "手作り"})
        self._make("20250612_x-v2", {"note": "別"})
        reserved = {"20250612_x", "20250612_x-v3"}  # -v3 は他の行が使う
        self.assertEqual(fe.resolve_output_folder(self.tmp, "20250612_x", "P/x", reserved),
                         ("20250612_x-v4", "new", ["20250612_x", "20250612_x-v2"]))
        self.assertIn("20250612_x-v4", reserved)

    def test_resolve_plain(self):
        self.assertEqual(fe.resolve_output_folder(self.tmp, "20250612_y", "P/y", set()), ("20250612_y", "new", []))


class TestSettingPath(unittest.TestCase):
    def test_check(self):
        ok = os.path.join("G:" + os.sep, "共有ドライブ", "研究室", "3Dギャラリー", "items")
        self.assertEqual(fe.check_setting_path(ok, "OUTPUT_DIR"), "")
        self.assertIn("書き換え", fe.check_setting_path(fe.OUTPUT_DIR, "OUTPUT_DIR"))  # 既定値のままは止める
        self.assertIn("設定されていません", fe.check_setting_path("", "OUTPUT_DIR"))

    def test_defaults_are_shared_drive(self):
        for p in (fe.OUTPUT_DIR, fe.TRIAGE_DIR, fe.TRIAGE_CSV):
            self.assertIn("共有ドライブ", p)
            self.assertNotIn("マイドライブ", p)


class TestSelectProjects(unittest.TestCase):
    def test_empty_means_all(self):
        self.assertEqual(fe.select_projects(["a", "b"], []), (["a", "b"], []))

    def test_filter_and_missing(self):
        self.assertEqual(fe.select_projects(["a", "b", "c"], ["c", "a", "zz"]), (["a", "c"], ["zz"]))


# ---------------------------------------------------------------------------
# ログ
# ---------------------------------------------------------------------------
class TestLog(TmpDirCase):
    def test_append(self):
        path = os.path.join(self.tmp, "export_log.csv")
        now = datetime.datetime(2026, 10, 30, 12, 0, 0)
        fe.append_log(path, "名前1", fe.RESULT_OK, "", mode=2, now=now)
        fe.append_log(path, "名前2", fe.RESULT_FAIL, "エラー, 詳細", mode=2, now=now)
        with open(path, "rb") as f:
            raw = f.read()
        self.assertTrue(raw.startswith(codecs.BOM_UTF8))
        self.assertEqual(raw.count(codecs.BOM_UTF8), 1)  # 追記で BOM が増えない
        rows = list(csv.reader(raw.decode("utf-8-sig").splitlines()))
        self.assertEqual(rows[0], fe.LOG_COLUMNS)
        self.assertEqual(rows[1], ["2026-10-30 12:00:00", "2", "名前1", "成功", ""])
        self.assertEqual(rows[2][3:], ["失敗", "エラー, 詳細"])
        self.assertEqual(len(rows), 3)

    def test_backup_path(self):
        p = fe.backup_path(os.path.join("d", "triage.csv"), datetime.datetime(2026, 10, 30, 9, 8, 7))
        self.assertEqual(p, os.path.join("d", "triage_20261030_090807.csv"))


# ---------------------------------------------------------------------------
# コレクションとボディの選別（Fusion のオブジェクトを形だけ真似る）
# ---------------------------------------------------------------------------
class FakeCollection:
    """count / item だけを持つコレクション。"""

    def __init__(self, items):
        self._items = list(items)

    @property
    def count(self):
        return len(self._items)

    def item(self, i):
        return self._items[i]


class FakeArrayCollection(FakeCollection):
    def asArray(self):
        return list(self._items)

    def item(self, i):
        raise AssertionError("asArray があれば item は使わない")


class FakeBody:
    def __init__(self, name, solid=True, visible=True, context=None):
        self.name, self.isSolid, self.isVisible, self.assemblyContext = name, solid, visible, context


class FakeOcc:
    def __init__(self, name, bodies, visible=True):
        self.name, self.isVisible = name, visible
        self.component = types.SimpleNamespace(name=name)
        self.bRepBodies = FakeCollection(bodies)


class FakeRoot:
    def __init__(self, bodies, occs):
        self.bRepBodies = FakeCollection(bodies)
        self.allOccurrences = FakeCollection(occs)


class TestIter(unittest.TestCase):
    def test_variants(self):
        self.assertEqual(fe._iter(None), [])
        self.assertEqual(fe._iter([1, 2]), [1, 2])
        self.assertEqual(fe._iter(FakeCollection("ab")), ["a", "b"])
        self.assertEqual(fe._iter(FakeArrayCollection("xyz")), ["x", "y", "z"])


class TestCollectBodies(unittest.TestCase):
    def test_visible_solids_only(self):
        occ1 = FakeOcc("o1", [FakeBody("p1", context="o1"), FakeBody("hidden", visible=False, context="o1")])
        occ_hidden = FakeOcc("o2", [FakeBody("p2", context="o2")], visible=False)
        root = FakeRoot([FakeBody("root"), FakeBody("surface", solid=False)], [occ1, occ_hidden])
        labels = [label for _b, label in fe.collect_visible_solid_bodies(root)]
        self.assertEqual(labels, ["root", "o1_p1"])  # オカレンス内はコンポーネント名_ボディ名

    def test_native_body_is_wrapped_in_proxy(self):
        class Native(FakeBody):
            def createForAssemblyContext(self, occ):
                return FakeBody(self.name + "@" + occ.name, context=occ)

        occ = FakeOcc("o1", [Native("p")])
        bodies = fe.collect_visible_solid_bodies(FakeRoot([], [occ]))
        self.assertEqual([b.name for b, _l in bodies], ["p@o1"])

    def test_broken_body_ignored(self):
        class Broken:
            name = "x"
            assemblyContext = "o"

            @property
            def isSolid(self):
                raise RuntimeError("transient")

        root = FakeRoot([Broken(), FakeBody("ok")], [])
        self.assertEqual([label for _b, label in fe.collect_visible_solid_bodies(root)], ["ok"])

    def test_same_body_name_in_components(self):
        lid = FakeOcc("lid", [FakeBody("Body1", context="lid")])
        base = FakeOcc("base", [FakeBody("Body1", context="base")])
        bodies = fe.collect_visible_solid_bodies(FakeRoot([FakeBody("Body1")], [lid, base]))
        self.assertEqual([label for _b, label in bodies], ["Body1", "lid_Body1", "base_Body1"])


# ---------------------------------------------------------------------------
# モード2の流れ（Fusion 部分は差し替え）。スキップ・やり直し・失敗時に meta.json を書かないことを確かめる
# ---------------------------------------------------------------------------
class FakeUI:
    def __init__(self):
        self.messages = []

    def messageBox(self, text, *a):
        self.messages.append(text)

    def createProgressDialog(self):
        return types.SimpleNamespace(isCancelButtonShown=False, cancelButtonText="", maximumValue=0,
                                     progressValue=0, message="", wasCancelled=False,
                                     show=lambda *a: True, hide=lambda: True)


class TestMode2Flow(TmpDirCase):
    def setUp(self):
        super().setUp()
        self.out = os.path.join(self.tmp, "items")
        self.csv = os.path.join(self.tmp, "triage.csv")
        fe.write_triage_csv(self.csv, [
            _row(name="済み", rank="A", datafile_id="urn:done"),
            _row(name="途中", rank="B", datafile_id="urn:partial"),
            _row(name="失敗", rank="A", datafile_id="urn:fail"),
            _row(name="外部参照", rank="A", datafile_id="urn:ref"),
            _row(name="無い", rank="A", datafile_id="urn:missing"),
            _row(name="手作り", rank="A", datafile_id="urn:hand"),
            _row(name="開いていた", rank="A", datafile_id="urn:open"),
            _row(name="対象外", rank="C", datafile_id="urn:c"),
        ])
        os.makedirs(os.path.join(self.out, "20250612_済み"))
        self.done_meta = {"author": "手で記入済み", "note": ["メモ", "Fusion元: P/済み"]}
        fe.write_meta_json(os.path.join(self.out, "20250612_済み"), self.done_meta)
        # 同名だが別の作品（手作り）のフォルダ。触らずに -v2 へ書き出すはず
        os.makedirs(os.path.join(self.out, "20250612_手作り"))
        self.hand_meta = {"author": "誰か", "note": "手で作った"}
        fe.write_meta_json(os.path.join(self.out, "20250612_手作り"), self.hand_meta)
        os.makedirs(os.path.join(self.out, "20250612_途中"))  # meta.json 無し＝途中で止まった

        self.saved = {k: getattr(fe, k) for k in
                      ("OUTPUT_DIR", "TRIAGE_CSV", "FileFinder", "open_document", "close_document",
                       "get_design", "export_item", "find_external_references")}
        fe.OUTPUT_DIR, fe.TRIAGE_CSV = self.out, self.csv
        self.opened, self.closed = [], []
        test = self

        class Finder:
            def __init__(self, app):
                pass

            def find(self, row):
                fid = row.get("datafile_id")
                if fid == "urn:missing":
                    return None, ""
                return types.SimpleNamespace(id=fid, name="n"), "datafile_id"

        def open_document(app, df):
            test.opened.append(df.id)
            if df.id == "urn:open":  # 元々開いていて、未保存の変更がある
                return types.SimpleNamespace(id=df.id, isModified=True), False
            return df, True

        def export_item(app, design, folder, name):
            if design.id == "urn:fail":
                raise RuntimeError("STL: 書き出し失敗")
            open(os.path.join(folder, name + ".f3d"), "w").close()
            return []

        fe.FileFinder = Finder
        fe.open_document = open_document
        fe.close_document = lambda doc, ours: doc is not None and test.closed.append(doc.id)
        fe.get_design = lambda doc: doc
        fe.export_item = export_item
        fe.find_external_references = lambda d, doc, df: ["部品A"] if df.id == "urn:ref" else []

    def tearDown(self):
        for k, v in self.saved.items():
            setattr(fe, k, v)
        super().tearDown()

    def _log(self):
        with open(os.path.join(self.out, "export_log.csv"), encoding="utf-8-sig") as f:
            return {(r["name"], r["result"]): r for r in csv.DictReader(f)}

    def test_flow(self):
        ui = FakeUI()
        fe.run_mode2(object(), ui)

        # 済みは開かない。C ランクは対象外
        self.assertEqual(self.opened, ["urn:partial", "urn:fail", "urn:ref", "urn:hand", "urn:open"])
        # 開いたものは失敗しても close_document を通る（自分で開いたかの判断は close_document 側）
        self.assertEqual(self.closed, ["urn:partial", "urn:fail", "urn:ref", "urn:hand", "urn:open"])
        # 手で記入済みの meta.json は上書きしない
        with open(os.path.join(self.out, "20250612_済み", "meta.json"), encoding="utf-8") as f:
            self.assertEqual(json.load(f), self.done_meta)
        # 別の作品の同名フォルダには触らず、-v2 に書く
        with open(os.path.join(self.out, "20250612_手作り", "meta.json"), encoding="utf-8") as f:
            self.assertEqual(json.load(f), self.hand_meta)
        self.assertEqual(os.listdir(os.path.join(self.out, "20250612_手作り")), ["meta.json"])
        self.assertTrue(fe.is_done(os.path.join(self.out, "20250612_手作り-v2")))
        # 途中のものはやり直して meta.json を書く
        self.assertTrue(fe.is_done(os.path.join(self.out, "20250612_途中")))
        # 失敗したものは meta.json を書かない（次回やり直す）
        self.assertFalse(fe.is_done(os.path.join(self.out, "20250612_失敗")))
        self.assertTrue(fe.is_done(os.path.join(self.out, "20250612_外部参照")))
        with open(os.path.join(self.out, "20250612_途中", "meta.json"), encoding="utf-8") as f:
            self.assertEqual(json.load(f)["note"], ["Fusion元: P/途中"])

        log = self._log()
        self.assertIn(("20250612_済み（済み）", "スキップ"), log)
        self.assertIn("取得: datafile_id", log[("20250612_途中（途中）", "成功")]["detail"])
        fail = log[("20250612_失敗（失敗）", "失敗")]["detail"]
        self.assertIn("取得: datafile_id", fail)
        self.assertIn("STL", fail)
        self.assertIn("部品A", log[("20250612_外部参照（外部参照）", "成功（要目視確認）")]["detail"])
        self.assertIn(("20250612_無い（無い）", "失敗"), log)
        self.assertIn("20250612_手作り", log[("20250612_手作り-v2（手作り）", "注意")]["detail"])
        self.assertIn(("20250612_手作り-v2（手作り）", "成功"), log)
        self.assertIn("未保存の変更", log[("20250612_開いていた（開いていた）", "成功")]["detail"])
        self.assertNotIn("未保存", log[("20250612_途中（途中）", "成功")]["detail"])

        summary = ui.messages[-1]
        for s in ("成功: 3 件", "要目視確認・外部参照あり）: 1 件", "失敗: 2 件", "スキップ（書き出し済み）: 1 件"):
            self.assertIn(s, summary)

        # 再実行: 失敗・見つからないものだけやり直す。-v2 に書いたものは -v2 で済みと判定される
        self.opened.clear()
        fe.run_mode2(object(), FakeUI())
        self.assertEqual(self.opened, ["urn:fail"])

    def test_no_ab_rows(self):
        fe.write_triage_csv(self.csv, [_row(rank="C")])
        ui = FakeUI()
        fe.run_mode2(object(), ui)
        self.assertIn("A か B", ui.messages[-1])
        self.assertEqual(self.opened, [])


if __name__ == "__main__":
    unittest.main()
