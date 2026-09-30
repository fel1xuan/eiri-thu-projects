import os
import tempfile
import unittest
from pathlib import Path

from utils.config_utils import get_config_path, load_config, save_config
from utils.log_utils import append_run_log, get_run_log_path, read_run_logs


class ConfigLogPathsTest(unittest.TestCase):
    def test_config_and_log_use_writable_user_dirs(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_dir = Path(tmp) / "config"
            data_dir = Path(tmp) / "data"
            old_config = os.environ.get("QH_DATA_ANALYSIS_CONFIG_DIR")
            old_data = os.environ.get("QH_DATA_ANALYSIS_DATA_DIR")
            os.environ["QH_DATA_ANALYSIS_CONFIG_DIR"] = str(config_dir)
            os.environ["QH_DATA_ANALYSIS_DATA_DIR"] = str(data_dir)
            try:
                config = load_config()
                config["target_month"] = "2026-05"
                save_config(config)
                append_run_log("测试", "success", "路径测试")

                self.assertEqual(Path(get_config_path()), config_dir.resolve(strict=False) / "app_config.json")
                self.assertTrue((config_dir / "app_config.json").exists())
                self.assertEqual(Path(get_run_log_path()), data_dir.resolve(strict=False) / "run_log.csv")
                self.assertTrue((data_dir / "run_log.csv").exists())
                self.assertEqual(read_run_logs()[0]["module"], "测试")
            finally:
                if old_config is None:
                    os.environ.pop("QH_DATA_ANALYSIS_CONFIG_DIR", None)
                else:
                    os.environ["QH_DATA_ANALYSIS_CONFIG_DIR"] = old_config
                if old_data is None:
                    os.environ.pop("QH_DATA_ANALYSIS_DATA_DIR", None)
                else:
                    os.environ["QH_DATA_ANALYSIS_DATA_DIR"] = old_data


if __name__ == "__main__":
    unittest.main()
