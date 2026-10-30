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
import re
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
    def setUp(self):
        super().setUp()
        self.saved = {k: getattr(fe, k) for k in ("DEFAULT_AUTHOR", "DEFAULT_STATUS", "DEFAULT_TAGS")}

    def tearDown(self):
        for k, v in self.saved.items():
            setattr(fe, k, v)
        super().tearDown()

    def test_build_meta(self):
        # note は空。Fusion の場所は入れず、fusion_id に DataFile.id を入れる
        meta = fe.build_meta("urn:adsk.wipprod:dm.lineage:abc")
        self.assertEqual(meta, {"author": "", "purpose": "", "status": "", "tags": [], "note": [],
                                "fusion_id": "urn:adsk.wipprod:dm.lineage:abc"})

    def test_settings_defaults_are_empty(self):
        self.assertEqual((self.saved["DEFAULT_AUTHOR"], self.saved["DEFAULT_STATUS"], self.saved["DEFAULT_TAGS"]),
                         ("", "", []))

    def test_build_meta_uses_defaults(self):
        fe.DEFAULT_AUTHOR, fe.DEFAULT_STATUS, fe.DEFAULT_TAGS = "山田", "参考", ["治具", " ", "PLA"]
        meta = fe.build_meta("urn:l")
        self.assertEqual((meta["author"], meta["status"], meta["tags"], meta["purpose"]),
                         ("山田", "参考", ["治具", "PLA"], ""))
        meta["tags"].append("x")
        self.assertEqual(fe.DEFAULT_TAGS, ["治具", " ", "PLA"])  # 設定欄のリストを書き換えない

    def test_build_meta_tags_string(self):
        self.assertEqual(fe.build_meta("urn:l", tags="治具")["tags"], ["治具"])
        self.assertEqual(fe.build_meta("urn:l", author="", status="", tags=[])["author"], "")

    def test_status_comment_matches_gas(self):
        # 設定欄のコメントに書いた状態の選択肢が、GAS の STATUS_CHOICES と同じか
        gs = os.path.normpath(os.path.join(HERE, "..", "..", "tools", "gas", "Code.gs"))
        with open(gs, encoding="utf-8") as f:
            m = re.search(r"var STATUS_CHOICES = \[([^\]]*)\]", f.read())
        choices = [c.strip().strip("'\"") for c in m.group(1).split(",")]
        with open(SCRIPT, encoding="utf-8") as f:
            script = f.read()
        self.assertIn(" / ".join('"%s"' % c for c in choices), script)

    def test_source_text_root_folder(self):
        self.assertEqual(fe.source_text("P", "", "N"), "P/N")
        self.assertEqual(fe.source_text("P", "/a/", "N"), "P/a/N")

    def test_json_text(self):
        text = fe.meta_json_text(fe.build_meta("urn:l", author="山田"))
        self.assertIn('"author": "山田"', text)            # ensure_ascii=False
        self.assertIn('\n  "author": "山田"', text)        # インデント2
        self.assertNotIn("Fusion元", text)
        self.assertEqual(list(json.loads(text).keys()), ["author", "purpose", "status", "tags", "note", "fusion_id"])

    def test_write_and_is_done(self):
        folder = os.path.join(self.tmp, "20250612_x")
        os.makedirs(folder)
        self.assertFalse(fe.is_done(folder))
        fe.write_meta_json(folder, fe.build_meta("urn:x"))
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

    def test_ignore_rank(self):
        # TARGET_NAMES で名前を指定したときは rank を問わない
        rows = [_row(name="a", rank=""), _row(name="b", rank="C"), _row(name="c", rank="A")]
        selected, _ = fe.select_rows_for_export(rows, ignore_rank=True)
        self.assertEqual([r["name"] for r in selected], ["a", "b", "c"])

    def test_empty_datafile_id_not_exported(self):
        # datafile_id が空の行は済み判定ができないので書き出さず、注意を出す。フォルダ名の番号も消費しない
        rows = [_row(name="x", rank="A", datafile_id=" "), _row(name="x", rank="A")]
        selected, warnings = fe.select_rows_for_export(rows)
        self.assertEqual([r["folder_name"] for r in selected], ["20250612_x"])
        self.assertTrue(any("datafile_id が空" in w and "「x」" in w for w in warnings))


class TestSelectByNames(unittest.TestCase):
    def test_empty_means_all(self):
        self.assertEqual(fe.select_by_names(["a", "b"], []), (["a", "b"], []))

    def test_exact_match_after_strip_and_nfc(self):
        decomposed = "か\u3099め"  # 「が」を「か＋濁点」で書いたもの
        items = ["がめ", "治具", "治具 改", "治具"]
        selected, missing = fe.select_by_names(items, [" " + decomposed + " ", "治具"])
        self.assertEqual(selected, ["がめ", "治具", "治具"])  # 同名は全部。部分一致はしない
        self.assertEqual(missing, [])

    def test_case_and_width_are_distinct(self):
        selected, missing = fe.select_by_names(["Jig", "ＡＢ"], ["jig", "AB"])
        self.assertEqual(selected, [])
        self.assertEqual(missing, ["jig", "AB"])

    def test_missing_in_wanted_order_without_duplicates(self):
        items = [{"name": "a"}, {"name": "b"}]
        selected, missing = fe.select_by_names(items, ["zz", "b", " zz ", "", "yy"], name_of=lambda r: r["name"])
        self.assertEqual(selected, [{"name": "b"}])
        self.assertEqual(missing, ["zz", "yy"])

    def test_single_string_is_one_name(self):
        # C1: TARGET_NAMES = "治具" と書いても1つの名前として扱う（1文字ずつに割らない）
        self.assertEqual(fe.select_by_names(["治具", "治", "具"], "治具"), (["治具"], []))
        self.assertEqual(fe.select_by_names(["a"], " 無い "), ([], ["無い"]))

    def test_as_name_list(self):
        self.assertEqual(fe.as_name_list("治具"), ["治具"])
        self.assertEqual(fe.as_name_list(None), [])
        self.assertEqual(fe.as_name_list(""), [])
        self.assertEqual(fe.as_name_list(("a", "b")), ["a", "b"])

    def test_duplicate_names(self):
        # C2: 同じ名前の行が複数あるもの（照合と同じそろえ方で数える）
        rows = [{"name": "治具"}, {"name": "台"}, {"name": " 治具"}, {"name": "台"}, {"name": "x"}]
        self.assertEqual(fe.duplicate_names(rows, name_of=lambda r: r["name"]), [("治具", 2), ("台", 2)])


