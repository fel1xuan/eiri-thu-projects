import os
import tempfile
import unittest
from pathlib import Path

from utils.resource_utils import resource_path
from utils.runtime_paths import get_project_root, get_user_config_dir, get_user_data_dir


class RuntimePathsTest(unittest.TestCase):
    def test_resource_path_uses_project_root_in_dev(self):
        self.assertEqual(Path(resource_path("assets/logo.png")), get_project_root() / "assets" / "logo.png")

    def test_user_dirs_support_environment_override(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_dir = Path(tmp) / "config"
            data_dir = Path(tmp) / "data"
            old_config = os.environ.get("QH_DATA_ANALYSIS_CONFIG_DIR")
            old_data = os.environ.get("QH_DATA_ANALYSIS_DATA_DIR")
            os.environ["QH_DATA_ANALYSIS_CONFIG_DIR"] = str(config_dir)
            os.environ["QH_DATA_ANALYSIS_DATA_DIR"] = str(data_dir)
            try:
                self.assertEqual(get_user_config_dir(), config_dir.resolve(strict=False))
                self.assertEqual(get_user_data_dir(), data_dir.resolve(strict=False))
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
