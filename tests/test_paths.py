import unittest

from utils.path_utils import month_folder_from_date, normalize_path


class PathUtilsTest(unittest.TestCase):
    def test_normalize_path_keeps_absolute_documents_path(self):
        path = "/private/tmp/qh-data-analysis"
        self.assertEqual(normalize_path(path), path)

    def test_month_folder_from_date(self):
        self.assertEqual(month_folder_from_date("2026-05-01"), "202605")


if __name__ == "__main__":
    unittest.main()