class TestMergeTriage(unittest.TestCase):
    def test_inherit_rank_and_folder_name(self):
        old = [_row(name="旧名", datafile_id="urn:a", rank="A", folder_name="20240101_手で直した", image="old.png")]
        new = [_row(name="新名", datafile_id="urn:a", rank="", folder_name="20250612_新名", image="new.png",
                    version_id="urn:v2")]
        merged = fe.merge_triage_rows(old, new)
        self.assertEqual(len(merged), 1)
        m = merged[0]
        self.assertEqual((m["rank"], m["folder_name"]), ("A", "20240101_手で直した"))
        self.assertEqual((m["name"], m["image"], m["version_id"]), ("新名", "new.png", "urn:v2"))  # 他は新しい値

    def test_blank_old_values_do_not_overwrite(self):
        old = [_row(datafile_id="urn:a", rank="", folder_name="")]
        new = [_row(datafile_id="urn:a", folder_name="20250612_n")]
        self.assertEqual(fe.merge_triage_rows(old, new)[0]["folder_name"], "20250612_n")

    def test_keep_old_image_when_shot_failed(self):
        old = [_row(datafile_id="urn:a", image="a.png")]
        new = [_row(datafile_id="urn:a", image="")]
        self.assertEqual(fe.merge_triage_rows(old, new)[0]["image"], "a.png")

    def test_keep_untouched_rows_and_order(self):
        old = [_row(name="o1", datafile_id="urn:1", rank="B"), _row(name="o2", datafile_id="urn:2", rank="C"),
               _row(name="o3", datafile_id="", rank="A")]
        new = [_row(name="new", datafile_id="urn:9"), _row(name="o2'", datafile_id="urn:2"),
               _row(name="noid", datafile_id="")]
        merged = fe.merge_triage_rows(old, new)
        self.assertEqual([r["name"] for r in merged], ["o1", "o2'", "o3", "new", "noid"])
        self.assertEqual([r["rank"] for r in merged], ["B", "C", "A", "", ""])

    def test_no_old(self):
        new = [_row(name="a", datafile_id="urn:a"), _row(name="b", datafile_id="urn:b")]
        self.assertEqual(fe.merge_triage_rows([], new), new)

    def test_duplicate_ids(self):
        old = [_row(name="o", datafile_id="urn:a", rank="A"), _row(name="o-copy", datafile_id="urn:a", rank="B")]
        new = [_row(name="n", datafile_id="urn:a"), _row(name="n2", datafile_id="urn:a")]
        merged = fe.merge_triage_rows(old, new)
        self.assertEqual([(r["name"], r["rank"]) for r in merged], [("n", "A"), ("o-copy", "B"), ("n2", "")])

    def test_inputs_not_mutated(self):
        old = [_row(datafile_id="urn:a", rank="A")]
        new = [_row(datafile_id="urn:a")]
        fe.merge_triage_rows(old, new)
        self.assertEqual(new[0]["rank"], "")

    def test_names_in_use(self):
        old = [_row(datafile_id="urn:a", folder_name="20250612_A", image="20250612_A.png"),
               _row(datafile_id="urn:b", folder_name="20250612_B", image="20250612_B.png"),
               _row(datafile_id="", folder_name="", image="")]
        self.assertEqual(fe.names_in_use(old, {"urn:a"}), ({"20250612_b"}, {"20250612_b.png"}))


class TestResolvePaths(unittest.TestCase):
    OUT = os.path.join("G:" + os.sep, "共有ドライブ", "研究室", "3Dギャラリー", "items")

    def test_triage_csv_defaults_to_triage_dir(self):
        paths, problems = fe.resolve_paths(2, os.path.join("C:" + os.sep, "t"), "", self.OUT)
        self.assertEqual(paths["triage_csv"], os.path.join("C:" + os.sep, "t", "triage.csv"))
        self.assertEqual(problems, [])

    def test_explicit_triage_csv(self):
        paths, _ = fe.resolve_paths(2, "C:/t", "  D:/x/my.csv ", self.OUT)
        self.assertEqual(paths["triage_csv"], "D:/x/my.csv")

    def test_expanduser(self):
        paths, _ = fe.resolve_paths(1, "~/仕分け", "", "")
        self.assertEqual(paths["triage_dir"], os.path.expanduser("~/仕分け"))

    def test_mode1_ignores_output_dir(self):
        # モード1は OUTPUT_DIR が未設定・<共有ドライブ名> のままでも動く
        for out in ("", fe.OUTPUT_DIR):
            self.assertEqual(fe.resolve_paths(1, "C:/t", "", out)[1], [])

    def test_empty_triage_dir_uses_documents(self):
        # C6: TRIAGE_DIR が空なら「ドキュメント」（Known Folder）の中の 3Dギャラリー_仕分け
        docs = os.path.join("D:" + os.sep, "OneDrive", "ドキュメント")
        for mode in (1, 2):
            paths, problems = fe.resolve_paths(mode, " ", "", self.OUT, documents=docs)
            self.assertEqual(problems, [])
            self.assertEqual(paths["triage_dir"], os.path.join(docs, "3Dギャラリー_仕分け"))
            self.assertEqual(paths["triage_csv"], os.path.join(docs, "3Dギャラリー_仕分け", "triage.csv"))

    def test_mode2_checks_output_dir_only_for_placeholder(self):
        problems = fe.resolve_paths(2, "C:/<名前>/t", "", fe.OUTPUT_DIR)[1]
        self.assertEqual(len(problems), 1)
        self.assertIn("OUTPUT_DIR", problems[0])
        self.assertIn("書き換え", problems[0])
        self.assertIn("設定されていません", fe.resolve_paths(2, "C:/t", "", "")[1][0])

    def test_missing_r_prefix_is_reported(self):
        # r を付け忘れた "G:\共有\3Dギャラリー" は "\3" が制御文字 \x03 に化ける
        broken = "G:\\共有\x03Dギャラリー"
        problems = fe.resolve_paths(1, broken, "", "")[1]
        self.assertEqual(len(problems), 1)
        self.assertIn("TRIAGE_DIR", problems[0])
        self.assertIn("先頭の r", problems[0])
        # モード2では TRIAGE_CSV・OUTPUT_DIR も調べる。OUTPUT_DIR は化けの指摘だけを出す
        problems = fe.resolve_paths(2, "C:/t", "C:/t\tx.csv", "G:\\x\x07\\items")[1]
        self.assertEqual(len(problems), 2)
        self.assertIn("TRIAGE_CSV", problems[0])
        self.assertIn("OUTPUT_DIR", problems[1])
        # モード1は TRIAGE_CSV・OUTPUT_DIR を使わないので調べない
        self.assertEqual(fe.resolve_paths(1, "C:/t", "a\tb", "c\x03d")[1], [])

    def test_default_settings(self):
        paths, problems = fe.resolve_paths(1, fe.TRIAGE_DIR, fe.TRIAGE_CSV, fe.OUTPUT_DIR, documents="C:/docs")
        self.assertEqual(problems, [])
        self.assertEqual(paths["triage_csv"], os.path.join("C:/docs", "3Dギャラリー_仕分け", "triage.csv"))


