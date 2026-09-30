import unittest

from utils.fifteen_chart_utils import group_plot_fields, line_style_for_field


NUMERIC_FIELDS = [
    "入磨-A",
    "入磨-B",
    "入窑-A磨入分解炉转子秤累计",
    "入窑-A磨入窑头转子秤累计",
    "入磨煤低位发热量",
    "入窑煤低位发热量",
    "废纺低位发热量",
    "废纺平均消耗量",
    "熟料产量",
    "熟料中CaO含量%",
    "熟料中MgO含量%",
    "湿度",
    "烟气温度",
    "烟气压力",
    "标干流量Path1",
    "标干流量Path2",
    "标干流量Path3",
    "标干流量Path1&3",
    "标干流量Path1&2",
    "标干流量Path2&3",
    "标干流量Path1&2&3",
    "CO2体积浓度",
    "过程排放2023",
    "过程排放2024",
    "入磨煤CO2排放_2023",
    "入窑煤CO2排放_2023",
    "入磨煤CO2排放_2024",
    "入窑煤CO2排放_2024",
    "碳排放_2023_入磨",
    "碳排放_2023_入窑",
    "碳排放_2024_入磨",
    "碳排放_2024_入窑",
    "CO2排放速率Path1",
    "CO2排放速率Path2",
    "CO2排放速率Path3",
    "CO2排放速率Path1&3",
    "CO2排放速率Path1&2",
    "CO2排放速率Path2&3",
    "CO2排放速率Path1&2&3",
    "煤矸石CO2排放",
    "碳排放_2023_入磨_废纺平均",
    "碳排放_2023_入窑_废纺平均",
    "碳排放_2024_入磨_废纺平均",
    "碳排放_2024_入窑_废纺平均",
    "碳排放_2023_入磨_废纺熟料能耗",
    "碳排放_2023_入窑_废纺熟料能耗",
    "碳排放_2024_入磨_废纺熟料能耗",
    "碳排放_2024_入窑_废纺熟料能耗",
]


class ChartCategoriesTest(unittest.TestCase):
    def test_all_48_fields_are_classified_once(self):
        grouped = group_plot_fields(NUMERIC_FIELDS)
        classified = [field for fields in grouped.values() for field in fields]
        self.assertEqual(len(NUMERIC_FIELDS), 48)
        self.assertEqual(len(classified), 48)
        self.assertEqual(set(classified), set(NUMERIC_FIELDS))
        self.assertFalse(any(category.startswith("其他字段") for category in grouped))

    def test_year_and_path_styles_follow_old_api_semantics(self):
        style_2023 = line_style_for_field("过程排放2023", "过程排放")
        style_2024 = line_style_for_field("过程排放2024", "过程排放")
        self.assertEqual(style_2023["color"], style_2024["color"])
        self.assertEqual(style_2023["linestyle"], "-")
        self.assertEqual(style_2024["linestyle"], "--")
        self.assertEqual(line_style_for_field("标干流量Path1", "标干流量")["color"], "#1982C4")
        self.assertEqual(line_style_for_field("标干流量Path2", "标干流量")["color"], "#FF595E")
        self.assertEqual(line_style_for_field("标干流量Path3", "标干流量")["color"], "#8AC926")

    def test_unknown_fields_are_isolated(self):
        grouped = group_plot_fields(["未知压力A", "未知压力B"])
        self.assertEqual(list(grouped.values()), [["未知压力A"], ["未知压力B"]])


if __name__ == "__main__":
    unittest.main()
