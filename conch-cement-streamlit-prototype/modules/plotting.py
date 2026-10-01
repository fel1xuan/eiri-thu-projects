import pandas as pd
import plotly.graph_objects as go
import re


DEFAULT_PLOT_FIELDS = [
    "碳排放_2023_入磨",
    "碳排放_2024_入磨",
    "碳排放_2023_入窑",
    "碳排放_2024_入窑",
    "碳排放_2023_入磨_废纺平均",
    "碳排放_2024_入磨_废纺平均",
    "碳排放_2023_入磨_废纺熟料能耗",
    "碳排放_2024_入磨_废纺熟料能耗",
    "过程排放2023",
    "过程排放2024",
    "燃煤CO2排放",
    "煤矸石CO2排放",
]

HIGH_CONTRAST_COLORS = [
    "#00429D",
    "#E41A1C",
    "#00A087",
    "#3C5488",
    "#F39B7F",
    "#8491B4",
    "#91D1C2",
    "#DC0000",
    "#7E6148",
    "#B09C85",
    "#0072B5",
    "#BC3C29",
    "#20854E",
    "#7876B1",
    "#6F99AD",
    "#FFDC91",
    "#EE4C97",
    "#1982C4",
    "#8AC926",
    "#FFCA3A",
    "#6A4C93",
    "#FF595E",
    "#2EC4B6",
    "#FF9F1C",
]

CO2_FIELD_KEYWORDS = [
    "碳排放",
    "CO2",
    "CO₂",
    "二氧化碳",
    "过程排放",
    "燃煤CO2",
    "燃煤 CO2",
    "煤矸石CO2",
    "煤矸石 CO2",
    "排放速率",
    "Path",
]

MONITORING_FIELD_KEYWORDS = [
    "湿度",
    "烟气温度",
    "烟气压力",
    "CO2体积浓度",
    "CO₂体积浓度",
    "氧气浓度",
]

PLOT_GROUP_ORDER = [
    "碳排放",
    "CO₂排放速率",
    "物料 / 生产参数",
    "标干流量",
    "其他监测指标",
]

PLOT_GROUP_Y_AXIS_TITLES = {
    "碳排放": "碳排放数值",
    "CO₂排放速率": "CO₂排放速率",
    "物料 / 生产参数": "物料 / 生产参数数值",
    "标干流量": "标干流量",
    "其他监测指标": "监测指标数值",
}

MATERIAL_PRODUCTION_KEYWORDS = [
    "入磨-A",
    "入磨-B",
    "入窑-A磨入分解炉转子秤累计",
    "入窑-A磨入窑头转子秤累计",
    "废纺平均消耗量",
    "熟料产量",
]

PATH_COLORS = {
    ("1",): "#1982C4",
    ("2",): "#FF595E",
    ("3",): "#8AC926",
    ("1", "3"): "#FFCA3A",
    ("1", "2"): "#EE4C97",
    ("2", "3"): "#2EC4B6",
    ("1", "2", "3"): "#7E6148",
}

CATEGORY_BASE_COLORS = {
    "#00429D",
    "#E41A1C",
    "#00A087",
    "#7876B1",
    "#FF9F1C",
    "#20854E",
    "#6A4C93",
    *PATH_COLORS.values(),
}
FALLBACK_COLORS = [color for color in HIGH_CONTRAST_COLORS if color not in CATEGORY_BASE_COLORS]


def read_15min_file(file_path):
    return pd.read_excel(file_path)


def discover_plot_fields(columns):
    fields = []
    for col in columns:
        col_text = str(col)
        if col_text == "数据时间":
            continue
        if any(keyword in col_text for keyword in CO2_FIELD_KEYWORDS + MONITORING_FIELD_KEYWORDS):
            fields.append(col_text)
    return list(dict.fromkeys(fields))


def discover_numeric_plot_fields(df):
    """Return actual numeric Excel fields in their original column order."""
    excluded_fields = {"数据时间", "状态"}
    fields = []
    for column in df.columns:
        column_name = str(column)
        if column_name in excluded_fields:
            continue
        values = pd.to_numeric(df[column], errors="coerce")
        if values.notna().any():
            fields.append(column_name)
    return fields


def classify_plot_field(field):
    """Classify selected fields so different units never share a Y axis."""
    text = _compact(field)
    if "排放速率" in text:
        return "CO₂排放速率"
    if any(keyword in text for keyword in MATERIAL_PRODUCTION_KEYWORDS):
        return "物料 / 生产参数"
    if "标干流量" in text:
        return "标干流量"
    if any(keyword in text for keyword in ["碳排放", "CO2排放", "CO₂排放", "过程排放", "燃煤CO2", "燃煤CO₂", "煤矸石CO2", "煤矸石CO₂", "废纺"]):
        return "碳排放"
    return "其他监测指标"


def group_plot_fields(fields):
    grouped = {group: [] for group in PLOT_GROUP_ORDER}
    for field in fields or []:
        grouped[classify_plot_field(field)].append(field)
    return {group: values for group, values in grouped.items() if values}