class TestDocumentsDir(unittest.TestCase):
    HOME = os.path.join("C:" + os.sep, "Users", "yamada")
    FALLBACK = os.path.join(HOME, "Documents")

    def test_known_folder_used(self):
        moved = os.path.join("C:" + os.sep, "Users", "yamada", "OneDrive", "ドキュメント")
        self.assertEqual(fe.documents_dir(lambda: moved, home=self.HOME), moved)

    def test_fallback_when_getter_fails(self):
        def boom():
            raise OSError("SHGetKnownFolderPath が失敗")
        self.assertEqual(fe.documents_dir(boom, home=self.HOME), self.FALLBACK)

    def test_fallback_when_empty_or_missing(self):
        for getter in (lambda: "", lambda: None, lambda: "   ", None):
            self.assertEqual(fe.documents_dir(getter, home=self.HOME), self.FALLBACK)

    @unittest.skipUnless(os.name == "nt", "Windows のみ")
    def test_real_known_folder(self):
        # このPCで実際に取れるか（取れたパスはフォルダとして在る）
        path = fe._known_documents_folder()
        self.assertTrue(os.path.isdir(path), path)
        self.assertEqual(fe.documents_dir(), path)


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

    def test_new_and_partial(self):
        self.assertEqual(fe.folder_state(os.path.join(self.tmp, "none"), "urn:x", "P/x"), "new")
        self.assertEqual(fe.folder_state(self._make("a"), "urn:x", "P/x"), "partial")

    def test_fusion_id_match_is_done(self):
        folder = self._make("b", fe.build_meta("urn:x"))
        self.assertEqual(fe.folder_state(folder, "urn:x", "P/x"), "done")
        self.assertEqual(fe.folder_state(folder, " urn:x ", ""), "done")

    def test_fusion_id_differs_is_conflict(self):
        # fusion_id が違えば、Fusion元の行が一致していても別の作品
        folder = self._make("c", {"note": ["Fusion元: P/x"], "fusion_id": "urn:other"})
        self.assertEqual(fe.folder_state(folder, "urn:x", "P/x"), "conflict")

    def test_no_fusion_id_is_skipped(self):
        # fusion_id が無い（手で消した・手作りの同名フォルダ）→ 念のため済み扱い
        self.assertEqual(fe.folder_state(self._make("d", {"author": "a", "note": ["手で作った"]}), "urn:x", "P/x"),
                         "done_no_id")
        self.assertEqual(fe.folder_state(self._make("e", {"fusion_id": "  ", "note": []}), "urn:x", "P/x"),
                         "done_no_id")
        self.assertEqual(fe.folder_state(self._make("e2", {"fusion_id": 123}), "urn:x", "P/x"), "done_no_id")

    def test_legacy_source_line(self):
        # 旧版の出力（fusion_id なし・note に「Fusion元」行）は、その行で照合する
        self.assertEqual(fe.folder_state(self._make("f", {"note": "Fusion元: P/x"}), "urn:x", "P/x"), "done")

    def test_legacy_source_line_differs_is_skipped(self):
        # C8: 旧版の行が違っても、fusion_id が無いので同じ作品か言い切れない（Fusion で名前や場所を変えただけかも）。
        # 重複して書き出すより飛ばす（done_no_id と同じ扱い）
        self.assertEqual(fe.folder_state(self._make("g", {"note": ["Fusion元: P/y"]}), "urn:x", "P/x"), "done_no_id")

    def test_legacy_with_bom_and_edited_note(self):
        folder = self._make("h")
        with open(os.path.join(folder, "meta.json"), "w", encoding="utf-8-sig") as f:
            json.dump({"author": "山田", "note": ["追記", " Fusion元: P/x "]}, f, ensure_ascii=False)
        self.assertEqual(fe.folder_state(folder, "urn:x", "P/x"), "done")

    def test_unreadable_is_conflict(self):
        self.assertEqual(fe.folder_state(self._make("i", raw="{壊れた"), "urn:x", "P/x"), "conflict")
        self.assertEqual(fe.folder_state(self._make("j", raw="[]"), "urn:x", "P/x"), "conflict")

    def test_resolve(self):
        self._make("20250612_x", {"fusion_id": "urn:hand"})
        self._make("20250612_x-v2", {"fusion_id": "urn:別"})
        reserved = {"20250612_x", "20250612_x-v3"}  # -v3 は他の行が使う
        self.assertEqual(fe.resolve_output_folder(self.tmp, "20250612_x", "urn:x", "P/x", reserved),
                         ("20250612_x-v4", "new", ["20250612_x", "20250612_x-v2"]))
        self.assertIn("20250612_x-v4", reserved)

    def _mark(self, name, fusion_id):
        folder = self._make(name)
        fe.write_marker(folder, fusion_id)
        return folder

    def test_marker_decides_partial(self):
        # S1: 途中のフォルダは目印 fusion_id.tmp で持ち主を見分ける
        self.assertEqual(fe.folder_state(self._mark("m1", "urn:x"), "urn:x", "P/x"), "partial")
        self.assertEqual(fe.folder_state(self._mark("m2", "urn:other"), "urn:x", "P/x"), "conflict")
        self.assertEqual(fe.folder_state(self._make("m3"), "urn:x", "P/x"), "partial")  # 目印なし（n==1 なら従来どおり）

    def test_marker_ignored_when_meta_exists(self):
        # 完了後に目印が消せずに残っていても、判定は meta.json で行う
        folder = self._mark("m4", "urn:other")
        fe.write_meta_json(folder, fe.build_meta("urn:x"))
        self.assertEqual(fe.folder_state(folder, "urn:x", "P/x"), "done")

    def test_resolve_skips_others_partial(self):
        # S1 の筋書き: X は別の作品、X-v2 は他の作品（B）が途中で止まったもの、X-v3 は自分（A）の完了済み
        self._make("20250612_x", {"fusion_id": "urn:hand"})
        self._mark("20250612_x-v2", "urn:b")
        self._make("20250612_x-v3", fe.build_meta("urn:a"))
        self.assertEqual(fe.resolve_output_folder(self.tmp, "20250612_x", "urn:a", "P/a", {"20250612_x"})[:2],
                         ("20250612_x-v3", "done"))

    def test_resolve_unmarked_partial_after_v1_is_conflict(self):
        # 目印の無い途中のフォルダは、n>1 なら誰のものか分からないので避ける。n==1 は従来どおり自分のもの
        self._make("20250612_x", {"fusion_id": "urn:hand"})
        self._make("20250612_x-v2")
        self.assertEqual(fe.resolve_output_folder(self.tmp, "20250612_x", "urn:a", "P/a", set()),
                         ("20250612_x-v3", "new", ["20250612_x", "20250612_x-v2"]))
        self._make("20250612_y")
        self.assertEqual(fe.resolve_output_folder(self.tmp, "20250612_y", "urn:a", "P/a", set()),
                         ("20250612_y", "partial", []))

    def test_resolve_own_marked_partial(self):
        self._make("20250612_x", {"fusion_id": "urn:hand"})
        self._mark("20250612_x-v2", "urn:a")
        self.assertEqual(fe.resolve_output_folder(self.tmp, "20250612_x", "urn:a", "P/a", set())[:2],
                         ("20250612_x-v2", "partial"))

    def test_resolve_prefers_done_over_earlier_free_name(self):
        # 先に空き（-v2 が消された）があっても、後ろに自分の完了済み（-v3）があればそれを選ぶ（重複して書き出さない）
        self._make("20250612_x", {"fusion_id": "urn:hand"})
        self._make("20250612_X-V3", fe.build_meta("urn:a"))  # 大文字小文字の違いも同じ名前として扱う
        name, state, _avoided = fe.resolve_output_folder(self.tmp, "20250612_x", "urn:a", "P/a", {"20250612_x"})
        self.assertEqual((name.lower(), state), ("20250612_x-v3", "done"))

    def test_resolve_done_wins_even_if_reserved(self):
        # fusion_id が一致するフォルダは確かに自分のもの。他の行の名前と重なっていても、そこを済みとする
        self._make("20250612_x", {"fusion_id": "urn:hand"})
        self._make("20250612_x-v2", fe.build_meta("urn:a"))
        self.assertEqual(fe.resolve_output_folder(self.tmp, "20250612_x", "urn:a", "P/a",
                                                  {"20250612_x", "20250612_x-v2"})[:2],
                         ("20250612_x-v2", "done"))

    def test_marker_write_and_remove(self):
        folder = self._make("m5")
        fe.write_marker(folder, " urn:x ")
        self.assertEqual(fe.read_marker(folder), "urn:x")
        self.assertTrue(fe.FUSION_MARKER_FILENAME.endswith(".tmp"))  # 同期が無視する名前
        fe.remove_marker(folder)
        self.assertIsNone(fe.read_marker(folder))
        fe.remove_marker(folder)  # 無くてもエラーにしない
        self.assertIsNone(fe.read_marker(os.path.join(self.tmp, "無い")))

    def test_resolve_finds_own_v2(self):
        self._make("20250612_x", {"fusion_id": "urn:other"})
        self._make("20250612_x-v2", fe.build_meta("urn:x"))
        self.assertEqual(fe.resolve_output_folder(self.tmp, "20250612_x", "urn:x", "P/x", set()),
                         ("20250612_x-v2", "done", ["20250612_x"]))

    def test_resolve_no_id_stops_there(self):
        self._make("20250612_x", {"author": "手作り"})
        self.assertEqual(fe.resolve_output_folder(self.tmp, "20250612_x", "urn:x", "P/x", set()),
                         ("20250612_x", "done_no_id", []))

    def test_resolve_plain(self):
        self.assertEqual(fe.resolve_output_folder(self.tmp, "20250612_y", "urn:y", "P/y", set()),
                         ("20250612_y", "new", []))


