import unittest

from utils.resource_utils import resource_exists
from utils.version import APP_DISPLAY_VERSION, APP_VERSION


class VersionResourcesTest(unittest.TestCase):
    def test_version_is_1_0(self):
        self.assertEqual(APP_VERSION, "1.0.0")
        self.assertEqual(APP_DISPLAY_VERSION, "詹宇轩1.0版")

    def test_help_images_exist(self):
        self.assertTrue(resource_exists("assets/mindmaps/physical_data_path.png"))
        self.assertTrue(resource_exists("assets/mindmaps/code_data_analysis_flow.png"))


if __name__ == "__main__":
    unittest.main()
