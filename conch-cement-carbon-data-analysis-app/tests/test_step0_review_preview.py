import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pandas as pd
from PySide6.QtWidgets import QApplication, QAbstractItemView

from core.step0_extract_report import DEFAULT_CELL_MAP
from core.pipeline import run_steps_1_to_3
from core.step0_review import review_step0_output
from ui.page_run_pipeline import RunPipelinePage
from ui.page_step0 import Step0Page
from utils.config_utils import invalidate_step0_review_if_inputs_changed, is_step0_review_approved
from utils.step0_preview import load_step0_preview


class Step0ReviewPreviewTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def _frame(self, dates):
        frame = pd.DataFrame({"日期": pd.to_datetime(dates)})
        for index, column in enumerate(DEFAULT_CELL_MAP, start=1):
            frame[column] = np.nan if column == "本日库存" else index
        return frame

    def _write(self, frame, name="result.xlsx"):
        path = self.root / name
        frame.to_excel(path, index=False)
        return path

    def _review(self, path, start="2026-05-01", end="2026-05-31"):
        return review_step0_output(
            str(path),
            target_month="2026-05",
            process_start_date=start,
            process_end_date=end,
        )

    def test_case_a_inventory_only_empty_is_passed_with_info(self):
        path = self._write(self._frame(pd.date_range("2026-05-01", "2026-05-31")))
        result = self._review(path)
        self.assertTrue(result["success"])
        self.assertEqual(result["status"], "passed")
        self.assertTrue(any("本日库存" in message for message in result["review_info"]))

    def test_case_b_missing_required_column_is_failed(self):
        frame = self._frame(pd.date_range("2026-05-01", "2026-05-31"))
        frame = frame.drop(columns=["燃煤消耗量t"])
        result = self._review(self._write(frame))
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "failed")
        self.assertIn("缺失关键字段", "\n".join(item["message"] for item in result["details"]))

    def test_case_c_wrong_month_is_failed(self):
        path = self._write(self._frame(pd.date_range("2026-04-01", "2026-04-30")))
        result = self._review(path)
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "failed")

    def test_case_d_missing_target_date_is_failed(self):
        dates = pd.date_range("2026-05-01", "2026-05-31").difference(pd.DatetimeIndex(["2026-05-15"]))
        result = self._review(self._write(self._frame(dates)))
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "failed")
        self.assertIn("2026-05-15", "\n".join(item["message"] for item in result["details"]))

    def test_preview_loads_all_rows_and_preserves_empty_inventory(self):
        path = self._write(self._frame(pd.date_range("2026-05-01", "2026-05-31")))
        preview = load_step0_preview(str(path))
        self.assertEqual(preview["rows"], 31)
        self.assertEqual(preview["columns"], 10)
        self.assertEqual(preview["start_date"], "2026-05-01")
        self.assertEqual(preview["end_date"], "2026-05-31")
        self.assertIn("本日库存", preview["empty_columns"])
        self.assertTrue(preview["dataframe"]["本日库存"].isna().all())

    def test_page_initializes_read_only_preview_and_clears_on_month_change(self):
        month_dir = self.root / "1.原始数据" / "(3)低频数据" / "202605"
        month_dir.mkdir(parents=True)
        self._frame(pd.date_range("2026-05-01", "2026-05-31")).to_excel(
            month_dir / "生产日报提取结果.xlsx", index=False
        )
        config = {
            "data_root": str(self.root),
            "target_month": "2026-05",
            "process_start_date": "2026-05-01",
            "process_end_date": "2026-05-31",
            "report_file": "",
            "step0_needs_rerun": False,
        }
        with patch("ui.page_step0.load_config", return_value=config):
            page = Step0Page()
        self.assertEqual(page.preview_model.rowCount(), 31)
        self.assertEqual(page.preview_table.editTriggers(), QAbstractItemView.NoEditTriggers)
        self.assertIn("自动检查：通过", page.preview_review_label.text())
        self.assertIn("人工审核：待审核", page.preview_review_label.text())

        page.config = dict(config, target_month="2026-06", process_start_date="2026-06-01", process_end_date="2026-06-30")
        page.refresh_preview()
        self.assertEqual(page.preview_model.rowCount(), 0)
        self.assertIn("尚未生成", page.preview_message_label.text())
        page.close()

    def test_partial_date_preview_contains_only_file_rows(self):
        path = self._write(self._frame(pd.date_range("2026-05-10", "2026-05-20")))
        preview = load_step0_preview(str(path))
        self.assertEqual(preview["rows"], 11)
        self.assertEqual(preview["start_date"], "2026-05-10")
        self.assertEqual(preview["end_date"], "2026-05-20")

    def test_successful_extract_result_triggers_preview_refresh(self):
        month_dir = self.root / "1.原始数据" / "(3)低频数据" / "202605"
        month_dir.mkdir(parents=True)
        output_file = month_dir / "生产日报提取结果.xlsx"
        self._frame(pd.date_range("2026-05-01", "2026-05-31")).to_excel(output_file, index=False)
        report_file = self.root / "生产综合日报.xls"
        report_file.touch()
        config = {
            "data_root": str(self.root),
            "target_month": "2026-05",
            "process_start_date": "2026-05-01",
            "process_end_date": "2026-05-31",
            "report_file": str(report_file),
            "step0_review_status": "approved",
            "step0_review_start_date": "2026-05-01",
            "step0_review_end_date": "2026-05-31",
            "step0_needs_rerun": False,
        }
        result = {"success": True, "message": "完成", "output_files": [str(output_file)]}
        with (
            patch("ui.page_step0.load_config", return_value=config),
            patch("ui.page_step0.save_config") as save_mock,
            patch("ui.page_step0.append_run_log"),
            patch("ui.page_step0.confirm_step_run", return_value=True),
            patch("ui.page_step0.run_step0_extract", return_value=result),
        ):
            page = Step0Page()
            page.preview_model.set_dataframe(None)
            page.run_extract()
        self.assertEqual(page.preview_model.rowCount(), 31)
        self.assertIn("0号日报提取完成", page.status_box.toPlainText())
        self.assertEqual(save_mock.call_args.args[0]["step0_review_status"], "")
        page.close()

    def test_old_passed_status_is_not_human_approval(self):
        config = {
            "step0_review_status": "passed",
            "step0_review_start_date": "2026-05-01",
            "step0_review_end_date": "2026-05-31",
            "step0_needs_rerun": False,
        }
        self.assertFalse(is_step0_review_approved(config, "2026-05-01", "2026-05-31"))

    def test_human_confirmation_is_the_only_way_page_saves_approved(self):
        month_dir = self.root / "1.原始数据" / "(3)低频数据" / "202605"
        month_dir.mkdir(parents=True)
        output_file = month_dir / "生产日报提取结果.xlsx"
        self._frame(pd.date_range("2026-05-01", "2026-05-31")).to_excel(output_file, index=False)
        config = {
            "data_root": str(self.root),
            "target_month": "2026-05",
            "process_start_date": "2026-05-01",
            "process_end_date": "2026-05-31",
            "report_file": "",
            "step0_review_status": "passed",
            "step0_review_start_date": "2026-05-01",
            "step0_review_end_date": "2026-05-31",
            "step0_needs_rerun": False,
        }
        with (
            patch("ui.page_step0.load_config", return_value=config),
            patch("ui.page_step0.save_config") as save_mock,
            patch("ui.page_step0.append_run_log"),
            patch.object(Step0Page, "_confirm_manual_approval", return_value=True),
        ):
            page = Step0Page()
            self.assertIn("人工审核：待审核", page.preview_review_label.text())
            page.approve_review()
        saved = save_mock.call_args.args[0]
        self.assertEqual(saved["step0_review_status"], "approved")
        self.assertTrue(is_step0_review_approved(saved, "2026-05-01", "2026-05-31"))
        self.assertIn("人工审核：审核通过", page.preview_review_label.text())
        page.close()

    def test_config_change_invalidates_human_approval(self):
        previous = {
            "target_month": "2026-05",
            "process_start_date": "2026-05-01",
            "process_end_date": "2026-05-31",
            "report_file": "/tmp/may.xls",
            "step0_review_status": "approved",
            "step0_review_start_date": "2026-05-01",
            "step0_review_end_date": "2026-05-31",
        }
        changes = {
            "target_month": "2026-06",
            "process_start_date": "2026-05-02",
            "process_end_date": "2026-05-30",
            "report_file": "/tmp/another-report.xls",
        }
        for key, value in changes.items():
            with self.subTest(key=key):
                current = dict(previous, **{key: value})
                updated, changed = invalidate_step0_review_if_inputs_changed(previous, current)
                self.assertIn(key, changed)
                self.assertEqual(updated["step0_review_status"], "")
                self.assertTrue(updated["step0_needs_rerun"])

    def test_pipeline_page_and_core_reject_old_automatic_passed(self):
        report_file = self.root / "report.xls"
        step0_file = self.root / "step0.xlsx"
        history_file = self.root / "history.xlsx"
        report_file.touch()
        step0_file.touch()
        history_file.touch()
        current_dir = self.root / "current"
        second_dir = self.root / "second"
        current_dir.mkdir()
        second_dir.mkdir()
        config = {
            "data_root": str(self.root),
            "target_month": "2026-05",
            "process_start_date": "2026-05-01",
            "process_end_date": "2026-05-31",
            "report_file": str(report_file),
            "step0_output_file": str(step0_file),
            "history_lowfreq_file": str(history_file),
            "lowfreq_current_path": str(current_dir),
            "second_data_dir": str(second_dir),
            "step0_review_status": "passed",
            "step0_review_start_date": "2026-05-01",
            "step0_review_end_date": "2026-05-31",
            "step0_needs_rerun": False,
        }
        ok, lines = RunPipelinePage._check_config(None, config)
        self.assertFalse(ok)
        self.assertIn("尚未完成人工审核", "\n".join(lines))
        with patch("core.pipeline.append_run_log"):
            result = run_steps_1_to_3(config)
        self.assertFalse(result["success"])
        self.assertIn("尚未完成人工审核", result["message"])

        config["step0_review_status"] = "approved"
        ok, lines = RunPipelinePage._check_config(None, config)
        self.assertTrue(ok, "\n".join(lines))


if __name__ == "__main__":
    unittest.main()