class TestSettingPath(unittest.TestCase):
    def test_check(self):
        ok = os.path.join("G:" + os.sep, "共有ドライブ", "研究室", "3Dギャラリー", "items")
        self.assertEqual(fe.check_setting_path(ok, "OUTPUT_DIR"), "")
        self.assertIn("書き換え", fe.check_setting_path(fe.OUTPUT_DIR, "OUTPUT_DIR"))  # 既定値のままは止める
        self.assertIn("設定されていません", fe.check_setting_path("", "OUTPUT_DIR"))

    def test_defaults(self):
        # Googleドライブ上でなければならないのはモード2の OUTPUT_DIR だけ。モード1は「ドキュメント」の中
        self.assertIn("共有ドライブ", fe.OUTPUT_DIR)
        self.assertNotIn("マイドライブ", fe.OUTPUT_DIR)
        self.assertEqual(fe.TRIAGE_DIR, "")  # 空＝ドキュメント\3Dギャラリー_仕分け（resolve_paths が決める）
        self.assertEqual(fe.TRIAGE_CSV, "")
        self.assertEqual(fe.TARGET_NAMES, [])

    def test_settings_order(self):
        # 設定欄の並び: 共通 → モード1だけ → モード2だけ → 細かい設定
        with open(SCRIPT, encoding="utf-8") as f:
            text = f.read()
        settings = text[:text.index("# ここから下は処理本体")]
        names = ["MODE =", "PROJECT_NAMES =", "TARGET_NAMES =", "TRIAGE_DIR =", "TRIAGE_CSV =", "OUTPUT_DIR =",
                 "DEFAULT_AUTHOR =", "DEFAULT_STATUS =", "DEFAULT_TAGS =", "STL_PER_BODY =", "MESH_QUALITY =",
                 "THUMB_WIDTH =", "THUMB_HEIGHT ="]
        positions = [settings.index("\n" + n) for n in names]
        self.assertEqual(positions, sorted(positions))

    def test_path_settings_are_raw_strings(self):
        # パスの設定は最初から r"..." にしておく（r の付け忘れで \ が化けるのを防ぐ）
        with open(SCRIPT, encoding="utf-8") as f:
            text = f.read()
        for name in ["TRIAGE_DIR", "TRIAGE_CSV", "OUTPUT_DIR"]:
            self.assertRegex(text, r'\n' + name + r' = r"')


class TestSelectProjects(unittest.TestCase):
    def test_empty_means_all(self):
        self.assertEqual(fe.select_projects(["a", "b"], []), (["a", "b"], []))

    def test_filter_and_missing(self):
        self.assertEqual(fe.select_projects(["a", "b", "c"], ["c", "a", "zz"]), (["a", "c"], ["zz"]))

    def test_single_string(self):
        # C1: PROJECT_NAMES = "研究室共有" と書いても1つの名前。部分一致（"研究室"）で選ばない
        self.assertEqual(fe.select_projects(["研究室", "研究室共有"], "研究室共有"), (["研究室共有"], []))
        self.assertEqual(fe.select_projects(["研究室"], "共有"), ([], ["共有"]))


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
# 外部参照の取り込み（breakLink）
# ---------------------------------------------------------------------------
class FakeRefOcc:
    """isReferencedComponent と breakLink だけを持つ配置。

    parent が参照のままだと breakLink は例外（参照先の中は書き換えられない、を真似る）。
    stubborn は常に False を返す。sticky は True を返すのに参照のまま（上限で止まるかを見る）。
    """

    def __init__(self, name, parent=None, referenced=True, stubborn=False, sticky=False):
        self.name, self.parent, self.referenced = name, parent, referenced
        self.stubborn, self.sticky, self.calls = stubborn, sticky, 0

    @property
    def isReferencedComponent(self):
        return self.referenced

    def breakLink(self):
        self.calls += 1
        if self.stubborn:
            return False
        if self.parent is not None and self.parent.referenced:
            raise RuntimeError("親が外部参照のまま")
        if not self.sticky:
            self.referenced = False
        return True


class FakeLiveRoot:
    """allOccurrences を取るたびに新しいコレクションを返す（取り込みで中身が変わるのを真似る）。"""

    def __init__(self, occs):
        self.occs, self.reads = occs, 0

    @property
    def allOccurrences(self):
        self.reads += 1
        return FakeCollection(self.occs)


class TestBreakLinks(unittest.TestCase):
    def test_nested_needs_second_round(self):
        parent = FakeRefOcc("親:1")
        child = FakeRefOcc("子:1", parent=parent)
        local = FakeRefOcc("ローカル:1", referenced=False)
        root = FakeLiveRoot([child, local, parent])  # 子が先に来ても、次の周で取り込める
        self.assertEqual(fe.break_external_links(root), (2, []))
        self.assertEqual(local.calls, 0)  # 参照でない配置には触らない
        self.assertGreaterEqual(root.reads, 3)  # 周ごとに見直している

    def test_failed_are_reported(self):
        ok, stub = FakeRefOcc("ok:1"), FakeRefOcc("だめ:1", stubborn=True)
        self.assertEqual(fe.break_external_links(FakeLiveRoot([stub, ok])), (1, ["だめ:1"]))
        self.assertEqual(stub.calls, 2)  # 進みがある間は試し直し、進まなくなったら止まる

    def test_round_limit(self):
        sticky = FakeRefOcc("いつまでも:1", sticky=True)
        self.assertEqual(fe.break_external_links(FakeLiveRoot([sticky]), max_rounds=3), (3, ["いつまでも:1"]))
        self.assertEqual(sticky.calls, 3)

    def test_nothing_to_break(self):
        self.assertEqual(fe.break_external_links(FakeLiveRoot([FakeRefOcc("a", referenced=False)])), (0, []))
        self.assertEqual(fe.break_external_links(FakeLiveRoot([])), (0, []))


