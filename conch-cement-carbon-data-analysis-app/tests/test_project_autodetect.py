import tempfile
import unittest
from pathlib import Path

import pandas as pd

from utils.project_autodetect import autodetect_month_config


class ProjectAutodetectTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.lowfreq_root = self.root / "1.原始数据" / "(3)低频数据"
        self.highfreq_root = self.root / "1.原始数据" / "(1)核心高频数据"
        self.lowfreq_root.mkdir(parents=True)
        self.highfreq_root.mkdir(parents=True)

    def tearDown(self):
        self.temp_dir.cleanup()

    def _write_history(self, filename, dates):
        path = self.lowfreq_root / filename
        pd.DataFrame({"日期": pd.to_datetime(dates), "值": range(len(dates))}).to_excel(path, index=False)
        return path

    def test_detects_may_inputs_and_reads_history_content(self):
        month_dir = self.lowfreq_root / "202605"
        month_dir.mkdir()
        report = month_dir / "2026年5月1-31日生产综合日报.xlsx"
        pd.DataFrame({"日报": [1]}).to_excel(report, index=False)
        exact_history = self._write_history(
            "海螺水泥低频数据_2026-04-30.xlsx",
            ["2026-04-29", "2026-04-30"],
        )
        self._write_history("海螺水泥低频数据_错误文件名.xlsx", ["2026-04-30"])
        for day in (1, 15, 31):
            (self.highfreq_root / f"2026-05-{day:02d}").mkdir()

        result = autodetect_month_config(str(self.root), "2026-05")

        self.assertEqual(result["process_start_date"], "2026-05-01")
        self.assertEqual(result["process_end_date"], "2026-05-31")
        self.assertEqual(result["report_file"], str(report.resolve()))
        self.assertEqual(result["history_lowfreq_file"], str(exact_history.resolve()))
        self.assertEqual(result["lowfreq_current_path"], str(month_dir.resolve()))
        self.assertEqual(result["second_data_dir"], str(self.highfreq_root.resolve()))
        self.assertEqual(result["step0_output_dir"], str(month_dir.resolve()))
        self.assertEqual(result["step0_output_file"], str(month_dir.resolve() / "生产日报提取结果.xlsx"))
        self.assertEqual(result["step1_output_dir"], str(self.lowfreq_root.resolve()))
        self.assertEqual(
            result["lowfreq_result_file"],
            str(self.lowfreq_root.resolve() / "海螺水泥低频数据_2026-05-31.xlsx"),
        )
        self.assertEqual(result["step2_result_dir"], str(self.root.resolve() / "2.秒级核算数据"))
        self.assertEqual(result["step2_abnormal_dir"], str(self.root.resolve() / "3.秒级异常数据统计"))
        self.assertEqual(result["step3_result_dir"], str(self.root.resolve() / "4.15min核算数据"))

    def test_multiple_best_reports_require_manual_confirmation(self):
        month_dir = self.lowfreq_root / "2026-06"
        month_dir.mkdir()
        for name in ("2026年6月生产综合日报A.xlsx", "2026年6月生产综合日报B.xls"):
            path = month_dir / name
            if path.suffix == ".xlsx":
                pd.DataFrame({"日报": [1]}).to_excel(path, index=False)
            else:
                path.touch()
        result = autodetect_month_config(str(self.root), "2026-06")
        self.assertEqual(result["report_file"], "")
        self.assertEqual(len(result["candidates"]["report_file"]), 2)
        self.assertEqual(result["statuses"]["report_file"]["status"], "warning")

    def test_month_switch_never_reuses_previous_month_directory(self):
        (self.lowfreq_root / "202605").mkdir()
        result = autodetect_month_config(str(self.root), "2026-06")
        self.assertEqual(result["lowfreq_current_path"], "")
        self.assertEqual(result["report_file"], "")
        self.assertEqual(result["process_end_date"], "2026-06-30")


if __name__ == "__main__":
    unittest.main()
