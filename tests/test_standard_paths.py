import unittest

from utils.standard_paths import derive_standard_paths, expected_result_files


class StandardPathsTest(unittest.TestCase):
    def test_derives_june_standard_paths(self):
        root = "/Users/test/清华能源实习数据分析"
        config = {
            "data_root": root,
            "target_month": "2026-06",
            "process_start_date": "2026-06-10",
            "process_end_date": "2026-06-20",
        }
        paths = derive_standard_paths(config)
        self.assertEqual(paths["step0_output_file"], f"{root}/1.原始数据/(3)低频数据/202606/生产日报提取结果.xlsx")
        self.assertEqual(paths["lowfreq_result_file"], f"{root}/1.原始数据/(3)低频数据/海螺水泥低频数据_2026-06-20.xlsx")
        self.assertEqual(paths["step2_result_dir"], f"{root}/2.秒级核算数据")
        self.assertEqual(paths["step2_abnormal_dir"], f"{root}/3.秒级异常数据统计")
        self.assertEqual(paths["step3_result_dir"], f"{root}/4.15min核算数据")

        expected = expected_result_files(config)
        self.assertEqual(len(expected), 1 + 11 * 3)
        self.assertIn(f"{root}/2.秒级核算数据/2026-06-10_秒级CO2排放结果.xlsx", expected)
        self.assertIn(f"{root}/4.15min核算数据/2026-06-20_15minCO2排放结果.xlsx", expected)


if __name__ == "__main__":
    unittest.main()