def _field_group(field):
    group = re.sub(r"20(23|24)", "YEAR", str(field))
    return re.sub(r"\s+", "", group)


def _compact(field):
    return re.sub(r"\s+", "", str(field))


def _is_path_field(field):
    text = str(field)
    return "排放速率" in text or "Path" in text


def _path_color(field):
    text = _compact(field)
    match = re.search(r"Path([123](?:[&+/、和]?[123])*)", text, re.IGNORECASE)
    if not match:
        return "#7E6148" if "组合Path" in text else None
    path_numbers = tuple(sorted(set(re.findall(r"[123]", match.group(1)))))
    return PATH_COLORS.get(path_numbers)


def _is_coal_co2(field):
    text = _compact(field)
    return "煤矸石" not in text and ("燃煤CO2" in text or "煤CO2排放" in text)


def _fallback_color(field, color_map):
    group = _field_group(field)
    if group not in color_map:
        palette = FALLBACK_COLORS or HIGH_CONTRAST_COLORS
        color_map[group] = palette[len(color_map) % len(palette)]
    return color_map[group]


def _preferred_color(field, color_map):
    text = str(field)
    compact = _compact(field)

    if "废纺熟料能耗" in text:
        return "#7876B1"
    if "废纺平均" in text:
        return "#00A087"
    if "过程排放" in text:
        return "#FF9F1C"
    if _is_coal_co2(field):
        return "#20854E"
    if "煤矸石CO2" in compact:
        return "#6A4C93"
    if _is_path_field(field):
        return _path_color(field) or _fallback_color(field, color_map)
    if "碳排放" in text and "入磨" in text:
        return "#00429D"
    if "碳排放" in text and "入窑" in text:
        return "#E41A1C"
    if any(keyword in text for keyword in ["CO2", "CO₂", "二氧化碳", "碳排放"]):
        return _fallback_color(field, color_map)
    return None


def _line_dash(field):
    text = str(field)
    if "2024" in text:
        return "dash"
    if "2023" in text:
        return "solid"
    if _is_path_field(field):
        return "dot"
    return "solid"


def _line_style(field, color_map):
    color = _preferred_color(field, color_map) or _fallback_color(field, color_map)
    dash = _line_dash(field)
    return color, dash


def make_15min_figure(df, fields=None, yaxis_title="数值"):
    selected_fields = DEFAULT_PLOT_FIELDS if fields is None else fields
    missing_fields = [field for field in selected_fields if field not in df.columns]
    available_fields = []
    empty_fields = []
    numeric_series = {}
    for field in selected_fields:
        if field not in df.columns:
            continue
        values = pd.to_numeric(df[field], errors="coerce")
        if values.notna().any():
            available_fields.append(field)
            numeric_series[field] = values
        else:
            empty_fields.append(field)

    time_col = "数据时间" if "数据时间" in df.columns else df.columns[0]
    x_values = pd.to_datetime(df[time_col], errors="coerce").dt.strftime("%H:%M")
    x_values = x_values.fillna(df[time_col].astype(str))

    fig = go.Figure()
    fallback_colors = {}
    line_width = 1.8 if len(available_fields) > 15 else 2.5
    for field in available_fields:
        color, dash = _line_style(field, fallback_colors)
        fig.add_trace(
            go.Scatter(
                x=x_values,
                y=numeric_series[field],
                mode="lines",
                name=field,
                line={"color": color, "dash": dash, "width": line_width},
                hovertemplate="时间=%{x}<br>字段=" + field + "<br>数值=%{y}<extra></extra>",
            )
        )

    fig.update_layout(
        template="plotly_white",
        plot_bgcolor="#FFFFFF",
        paper_bgcolor="#FFFFFF",
        font={"color": "#333333", "family": "Arial, sans-serif"},
        height=560,
        margin={"l": 30, "r": 240, "t": 40, "b": 64},
        xaxis_title="15min时间点",
        yaxis_title=yaxis_title,
        legend_title_text="字段",
        legend={
            "x": 1.02,
            "xanchor": "left",
            "y": 1,
            "yanchor": "top",
            "bgcolor": "rgba(255,255,255,0.92)",
            "bordercolor": "#E5E5E5",
            "borderwidth": 1,
            "font": {"color": "#111111", "size": 12},
            "title": {"font": {"color": "#111111"}},
        },
        hovermode="x unified",
    )
    fig.update_xaxes(
        gridcolor="#E5E5E5",
        zerolinecolor="#E5E5E5",
        tickfont={"color": "#333333"},
        title_font={"color": "#333333"},
        type="category",
        tickangle=-35,
        automargin=True,
    )
    fig.update_yaxes(
        gridcolor="#E5E5E5",
        zerolinecolor="#E5E5E5",
        tickfont={"color": "#333333"},
        title_font={"color": "#333333"},
    )
    return fig, missing_fields, available_fields, empty_fields