class TestExternalRefOutcome(unittest.TestCase):
    def test_no_refs(self):
        self.assertEqual(fe.external_ref_outcome([], True, 0, []), (False, ""))

    def test_broken_all(self):
        self.assertEqual(fe.external_ref_outcome(["部品:1"], True, 3, []),
                         (False, "外部参照 3 件を取り込んで f3d を書き出し"))

    def test_some_failed(self):
        check, note = fe.external_ref_outcome(["部品:1"], True, 1, ["だめ:1"])
        self.assertTrue(check)
        self.assertIn("外部参照 1 件を取り込んで f3d を書き出し", note)
        self.assertIn("だめ:1", note)

    def test_nothing_breakable(self):
        check, note = fe.external_ref_outcome(["参照ドキュメント 1 件"], True, 0, [])
        self.assertTrue(check)
        self.assertIn("参照ドキュメント 1 件", note)

    def test_not_opened_by_us(self):
        check, note = fe.external_ref_outcome(["部品:1"], False, 0, [])
        self.assertTrue(check)
        self.assertIn("取り込まず", note)


class TestExportItemOrder(TmpDirCase):
    """export_item の順番: STEP/STL/3MF/サムネイルを出してから取り込み、最後に f3d。"""

    def setUp(self):
        super().setUp()
        names = ("export_step", "export_stl", "export_3mf", "save_thumbnail", "export_f3d")
        self.saved = {k: getattr(fe, k) for k in names}
        self.calls = []
        fe.export_step = lambda d, p: self.calls.append("STEP")
        fe.export_stl = lambda d, g, p: self.calls.append("STL")
        fe.export_3mf = lambda d, g, p: self.calls.append("3MF")
        fe.save_thumbnail = lambda a, p: self.calls.append("thumb")
        fe.export_f3d = lambda d, p: self.calls.append("f3d")
        self.design = types.SimpleNamespace(rootComponent=FakeRoot([FakeBody("b")], []))

    def tearDown(self):
        for k, v in self.saved.items():
            setattr(fe, k, v)
        super().tearDown()

    def test_order(self):
        fe.export_item(None, self.design, self.tmp, "x", before_f3d=lambda: self.calls.append("break"))
        self.assertEqual(self.calls, ["STEP", "STL", "3MF", "thumb", "break", "f3d"])

    def test_without_break(self):
        fe.export_item(None, self.design, self.tmp, "x")
        self.assertEqual(self.calls, ["STEP", "STL", "3MF", "thumb", "f3d"])

    def test_break_error_still_exports_f3d_but_fails(self):
        def boom():
            raise RuntimeError("壊れた")
        with self.assertRaises(RuntimeError) as cm:
            fe.export_item(None, self.design, self.tmp, "x", before_f3d=boom)
        self.assertIn("外部参照の取り込み", str(cm.exception))
        self.assertEqual(self.calls[-1], "f3d")


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


class Mode2Case(TmpDirCase):
    """モード2の流れを試す土台。Fusion 部分を差し替える。fail_ids の datafile_id は書き出しに失敗する。"""

    def setUp(self):
        super().setUp()
        self.out = os.path.join(self.tmp, "items")
        self.csv = os.path.join(self.tmp, "triage.csv")
        os.makedirs(self.out)
        self.saved = {k: getattr(fe, k) for k in
                      ("OUTPUT_DIR", "TRIAGE_CSV", "TARGET_NAMES", "FileFinder", "open_document", "close_document",
                       "get_design", "export_item", "find_external_references", "break_external_links")}
        fe.OUTPUT_DIR, fe.TRIAGE_CSV, fe.TARGET_NAMES = self.out, self.csv, []
        self.opened, self.closed, self.broken = [], [], []
        self.fail_ids = {"urn:fail"}
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

        def export_item(app, design, folder, name, before_f3d=None):
            # 書き出しの最中には、作品フォルダに自分の目印がある
            test.assertEqual(fe.read_marker(folder), design.id)
            if design.id in test.fail_ids:
                raise RuntimeError("STL: 書き出し失敗")
            if before_f3d:
                before_f3d()
            open(os.path.join(folder, name + ".f3d"), "w").close()
            return []

        def break_external_links(root):
            test.broken.append(root)
            return {"urn:ref": (2, []), "urn:reffail": (1, ["だめ:1"])}[root]

        fe.FileFinder = Finder
        fe.open_document = open_document
        fe.close_document = lambda doc, ours: doc is not None and test.closed.append(doc.id)
        fe.get_design = lambda doc: types.SimpleNamespace(id=doc.id, rootComponent=doc.id)
        fe.export_item = export_item
        fe.find_external_references = (lambda d, doc, df: ["部品A"] if df.id in ("urn:ref", "urn:reffail", "urn:open")
                                       else [])
        fe.break_external_links = break_external_links

    def tearDown(self):
        for k, v in self.saved.items():
            setattr(fe, k, v)
        super().tearDown()

    def _log_rows(self):
        path = os.path.join(self.out, "export_log.csv")
        if not os.path.isfile(path):
            return []
        with open(path, encoding="utf-8-sig") as f:
            return list(csv.DictReader(f))

    def _log(self):
        return {(r["name"], r["result"]): r for r in self._log_rows()}

    def _meta(self, folder):
        with open(os.path.join(self.out, folder, "meta.json"), encoding="utf-8") as f:
            return json.load(f)


