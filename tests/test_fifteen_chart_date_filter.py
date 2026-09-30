import tempfile
import unittest
from pathlib import Path

from utils.fifteen_chart_utils import scan_15min_files


class FifteenChartDateFilterTest(unittest.TestCase):
    def test_directory_range_excludes_monthly_file_without_day(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            for name in (
                "2026-06-01_15minCO2排放结果.xlsx",
                "2026-06-30_15minCO2排放结果.xlsx",
                "2026-07-01_15minCO2排放结果.xlsx",
                "2026-07_15minCO2排放结果.xlsx",
            ):
                (root / name).touch()
            files = scan_15min_files(str(root), "2026-06-01", "2026-06-30")
            self.assertEqual(
                [path.name for path in files],
                ["2026-06-01_15minCO2排放结果.xlsx", "2026-06-30_15minCO2排放结果.xlsx"],
            )


if __name__ == "__main__":
    unittest.main()