class TestMode2Flow(Mode2Case):
    def setUp(self):
        super().setUp()
        fe.write_triage_csv(self.csv, [
            _row(name="済み", rank="A", datafile_id="urn:done"),
            _row(name="旧版", rank="A", datafile_id="urn:legacy"),
            _row(name="旧版別", rank="A", datafile_id="urn:legacy2"),
            _row(name="IDなし", rank="A", datafile_id="urn:noid"),
            _row(name="途中", rank="B", datafile_id="urn:partial"),
            _row(name="失敗", rank="A", datafile_id="urn:fail"),
            _row(name="外部参照", rank="A", datafile_id="urn:ref"),
            _row(name="参照失敗", rank="A", datafile_id="urn:reffail"),
            _row(name="無い", rank="A", datafile_id="urn:missing"),
            _row(name="手作り", rank="A", datafile_id="urn:hand"),
            _row(name="開いていた", rank="A", datafile_id="urn:open"),
            _row(name="ID空", rank="A", datafile_id=""),
            _row(name="対象外", rank="C", datafile_id="urn:c"),
        ])
        self.metas = {
            # このスクリプトで書き出し済み（fusion_id が一致）。人が記入した内容は上書きしない
            "20250612_済み": {"author": "手で記入済み", "note": ["メモ"], "fusion_id": "urn:done"},
            # 旧版の出力（fusion_id なし、note に Fusion元）
            "20250612_旧版": {"author": "", "note": ["Fusion元: P/旧版"]},
            # 旧版の出力だが「Fusion元」の場所が違う（Fusion で名前や場所を変えたのかもしれない）→ 念のため飛ばす（C8）
            "20250612_旧版別": {"author": "", "note": ["Fusion元: P/前の名前"]},
            # fusion_id も Fusion元 も無い（手で消した・手作り）→ 念のため飛ばす
            "20250612_IDなし": {"author": "誰か", "note": "手で作った"},
            # 同名だが別の作品。触らずに -v2 へ書き出すはず
            "20250612_手作り": {"author": "誰か", "fusion_id": "urn:someone-else"},
        }
        for name, meta in self.metas.items():
            os.makedirs(os.path.join(self.out, name), exist_ok=True)
            fe.write_meta_json(os.path.join(self.out, name), meta)
        os.makedirs(os.path.join(self.out, "20250612_途中"))  # meta.json 無し＝途中で止まった（目印なし。旧版の途中）

    def test_flow(self):
        ui = FakeUI()
        fe.run_mode2(object(), ui)

        # 済み（fusion_id 一致・旧版の Fusion元 一致・fusion_id なし・旧版の Fusion元 不一致）は開かない。
        # C ランクと ID 空は対象外
        expected = ["urn:partial", "urn:fail", "urn:ref", "urn:reffail", "urn:hand", "urn:open"]
        self.assertEqual(self.opened, expected)
        # 開いたものは失敗しても close_document を通る（自分で開いたかの判断は close_document 側）
        self.assertEqual(self.closed, expected)
        # 取り込みは自分で開いたドキュメントで、外部参照があるときだけ（元々開いていたものはしない）
        self.assertEqual(self.broken, ["urn:ref", "urn:reffail"])
        # 既存の meta.json は上書きしない
        for name, meta in self.metas.items():
            self.assertEqual(self._meta(name), meta)
        # 別の作品の同名フォルダには触らず、-v2 に書く
        self.assertEqual(os.listdir(os.path.join(self.out, "20250612_手作り")), ["meta.json"])
        self.assertEqual(self._meta("20250612_手作り-v2")["fusion_id"], "urn:hand")
        # 途中のものはやり直して meta.json を書く。note は空、fusion_id に datafile_id
        meta = self._meta("20250612_途中")
        self.assertEqual((meta["note"], meta["fusion_id"]), ([], "urn:partial"))
        # 失敗したものは meta.json を書かない（次回やり直す）
        self.assertFalse(fe.is_done(os.path.join(self.out, "20250612_失敗")))
        self.assertTrue(fe.is_done(os.path.join(self.out, "20250612_外部参照")))
        self.assertTrue(fe.is_done(os.path.join(self.out, "20250612_参照失敗")))
        self.assertFalse(os.path.exists(os.path.join(self.out, "20250612_ID空")))
        # 目印 fusion_id.tmp: 完了したら消え、失敗したら残る（次回、自分の途中のフォルダと分かる）
        self.assertIsNone(fe.read_marker(os.path.join(self.out, "20250612_途中")))
        self.assertIsNone(fe.read_marker(os.path.join(self.out, "20250612_手作り-v2")))
        self.assertEqual(fe.read_marker(os.path.join(self.out, "20250612_失敗")), "urn:fail")

        log = self._log()
        self.assertIn("同じ作品", log[("20250612_済み（済み）", "スキップ")]["detail"])
        self.assertIn(("20250612_旧版（旧版）", "スキップ"), log)
        no_id = log[("20250612_IDなし（IDなし）", "スキップ")]["detail"]
        self.assertIn("fusion_id が無いため念のためスキップ", no_id)
        self.assertIn("同じ作品なら fusion_id を戻すかフォルダを消してから再実行", no_id)
        self.assertIn("別の作品なら triage.csv の folder_name を変える", no_id)
        self.assertIn("fusion_id が無いため念のためスキップ", log[("20250612_旧版別（旧版別）", "スキップ")]["detail"])
        self.assertIn("取得: datafile_id", log[("20250612_途中（途中）", "成功")]["detail"])
        fail = log[("20250612_失敗（失敗）", "失敗")]["detail"]
        self.assertIn("取得: datafile_id", fail)
        self.assertIn("STL", fail)
        self.assertIn("外部参照 2 件を取り込んで f3d を書き出し", log[("20250612_外部参照（外部参照）", "成功")]["detail"])
        self.assertIn("だめ:1", log[("20250612_参照失敗（参照失敗）", "成功（要目視確認）")]["detail"])
        self.assertIn(("20250612_無い（無い）", "失敗"), log)
        self.assertIn("20250612_手作り", log[("20250612_手作り-v2（手作り）", "注意")]["detail"])
        self.assertIn(("20250612_手作り-v2（手作り）", "成功"), log)
        opened = log[("20250612_開いていた（開いていた）", "成功（要目視確認）")]["detail"]
        self.assertIn("未保存の変更", opened)
        self.assertIn("取り込まず", opened)
        self.assertNotIn("未保存", log[("20250612_途中（途中）", "成功")]["detail"])
        self.assertIn("「ID空」は datafile_id が空", log[("", "注意")]["detail"])

        summary = ui.messages[-1]
        for s in ("成功: 3 件", "要目視確認・外部参照）: 2 件", "失敗: 2 件", "スキップ（書き出し済み）: 2 件",
                  "スキップ（fusion_id なし・未確認）: 2 件", "注意: 1 件"):
            self.assertIn(s, summary)

        # 再実行: 失敗・見つからないものだけやり直す。-v2 に書いたものは -v2 で済みと判定される
        self.opened.clear()
        before = len(self._log_rows())
        fe.run_mode2(object(), FakeUI())
        self.assertEqual(self.opened, ["urn:fail"])
        # C3: 済みのときは「同名のフォルダが別の作品のため…」の注意を出さない
        added = self._log_rows()[before:]
        self.assertIn(("20250612_手作り-v2（手作り）", "スキップ"), [(r["name"], r["result"]) for r in added])
        self.assertEqual([r for r in added if r["result"] == "注意" and "手作り" in r["name"]], [])

    def test_no_ab_rows(self):
        fe.write_triage_csv(self.csv, [_row(rank="C")])
        ui = FakeUI()
        fe.run_mode2(object(), ui)
        self.assertIn("A か B", ui.messages[-1])
        self.assertEqual(self.opened, [])

    def test_target_names_ignore_rank(self):
        # 名前を指定したら rank を問わずその行だけ書き出す。見つからない名前はメッセージとログに出る
        fe.TARGET_NAMES = [" 対象外 ", "存在しない"]
        ui = FakeUI()
        fe.run_mode2(object(), ui)
        self.assertEqual(self.opened, ["urn:c"])
        self.assertIn("存在しない", ui.messages[-1])
        self.assertIn(("存在しない", "注意"), self._log())

    def test_target_names_single_string(self):
        # C1: 文字列1つで書いても、その名前1つとして扱う
        fe.TARGET_NAMES = " 対象外 "
        ui = FakeUI()
        fe.run_mode2(object(), ui)
        self.assertEqual(self.opened, ["urn:c"])
        self.assertNotIn("見つからなかった", ui.messages[-1])

    def test_target_names_duplicate_rows_warn(self):
        # C2: 指定した名前の行が triage.csv に複数（別プロジェクトの同名ファイルなど）あれば、ログに注意を出す
        fe.write_triage_csv(self.csv, [_row(project="P", name="同名", datafile_id="urn:p"),
                                       _row(project="Q", name="同名", datafile_id="urn:q"),
                                       _row(project="P", name="ほか", datafile_id="urn:r")])
        fe.TARGET_NAMES = ["同名", "ほか"]
        fe.run_mode2(object(), FakeUI())
        self.assertEqual(self.opened, ["urn:p", "urn:q", "urn:r"])  # 同名の2行は両方書き出す（-v2 に分かれる）
        self.assertEqual(self._meta("20250612_同名-v2")["fusion_id"], "urn:q")
        notes = [r["detail"] for r in self._log_rows() if r["result"] == "注意"]
        self.assertTrue(any("「同名」" in d and "2 行" in d for d in notes), notes)
        self.assertFalse(any("「ほか」" in d for d in notes))

    def test_target_names_none_found(self):
        fe.TARGET_NAMES = ["存在しない"]
        ui = FakeUI()
        fe.run_mode2(object(), ui)
        self.assertEqual(self.opened, [])
        self.assertIn("TARGET_NAMES に合う行がありません", ui.messages[-1])
        self.assertIn("存在しない", ui.messages[-1])

    def test_triage_csv_defaults_to_triage_dir(self):
        saved = fe.TRIAGE_DIR
        self.addCleanup(setattr, fe, "TRIAGE_DIR", saved)
        fe.TRIAGE_DIR, fe.TRIAGE_CSV = self.tmp, ""  # self.tmp/triage.csv を読む
        fe.run_mode2(object(), FakeUI())
        self.assertIn("urn:partial", self.opened)

    def test_missing_triage_csv(self):
        fe.TRIAGE_CSV = os.path.join(self.tmp, "無い.csv")
        with self.assertRaises(ValueError) as cm:
            fe.run_mode2(object(), FakeUI())
        self.assertIn("見つかりません", str(cm.exception))

    def test_placeholder_output_dir_stops(self):
        fe.OUTPUT_DIR = self.saved["OUTPUT_DIR"]
        with self.assertRaises(ValueError) as cm:
            fe.run_mode2(object(), FakeUI())
        self.assertIn("OUTPUT_DIR", str(cm.exception))


class TestMode2Renumber(Mode2Case):
    """S1: -v2 の空き名探しで、他の作品の途中のフォルダを取らない。再実行で番号が変わらない。"""

    X = "20250612_X"

    def setUp(self):
        super().setUp()
        os.makedirs(os.path.join(self.out, self.X))
        fe.write_meta_json(os.path.join(self.out, self.X), {"author": "誰か", "fusion_id": "urn:hand"})  # 別の作品
        # A と B は folder_name が同じ。CSV 内の重複処理で B が X-v2 になる
        fe.write_triage_csv(self.csv, [_row(name="A", rank="A", datafile_id="urn:a", folder_name=self.X),
                                       _row(name="B", rank="A", datafile_id="urn:b", folder_name=self.X)])
        self.fail_ids = {"urn:b"}

    def _folders(self):
        return sorted(n for n in os.listdir(self.out) if os.path.isdir(os.path.join(self.out, n)))

    def test_scenario(self):
        # 1回目: A は X（別の作品）と X-v2（B の予約）を避けて X-v3 で完了。B は X-v2 で失敗（途中）
        fe.run_mode2(object(), FakeUI())
        self.assertEqual(self._meta(self.X + "-v3")["fusion_id"], "urn:a")
        self.assertFalse(fe.is_done(os.path.join(self.out, self.X + "-v2")))
        self.assertEqual(fe.read_marker(os.path.join(self.out, self.X + "-v2")), "urn:b")
        folders = self._folders()

        # 2回目: A だけ指定。X-v2 は B の途中なので取らず、X-v3 で済みと判定する（開かない・注意も出さない）
        fe.TARGET_NAMES = ["A"]
        self.opened.clear()
        before = len(self._log_rows())
        fe.run_mode2(object(), FakeUI())
        self.assertEqual(self.opened, [])
        self.assertEqual(self._folders(), folders)
        self.assertFalse(fe.is_done(os.path.join(self.out, self.X + "-v2")))
        added = [(r["name"], r["result"]) for r in self._log_rows()[before:]]
        self.assertEqual(added, [(self.X + "-v3（A）", "スキップ")])

        # 3回目: 全部。B が直って X-v2 で完了する。番号は1回目と同じ
        fe.TARGET_NAMES = []
        self.fail_ids = set()
        self.opened.clear()
        fe.run_mode2(object(), FakeUI())
        self.assertEqual(self.opened, ["urn:b"])
        self.assertEqual(self._folders(), folders)
        self.assertEqual(self._meta(self.X + "-v2")["fusion_id"], "urn:b")
        self.assertEqual(self._meta(self.X + "-v3")["fusion_id"], "urn:a")

        # 4回目: B だけ指定しても、B は X-v2（CSV 内の番号）で済み
        fe.TARGET_NAMES = ["B"]
        self.opened.clear()
        fe.run_mode2(object(), FakeUI())
        self.assertEqual(self.opened, [])
        self.assertEqual(self._folders(), folders)

    def test_target_only_b_after_failure(self):
        # B だけ指定すると B の行の folder_name は X（CSV 内の重複が無い）。X は別の作品、X-v2 は B 自身の途中 → X-v2 でやり直す
        fe.run_mode2(object(), FakeUI())
        fe.TARGET_NAMES = ["B"]
        self.fail_ids = set()
        self.opened.clear()
        fe.run_mode2(object(), FakeUI())
        self.assertEqual(self.opened, ["urn:b"])
        self.assertEqual(self._meta(self.X + "-v2")["fusion_id"], "urn:b")
        self.assertEqual(self._meta(self.X + "-v3")["fusion_id"], "urn:a")


# ---------------------------------------------------------------------------
# モード1の流れ（Fusion 部分は差し替え）。既存の triage.csv との合わせ方と TARGET_NAMES を確かめる
# ---------------------------------------------------------------------------
class FakeDF:
    def __init__(self, name, fid, epoch=1749700800):
        self.name, self.id, self.versionId = name, fid, fid + "?version=1"
        self.dateModified, self._epoch = epoch, epoch


class TestMode1Flow(TmpDirCase):
    def setUp(self):
        super().setUp()
        self.files = [FakeDF("治具", "urn:a"), FakeDF("ステージ", "urn:b"), FakeDF("新作", "urn:new")]
        self.saved = {k: getattr(fe, k) for k in
                      ("TRIAGE_DIR", "OUTPUT_DIR", "TARGET_NAMES", "list_target_projects", "walk_f3d_files",
                       "first_created_epoch", "open_document", "close_document", "get_design", "save_thumbnail")}
        fe.TRIAGE_DIR, fe.TARGET_NAMES = self.tmp, []
        fe.OUTPUT_DIR = ""  # モード1は OUTPUT_DIR が未設定でも動く
        self.shot = []
        test = self
        fe.list_target_projects = lambda app: ([types.SimpleNamespace(name="P")], [])
        fe.walk_f3d_files = lambda p, on_progress=None: [(df, "") for df in test.files]
        fe.first_created_epoch = lambda df: df._epoch
        fe.open_document = lambda app, df: (df, True)
        fe.close_document = lambda doc, ours: None
        fe.get_design = lambda doc: doc

        def save_thumbnail(app, path):
            test.shot.append(os.path.basename(path))
            open(path, "w").close()

        fe.save_thumbnail = save_thumbnail
        self.date = datetime.datetime.fromtimestamp(1749700800).strftime("%Y%m%d")

    def tearDown(self):
        for k, v in self.saved.items():
            setattr(fe, k, v)
        super().tearDown()

    def _csv(self):
        return fe.read_triage_csv(os.path.join(self.tmp, "triage.csv"))

    def test_merge_with_existing(self):
        old = [_row(name="治具", datafile_id="urn:a", rank="A", folder_name="20240101_手で直した",
                    image="20240101_手で直した.png"),
               _row(name="消えた", datafile_id="urn:gone", rank="B", folder_name=self.date + "_新作",
                    image=self.date + "_新作.png"),
               _row(name="ステージ", datafile_id="urn:b", rank="C")]
        fe.write_triage_csv(os.path.join(self.tmp, "triage.csv"), old)
        fe.run_mode1(object(), FakeUI())
        rows = self._csv()
        self.assertEqual([(r["name"], r["rank"], r["folder_name"]) for r in rows], [
            ("治具", "A", "20240101_手で直した"),
            ("消えた", "B", self.date + "_新作"),          # 今回撮らなかった行も残る
            ("ステージ", "C", self.date + "_ステージ"),
            ("新作", "", self.date + "_新作-v2"),          # 残す行のフォルダ名と重ならない
        ])
        self.assertEqual(rows[0]["image"], "20240101_手で直した.png")  # 記入済みの名前で撮り直す
        self.assertEqual(rows[3]["image"], self.date + "_新作-v2.png")
        self.assertNotIn(self.date + "_新作.png", self.shot)       # 残す行の画像を上書きしない
        backups = [n for n in os.listdir(self.tmp) if n.startswith("triage_") and n.endswith(".csv")]
        self.assertEqual(len(backups), 1)  # 既存は退避した

    def test_target_names(self):
        fe.write_triage_csv(os.path.join(self.tmp, "triage.csv"),
                            [_row(name="治具", datafile_id="urn:a", rank="A", image="a.png")])
        fe.TARGET_NAMES = ["ステージ", "無いもの"]
        ui = FakeUI()
        fe.run_mode1(object(), ui)
        self.assertEqual(self.shot, [self.date + "_ステージ.png"])
        rows = self._csv()
        self.assertEqual([(r["name"], r["rank"], r["image"]) for r in rows],
                         [("治具", "A", "a.png"), ("ステージ", "", self.date + "_ステージ.png")])
        self.assertIn("無いもの", ui.messages[-1])
        with open(os.path.join(self.tmp, "export_log.csv"), encoding="utf-8-sig") as f:
            self.assertIn(("無いもの", "注意"), {(r["name"], r["result"]) for r in csv.DictReader(f)})

    def test_first_run(self):
        fe.run_mode1(object(), FakeUI())
        self.assertEqual([r["name"] for r in self._csv()], ["治具", "ステージ", "新作"])
        self.assertEqual([n for n in os.listdir(self.tmp) if n.startswith("triage_")], [])

    def test_unreadable_existing_csv_stops(self):
        with open(os.path.join(self.tmp, "triage.csv"), "w", encoding="utf-8") as f:
            f.write("project,name\nP,n\n")  # 必要な列が無い
        with self.assertRaises(ValueError):
            fe.run_mode1(object(), FakeUI())
        self.assertEqual(self.shot, [])

    # S3: triage.csv を Excel で開いたままにしている
    @unittest.skipUnless(os.name == "nt", "Windows のみ（Excel と同じ形でファイルを押さえる）")
    def test_locked_csv_stops_before_shooting(self):
        path = os.path.join(self.tmp, "triage.csv")
        fe.write_triage_csv(path, [_row(name="治具", datafile_id="urn:a", rank="A")])
        unlock = _lock_like_excel(path)
        try:
            ui = FakeUI()
            fe.run_mode1(object(), ui)  # 例外にせず、メッセージで止まる
        finally:
            unlock()
        self.assertEqual(self.shot, [])  # 撮影を始めない
        self.assertIn("閉じて", ui.messages[-1])
        self.assertEqual(self._csv()[0]["rank"], "A")  # 元の triage.csv はそのまま

    @unittest.skipUnless(os.name == "nt", "Windows のみ（Excel と同じ形でファイルを押さえる）")
    def test_locked_during_run_writes_new_csv(self):
        # 撮影の途中で Excel で開かれた → 最後に triage.csv を書けない。結果は triage_new_<日時>.csv に残す
        path = os.path.join(self.tmp, "triage.csv")
        fe.write_triage_csv(path, [_row(name="治具", datafile_id="urn:a", rank="A")])
        unlocks = []
        shoot = fe.save_thumbnail

        def save_thumbnail(app, p):
            shoot(app, p)
            if not unlocks:
                unlocks.append(_lock_like_excel(path))

        fe.save_thumbnail = save_thumbnail
        ui = FakeUI()
        try:
            fe.run_mode1(object(), ui)
        finally:
            for u in unlocks:
                u()
        news = [n for n in os.listdir(self.tmp) if n.startswith("triage_new_") and n.endswith(".csv")]
        self.assertEqual(len(news), 1)
        rows = fe.read_triage_csv(os.path.join(self.tmp, news[0]))
        self.assertEqual([(r["name"], r["rank"]) for r in rows], [("治具", "A"), ("ステージ", ""), ("新作", "")])
        self.assertIn(news[0], ui.messages[-1])
        self.assertIn("閉じて", ui.messages[-1])
        self.assertEqual([r["name"] for r in self._csv()], ["治具"])  # 元の triage.csv は壊れていない

    def test_check_writable(self):
        path = os.path.join(self.tmp, "triage.csv")
        self.assertTrue(fe.can_overwrite(path))  # 無ければ書ける
        fe.write_triage_csv(path, [_row()])
        self.assertTrue(fe.can_overwrite(path))
        with open(path, "rb") as f:
            self.assertEqual(f.read()[:3], codecs.BOM_UTF8)  # 確かめるだけで中身は変えない
        self.assertEqual(fe.read_triage_csv(path), [_row()])

    def test_save_triage_fallback(self):
        # 書けなかったときの退避先の名前
        p = fe.fallback_triage_path(os.path.join("d", "triage.csv"), datetime.datetime(2026, 10, 30, 9, 8, 7))
        self.assertEqual(p, os.path.join("d", "triage_new_20261030_090807.csv"))


def _lock_like_excel(path):
    """Excel が開いているときと同じく、他から書けない・消せない・名前を変えられない状態にする（読むのはできる）。

    戻り値: 押さえを外す関数。
    """
    import ctypes
    from ctypes import wintypes
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateFileW.restype = wintypes.HANDLE
    k32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                                wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    k32.CloseHandle.argtypes = [wintypes.HANDLE]
    generic_read, share_read, open_existing, normal = 0x80000000, 0x1, 3, 0x80
    handle = k32.CreateFileW(path, generic_read, share_read, None, open_existing, normal, None)
    if handle in (None, wintypes.HANDLE(-1).value):
        raise OSError(ctypes.get_last_error(), "ファイルを押さえられません: " + path)
    return lambda: k32.CloseHandle(handle)

if __name__ == "__main__":
    unittest.main()
