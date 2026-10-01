import base64
import csv
import re
from datetime import datetime
from html import escape
from pathlib import Path

import pandas as pd
import streamlit as st

from modules.agg_15min import run_15min_agg
from modules.extract_report import load_cell_map, run_extract_report, save_cell_map
from modules.lowfreq_update import run_lowfreq_update
from modules.plotting import (
    DEFAULT_PLOT_FIELDS,
    PLOT_GROUP_ORDER,
    PLOT_GROUP_Y_AXIS_TITLES,
    discover_numeric_plot_fields,
    group_plot_fields,
    make_15min_figure,
    read_15min_file,
)
from modules.second_calc import run_second_calc
from modules.utils import (
    check_project_structure,
    file_bytes,
    find_standard_data_dirs,
    format_exception,
    get_standard_paths,
    list_files,
    load_json,
    month_folder_from_date,
    normalize_date_str,
    normalize_path,
    validate_core_high_freq_dir,
    save_json,
)


BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config" / "app_config.json"
CELL_MAP_PATH = BASE_DIR / "config" / "cell_map.json"
OUTPUT_DIR = BASE_DIR / "outputs"
RUN_LOG_PATH = OUTPUT_DIR / "run_log.csv"
RUNTIME_DEBUG_LOG_PATH = OUTPUT_DIR / "runtime_debug.log"
LOGO_PATH = BASE_DIR / "assets" / "conch_logo.png"
UPLOAD_DIR = BASE_DIR / "uploads"
PROJECT_ROOT_EXAMPLE = str(Path.home() / "Documents" / "清华能源实习数据分析")
FLOW_IMAGE_CANDIDATES = [
    BASE_DIR / "assets" / "code_data_analysis_flow.png",
    BASE_DIR / "assets" / "代码数据分析流程图.png",
    BASE_DIR / "docs" / "code_data_analysis_flow.png",
]
PHYSICAL_IMAGE_CANDIDATES = [
    BASE_DIR / "assets" / "physical_data_path.png",
    BASE_DIR / "assets" / "物理数据路径图.png",
    BASE_DIR / "docs" / "physical_data_path.png",
]

PAGES = [
    "首页 / 工作台",
    "项目配置",
    "0号：日报数据提取",
    "一键运行后续流程",
    "结果下载",
    "15min图表查看",
    "使用说明",
]

STEP_LABELS = [
    ("step0", "0 日报数据提取"),
    ("step1", "1 低频数据汇总"),
    ("step2", "2 秒级核算/异常检测"),
    ("step3", "3 15min数据聚合"),
    ("review", "图表查看与结果下载"),
]

HOME_FLOW_LABELS = STEP_LABELS[:4]

STATUS_META = {
    "未开始": {"fg": "#666666", "bg": "#F1F1F1", "border": "#E5E5E5", "dot": "#B8B8B8"},
    "未运行": {"fg": "#666666", "bg": "#F1F1F1", "border": "#E5E5E5", "dot": "#B8B8B8"},
    "等待运行": {"fg": "#555555", "bg": "#F3F3F3", "border": "#E5E5E5", "dot": "#A8A8A8"},
    "运行中": {"fg": "#FFFFFF", "bg": "#666666", "border": "#666666", "dot": "#D6D6D6"},
    "已完成": {"fg": "#FFFFFF", "bg": "#111111", "border": "#111111", "dot": "#6BA36F"},
    "失败": {"fg": "#9F1D1D", "bg": "#FFFFFF", "border": "#D9A5A5", "dot": "#B42318"},
}

CONFIG_INPUT_KEYS = [
    "project_root",
    "daily_report_path",
    "daily_extract_output",
    "low_freq_main_file",
    "low_freq_source_folder",
    "low_freq_output_folder",
    "high_freq_base_path",
    "three_channel_path",
    "second_output_folder",
    "abnormal_output_folder",
    "fifteen_output_folder",
]

CONFIG_SESSION_ALIASES = {
    "project_root": ["project_root"],
    "daily_report_path": ["daily_report_file_path", "daily_report_path"],
    "daily_extract_output": ["zero_output_file_path", "daily_extract_output"],
    "low_freq_main_file": ["lowfreq_main_file", "low_freq_main_file"],
    "low_freq_source_folder": ["lowfreq_source_folder", "low_freq_source_folder"],
    "low_freq_output_folder": ["lowfreq_output_folder", "low_freq_output_folder"],
    "high_freq_base_path": ["high_freq_base_path"],
    "three_channel_path": ["shengdao_three_path", "three_channel_path"],
    "second_output_folder": ["second_output_folder"],
    "abnormal_output_folder": ["abnormal_output_folder"],
    "fifteen_output_folder": ["fifteenmin_output_folder", "fifteen_output_folder"],
}

DAILY_EXCEL_TYPES = ["xls", "xlsx"]
LOWFREQ_EXCEL_TYPES = ["xlsx"]
RUN_LOG_COLUMNS = ["timestamp", "step", "date_range", "status", "output_files", "message"]
LOWFREQ_MAIN_FILE_PATTERN = re.compile(r"^海螺水泥低频数据_(\d{4}-\d{2}-\d{2})\.xlsx$")
START_DATE_WIDGET_KEY = "start_date_widget"
END_DATE_WIDGET_KEY = "end_date_widget"
CONFIG_STATE_VERSION = 2


st.set_page_config(
    page_title="海螺水泥碳排放数据处理系统",
    page_icon=str(LOGO_PATH) if LOGO_PATH.exists() else None,
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    :root {
        --app-bg: #F7F7F8;
        --card-bg: #FFFFFF;
        --text-main: #111111;
        --text-body: #333333;
        --text-muted: #777777;
        --text-subtle: #8A8A8A;
        --border: #E5E5E5;
        --border-strong: #D6D6D6;
        --soft: #F2F2F3;
        --soft-2: #FAFAFA;
        --danger: #B42318;
        --success-dot: #5C9A62;
    }
    .stApp {
        background: var(--app-bg);
        color: var(--text-body);
    }
    .block-container {
        padding-top: 0.75rem !important;
        max-width: 1280px;
    }
    header[data-testid="stHeader"],
    div[data-testid="stToolbar"],
    div[data-testid="stDecoration"],
    div[data-testid="stStatusWidget"],
    div[data-testid="stHeaderActionElements"],
    div[data-testid="stAppDeployButton"],
    .stDeployButton,
    [data-testid="collapsedControl"],
    button[data-testid="stBaseButton-header"],
    button[data-testid="stBaseButton-headerNoPadding"],
    button[title="Hide sidebar"],
    button[title="Show sidebar"],
    button[aria-label="Hide sidebar"],
    button[aria-label="Show sidebar"],
    #MainMenu,
    footer {
        display: none !important;
        visibility: hidden !important;
        height: 0 !important;
        min-height: 0 !important;
        max-height: 0 !important;
        opacity: 0 !important;
        pointer-events: none !important;
    }
    div[data-testid="stAppViewContainer"] {
        background: var(--app-bg);
    }
    div[data-testid="stAppViewContainer"] > section,
    div[data-testid="stMain"] {
        padding-top: 0 !important;
    }
    section[data-testid="stSidebar"] {
        background: #FFFFFF;
        border-right: 1px solid var(--border);
        width: 15rem !important;
        min-width: 15rem !important;
        max-width: 15rem !important;
        transform: none !important;
        visibility: visible !important;
    }
    section[data-testid="stSidebar"] > div {
        padding-top: 1rem;
        background: #FFFFFF;
    }
    section[data-testid="stSidebar"] h3 {
        color: var(--text-main);
        font-size: 15px;
        font-weight: 650;
        letter-spacing: 0;
        margin-bottom: 0.65rem;
    }
    section[data-testid="stSidebar"] label,
    section[data-testid="stSidebar"] p,
    section[data-testid="stSidebar"] span {
        color: var(--text-body);
    }
    div[role="radiogroup"] label {
        border-radius: 10px;
        padding: 7px 10px;
        margin: 2px 0;
        transition: background 120ms ease;
    }
    div[role="radiogroup"] label:hover {
        background: #F4F4F4;
    }
    div[role="radiogroup"] label:has(input:checked) {
        background: #EDEDED;
    }
    h1, h2, h3, h4 {
        color: var(--text-main);
        letter-spacing: 0;
    }
    h3 {
        font-size: 18px;
        font-weight: 650;
    }
    p, label, span {
        color: var(--text-body);
    }
    .stTextInput input,
    .stDateInput input,
    .stSelectbox div[data-baseweb="select"],
    .stMultiSelect div[data-baseweb="select"],
    textarea {
        border-radius: 10px !important;
        border-color: var(--border) !important;
        background: #FFFFFF !important;
        color: var(--text-main) !important;
        box-shadow: none !important;
    }
    .stTextInput input:focus,
    .stDateInput input:focus,
    textarea:focus {
        border-color: #A8A8A8 !important;
        box-shadow: 0 0 0 1px #A8A8A8 !important;
    }
    div[data-testid="stDataFrame"],
    div[data-testid="stDataEditor"] {
        border: 1px solid var(--border);
        border-radius: 12px;
        overflow: hidden;
        background: #FFFFFF;
    }
    .stButton > button,
    .stDownloadButton > button {
        border-radius: 10px;
        border: 1px solid var(--border-strong);
        background: #FFFFFF;
        color: var(--text-main);
        font-weight: 560;
        box-shadow: none;
        min-height: 38px;
    }
    .stButton > button:hover,
    .stDownloadButton > button:hover {
        border-color: #BDBDBD;
        background: #F7F7F7;
        color: var(--text-main);
    }
    .stButton > button:disabled,
    .stDownloadButton > button:disabled {
        background: #E5E5E5 !important;
        color: #888888 !important;
        border-color: #D9D9D9 !important;
    }
    .stButton > button:disabled *,
    .stDownloadButton > button:disabled * {
        color: #888888 !important;
        font-weight: 600 !important;
    }
    .stButton > button[kind="primary"],
    .stDownloadButton > button[kind="primary"],
    button[data-testid="stBaseButton-primary"] {
        background: #111111 !important;
        color: #FFFFFF !important;
        border-color: #111111 !important;
        font-weight: 600 !important;
    }
    .stButton > button[kind="primary"] *,
    .stDownloadButton > button[kind="primary"] *,
    button[data-testid="stBaseButton-primary"] * {
        color: #FFFFFF !important;
        font-weight: 600 !important;
    }
    .stButton > button[kind="primary"]:hover,
    .stDownloadButton > button[kind="primary"]:hover,
    button[data-testid="stBaseButton-primary"]:hover {
        background: #222222 !important;
        border-color: #222222 !important;
        color: #FFFFFF !important;
    }
    .stButton > button[kind="primary"]:hover *,
    .stDownloadButton > button[kind="primary"]:hover *,
    button[data-testid="stBaseButton-primary"]:hover * {
        color: #FFFFFF !important;
    }
    div[data-testid="stVerticalBlockBorderWrapper"] {
        border-color: var(--border);
        border-radius: 12px;
        background: #FFFFFF;
        box-shadow: 0 1px 2px rgba(0, 0, 0, 0.025);
    }
    .main-title {
        padding: 14px 18px;
        border: 1px solid var(--border);
        border-radius: 14px;
        background: #FFFFFF;
        margin: 0 0 1rem 0;
        box-shadow: 0 1px 2px rgba(0, 0, 0, 0.025);
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 16px;
    }
    .brand-left {
        display: flex;
        align-items: center;
        gap: 12px;
        min-width: 0;
    }
    .brand-logo {
        width: 40px;
        height: 40px;
        object-fit: contain;
        border-radius: 8px;
        flex: 0 0 auto;
        background: #FFFFFF;
    }
    .brand-copy {
        min-width: 0;
    }
    .main-title h1 {
        margin: 0;
        color: var(--text-main);
        font-size: 23px;
        font-weight: 680;
        letter-spacing: 0;
    }
    .main-title p {
        margin: 4px 0 0 0;
        color: var(--text-muted);
        font-size: 13px;
    }
    .header-actions {
        display: flex;
        gap: 8px;
        align-items: center;
        color: var(--text-muted);
        font-size: 13px;
        white-space: nowrap;
    }
    .header-pill {
        border: 1px solid var(--border);
        border-radius: 999px;
        padding: 6px 10px;
        background: #FAFAFA;
    }
    .step-flow-container {
        display: flex;
        align-items: stretch;
        gap: 12px;
        overflow-x: auto;
        padding: 2px 2px 8px 2px;
        margin-bottom: 14px;
        scrollbar-width: thin;
        scrollbar-color: #D5D5D5 transparent;
    }
    .step-flow-container::-webkit-scrollbar {
        height: 6px;
    }
    .step-flow-container::-webkit-scrollbar-track {
        background: transparent;
    }
    .step-flow-container::-webkit-scrollbar-thumb {
        background: #D5D5D5;
        border-radius: 999px;
    }
    .step-card,
    .flow-card {
        border: 1px solid var(--border);
        border-radius: 12px;
        padding: 14px;
        background: #ffffff;
        min-width: 190px;
        height: 112px;
        flex: 1 0 190px;
        display: flex;
        flex-direction: column;
        justify-content: space-between;
        box-shadow: 0 1px 2px rgba(0, 0, 0, 0.025);
    }
    .step-title,
    .flow-card h4 {
        margin: 0;
        font-size: 13px;
        color: var(--text-main);
        font-weight: 650;
        letter-spacing: 0;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
        line-height: 1.25;
    }
    .step-arrow {
        flex: 0 0 18px;
        height: 112px;
        display: flex;
        align-items: center;
        justify-content: center;
        color: #A3A3A3;
        font-size: 18px;
        line-height: 1;
    }
    .status-badge {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        padding: 4px 9px;
        border-radius: 999px;
        font-size: 12px;
        font-weight: 620;
        border: 1px solid transparent;
        line-height: 1.2;
    }
    .status-dot {
        display: inline-block;
        width: 6px;
        height: 6px;
        border-radius: 999px;
        background: currentColor;
    }
    .metric-card {
        border: 1px solid var(--border);
        border-radius: 12px;
        padding: 14px;
        background: #ffffff;
        min-height: 86px;
        box-shadow: 0 1px 2px rgba(0, 0, 0, 0.025);
    }
    .metric-card .label {
        color: var(--text-muted);
        font-size: 12px;
        margin-bottom: 7px;
    }
    .metric-card .value {
        color: var(--text-main);
        font-size: 16px;
        font-weight: 650;
        margin-top: 4px;
    }
    .small-path {
        font-size: 13px;
        color: var(--text-body);
        word-break: break-all;
    }
    .card-shell {
        border: 1px solid var(--border);
        border-radius: 12px;
        background: #FFFFFF;
        padding: 16px;
        box-shadow: 0 1px 2px rgba(0, 0, 0, 0.025);
        margin-bottom: 14px;
    }
    .card-title {
        font-size: 15px;
        font-weight: 650;
        color: var(--text-main);
        margin-bottom: 4px;
    }
    .card-subtitle {
        color: var(--text-muted);
        font-size: 13px;
        margin-bottom: 10px;
    }
    .notice {
        display: flex;
        gap: 9px;
        align-items: flex-start;
        border: 1px solid var(--border);
        border-radius: 12px;
        background: #FFFFFF;
        padding: 12px 14px;
        color: var(--text-body);
        margin: 10px 0;
        font-size: 14px;
    }
    .notice-dot {
        width: 7px;
        height: 7px;
        border-radius: 999px;
        margin-top: 7px;
        flex: 0 0 auto;
        background: #9A9A9A;
    }
    .notice.success .notice-dot { background: var(--success-dot); }
    .notice.error {
        border-color: #E3B8B8;
        color: var(--danger);
    }
    .notice.error .notice-dot { background: var(--danger); }
    .notice.warning {
        background: #FAFAFA;
        border-color: #D8D8D8;
    }
    .page-title {
        margin-top: 18px !important;
        margin-bottom: 22px !important;
        padding: 0 !important;
        color: #111111 !important;
        font-size: 26px !important;
        font-weight: 700 !important;
        line-height: 1.3 !important;
        letter-spacing: 0 !important;
    }
    .section-title {
        margin-top: 24px !important;
        margin-bottom: 10px !important;
        padding: 0 !important;
        color: #111111 !important;
        font-size: 20px !important;
        font-weight: 700 !important;
        line-height: 1.35 !important;
        letter-spacing: 0 !important;
    }
    .section-title.compact {
        margin-top: 0 !important;
    }
    .record-title {
        margin: 0 !important;
        line-height: 40px;
    }
    .record-filter-label {
        color: var(--text-muted);
        font-size: 13px;
        line-height: 40px;
        white-space: nowrap;
        text-align: right;
    }
    .record-subtitle {
        color: var(--text-muted);
        font-size: 13px;
        margin: 0 0 10px 0;
    }
    .run-records {
        border: 1px solid var(--border);
        border-radius: 12px;
        background: #FFFFFF;
        padding: 4px 18px;
        margin-top: 12px;
        box-shadow: 0 1px 2px rgba(0, 0, 0, 0.025);
    }
    .run-record-card {
        border-top: 1px solid #DADADA;
        padding: 16px 0;
    }
    .run-record-card:first-child {
        border-top: 0;
    }
    .run-record-top {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 12px;
        margin-bottom: 8px;
    }
    .run-record-time {
        color: var(--text-muted);
        font-size: 12px;
    }
    .run-record-status {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        border: 1px solid var(--border);
        border-radius: 999px;
        background: #FAFAFA;
        color: #333333;
        padding: 3px 9px;
        font-size: 12px;
        font-weight: 620;
        white-space: nowrap;
    }
    .run-record-status-dot {
        width: 6px;
        height: 6px;
        border-radius: 999px;
        background: #9A9A9A;
        display: inline-block;
    }
    .run-record-status.success .run-record-status-dot,
    .run-record-status.pass .run-record-status-dot {
        background: var(--success-dot);
    }
    .run-record-status.error .run-record-status-dot,
    .run-record-status.fail .run-record-status-dot {
        background: var(--danger);
    }
    .run-record-status.running .run-record-status-dot {
        background: #666666;
    }
    .run-record-step {
        color: var(--text-main);
        font-weight: 660;
        font-size: 15px;
        margin-bottom: 10px;
    }
    .run-record-grid {
        display: grid;
        grid-template-columns: 120px minmax(0, 1fr);
        gap: 8px 12px;
        font-size: 13px;
        line-height: 1.45;
    }
    .run-record-label {
        color: var(--text-muted);
        background: #F6F6F6;
        border-radius: 6px;
        padding: 4px 8px;
    }
    .run-record-value {
        color: var(--text-body);
        padding: 4px 0;
        overflow-wrap: anywhere;
    }
    .download-card {
        border: 1px solid var(--border);
        border-radius: 12px;
        background: #FFFFFF;
        padding: 14px;
        box-shadow: 0 1px 2px rgba(0, 0, 0, 0.025);
        min-height: 118px;
    }
    .download-type {
        color: var(--text-muted);
        font-size: 12px;
        margin-bottom: 6px;
    }
    .download-name {
        color: var(--text-main);
        font-size: 14px;
        font-weight: 650;
        margin-bottom: 6px;
        word-break: break-all;
    }
    .download-path {
        color: var(--text-subtle);
        font-size: 12px;
        word-break: break-all;
        line-height: 1.45;
    }
    .stepper {
        border: 1px solid var(--border);
        border-radius: 12px;
        background: #FFFFFF;
        padding: 14px;
        margin-bottom: 14px;
    }
    .stepper-row {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 12px;
        padding: 8px 0;
        border-bottom: 1px solid #F0F0F0;
    }
    .stepper-row:last-child {
        border-bottom: 0;
    }
    .stepper-title {
        color: var(--text-main);
        font-weight: 560;
        font-size: 14px;
    }
    .path-row {
        margin-bottom: 10px;
    }
    .path-row .stButton > button {
        margin-top: 28px;
        white-space: nowrap;
    }
    div[data-testid="stFileUploader"] {
        border: 1px dashed #D8D8D8;
        border-radius: 12px;
        background: #FAFAFA;
        padding: 12px;
        margin-bottom: 8px;
    }
    div[data-testid="stFileUploader"] section {
        border: 0 !important;
        background: transparent !important;
        padding: 0 !important;
    }
    div[data-testid="stFileUploader"] button {
        border-radius: 9px !important;
        border: 1px solid var(--border-strong) !important;
        background: #FFFFFF !important;
        color: var(--text-main) !important;
        box-shadow: none !important;
    }
    div[data-testid="stFileUploader"] small,
    div[data-testid="stFileUploader"] p,
    div[data-testid="stFileUploader"] span {
        color: var(--text-muted) !important;
    }
    .upload-path {
        color: var(--text-muted);
        font-size: 12px;
        line-height: 1.45;
        word-break: break-all;
        margin: 2px 0 10px 0;
    }
    .path-check {
        display: flex;
        align-items: center;
        gap: 7px;
        color: var(--text-muted);
        font-size: 12px;
        margin: -3px 0 10px 0;
    }
    .path-check .check-dot {
        width: 6px;
        height: 6px;
        border-radius: 999px;
        background: #A8A8A8;
        flex: 0 0 auto;
    }
    .path-check.ok .check-dot { background: var(--success-dot); }
    .path-check.error {
        color: var(--danger);
    }
    .path-check.error .check-dot { background: var(--danger); }
    .path-summary-card {
        border: 1px solid var(--border);
        border-radius: 12px;
        background: #FFFFFF;
        padding: 16px;
        margin-bottom: 14px;
        box-shadow: 0 1px 2px rgba(0, 0, 0, 0.025);
    }
    .path-summary-title {
        color: var(--text-main);
        font-size: 15px;
        font-weight: 680;
        margin-bottom: 4px;
    }
    .path-flow-note {
        color: var(--text-muted);
        font-size: 12px;
        margin-bottom: 12px;
    }
    .path-item {
        border-top: 1px solid #F0F0F0;
        padding: 10px 0;
    }
    .path-item:first-of-type {
        border-top: 0;
    }
    .path-label {
        color: var(--text-muted);
        font-size: 12px;
        margin-bottom: 5px;
    }
    .path-value {
        color: var(--text-main);
        font-size: 13px;
        line-height: 1.5;
        word-break: break-all;
        font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
    }
    .path-status-line {
        display: inline-flex;
        align-items: center;
        gap: 7px;
        color: var(--text-muted);
        font-size: 12px;
        margin-top: 6px;
    }
    .path-status-line .check-dot {
        width: 6px;
        height: 6px;
        border-radius: 999px;
        background: #A8A8A8;
        flex: 0 0 auto;
    }
    .path-status-line.ok .check-dot { background: var(--success-dot); }
    .path-status-line.error {
        color: var(--danger);
    }
    .path-status-line.error .check-dot { background: var(--danger); }
    .path-status-line.warning {
        color: #8A6A14;
    }
    .path-status-line.warning .check-dot { background: #C58A1A; }
    .path-status-line.neutral {
        color: var(--text-muted);
    }
    .path-status-line.neutral .check-dot { background: #A8A8A8; }
    .path-value-prefix {
        color: var(--text-muted);
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        margin-right: 2px;
    }
    .result-output-path {
        color: #6F6F6F;
        font-size: 13px;
        line-height: 1.5;
        margin-top: 4px;
        word-break: break-word;
        overflow-wrap: anywhere;
    }
    .path-overview-grid {
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 14px;
    }
    @media (max-width: 980px) {
        .path-overview-grid {
            grid-template-columns: 1fr;
        }
    }
    .stMultiSelect [data-baseweb="tag"],
    [data-baseweb="tag"] {
        background-color: #111111 !important;
        border-color: #111111 !important;
        color: #FFFFFF !important;
        border-radius: 999px !important;
    }
    .stMultiSelect [data-baseweb="tag"] span,
    .stMultiSelect [data-baseweb="tag"] svg,
    [data-baseweb="tag"] span,
    [data-baseweb="tag"] svg {
        color: #FFFFFF !important;
        fill: #FFFFFF !important;
    }
    .stMultiSelect [data-baseweb="tag"] svg path,
    [data-baseweb="tag"] svg path {
        fill: #FFFFFF !important;
    }
    .stButton > button[kind="primary"]:disabled,
    .stDownloadButton > button[kind="primary"]:disabled,
    button[data-testid="stBaseButton-primary"]:disabled {
        background: #E5E5E5 !important;
        color: #888888 !important;
        border-color: #D9D9D9 !important;
    }
    .stButton > button[kind="primary"]:disabled *,
    .stDownloadButton > button[kind="primary"]:disabled *,
    button[data-testid="stBaseButton-primary"]:disabled * {
        color: #888888 !important;
        font-weight: 600 !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def parse_date(value):
    return datetime.strptime(normalize_date_str(value), "%Y-%m-%d").date()


def validate_single_month_range(start_date, end_date):
    try:
        start_dt = parse_date(start_date)
        end_dt = parse_date(end_date)
    except Exception as exc:
        return False, str(exc)

    if end_dt < start_dt:
        return False, "数据处理结束日期不能早于数据处理开始日期。"
    if start_dt.year != end_dt.year or start_dt.month != end_dt.month:
        return False, "当前版本仅支持单月内处理，请不要跨月选择日期范围。"
    return True, ""


def date_value_to_iso(value):
    if value is None or str(value).strip() == "":
        return ""
    try:
        return normalize_date_str(value)
    except Exception:
        return str(value or "").strip()


def config_date_to_widget_value(value):
    """Return a date_input-compatible value while keeping an unconfigured date blank."""
    if value is None or str(value).strip() == "":
        return None
    try:
        return parse_date(value)
    except Exception:
        return None


def set_runtime_dates(start_date=None, end_date=None):
    if start_date is not None:
        start_iso = date_value_to_iso(start_date)
        st.session_state.runtime_start_date = start_iso
        st.session_state.start_date = start_iso
    if end_date is not None:
        end_iso = date_value_to_iso(end_date)
        st.session_state.runtime_end_date = end_iso
        st.session_state.end_date = end_iso


def runtime_dates_from_state(config=None):
    config = config or st.session_state.get("config", {})
    start_source = st.session_state["runtime_start_date"] if "runtime_start_date" in st.session_state else config.get("start_date", "")
    end_source = st.session_state["runtime_end_date"] if "runtime_end_date" in st.session_state else config.get("end_date", "")
    start_date = date_value_to_iso(start_source)
    end_date = date_value_to_iso(end_source)
    return start_date, end_date


def apply_runtime_dates_to_config(config):
    config = normalize_config_paths((config or {}).copy())
    start_date, end_date = runtime_dates_from_state(config)
    config["start_date"] = start_date
    config["end_date"] = end_date
    return config


def session_value_for_config_key(key):
    input_key = f"{key}_input"
    candidates = [input_key] + CONFIG_SESSION_ALIASES.get(key, [key])
    for candidate in candidates:
        if candidate in st.session_state:
            value = normalize_path(st.session_state.get(candidate, ""))
            if value:
                return value
    return ""


def mirror_config_value_to_session(key, value, overwrite=False):
    value = normalize_path(value)
    input_key = f"{key}_input"
    if value and (overwrite or not normalize_path(st.session_state.get(input_key, ""))):
        st.session_state[input_key] = value
    current_input = normalize_path(st.session_state.get(input_key, value))
    if current_input:
        for alias in CONFIG_SESSION_ALIASES.get(key, [key]):
            st.session_state[alias] = current_input


def hydrate_config_inputs_from_config(config=None, overwrite=False):
    config = normalize_config_paths((config or st.session_state.get("config") or {}).copy())
    for key in CONFIG_INPUT_KEYS:
        value = session_value_for_config_key(key) or normalize_path(config.get(key, ""))
        mirror_config_value_to_session(key, value, overwrite=overwrite)
    return config


def merge_session_inputs_into_config(config):
    merged = normalize_config_paths((config or {}).copy())
    for key in CONFIG_INPUT_KEYS:
        value = session_value_for_config_key(key)
        if value:
            merged[key] = value
    return apply_runtime_dates_to_config(merged)


def init_state():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ensure_run_log_file()
    config_state_needs_refresh = st.session_state.get("config_state_version") != CONFIG_STATE_VERSION
    if "config_state_initialized" not in st.session_state or config_state_needs_refresh:
        st.session_state.config = load_saved_user_config()
        if not st.session_state.config.get("user_configured"):
            for key in CONFIG_INPUT_KEYS:
                st.session_state.pop(f"{key}_input", None)
                for alias in CONFIG_SESSION_ALIASES.get(key, [key]):
                    st.session_state.pop(alias, None)
            st.session_state.pop(START_DATE_WIDGET_KEY, None)
            st.session_state.pop(END_DATE_WIDGET_KEY, None)
            st.session_state.auto_fill_result = None
        st.session_state.config_state_initialized = True
        st.session_state.config_state_version = CONFIG_STATE_VERSION
    if "runtime_start_date" not in st.session_state:
        st.session_state.runtime_start_date = date_value_to_iso(st.session_state.config.get("start_date", ""))
    if "runtime_end_date" not in st.session_state:
        st.session_state.runtime_end_date = date_value_to_iso(st.session_state.config.get("end_date", ""))
    st.session_state.start_date = st.session_state.runtime_start_date
    st.session_state.end_date = st.session_state.runtime_end_date
    st.session_state.config = apply_runtime_dates_to_config(st.session_state.config)
    for key in CONFIG_INPUT_KEYS:
        input_key = f"{key}_input"
        if input_key not in st.session_state:
            st.session_state[input_key] = st.session_state.config.get(key, "")
        mirror_config_value_to_session(key, st.session_state.get(input_key, "") or st.session_state.config.get(key, ""))
    if START_DATE_WIDGET_KEY not in st.session_state:
        st.session_state[START_DATE_WIDGET_KEY] = config_date_to_widget_value(st.session_state.runtime_start_date)
    if END_DATE_WIDGET_KEY not in st.session_state:
        st.session_state[END_DATE_WIDGET_KEY] = config_date_to_widget_value(st.session_state.runtime_end_date)
    if "step_status" not in st.session_state:
        st.session_state.step_status = {
            "step0": "未开始",
            "step1": "等待运行",
            "step2": "等待运行",
            "step3": "等待运行",
            "review": "未开始",
        }
    if "audit_passed" not in st.session_state:
        st.session_state.audit_passed = False
    if "run_records" not in st.session_state:
        st.session_state.run_records = load_run_records()
    if "current_page" not in st.session_state:
        st.session_state.current_page = PAGES[0]
    elif st.session_state.current_page not in PAGES:
        st.session_state.current_page = "0号：日报数据提取"
    if "config_notice" not in st.session_state:
        st.session_state.config_notice = ""
    if "config_notice_kind" not in st.session_state:
        st.session_state.config_notice_kind = "neutral"
    if "auto_fill_result" not in st.session_state:
        st.session_state.auto_fill_result = None
    if "config_saved_at" not in st.session_state:
        st.session_state.config_saved_at = ""
    if "upload_messages" not in st.session_state:
        st.session_state.upload_messages = {}
    if "run_in_progress" not in st.session_state:
        st.session_state.run_in_progress = False
    if "last_run_config" not in st.session_state:
        st.session_state.last_run_config = {}


def ensure_run_log_file():
    RUN_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not RUN_LOG_PATH.exists() or RUN_LOG_PATH.stat().st_size == 0:
        with RUN_LOG_PATH.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=RUN_LOG_COLUMNS)
            writer.writeheader()


def load_run_records():
    ensure_run_log_file()
    records = []
    with RUN_LOG_PATH.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            records.append({column: str(row.get(column, "") or "") for column in RUN_LOG_COLUMNS})
    return records


def clear_run_records():
    RUN_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with RUN_LOG_PATH.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=RUN_LOG_COLUMNS)
        writer.writeheader()
    st.session_state.run_records = []


def format_date_range(start_date, end_date):
    start_text = str(start_date or "").strip()
    end_text = str(end_date or "").strip()
    if start_text and end_text and start_text != end_text:
        return f"{start_text} 至 {end_text}"
    return start_text or end_text


def current_date_range(config=None):
    cfg = config or get_config()
    return format_date_range(cfg.get("start_date", ""), cfg.get("end_date", ""))


def format_output_files(output_files):
    if output_files is None:
        return ""
    if isinstance(output_files, (list, tuple, set)):
        return "；".join(str(item) for item in output_files if str(item).strip())
    return str(output_files or "")


def compact_file_name(path_value):
    text = str(path_value or "").strip()
    if not text:
        return ""
    return Path(text).name or text


def compact_record_output(output_files, max_length=180):
    text = format_output_files(output_files)
    if not text:
        return ""
    parts = [part.strip() for part in text.split("；") if part.strip()]
    if len(parts) > 6:
        return f"{parts[0]}；{parts[1]}；...；共 {len(parts)} 项"
    if len(text) > max_length:
        return text[:max_length].rstrip() + "..."
    return text


def append_run_record(step, status, date_range, output_files="", message=""):
    ensure_run_log_file()
    row = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "step": str(step or ""),
        "date_range": str(date_range or ""),
        "status": str(status or ""),
        "output_files": compact_record_output(output_files),
        "message": str(message or ""),
    }
    with RUN_LOG_PATH.open("a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=RUN_LOG_COLUMNS)
        writer.writerow(row)
    if "run_records" not in st.session_state:
        st.session_state.run_records = load_run_records()
    st.session_state.run_records.append(row)


def ignore_module_log(message):
    return None


def set_status(step, status):
    st.session_state.step_status[step] = status


def is_app_upload_path(path_value):
    path_text = normalize_path(path_value)
    if not path_text:
        return False
    try:
        Path(path_text).expanduser().resolve().relative_to(UPLOAD_DIR.resolve())
        return True
    except Exception:
        return False


def normalize_config_paths(config):
    normalized = config.copy()
    for key in CONFIG_INPUT_KEYS:
        normalized[key] = normalize_path(normalized.get(key, ""))
    if is_app_upload_path(normalized.get("daily_report_path", "")):
        normalized["daily_report_path"] = ""
    if is_app_upload_path(normalized.get("daily_extract_output", "")):
        normalized["daily_extract_output"] = ""
    return normalized


def empty_user_config():
    config = {key: "" for key in CONFIG_INPUT_KEYS}
    config.update({
        "start_date": "",
        "end_date": "",
        "user_configured": False,
    })
    return config


def load_saved_user_config():
    """Load only configuration explicitly saved by a user, never old test residue."""
    saved = load_json(CONFIG_PATH, default={})
    if not isinstance(saved, dict) or not saved.get("user_configured"):
        return empty_user_config()

    config = normalize_config_paths(saved)
    config["start_date"] = date_value_to_iso(config.get("start_date", ""))
    config["end_date"] = date_value_to_iso(config.get("end_date", ""))
    config["user_configured"] = True
    return config


def path_normalization_message(value):
    raw = str(value or "").strip().strip('"').strip("'")
    normalized = normalize_path(value)
    if raw and normalized and raw != normalized:
        return f"已自动将 Finder 显示路径转换为系统真实路径：{normalized}"
    return ""


def save_config(config, user_confirmed=False):
    set_runtime_dates(config.get("start_date", ""), config.get("end_date", ""))
    config = normalize_config_paths(config)
    config = apply_runtime_dates_to_config(config)
    is_user_configured = bool(st.session_state.get("config", {}).get("user_configured")) or user_confirmed
    config["user_configured"] = is_user_configured
    st.session_state.config = config
    if is_user_configured:
        save_json(CONFIG_PATH, config)


def get_current_config():
    return get_config()


def save_current_config(config):
    save_config(config)


def write_runtime_debug(event, config=None, source="", extra=None):
    try:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        cfg = config or get_config()
        lines = [
            f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [{event}]",
            f"start_date = {cfg.get('start_date', '')}",
            f"end_date = {cfg.get('end_date', '')}",
        ]
        if source:
            lines.append(f"source = {source}")
        if extra:
            for key, value in extra.items():
                lines.append(f"{key} = {value}")
        with RUNTIME_DEBUG_LOG_PATH.open("a", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n\n")
    except Exception:
        pass


def write_process_debug(message):
    try:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        with RUNTIME_DEBUG_LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}\n")
    except Exception:
        pass


def set_config_notice(message, kind="neutral"):
    st.session_state.config_notice = message
    st.session_state.config_notice_kind = kind


def sync_inputs_from_config(config):
    set_runtime_dates(config.get("start_date", ""), config.get("end_date", ""))
    config = apply_runtime_dates_to_config(config)
    for key in CONFIG_INPUT_KEYS:
        mirror_config_value_to_session(key, config.get(key, ""), overwrite=True)
    start_date, end_date = runtime_dates_from_state(config)
    st.session_state[START_DATE_WIDGET_KEY] = config_date_to_widget_value(start_date)
    st.session_state[END_DATE_WIDGET_KEY] = config_date_to_widget_value(end_date)


def sync_date_widgets_from_runtime(force=False):
    start_date, end_date = runtime_dates_from_state()
    if force or START_DATE_WIDGET_KEY not in st.session_state:
        st.session_state[START_DATE_WIDGET_KEY] = config_date_to_widget_value(start_date)
    if force or END_DATE_WIDGET_KEY not in st.session_state:
        st.session_state[END_DATE_WIDGET_KEY] = config_date_to_widget_value(end_date)


def current_start_date_value():
    if st.session_state.get("current_page") == "项目配置" and START_DATE_WIDGET_KEY in st.session_state:
        return st.session_state.get(START_DATE_WIDGET_KEY)
    return st.session_state.get("runtime_start_date")


def current_end_date_value():
    if st.session_state.get("current_page") == "项目配置" and END_DATE_WIDGET_KEY in st.session_state:
        return st.session_state.get(END_DATE_WIDGET_KEY)
    return st.session_state.get("runtime_end_date")


def fill_project_root_example():
    st.session_state.project_root_input = PROJECT_ROOT_EXAMPLE
    st.session_state.auto_fill_result = None
    config = collect_config_from_inputs(
        current_start_date_value(),
        current_end_date_value(),
    )
    config["project_root"] = PROJECT_ROOT_EXAMPLE
    save_config(config)
    set_config_notice("已填入推荐示例路径，请根据本机实际项目位置确认后再自动填充。", "neutral")


def collect_config_from_inputs(start_date=None, end_date=None):
    set_runtime_dates(start_date, end_date)
    config = get_config().copy()
    for key in CONFIG_INPUT_KEYS:
        value = session_value_for_config_key(key)
        if value:
            config[key] = value
    return apply_runtime_dates_to_config(config)


def make_failed_auto_fill_result(config, issue, message, extra=None):
    result = {
        "status": "failed",
        "project_root": str(config.get("project_root", "") or "").strip(),
        "start_date": config.get("start_date", ""),
        "end_date": config.get("end_date", ""),
        "recognized_dirs": [],
        "missing_dirs": [],
        "core_validation": None,
        "root_issue": {
            "type": issue,
            "message": message,
        },
    }
    if extra:
        result["root_issue"].update(extra)
    return result


def auto_fill_standard_path_inputs():
    config = collect_config_from_inputs(
        current_start_date_value(),
        current_end_date_value(),
    )
    if not config.get("project_root") or not config.get("start_date") or not config.get("end_date"):
        st.session_state.auto_fill_result = None
        set_config_notice("请先填写项目根目录、数据处理开始日期和数据处理结束日期。", "error")
        return
    range_ok, range_message = validate_single_month_range(config.get("start_date", ""), config.get("end_date", ""))
    if not range_ok:
        st.session_state.auto_fill_result = None
        set_config_notice(range_message, "error")
        return

    project_root = str(config.get("project_root", "") or "").strip()
    if not project_root:
        message = "请先填写项目根目录。项目根目录应为包含 “1.原始数据” 的那一级目录。"
        st.session_state.auto_fill_result = make_failed_auto_fill_result(config, "empty_root", message)
        set_config_notice(message, "error")
        return

    project_root_path = Path(project_root).expanduser()
    if not project_root_path.exists() or not project_root_path.is_dir():
        message = "项目根目录不存在，请检查路径是否复制完整。"
        st.session_state.auto_fill_result = make_failed_auto_fill_result(
            config,
            "missing_root",
            message,
            {"current_path": str(project_root_path)},
        )
        set_config_notice(message, "error")
        return

    raw_data_path = project_root_path / "1.原始数据"
    if not raw_data_path.is_dir():
        message = "当前目录存在，但未找到 1.原始数据。请确认填写的是项目根目录，而不是上级目录或子目录。"
        st.session_state.auto_fill_result = make_failed_auto_fill_result(
            config,
            "missing_raw_data",
            message,
            {
                "current_path": str(project_root_path),
                "expected_raw_data_path": str(raw_data_path),
            },
        )
        set_config_notice(message, "error")
        return

    try:
        config, fill_result = auto_fill_standard_paths(config)
    except ValueError as exc:
        st.session_state.auto_fill_result = None
        set_config_notice(str(exc), "error")
        return

    st.session_state.auto_fill_result = fill_result
    if not fill_result["recognized_dirs"]:
        set_config_notice("请先填写项目根目录，或项目根目录下未找到标准数据目录。", "error")
        return

    save_config(config)
    sync_inputs_from_config(config)
    write_runtime_debug(
        "CONFIG SAVE",
        st.session_state.config,
        source="auto_fill_standard_paths",
        extra={"config_file": CONFIG_PATH},
    )
    core_validation = fill_result.get("core_validation") or {}
    if core_validation.get("status") == "complete" and not fill_result.get("missing_dirs"):
        set_config_notice("已自动填充标准路径，并完成日期范围检查。", "success")
    elif core_validation.get("status") == "missing_core_dir":
        set_config_notice("未找到核心高频数据父目录，请检查项目根目录是否填写正确。", "error")
    else:
        if core_validation.get("status") == "partial":
            set_config_notice("已识别核心高频数据父目录，但所选日期范围内部分日期文件夹缺失。", "warning")
        else:
            set_config_notice("已识别部分标准路径，请检查缺失目录。", "warning")


def save_project_config_inputs():
    try:
        config = collect_config_from_inputs(
            current_start_date_value(),
            current_end_date_value(),
        )
        if not config.get("project_root") or not config.get("start_date") or not config.get("end_date"):
            set_config_notice("请先填写项目根目录、数据处理开始日期和数据处理结束日期。", "error")
            return
        range_ok, range_message = validate_single_month_range(config.get("start_date", ""), config.get("end_date", ""))
        if not range_ok:
            set_config_notice(range_message, "error")
            return
        config = derive_paths_from_config(config, force_auto=True)
        save_config(config, user_confirmed=True)
        sync_inputs_from_config(st.session_state.config)
        write_runtime_debug(
            "CONFIG SAVE",
            st.session_state.config,
            source="project_config_page",
            extra={"config_file": CONFIG_PATH},
        )
        st.session_state.config_saved_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        set_config_notice("项目配置已保存", "success")
    except Exception as exc:
        set_config_notice(f"项目配置保存失败：{exc}", "error")


def persist_current_config_from_inputs():
    config = collect_config_from_inputs(
        current_start_date_value(),
        current_end_date_value(),
    )
    if not config.get("project_root") or not config.get("start_date") or not config.get("end_date"):
        st.session_state.config = config
        return
    range_ok, range_message = validate_single_month_range(config.get("start_date", ""), config.get("end_date", ""))
    if not range_ok:
        set_config_notice(range_message, "error")
        return
    save_config(config)
    write_runtime_debug(
        "CONFIG SAVE",
        st.session_state.config,
        source="widget_change",
        extra={"config_file": CONFIG_PATH},
    )
    st.session_state.config_notice = ""
    st.session_state.config_notice_kind = "neutral"


def safe_upload_name(name):
    return Path(name or "uploaded_file").name


def upload_signature(uploaded_file):
    size = getattr(uploaded_file, "size", None)
    if size is None:
        size = len(uploaded_file.getvalue())
    return f"{uploaded_file.name}:{size}"


def daily_report_month_folder_from_inputs():
    config = collect_config_from_inputs(
        current_start_date_value(),
        current_end_date_value(),
    )
    config = derive_paths_from_config(config, force_auto=True)
    folder = normalize_path(config.get("low_freq_source_folder", ""))
    return Path(folder).expanduser() if folder else None


def preferred_upload_folder(kind):
    if kind == "daily_report":
        folder = daily_report_month_folder_from_inputs()
        if not folder:
            raise ValueError("请先填写项目根目录和数据处理开始日期，再上传生产综合日报。")
        return folder

    low_freq_output = normalize_path(st.session_state.get("low_freq_output_folder_input", ""))
    if low_freq_output:
        return Path(low_freq_output).expanduser()
    return UPLOAD_DIR / "lowfreq_main"


def set_daily_output_default(overwrite=False):
    report_path = normalize_path(st.session_state.get("daily_report_path_input", ""))
    current_output = normalize_path(st.session_state.get("daily_extract_output_input", ""))
    if report_path and not is_app_upload_path(report_path) and (overwrite or not current_output or is_app_upload_path(current_output)):
        st.session_state["daily_extract_output_input"] = str(Path(report_path).expanduser().parent / "生产日报提取结果.xlsx")
        return

    if overwrite or not current_output or is_app_upload_path(current_output):
        folder = daily_report_month_folder_from_inputs()
        if folder:
            st.session_state["daily_extract_output_input"] = str(folder / "生产日报提取结果.xlsx")


def safe_read_excel_for_audit(output_path):
    output_path = normalize_path(output_path)
    if not output_path:
        return None

    path = Path(output_path).expanduser()

    if not path.exists():
        render_notice("未找到 0号结果文件，请先运行「0号：日报数据提取」，或检查结果路径是否正确。", "warning")
        st.caption("当前路径：")
        st.code(str(path))
        return None

    if path.is_dir():
        render_notice("当前 0号结果路径指向的是文件夹，不是 Excel 文件。请检查路径是否填写到具体的 .xlsx 或 .xls 文件。", "warning")
        st.code(str(path))
        return None

    if path.suffix.lower() not in {".xlsx", ".xls"}:
        render_notice("当前 0号结果路径不是 Excel 文件，请检查文件后缀。", "error")
        st.code(str(path))
        return None

    try:
        return pd.read_excel(path)
    except Exception as exc:
        render_notice("读取 0号结果文件失败，请检查 Excel 文件是否存在、是否损坏、格式是否正确。", "error")
        st.exception(exc)
        return None


def filter_daily_extract_output_by_range(output_path, start_date, end_date):
    path = Path(normalize_path(output_path)).expanduser()
    if not path.is_file():
        return {
            "raw_rows": 0,
            "parsed_rows": 0,
            "filtered_rows": 0,
            "min_date": "",
            "max_date": "",
        }

    start_dt = pd.to_datetime(start_date)
    end_dt = pd.to_datetime(end_date)
    df = pd.read_excel(path)
    if "日期" not in df.columns:
        raise ValueError("0号提取结果缺少日期列，无法按数据处理日期范围过滤。")

    date_values = pd.to_datetime(df["日期"], errors="coerce")
    mask = (date_values >= start_dt) & (date_values <= end_dt)
    filtered_df = df.loc[mask].copy()
    filtered_df["日期"] = date_values.loc[mask].dt.strftime("%Y-%m-%d")
    filtered_df.to_excel(path, index=False)
    parsed_dates = date_values.dropna()
    return {
        "raw_rows": len(df),
        "parsed_rows": int(date_values.notna().sum()),
        "filtered_rows": len(filtered_df),
        "min_date": parsed_dates.min().strftime("%Y-%m-%d") if not parsed_dates.empty else "",
        "max_date": parsed_dates.max().strftime("%Y-%m-%d") if not parsed_dates.empty else "",
    }


def format_extract_debug_info(config, daily_report_path, output_path, diagnostics=None):
    diagnostics = diagnostics or {}
    return "\n".join(
        [
            "当前运行配置：",
            f"start_date = {config.get('start_date', '')}",
            f"end_date = {config.get('end_date', '')}",
            f"daily_report_file_path = {daily_report_path or ''}",
            f"zero_output_file_path = {output_path or ''}",
            f"原始日报读取行数 = {diagnostics.get('raw_rows', '未读取')}",
            f"日期列解析成功行数 = {diagnostics.get('parsed_rows', '未解析')}",
            f"识别出的最早日期 = {diagnostics.get('min_date', '') or '无'}",
            f"识别出的最晚日期 = {diagnostics.get('max_date', '') or '无'}",
            f"过滤后行数 = {diagnostics.get('filtered_rows', '未过滤')}",
        ]
    )


def preview_matches_current_range(preview_df, config):
    if preview_df is None or preview_df.empty or "日期" not in preview_df.columns:
        return False
    try:
        start_dt = pd.to_datetime(config.get("start_date", ""))
        end_dt = pd.to_datetime(config.get("end_date", ""))
        dates = pd.to_datetime(preview_df["日期"], errors="coerce").dropna()
    except Exception:
        return False
    if dates.empty:
        return False
    return bool((dates >= start_dt).all() and (dates <= end_dt).all())


def save_uploaded_excel(uploaded_file, field_key, kind):
    target_dir = preferred_upload_folder(kind)
    target_dir.mkdir(parents=True, exist_ok=True)
    saved_path = target_dir / safe_upload_name(uploaded_file.name)
    saved_path.write_bytes(uploaded_file.getvalue())

    st.session_state[f"{field_key}_input"] = str(saved_path)
    mirror_config_value_to_session(field_key, str(saved_path), overwrite=True)
    st.session_state.upload_messages[field_key] = f"上传文件已保存到：{saved_path}"
    st.session_state[f"{field_key}_upload_signature"] = upload_signature(uploaded_file)

    if field_key == "daily_report_path":
        set_daily_output_default(overwrite=True)

    persist_current_config_from_inputs()
    return saved_path


def render_excel_upload(label, field_key, uploader_key, file_types, kind):
    hydrate_config_inputs_from_config()
    uploaded_file = st.file_uploader(
        label,
        type=file_types,
        accept_multiple_files=False,
        key=uploader_key,
        help="点击上传区域选择文件，或将文件拖拽到此处。",
    )

    if uploaded_file is not None:
        signature = upload_signature(uploaded_file)
        already_saved = st.session_state.get(f"{field_key}_upload_signature") == signature
        current_path = st.session_state.get(f"{field_key}_input", "")
        if not already_saved or not current_path:
            try:
                save_uploaded_excel(uploaded_file, field_key, kind)
            except Exception as exc:
                render_notice(f"上传文件保存失败：{exc}", "error")

    current_value = st.session_state.get(f"{field_key}_input", "").strip()
    message = st.session_state.upload_messages.get(field_key)
    if message and current_value:
        st.markdown(f'<div class="upload-path">{h(message)}</div>', unsafe_allow_html=True)
    elif current_value:
        st.markdown(f'<div class="upload-path">当前已配置文件：{h(current_value)}</div>', unsafe_allow_html=True)


def render_path_check(value, path_type="folder"):
    path_text = normalize_path(value)
    if not path_text:
        return
    conversion_message = path_normalization_message(value)
    if conversion_message:
        st.caption(conversion_message)
    path = Path(path_text).expanduser()
    exists = path.is_file() if path_type == "file" else path.is_dir()
    label = "路径存在" if exists else "路径不存在，请检查或先创建"
    class_name = "ok" if exists else "error"
    st.markdown(
        f"""
        <div class="path-check {class_name}">
            <span class="check-dot"></span>
            <span>{h(label)}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_daily_report_upload_warning(value):
    if is_app_upload_path(value):
        render_notice(
            "当前生产日报路径位于软件目录 uploads 中，不建议作为正式数据路径。请重新上传或选择数据目录中的生产日报文件。",
            "warning",
        )


def render_folder_input(label, field_key, help_text=None, optional=False):
    st.text_input(label, key=f"{field_key}_input", on_change=persist_current_config_from_inputs)
    if help_text:
        st.caption(help_text)

    value = normalize_path(st.session_state.get(f"{field_key}_input", ""))
    if optional:
        if not value:
            render_notice("未配置，将使用核心高频数据中的原始Path3。", "neutral")
        elif Path(value).expanduser().is_dir():
            render_notice("路径存在；若当前日期有三声道文件，将用于修正Path3。", "success")
        else:
            render_notice("未找到目录，将使用核心高频数据中的原始Path3。", "neutral")
        return

    render_path_check(value, "folder")


def render_project_root_input():
    st.text_input(
        "项目根目录",
        key="project_root_input",
        placeholder=f"例如：{PROJECT_ROOT_EXAMPLE}",
        help="填写包含 1.原始数据、2.结果数据、3.异常数据 的那一级目录。",
        on_change=persist_current_config_from_inputs,
    )
    st.caption("请填写项目根目录，也就是包含 “1.原始数据”、“2.结果数据”、“3.异常数据” 的那一级目录。")
    st.caption(f"推荐示例：{PROJECT_ROOT_EXAMPLE}")
    st.caption("不要填写到子目录，例如不要填到：项目根目录/1.原始数据/(1) 核心高频数据")
    st.caption("Mac Finder 中进入项目文件夹后，可以右键文件夹，按住 Option，选择“复制 xxx 作为路径名”，然后粘贴到这里。")
    st.button(
        "填入推荐示例",
        key="fill_project_root_example",
        on_click=fill_project_root_example,
    )
    render_path_check(st.session_state.get("project_root_input", ""), "folder")


def render_output_folder_input(label, field_key, exists_message=None):
    st.text_input(label, key=f"{field_key}_input", on_change=persist_current_config_from_inputs)
    value = normalize_path(st.session_state.get(f"{field_key}_input", "").strip())
    if value:
        folder_exists = Path(value).expanduser().is_dir()
        message = exists_message if folder_exists and exists_message else "默认输出文件夹，运行时使用；不存在时会自动创建"
        if not folder_exists:
            message = "运行时自动创建"
        st.markdown(
            f"""
            <div class="path-check {'ok' if folder_exists else ''}">
                <span class="check-dot"></span>
                <span>{h(message)}</span>
            </div>
            """,
            unsafe_allow_html=True,
        )


def date_bounds(config):
    start_date = str(config.get("start_date", "") or "").strip()
    end_date = str(config.get("end_date", "") or "").strip()
    return start_date, end_date


def path_is_inside(path_value, parent_value):
    path_text = normalize_path(path_value)
    parent_text = normalize_path(parent_value)
    if not path_text or not parent_text:
        return False
    try:
        Path(path_text).expanduser().resolve().relative_to(Path(parent_text).expanduser().resolve())
        return True
    except Exception:
        return False


def date_range_file_stem(start_date, end_date):
    if start_date and end_date and start_date != end_date:
        return f"{start_date}_to_{end_date}"
    return start_date or end_date or ""


def expected_daily_report_name(start_date, end_date):
    if not start_date:
        return ""
    start_dt = parse_date(start_date)
    end_dt = parse_date(end_date or start_date)
    day_part = str(start_dt.day) if start_dt == end_dt else f"{start_dt.day}-{end_dt.day}"
    return f"{start_dt.year}年{start_dt.month}月{day_part}日生产综合日报.xlsx"


def find_daily_report_file(source_folder):
    folder_text = normalize_path(source_folder)
    if not folder_text:
        return ""
    folder = Path(folder_text).expanduser()
    if not folder.is_dir():
        return ""
    report_files = sorted(list(folder.glob("*生产综合日报.xls")) + list(folder.glob("*生产综合日报.xlsx")))
    return str(report_files[0]) if report_files else ""


def extract_date_from_text(value):
    text = str(value or "")
    match = re.search(r"(20\d{2}-\d{2}-\d{2})", text)
    if match:
        try:
            return parse_date(match.group(1))
        except Exception:
            return None

    match = re.search(r"(20\d{2})(0[1-9]|1[0-2])", text)
    if match:
        try:
            return datetime.strptime(match.group(1) + match.group(2) + "01", "%Y%m%d").date()
        except Exception:
            return None

    match = re.search(r"(20\d{2})年(\d{1,2})月", text)
    if match:
        try:
            return datetime(int(match.group(1)), int(match.group(2)), 1).date()
        except Exception:
            return None

    return None


def lowfreq_main_candidates(low_freq_base_folder):
    folder_text = normalize_path(low_freq_base_folder)
    if not folder_text:
        return []
    folder = Path(folder_text).expanduser()
    if not folder.exists():
        return []

    candidates = []
    paths = list(folder.glob("海螺水泥低频数据_*.xlsx"))
    paths.extend(folder.rglob("海螺水泥低频数据_*.xlsx"))
    for path in sorted(set(paths)):
        if not path.is_file():
            continue
        match = LOWFREQ_MAIN_FILE_PATTERN.match(path.name)
        if not match:
            continue
        candidates.append((parse_date(match.group(1)), path))
    return candidates


def select_cumulative_lowfreq_main(low_freq_base_folder, start_date, end_date):
    if not start_date:
        return {"path": "", "file_date": None, "coverage": "missing"}
    end_dt = parse_date(end_date or start_date)
    candidates = lowfreq_main_candidates(low_freq_base_folder)
    if not candidates:
        return {"path": "", "file_date": None, "coverage": "missing"}

    on_or_after_end = [item for item in candidates if item[0] >= end_dt]
    if on_or_after_end:
        on_or_after_end.sort(key=lambda item: (item[0], item[1].name))
        selected_date, selected_path = on_or_after_end[0]
        return {
            "path": str(selected_path),
            "file_date": selected_date,
            "coverage": "exact" if selected_date == end_dt else "future_covering",
        }

    before_end = [item for item in candidates if item[0] < end_dt]
    before_end.sort(key=lambda item: (item[0], item[1].name), reverse=True)
    selected_date, selected_path = before_end[0]
    return {
        "path": str(selected_path),
        "file_date": selected_date,
        "coverage": "past_warning",
    }


def select_historical_lowfreq_main(low_freq_base_folder, start_date, end_date=None):
    if not start_date:
        return {"path": "", "file_date": None, "coverage": "missing"}
    start_dt = parse_date(start_date)
    candidates = lowfreq_main_candidates(low_freq_base_folder)
    if not candidates:
        return {"path": "", "file_date": None, "coverage": "missing"}

    before_start = [item for item in candidates if item[0] < start_dt]
    if before_start:
        before_start.sort(key=lambda item: (item[0], item[1].name), reverse=True)
        selected_date, selected_path = before_start[0]
        return {
            "path": str(selected_path),
            "file_date": selected_date,
            "coverage": "historical_base",
        }

    before_or_on_end = []
    if end_date:
        end_dt = parse_date(end_date)
        before_or_on_end = [item for item in candidates if item[0] <= end_dt]
    if before_or_on_end:
        before_or_on_end.sort(key=lambda item: (item[0], item[1].name), reverse=True)
        selected_date, selected_path = before_or_on_end[0]
        return {
            "path": str(selected_path),
            "file_date": selected_date,
            "coverage": "current_or_past_fallback",
        }

    candidates.sort(key=lambda item: (item[0], item[1].name))
    selected_date, selected_path = candidates[0]
    return {
        "path": str(selected_path),
        "file_date": selected_date,
        "coverage": "future_warning",
    }


def derive_paths_from_config(config, force_auto=False):
    derived = normalize_config_paths(config.copy())
    project_root = derived.get("project_root", "")
    start_date, end_date = date_bounds(derived)
    if not project_root:
        return derived

    paths = get_standard_paths(project_root)
    standard_dirs = find_standard_data_dirs(project_root)
    low_freq_base = paths["low_freq_base_path"]
    if low_freq_base:
        derived["low_freq_output_folder"] = low_freq_base
    derived["high_freq_base_path"] = paths["high_freq_base_path"]
    three_channel_item = standard_dirs.get("three_channel_path", {})
    three_channel_path = normalize_path(three_channel_item.get("path", ""))
    if three_channel_item.get("exists"):
        derived["three_channel_path"] = three_channel_path
    elif force_auto and normalize_path(derived.get("three_channel_path", "")) == three_channel_path:
        # Do not present a nonexistent standard candidate as an active configuration.
        derived["three_channel_path"] = ""
    derived["second_output_folder"] = paths["second_output_folder"]
    derived["abnormal_output_folder"] = paths["abnormal_output_folder"]
    derived["fifteen_output_folder"] = paths["fifteen_output_folder"]

    if start_date:
        month_folder = month_folder_from_date(start_date)
        low_freq_source_folder = str(Path(low_freq_base).expanduser() / month_folder) if low_freq_base else ""
        if low_freq_source_folder:
            derived["low_freq_source_folder"] = low_freq_source_folder
            derived["daily_extract_output"] = str(Path(low_freq_source_folder).expanduser() / "生产日报提取结果.xlsx")

            current_report = find_daily_report_file(low_freq_source_folder)
            existing_report = derived.get("daily_report_path", "")
            existing_report_is_upload = is_app_upload_path(existing_report)
            existing_report_is_standard = path_is_inside(existing_report, low_freq_base)
            existing_report_is_manual = bool(
                existing_report
                and not existing_report_is_standard
                and not existing_report_is_upload
                and Path(existing_report).expanduser().is_file()
            )
            if existing_report_is_manual:
                pass
            elif current_report:
                derived["daily_report_path"] = current_report
            elif force_auto or not existing_report or existing_report_is_standard or existing_report_is_upload:
                derived["daily_report_path"] = str(Path(low_freq_source_folder).expanduser() / expected_daily_report_name(start_date, end_date))

        historical_lowfreq = find_lowfreq_main_file_for_range(low_freq_base, start_date, end_date)
        existing_lowfreq = derived.get("low_freq_main_file", "")
        existing_lowfreq_is_standard = path_is_inside(existing_lowfreq, low_freq_base)
        existing_lowfreq_is_manual = bool(existing_lowfreq and not existing_lowfreq_is_standard)
        if existing_lowfreq_is_manual:
            pass
        elif historical_lowfreq:
            derived["low_freq_main_file"] = historical_lowfreq
        elif force_auto or existing_lowfreq_is_standard:
            derived["low_freq_main_file"] = ""

    for stale_key in ["last_low_freq_output", "last_second_outputs", "last_abnormal_outputs", "last_15min_outputs"]:
        derived.pop(stale_key, None)
    return normalize_config_paths(derived)


def expected_lowfreq_output(config):
    output_folder = str(config.get("low_freq_output_folder", "") or "").strip()
    _, end_date = date_bounds(config)
    if not output_folder or not end_date:
        return ""
    return str(Path(output_folder).expanduser() / f"海螺水泥低频数据_{end_date}.xlsx")


def verify_lowfreq_output_for_current_range(output_path, start_date, end_date):
    path = Path(normalize_path(output_path)).expanduser()
    start_dt = parse_date(start_date)
    end_dt = parse_date(end_date)
    expected_dates = {start_dt + pd.Timedelta(days=offset).to_pytimedelta() for offset in range((end_dt - start_dt).days + 1)}

    if not path.exists():
        raise RuntimeError(f"1号低频汇总失败：输出文件不存在。输出文件={path}")
    if not path.is_file():
        raise RuntimeError(f"1号低频汇总失败：输出路径不是 Excel 文件。输出路径={path}")

    saved_df = pd.read_excel(path)
    date_col = "日期" if "日期" in saved_df.columns else "数据时间" if "数据时间" in saved_df.columns else ""
    if not date_col:
        raise RuntimeError(f"1号低频汇总失败：输出文件缺少日期列。输出文件={path}")

    saved_dates = pd.to_datetime(saved_df[date_col], errors="coerce").dt.date
    valid_dates = saved_dates.dropna()
    actual_dates = set(valid_dates)
    range_mask = saved_dates.isin(expected_dates)
    range_count = int(range_mask.sum())
    contains_start = start_dt in actual_dates
    contains_end = end_dt in actual_dates
    min_date = valid_dates.min() if not valid_dates.empty else "无"
    max_date = valid_dates.max() if not valid_dates.empty else "无"
    missing_dates = sorted(expected_dates - actual_dates)

    if range_count != len(expected_dates) or missing_dates or not contains_start or not contains_end:
        missing_text = "；".join(day.strftime("%Y-%m-%d") for day in missing_dates[:10])
        if len(missing_dates) > 10:
            missing_text += f"；等 {len(missing_dates)} 天"
        raise RuntimeError(
            "1号低频汇总失败：输出文件未包含当前日期范围数据。"
            f" start_date={start_dt}, end_date={end_dt}, 输出文件={path},"
            f" 输出日期最小值={min_date}, 输出日期最大值={max_date},"
            f" 当前范围行数={range_count}, 应有行数={len(expected_dates)},"
            f" 包含开始日期={contains_start}, 包含结束日期={contains_end},"
            f" 缺失日期={missing_text or '无'}"
        )

    return {
        "rows": len(saved_df),
        "min_date": min_date,
        "max_date": max_date,
        "target_range_rows": range_count,
        "contains_start_date": contains_start,
        "contains_end_date": contains_end,
    }


def expected_daily_extract_output(config):
    source_folder = normalize_path(config.get("low_freq_source_folder", ""))
    if source_folder:
        return str(Path(source_folder).expanduser() / "生产日报提取结果.xlsx")
    low_freq_base = normalize_path(config.get("low_freq_output_folder", ""))
    start_date, _ = date_bounds(config)
    if low_freq_base and start_date:
        month_folder = month_folder_from_date(start_date)
        return str(Path(low_freq_base).expanduser() / month_folder / "生产日报提取结果.xlsx")
    return normalize_path(config.get("daily_extract_output", ""))


def expected_lowfreq_month_folders(config):
    low_freq_base = normalize_path(config.get("low_freq_output_folder", ""))
    configured_source = normalize_path(config.get("low_freq_source_folder", ""))
    start_date, end_date = date_bounds(config)
    if not start_date or not end_date:
        return [configured_source] if configured_source else []
    try:
        periods = pd.period_range(pd.to_datetime(start_date), pd.to_datetime(end_date), freq="M")
    except Exception:
        return [configured_source] if configured_source else []
    if not low_freq_base:
        return [configured_source] if configured_source else []
    return [str(Path(low_freq_base).expanduser() / period.strftime("%Y%m")) for period in periods]


def expected_daily_outputs(config, folder_key, suffix, last_key=None):
    folder = str(config.get(folder_key, "") or "").strip()
    start_date, end_date = date_bounds(config)
    if not folder or not start_date:
        return []

    dates = [start_date]
    if end_date and end_date != start_date:
        dates.append(end_date)
    return [str(Path(folder).expanduser() / f"{date_text}_{suffix}") for date_text in dates]


def expected_15min_outputs(config):
    folder = str(config.get("fifteen_output_folder", "") or "").strip()
    start_date, end_date = date_bounds(config)
    stem = date_range_file_stem(start_date, end_date)
    if not folder or not stem:
        return []
    return [str(Path(folder).expanduser() / f"{stem}_15minCO2排放结果.xlsx")]


def path_exists(value, path_type):
    path_text = normalize_path(value)
    if not path_text:
        return False
    path = Path(path_text).expanduser()
    if path_type == "folder":
        return path.is_dir()
    return path.is_file()


def render_path_item(label, value, path_type="file", status_mode=None, status_text_override=None):
    if isinstance(value, (list, tuple)):
        paths = [str(item) for item in value if item]
    else:
        paths = [str(value)] if value else []

    if status_mode is None:
        status_mode = "check" if path_type in {"file", "folder"} else "output"

    if paths:
        prefix = ""
        if status_mode == "output":
            prefix = '<span class="path-value-prefix">预计输出：</span>'
        elif status_mode == "generated":
            prefix = '<span class="path-value-prefix">运行后生成：</span>'
        elif status_mode == "folder_output":
            prefix = '<span class="path-value-prefix">默认输出文件夹：</span>'
        value_html = "<br>".join(f"{prefix}{h(path)}" for path in paths)
        if status_mode in {"check", "required_input", "optional_input"}:
            exists = all(path_exists(path, path_type) for path in paths)
            if exists:
                status_class = "ok"
                status_text = "路径存在"
            elif status_mode == "optional_input":
                status_class = "warning"
                status_text = status_text_override or "可选但未配置"
            else:
                status_class = "error"
                status_text = status_text_override or "必填输入缺失，请检查"
        elif status_mode == "folder_output":
            status_class = "neutral"
            status_text = "运行时使用；不存在时会自动创建"
        elif status_mode == "output":
            exists = all(path_exists(path, path_type) for path in paths)
            status_class = "ok" if exists else "neutral"
            status_text = "路径存在" if exists else "运行后生成"
        elif status_mode == "generated":
            exists = all(path_exists(path, path_type) for path in paths)
            status_class = "ok" if exists else "neutral"
            status_text = "路径存在，2号可读取" if exists else (status_text_override or "等待上游流程完成")
        else:
            status_class = "neutral"
            status_text = "运行后生成"
    else:
        value_html = "未配置"
        if status_mode == "required_input":
            status_class = "error"
            status_text = status_text_override or "必填输入未配置"
        elif status_mode == "optional_input":
            status_class = "warning"
            status_text = status_text_override or "可选但未配置"
        elif status_mode == "check":
            status_class = "error"
            status_text = "路径不存在，请检查"
        elif status_mode == "generated":
            status_class = "neutral"
            status_text = status_text_override or "等待上游流程完成"
        else:
            status_class = "neutral"
            status_text = "运行后生成"

    return (
        f'<div class="path-item">'
        f'<div class="path-label">{h(label)}</div>'
        f'<div class="path-value">{value_html}</div>'
        f'<div class="path-status-line {status_class}">'
        f'<span class="check-dot"></span>'
        f'<span>{h(status_text)}</span>'
        f"</div>"
        f"</div>"
    )


def path_summary_card_html(title, rows, flow_note=""):
    note_html = f'<div class="path-flow-note">{h(flow_note)}</div>' if flow_note else ""
    row_html = "".join(render_path_item(*row) for row in rows)
    return (
        f'<div class="path-summary-card">'
        f'<div class="path-summary-title">{h(title)}</div>'
        f"{note_html}"
        f"{row_html}"
        f"</div>"
    )


def render_path_summary_card(title, rows, flow_note=""):
    st.markdown(path_summary_card_html(title, rows, flow_note), unsafe_allow_html=True)


def make_input_check(check_name, path, status, level, message):
    return {
        "check_name": check_name,
        "path": normalize_path(path) if path else "",
        "status": status,
        "level": level,
        "message": message,
    }


def find_lowfreq_optional_files(source_folders, keywords):
    matches = []
    for folder_text in source_folders:
        folder = Path(normalize_path(folder_text)).expanduser()
        if not folder.is_dir():
            continue
        for path in sorted(folder.glob("*.xlsx")):
            file_name = path.name.lower()
            if any(str(keyword).lower() in file_name for keyword in keywords):
                matches.append(str(path))
    return matches


def find_dcs_candidates_in_folder(folder):
    folder_path = Path(normalize_path(folder)).expanduser()
    if not folder_path.is_dir():
        return []

    candidates = []
    for path in sorted(folder_path.rglob("*")):
        if "dcs" in path.name.lower():
            candidates.append(path)
    return candidates


def summarize_dcs_check(low_freq_base, source_folders, start_date, end_date):
    end_dt = parse_date(end_date or start_date) if start_date else None

    current_month_candidates = []
    for folder in source_folders:
        current_month_candidates.extend(find_dcs_candidates_in_folder(folder))
    if current_month_candidates:
        return make_input_check(
            "DCS文件",
            "；".join(str(path) for path in current_month_candidates[:5]),
            "通过",
            "optional",
            "已在当前月份低频源文件夹中检测到DCS数据",
        )

    base_path = Path(normalize_path(low_freq_base)).expanduser() if low_freq_base else None
    all_candidates = find_dcs_candidates_in_folder(base_path) if base_path and base_path.is_dir() else []
    if not all_candidates:
        return make_input_check(
            "DCS文件",
            "；".join(source_folders),
            "可选缺失",
            "optional",
            "未检测到DCS文件，本月可能无需该数据；如本月应包含DCS，请检查文件夹。",
        )

    dated_candidates = []
    undated_candidates = []
    for path in all_candidates:
        candidate_dt = extract_date_from_text(path)
        if candidate_dt:
            dated_candidates.append((candidate_dt, path))
        else:
            undated_candidates.append(path)

    if end_dt and dated_candidates:
        covering = [item for item in dated_candidates if item[0] >= end_dt]
        if covering:
            covering.sort(key=lambda item: (item[0], item[1].name))
            selected_dt, selected_path = covering[0]
            return make_input_check(
                "DCS文件",
                str(selected_path),
                "通过",
                "optional",
                f"检测到晚于或等于本次处理范围的DCS累计数据（{selected_dt}），可能已覆盖本次处理月份。",
            )

        dated_candidates.sort(key=lambda item: (item[0], item[1].name), reverse=True)
        selected_dt, selected_path = dated_candidates[0]
        return make_input_check(
            "DCS文件",
            str(selected_path),
            "警告",
            "optional",
            f"DCS数据日期早于当前处理月份（{selected_dt}），请确认是否覆盖本次处理范围。",
        )

    return make_input_check(
        "DCS文件",
        "；".join(str(path) for path in undated_candidates[:5]),
        "警告",
        "optional",
        "检测到DCS数据，但无法从文件名或路径识别日期；请确认是否覆盖本次处理范围。",
    )


def summarize_three_channel_check(three_channel_path, start_date, end_date):
    path_text = normalize_path(three_channel_path)
    if not path_text:
        return make_input_check(
            "清华三声道数据",
            "",
            "可选缺失",
            "optional",
            "未配置，将使用核心高频数据中的原始Path3。",
        )

    folder = Path(path_text).expanduser()
    if not folder.is_dir():
        return make_input_check(
            "清华三声道数据",
            path_text,
            "可选缺失",
            "optional",
            "未找到，将使用核心高频数据中的原始Path3。",
        )

    try:
        start_dt = parse_date(start_date)
        end_dt = parse_date(end_date or start_date)
        expected_names = {
            f"S{day.strftime('%y%m%d')}.CSV".lower()
            for day in pd.date_range(start_dt, end_dt, freq="D")
        }
        matched_files = [path for path in folder.iterdir() if path.is_file() and path.name.lower() in expected_names]
    except Exception:
        matched_files = []

    if matched_files:
        return make_input_check(
            "清华三声道数据",
            "；".join(str(path) for path in sorted(matched_files)),
            "通过",
            "optional",
            f"检测到 {len(matched_files)} 天可用数据，将用于修正Path3；其余日期自动使用原始Path3。",
        )
    return make_input_check(
        "清华三声道数据",
        path_text,
        "警告",
        "optional",
        "当前日期无数据，将使用核心高频数据中的原始Path3。",
    )


def output_folder_check(check_name, folder):
    folder_text = normalize_path(folder)
    if not folder_text:
        return make_input_check(check_name, "", "运行时自动创建", "optional", "未配置输出文件夹；运行前建议确认输出目录")
    folder_path = Path(folder_text).expanduser()
    if folder_path.is_dir():
        return make_input_check(check_name, folder_text, "通过", "optional", "输出文件夹已存在")
    return make_input_check(check_name, folder_text, "运行时自动创建", "optional", "输出文件夹不存在，运行时会自动创建")


def check_input_files(config):
    config = derive_paths_from_config(config.copy())
    records = []
    start_date, end_date = date_bounds(config)
    end_dt = parse_date(end_date or start_date) if start_date else None

    project_root = normalize_path(config.get("project_root", ""))
    project_root_path = Path(project_root).expanduser() if project_root else None
    if project_root_path and project_root_path.is_dir():
        records.append(make_input_check("项目根目录", project_root, "通过", "required", "路径存在"))
    else:
        records.append(make_input_check("项目根目录", project_root, "缺失", "required", "项目根目录未配置或不存在"))

    daily_report = normalize_path(config.get("daily_report_path", ""))
    daily_report_path = Path(daily_report).expanduser() if daily_report else None
    if not daily_report:
        records.append(make_input_check("生产综合日报文件", "", "缺失", "required", "运行0号前必须上传或填写生产综合日报文件"))
    elif not daily_report_path.is_file():
        records.append(make_input_check("生产综合日报文件", daily_report, "缺失", "required", "文件不存在"))
    elif daily_report_path.suffix.lower() not in {".xls", ".xlsx"}:
        records.append(make_input_check("生产综合日报文件", daily_report, "缺失", "required", "仅支持 .xls 或 .xlsx 文件"))
    else:
        records.append(make_input_check("生产综合日报文件", daily_report, "通过", "required", "文件存在，格式支持"))

    low_freq_base = normalize_path(config.get("low_freq_output_folder", ""))
    low_freq_base_path = Path(low_freq_base).expanduser() if low_freq_base else None
    if low_freq_base_path and low_freq_base_path.is_dir():
        records.append(make_input_check("低频数据总文件夹", low_freq_base, "通过", "required", "路径存在"))
    else:
        records.append(make_input_check("低频数据总文件夹", low_freq_base, "缺失", "required", "未找到低频数据总文件夹"))

    lowfreq_selection = select_historical_lowfreq_main(low_freq_base, start_date, end_date) if low_freq_base else {"path": "", "file_date": None, "coverage": "missing"}
    if lowfreq_selection.get("path"):
        config["low_freq_main_file"] = lowfreq_selection["path"]
    lowfreq_main = normalize_path(config.get("low_freq_main_file", ""))
    lowfreq_main_path = Path(lowfreq_main).expanduser() if lowfreq_main else None
    if lowfreq_main_path and lowfreq_main_path.is_file():
        file_date = lowfreq_selection.get("file_date") or extract_date_from_text(lowfreq_main_path.name)
        coverage = lowfreq_selection.get("coverage")
        if file_date and start_date and file_date < parse_date(start_date):
            records.append(make_input_check("历史低频主表", lowfreq_main, "通过", "required", "已识别当前处理开始日期之前最近的历史低频主表。"))
        elif file_date and end_dt and file_date <= end_dt:
            records.append(make_input_check("历史低频主表", lowfreq_main, "警告", "required", "当前低频主表日期不早于处理开始日期，将作为覆盖更新基准，请确认不是本次输出文件。"))
        elif file_date and end_dt:
            records.append(make_input_check("历史低频主表", lowfreq_main, "警告", "required", "当前低频主表日期晚于本次处理结束日期，请确认是否误选了后续月份文件。"))
        else:
            records.append(make_input_check("历史低频主表", lowfreq_main, "警告", "required", "文件存在，但无法识别累计日期，请确认是否覆盖本次处理范围。"))
    else:
        records.append(make_input_check("历史低频主表", lowfreq_main, "缺失", "required", "运行1号前必须配置或自动识别历史低频主表"))

    lowfreq_source_folders = expected_lowfreq_month_folders(config)
    if not lowfreq_source_folders:
        records.append(make_input_check("低频源文件夹", "", "缺失", "required", "运行1号前必须配置低频源文件夹"))
    else:
        missing_sources = [folder for folder in lowfreq_source_folders if not Path(normalize_path(folder)).expanduser().is_dir()]
        if missing_sources:
            records.append(make_input_check("低频源文件夹", "；".join(lowfreq_source_folders), "缺失", "required", "未找到低频源文件夹：" + "；".join(missing_sources)))
        else:
            records.append(make_input_check("低频源文件夹", "；".join(lowfreq_source_folders), "通过", "required", "路径存在"))

    high_freq_base = normalize_path(config.get("high_freq_base_path", ""))
    high_freq_base_path = Path(high_freq_base).expanduser() if high_freq_base else None
    if high_freq_base_path and high_freq_base_path.is_dir():
        records.append(make_input_check("核心高频数据文件夹", high_freq_base, "通过", "required", "路径存在"))
    else:
        records.append(make_input_check("核心高频数据文件夹", high_freq_base, "缺失", "required", "运行2号前必须存在"))

    records.append(
        summarize_three_channel_check(
            config.get("three_channel_path", ""),
            start_date,
            end_date,
        )
    )

    records.append(summarize_dcs_check(low_freq_base, lowfreq_source_folders, start_date, end_date))

    optional_sources = [
        ("铜渣文件", ["铜渣"]),
        ("氟化钙污泥文件", ["氟化钙污泥"]),
        ("替代燃料文件", ["替代燃料"]),
    ]
    for check_name, keywords in optional_sources:
        matches = find_lowfreq_optional_files(lowfreq_source_folders, keywords)
        if matches:
            records.append(make_input_check(check_name, "；".join(matches), "通过", "optional", "已检测到可选低频源文件"))
        else:
            records.append(make_input_check(check_name, "；".join(lowfreq_source_folders), "可选缺失", "optional", "未检测到该可选低频源文件；如本月应包含该数据，请检查文件夹。"))

    records.append(output_folder_check("秒级核算输出文件夹", config.get("second_output_folder", "")))
    records.append(output_folder_check("秒级异常检测输出文件夹", config.get("abnormal_output_folder", "")))
    records.append(output_folder_check("15min输出文件夹", config.get("fifteen_output_folder", "")))

    required_missing = [record for record in records if record["level"] == "required" and record["status"] == "缺失"]
    optional_warnings = [record for record in records if record["level"] == "optional" and record["status"] in {"警告", "可选缺失"}]
    return {
        "records": records,
        "required_missing": required_missing,
        "optional_warnings": optional_warnings,
    }


def required_checks_missing(check_result, check_names=None):
    names = set(check_names or [])
    for record in check_result.get("required_missing", []):
        if not names or record["check_name"] in names:
            return True
    return False


def render_input_file_checks(config):
    result = check_input_files(config)
    display_rows = [
        {
            "检查项": record["check_name"],
            "路径": record["path"] or "未配置",
            "类型": "必须" if record["level"] == "required" else "可选",
            "状态": record["status"],
            "说明": record["message"],
        }
        for record in result["records"]
    ]
    st.dataframe(pd.DataFrame(display_rows), hide_index=True, width="stretch")

    if result["required_missing"]:
        render_notice(f"存在 {len(result['required_missing'])} 个必须项缺失，请补齐后再运行对应流程。", "error")
    elif result["optional_warnings"]:
        render_notice("必须项均已通过；可选项缺失只作提醒，不会阻止流程运行。", "warning")
    else:
        render_notice("运行前检查通过。", "success")
    return result


def render_pipeline_path_overview(config):
    config = derive_paths_from_config(config)
    lowfreq_output = expected_lowfreq_output(config)
    lowfreq_source_folders = expected_lowfreq_month_folders(config)
    second_result_outputs = expected_daily_outputs(
        config,
        "second_output_folder",
        "秒级CO2排放结果.xlsx",
        "last_second_outputs",
    )
    abnormal_outputs = expected_daily_outputs(
        config,
        "abnormal_output_folder",
        "秒级异常检测结果.xlsx",
        "last_abnormal_outputs",
    )
    fifteen_outputs = expected_15min_outputs(config)

    cards = [
        path_summary_card_html(
            "0号：日报数据提取路径",
            [
                ("生产综合日报输入文件路径", config.get("daily_report_path", ""), "file"),
                ("0号提取结果输出文件路径", config.get("daily_extract_output", ""), "file", "output"),
            ],
        ),
        path_summary_card_html(
            "1号：低频数据汇总路径",
            [
                (
                    "输入：历史低频主表（必填基准表）",
                    config.get("low_freq_main_file", ""),
                    "file",
                    "required_input",
                    "低频主表路径未配置，请在项目配置页上传或填写低频主表 Excel 文件。",
                ),
                ("输入：低频源文件夹路径", lowfreq_source_folders, "folder"),
                ("低频汇总输出文件夹路径", config.get("low_freq_output_folder", ""), "folder", "folder_output"),
                ("输出：1号低频汇总表", lowfreq_output, "file", "output"),
            ],
            "数据流向：低频主表 + 低频源文件夹 → 1号生成低频汇总表 → 2号读取低频汇总表",
        ),
        path_summary_card_html(
            "2号：秒级核算与异常检测路径",
            [
                ("核心高频数据母路径", config.get("high_freq_base_path", ""), "folder"),
                (
                    "清华三声道数据路径（可选）",
                    config.get("three_channel_path", ""),
                    "folder",
                    "optional_input",
                    "未配置时将使用原始Path3",
                ),
                ("2号读取的低频汇总表路径", lowfreq_output, "file", "generated", "等待 1号完成后生成"),
                ("秒级核算结果输出文件夹", config.get("second_output_folder", ""), "folder", "folder_output"),
                ("秒级异常检测结果输出文件夹", config.get("abnormal_output_folder", ""), "folder", "folder_output"),
                ("2号最终输出秒级结果路径", second_result_outputs, "file", "output"),
                ("2号最终输出异常检测路径", abnormal_outputs, "file", "output"),
            ],
            "数据流向：2号输出秒级核算结果 → 3号读取秒级结果",
        ),
        path_summary_card_html(
            "3号：15min聚合路径",
            [
                ("3号输入文件夹路径（2号秒级核算结果输出文件夹）", config.get("second_output_folder", ""), "folder", "folder_output"),
                ("3号输出文件夹路径", config.get("fifteen_output_folder", ""), "folder", "folder_output"),
                ("3号最终输出文件路径", fifteen_outputs, "file", "output"),
            ],
            "数据流向：3号输出15min聚合结果 → 图表模块读取15min结果",
        ),
    ]
    st.markdown(f'<div class="path-overview-grid">{"".join(cards)}</div>', unsafe_allow_html=True)


def h(value):
    return escape(str(value or ""))


def render_page_title(title):
    st.markdown(f'<div class="page-title">{h(title)}</div>', unsafe_allow_html=True)


def render_section_title(title, compact=False, extra_class=""):
    classes = ["section-title"]
    if compact:
        classes.append("compact")
    if extra_class:
        classes.append(extra_class)
    st.markdown(f'<div class="{" ".join(classes)}">{h(title)}</div>', unsafe_allow_html=True)


def logo_data_uri():
    if not LOGO_PATH.exists():
        return ""
    try:
        encoded = base64.b64encode(LOGO_PATH.read_bytes()).decode("ascii")
        return f"data:image/png;base64,{encoded}"
    except Exception:
        return ""


def render_status_badge(status):
    meta = STATUS_META.get(status, STATUS_META["未开始"])
    return (
        f'<span class="status-badge" '
        f'style="color:{meta["fg"]};background:{meta["bg"]};border-color:{meta["border"]};">'
        f'<span class="status-dot" style="background:{meta["dot"]};"></span>{h(status)}</span>'
    )


def render_notice(message, kind="neutral"):
    st.markdown(
        f"""
        <div class="notice {h(kind)}">
            <span class="notice-dot"></span>
            <div>{h(message)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_card_header(title, subtitle=""):
    st.markdown(
        f"""
        <div class="card-shell">
            <div class="card-title">{h(title)}</div>
            <div class="card-subtitle">{h(subtitle)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_header():
    logo_uri = logo_data_uri()
    logo_html = f'<img class="brand-logo" src="{logo_uri}" alt="CONCH logo">' if logo_uri else ""
    st.markdown(
        f"""
        <div class="main-title">
            <div class="brand-left">
                {logo_html}
                <div class="brand-copy">
                    <h1>海螺水泥碳排放数据处理系统</h1>
                    <p>詹宇轩1.0版</p>
                </div>
            </div>
            <div class="header-actions">
                <span class="header-pill">本地 Streamlit</span>
                <span class="header-pill">内部工具</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_flow_cards(step_labels=None):
    step_labels = step_labels or STEP_LABELS
    items = []
    for idx, (key, label) in enumerate(step_labels):
        status = st.session_state.step_status.get(key, "未开始")
        items.append(
            f'<div class="step-card"><div class="step-title" title="{h(label)}">{h(label)}</div>'
            f"<div>{render_status_badge(status)}</div></div>"
        )
        if idx < len(step_labels) - 1:
            items.append('<div class="step-arrow">→</div>')

    st.markdown(
        f'<div class="step-flow-container">{"".join(items)}</div>',
        unsafe_allow_html=True,
    )


def render_record_status(status):
    status_text = str(status or "未记录")
    class_name = "neutral"
    if status_text in {"成功"}:
        class_name = "success"
    elif status_text in {"通过"}:
        class_name = "pass"
    elif status_text in {"失败"}:
        class_name = "error"
    elif status_text in {"未通过"}:
        class_name = "fail"
    elif status_text in {"运行中"}:
        class_name = "running"
    return (
        f'<span class="run-record-status {class_name}">'
        f'<span class="run-record-status-dot"></span>{h(status_text)}</span>'
    )


def render_run_record_card(record):
    output_files = compact_record_output(record.get("output_files", "")) or "无"
    message = record.get("message", "") or "无"
    date_range = record.get("date_range", "") or "未记录"
    st.markdown(
        f"""
        <div class="run-record-card">
            <div class="run-record-top">
                <span class="run-record-time">{h(record.get("timestamp", ""))}</span>
                {render_record_status(record.get("status", ""))}
            </div>
            <div class="run-record-step">{h(record.get("step", "未记录流程"))}</div>
            <div class="run-record-grid">
                <div class="run-record-label">数据范围</div>
                <div class="run-record-value">{h(date_range)}</div>
                <div class="run-record-label">输出文件</div>
                <div class="run-record-value">{h(output_files)}</div>
                <div class="run-record-label">备注</div>
                <div class="run-record-value">{h(message)}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_run_record_summary_card(record):
    message = record.get("message", "") or "无"
    date_range = record.get("date_range", "") or "未记录"
    output_files = compact_record_output(record.get("output_files", "")) or "无"
    st.markdown(
        f"""
        <div class="run-record-card">
            <div class="run-record-top">
                <span class="run-record-time">{h(record.get("timestamp", ""))}</span>
                {render_record_status(record.get("status", ""))}
            </div>
            <div class="run-record-step">{h(record.get("step", "未记录流程"))}</div>
            <div class="run-record-grid">
                <div class="run-record-label">数据范围</div>
                <div class="run-record-value">{h(date_range)}</div>
                <div class="run-record-label">备注</div>
                <div class="run-record-value">{h(message)}</div>
                <div class="run-record-label">输出</div>
                <div class="run-record-value">{h(output_files)}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_recent_run_summary(limit=3, title=None):
    if title:
        render_section_title(title, compact=True)
    records = list(reversed(st.session_state.get("run_records", [])))
    if not records:
        render_notice("暂无运行记录。", "neutral")
        return
    st.markdown('<div class="run-records">', unsafe_allow_html=True)
    for record in records[:limit]:
        render_run_record_summary_card(record)
    st.markdown("</div>", unsafe_allow_html=True)


def render_log_panel(title="运行记录", step_filter=None, show_actions=True, empty_message="暂无运行记录。"):
    display_options = {"最近10条": 10, "最近20条": 20, "全部": None}
    filter_set = set(step_filter or [])

    title_col, range_col = st.columns([5, 2.2])
    with title_col:
        render_section_title(title, compact=True, extra_class="record-title")
    with range_col:
        range_label_col, range_select_col = st.columns([0.8, 1.25])
        with range_label_col:
            st.markdown(
                '<div class="record-filter-label">显示范围</div>',
                unsafe_allow_html=True,
            )
        with range_select_col:
            selected_range = st.selectbox(
                "显示范围",
                options=list(display_options.keys()),
                index=1,
                key="run_record_display_range",
                label_visibility="collapsed",
            )

    if show_actions:
        st.markdown(
            '<div class="record-subtitle">仅记录关键数据处理流程，本地保存于 outputs/run_log.csv</div>',
            unsafe_allow_html=True,
        )

        col_refresh, col_export, col_clear, col_confirm = st.columns([1, 1, 1, 2])
        with col_confirm:
            confirm_clear = st.checkbox("我确认要清空本地运行记录", key="confirm_clear_run_records")
        with col_refresh:
            if st.button("刷新记录", width="stretch"):
                st.session_state.run_records = load_run_records()
        with col_export:
            ensure_run_log_file()
            st.download_button(
                "导出运行记录",
                data=RUN_LOG_PATH.read_bytes(),
                file_name="run_log.csv",
                mime="text/csv",
                width="stretch",
            )
        with col_clear:
            if st.button("清空本地记录", disabled=not confirm_clear, width="stretch"):
                clear_run_records()
    else:
        st.markdown(
            '<div class="record-subtitle">仅显示本页面相关的关键运行记录。</div>',
            unsafe_allow_html=True,
        )

    records = st.session_state.get("run_records", [])
    if filter_set:
        records = [record for record in records if record.get("step", "") in filter_set]
    if not records:
        render_notice(empty_message, "neutral")
        return

    latest_records = list(reversed(records))
    limit = display_options[selected_range]
    if limit is not None:
        latest_records = latest_records[:limit]

    st.markdown('<div class="run-records">', unsafe_allow_html=True)
    for record in latest_records:
        render_run_record_card(record)
    st.markdown("</div>", unsafe_allow_html=True)


def set_pipeline_summary(status, date_range, output_files="", message=""):
    st.session_state.pipeline_run_summary = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "step": "一键运行后续流程",
        "date_range": date_range,
        "status": status,
        "output_files": format_output_files(output_files),
        "message": message,
    }


def render_pipeline_summary():
    summary = st.session_state.get("pipeline_run_summary")
    if not summary:
        return
    render_section_title("本次运行摘要", compact=True)
    render_run_record_card(summary)


def render_path_card(label, value):
    st.markdown(
        f"""
        <div class="metric-card">
            <div class="label">{h(label)}</div>
            <div class="small-path">{h(value or "未配置")}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def summarize_check_items(items, limit=3):
    names = [str(item.get("check_name", "")) for item in items if item.get("check_name")]
    if not names:
        return ""
    visible_names = names[:limit]
    suffix = f" 等 {len(names)} 项" if len(names) > limit else ""
    return "、".join(visible_names) + suffix


def render_current_task_summary(config, input_check=None, range_ok=True):
    required_missing = (input_check or {}).get("required_missing", [])
    if required_missing:
        config_status = f"必需项缺失：{summarize_check_items(required_missing)}"
    elif not range_ok:
        config_status = "日期范围需要调整"
    else:
        config_status = "必需项已通过"

    render_section_title("当前任务", compact=True)
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        render_path_card("数据范围", current_date_range(config))
    with c2:
        render_path_card("项目根目录", config.get("project_root", ""))
    with c3:
        render_path_card("0号审核", "已通过" if st.session_state.audit_passed else "未通过")
    with c4:
        render_path_card("当前配置状态", config_status)
    render_notice("如需修改项目根目录、日期范围或数据文件，请前往项目配置页面。", "neutral")


def render_preflight_summary(input_check):
    required_missing = input_check.get("required_missing", [])
    optional_warnings = input_check.get("optional_warnings", [])

    render_section_title("运行前检查", compact=True)
    c1, c2 = st.columns(2)
    with c1:
        if required_missing:
            render_path_card("必需项", f"缺失：{summarize_check_items(required_missing)}")
        else:
            render_path_card("必需项", "全部通过")
    with c2:
        if optional_warnings:
            render_path_card("可选项", f"{summarize_check_items(optional_warnings)} 未完全检测到，不影响运行")
        else:
            render_path_card("可选项", "未发现影响运行的提醒")

    if required_missing:
        render_notice("运行前检查存在必需项缺失，已阻止一键运行。", "error")
    elif optional_warnings:
        render_notice("可选项存在提醒，不会阻止流程运行。", "warning")
    else:
        render_notice("运行前检查通过。", "success")


def render_pipeline_result_locations(config):
    summary = st.session_state.get("pipeline_run_summary")
    if not summary or summary.get("status") != "成功":
        return

    render_section_title("本次运行结果", compact=True)
    rows = [
        ("1号低频汇总结果", "已生成", config.get("low_freq_output_folder", "")),
        ("2号秒级核算结果", "已生成", config.get("second_output_folder", "")),
        ("2号异常检测结果", "已生成", config.get("abnormal_output_folder", "")),
        ("3号15min聚合结果", "已生成", config.get("fifteen_output_folder", "")),
    ]
    for label, status, folder in rows:
        st.markdown(
            f"""
            <div class="path-item">
                <div class="path-label">{h(label)}</div>
                <div class="path-value">{h(status)}</div>
                <div class="result-output-path">输出位置：{h(folder or "未配置")}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def get_config():
    if "config" not in st.session_state:
        st.session_state.config = normalize_config_paths(load_json(CONFIG_PATH, default={}))
    current_config = merge_session_inputs_into_config(st.session_state.config)
    st.session_state.config = apply_runtime_dates_to_config(current_config)
    return st.session_state.config


def find_lowfreq_main_file_for_range(low_freq_base_folder, start_date, end_date):
    return select_historical_lowfreq_main(low_freq_base_folder, start_date, end_date).get("path", "")


def auto_fill_standard_paths(config):
    project_root = config.get("project_root", "")
    if not project_root:
        return config, {
            "status": "failed",
            "recognized_dirs": [],
            "missing_dirs": [],
            "core_validation": None,
        }

    standard_dirs = find_standard_data_dirs(project_root)
    recognized_dirs = [item for item in standard_dirs.values() if item["exists"]]
    missing_dirs = [item for item in standard_dirs.values() if not item["exists"] and item["label"] != "源代码目录"]

    start_date = config.get("start_date", "")
    end_date = config.get("end_date", "")
    config = derive_paths_from_config(config, force_auto=True)
    core_validation = None
    if start_date and end_date:
        core_validation = validate_core_high_freq_dir(project_root, start_date, end_date)
        if core_validation.get("status") != "missing_core_dir":
            config["high_freq_base_path"] = core_validation["core_dir"]

    if not recognized_dirs:
        status = "failed"
    elif core_validation and core_validation.get("status") == "complete" and not missing_dirs:
        status = "complete"
    else:
        status = "partial"

    return config, {
        "status": status,
        "project_root": str(project_root),
        "start_date": str(start_date or ""),
        "end_date": str(end_date or ""),
        "recognized_dirs": recognized_dirs,
        "missing_dirs": missing_dirs,
        "core_validation": core_validation,
    }


def render_auto_fill_result(result):
    if not result:
        return

    root_issue = result.get("root_issue")
    if root_issue:
        render_section_title("自动填充检查结果", compact=True)
        render_notice(root_issue.get("message", "自动填充失败，请检查项目根目录。"), "error")
        current_path = root_issue.get("current_path") or result.get("project_root")
        if current_path:
            st.caption("当前填写的项目根目录：")
            st.code(current_path)
        expected_raw_data_path = root_issue.get("expected_raw_data_path")
        if expected_raw_data_path:
            st.caption("系统期望找到：")
            st.code(expected_raw_data_path)
        return

    core_validation = result.get("core_validation")
    if result.get("recognized_dirs"):
        render_section_title("自动填充识别结果", compact=True)
        for item in result["recognized_dirs"]:
            st.caption(f"已识别{item['label']}：{item['path']}")

    if core_validation:
        if core_validation["status"] == "missing_core_dir":
            render_notice("未找到核心高频数据父目录，请检查项目根目录是否填写正确。", "error")
            st.code(core_validation["core_dir"])
        else:
            render_section_title("核心高频数据日期范围检查", compact=True)
            st.caption(f"核心高频数据目录：{core_validation['core_dir']}")
            st.caption(
                f"应有日期文件夹 {core_validation['expected_count']} 个；"
                f"实际找到 {core_validation['found_count']} 个；"
                f"缺失 {len(core_validation['missing_dates'])} 个。"
            )
            if core_validation["missing_dates"]:
                render_notice("已填充核心高频数据父目录，但日期范围内存在缺失文件夹。", "warning")
                st.code("\n".join(core_validation["missing_dates"]))
            else:
                render_notice("已自动填充核心高频数据路径，并完成日期范围检查。", "success")

    if result.get("missing_dirs"):
        render_section_title("未识别到的标准目录", compact=True)
        for item in result["missing_dirs"]:
            st.caption(f"{item['label']}：{item['path']}")


def page_home():
    render_page_title("工作台")
    render_flow_cards(HOME_FLOW_LABELS)
    st.write("")
    config = get_config()
    overall_status = "审核通过，后续流程可运行" if st.session_state.audit_passed else "等待0号审核"
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        render_path_card("项目根目录", config.get("project_root", ""))
    with c2:
        render_path_card("数据处理范围", f"{config.get('start_date', '')} 至 {config.get('end_date', '')}")
    with c3:
        render_path_card("当前状态", overall_status)
    with c4:
        audit_text = "已审核" if st.session_state.audit_passed else "未审核"
        render_path_card("0号结果审核", audit_text)

    render_notice("0号提取结果通过审核后，后续 1、2、3 号流程才允许运行。", "neutral")
    with st.expander("运行记录", expanded=False):
        render_log_panel(title="运行记录")


def page_project_config():
    render_page_title("项目配置")
    hydrate_config_inputs_from_config()
    sync_date_widgets_from_runtime()
    if st.session_state.get("run_in_progress"):
        render_notice("当前任务正在运行，请勿修改项目配置。页面切换不会清空当前配置。", "warning")
    render_notice(
        "单个 Excel 文件可点击上传框选择或拖拽上传；文件夹路径请从 Finder 复制路径后粘贴，系统会自动识别 Mac 中文目录别名，例如“文稿”会自动转换为 Documents。",
        "neutral",
    )

    if st.session_state.config_notice:
        notice_kind = st.session_state.get("config_notice_kind", "neutral")
        render_notice(st.session_state.config_notice, notice_kind)
        st.session_state.config_notice = ""
        st.session_state.config_notice_kind = "neutral"

    with st.container(border=True):
        render_section_title("基础信息", compact=True)
        render_project_root_input()
        col_start, col_end = st.columns(2)
        with col_start:
            st.date_input(
                "数据处理开始日期",
                key=START_DATE_WIDGET_KEY,
                value=None,
                format="YYYY/MM/DD",
                on_change=persist_current_config_from_inputs,
            )
        with col_end:
            st.date_input(
                "数据处理结束日期",
                key=END_DATE_WIDGET_KEY,
                value=None,
                format="YYYY/MM/DD",
                on_change=persist_current_config_from_inputs,
            )
        st.button(
            "自动填充标准路径",
            key="auto_fill_paths",
            on_click=auto_fill_standard_path_inputs,
            width="stretch",
        )
        render_auto_fill_result(st.session_state.get("auto_fill_result"))

        project_root = normalize_path(st.session_state.get("project_root_input", ""))
        if project_root:
            check = check_project_structure(project_root)
            if check["ok"]:
                render_notice("文件夹结构检查通过", "success")
            else:
                render_notice("缺失文件夹：" + "，".join(check["missing"]), "error")
                st.caption("请先创建该文件夹，或检查项目根目录是否选择正确。")
        else:
            render_notice("请先填写项目根目录和日期，再自动填充标准路径。", "neutral")

    with st.container(border=True):
        render_section_title("0号日报提取路径", compact=True)
        render_excel_upload(
            "点击或拖拽上传生产综合日报（支持 .xls / .xlsx）",
            "daily_report_path",
            "project_daily_report_upload",
            DAILY_EXCEL_TYPES,
            "daily_report",
        )
        st.text_input("生产综合日报路径（可手动填写已有文件路径）", key="daily_report_path_input", on_change=persist_current_config_from_inputs)
        render_path_check(st.session_state.get("daily_report_path_input", ""), "file")
        render_daily_report_upload_warning(st.session_state.get("daily_report_path_input", ""))
        set_daily_output_default(overwrite=False)
        st.text_input("0号输出文件路径", key="daily_extract_output_input", on_change=persist_current_config_from_inputs)

    with st.container(border=True):
        render_section_title("1号低频汇总路径", compact=True)
        render_excel_upload(
            "点击或拖拽上传低频主表（支持 .xlsx）",
            "low_freq_main_file",
            "project_lowfreq_main_upload",
            LOWFREQ_EXCEL_TYPES,
            "lowfreq_main",
        )
        st.text_input("历史低频主表路径（1号必填基准表，可手动填写已有文件路径）", key="low_freq_main_file_input", on_change=persist_current_config_from_inputs)
        render_path_check(st.session_state.get("low_freq_main_file_input", ""), "file")
        render_folder_input("低频源文件夹路径", "low_freq_source_folder")
        render_output_folder_input(
            "低频汇总输出文件夹路径",
            "low_freq_output_folder",
            exists_message="路径存在，1号低频汇总结果将输出到此文件夹",
        )

    with st.container(border=True):
        render_section_title("2号：秒级核算与异常检测路径", compact=True)
        render_folder_input("核心高频数据母路径", "high_freq_base_path")
        render_folder_input(
            "清华三声道数据路径（可选）",
            "three_channel_path",
            help_text="三声道数据已停止持续更新。若当前日期存在对应三声道文件，则用于修正标干流量Path3；若不存在，则自动使用核心高频数据中的原始标干流量Path3，不影响正常计算。",
            optional=True,
        )
        render_output_folder_input("秒级核算结果输出文件夹", "second_output_folder")
        render_output_folder_input("秒级异常检测结果输出文件夹", "abnormal_output_folder")

    with st.container(border=True):
        render_section_title("3号：15min聚合路径", compact=True)
        st.markdown(
            render_path_item(
                "3号输入文件夹路径（2号秒级核算结果输出文件夹）",
                st.session_state.get("second_output_folder_input", ""),
                "folder",
                "folder_output",
            ),
            unsafe_allow_html=True,
        )
        render_output_folder_input("3号输出文件夹路径", "fifteen_output_folder")

    render_section_title("代码路径总览")
    preview_config = collect_config_from_inputs(
        current_start_date_value(),
        current_end_date_value(),
    )
    render_pipeline_path_overview(preview_config)

    render_section_title("数据文件检查结果")
    render_input_file_checks(preview_config)

    st.button(
        "保存项目配置",
        type="primary",
        key="save_project_config",
        on_click=save_project_config_inputs,
        width="stretch",
    )
    st.caption(f"配置文件：{CONFIG_PATH}")
    if st.session_state.config_saved_at:
        render_notice(f"上次保存时间：{st.session_state.config_saved_at}", "neutral")


def render_zero_audit_section(config, output_path, preview_df):
    render_section_title("0号结果审核")
    audit_status = "已通过" if st.session_state.audit_passed else "未通过"
    render_notice(f"当前审核状态：{audit_status}", "success" if st.session_state.audit_passed else "neutral")
    audit_note = st.text_area("审核备注（可选）", key="audit_note_input", height=90)

    output_matches_range = preview_matches_current_range(preview_df, config)
    can_audit = preview_df is not None and output_path is not None and output_path.is_file() and output_matches_range
    if not can_audit:
        if preview_df is not None and output_path is not None and output_path.is_file() and not output_matches_range:
            render_notice("当前0号结果为空或日期范围与当前配置不一致，请重新运行0号日报提取后再审核。", "warning")
        else:
            render_notice("请先运行0号日报提取并生成结果后再审核。", "neutral")
        return

    col_pass, col_fail = st.columns([1, 1])
    with col_pass:
        if st.button("审核通过，进入后续流程", type="primary", width="stretch"):
            st.session_state.audit_passed = True
            set_status("review", "已完成")
            message = "0号结果已审核通过，允许继续运行后续流程"
            if audit_note.strip():
                message = f"{message}；备注：{audit_note.strip()}"
            append_run_record(
                step="0号结果审核",
                status="通过",
                date_range=current_date_range(config),
                message=message,
            )
            render_notice("审核已通过，可以运行后续流程。", "success")
    with col_fail:
        if st.button("审核不通过，返回修改", width="stretch"):
            st.session_state.audit_passed = False
            set_status("review", "失败")
            message = "0号结果未通过审核"
            if audit_note.strip():
                message = f"{message}；备注：{audit_note.strip()}"
            append_run_record(
                step="0号结果审核",
                status="未通过",
                date_range=current_date_range(config),
                message=message,
            )
            render_notice("已记录审核不通过，请修改提取规则或重新运行0号。", "warning")


def page_extract_report():
    render_page_title("0号：日报数据提取")
    hydrate_config_inputs_from_config()
    render_cell_map_editor()

    with st.container(border=True):
        render_section_title("输入配置", compact=True)
        render_excel_upload(
            "点击或拖拽上传生产综合日报（支持 .xls / .xlsx）",
            "daily_report_path",
            "extract_daily_report_upload",
            DAILY_EXCEL_TYPES,
            "daily_report",
        )
        st.text_input("生产综合日报路径（可手动填写已有文件路径）", key="daily_report_path_input", on_change=persist_current_config_from_inputs)
        render_path_check(st.session_state.get("daily_report_path_input", ""), "file")
        render_daily_report_upload_warning(st.session_state.get("daily_report_path_input", ""))
        set_daily_output_default(overwrite=False)
        st.text_input("输出文件路径", key="daily_extract_output_input", on_change=persist_current_config_from_inputs)

    input_path_text = normalize_path(st.session_state.get("daily_report_path_input", ""))
    output_path_text = normalize_path(st.session_state.get("daily_extract_output_input", ""))
    extract_config = collect_config_from_inputs(
        current_start_date_value(),
        current_end_date_value(),
    )
    write_runtime_debug("ZERO PAGE LOAD", extract_config, source="runtime_config")
    extract_range_ok, extract_range_message = validate_single_month_range(
        extract_config.get("start_date", ""),
        extract_config.get("end_date", ""),
    )
    extract_check = check_input_files(extract_config)
    extract_required_missing = required_checks_missing(extract_check, {"项目根目录", "生产综合日报文件"})
    can_run_extract = bool(
        input_path_text
        and not is_app_upload_path(input_path_text)
        and Path(input_path_text).expanduser().is_file()
        and output_path_text
        and not is_app_upload_path(output_path_text)
        and extract_range_ok
        and not extract_required_missing
    )
    if not extract_range_ok:
        render_notice(extract_range_message, "error")
    if not can_run_extract:
        render_notice("请先上传生产综合日报或填写有效路径，并确认项目根目录存在。", "warning")
    with st.container(border=True):
        render_section_title("当前运行配置", compact=True)
        st.caption(f"当前运行日期范围：{current_date_range(extract_config)}")
        st.caption(f"当前生产日报路径：{input_path_text or '未配置'}")
        st.caption(f"当前0号输出路径：{output_path_text or '未配置'}")

    if st.button("运行0号日报提取", type="primary", disabled=not can_run_extract):
        config = collect_config_from_inputs(
            current_start_date_value(),
            current_end_date_value(),
        )
        range_ok, range_message = validate_single_month_range(config.get("start_date", ""), config.get("end_date", ""))
        if not range_ok:
            render_notice(range_message, "error")
            return
        daily_report_path = config.get("daily_report_path", "")
        daily_extract_output = config.get("daily_extract_output", "")
        config["daily_report_path"] = daily_report_path
        config["daily_extract_output"] = daily_extract_output
        save_config(config)
        write_runtime_debug(
            "ZERO RUN",
            st.session_state.config,
            source="runtime_config",
            extra={
                "daily_report_file_path": daily_report_path,
                "zero_output_file_path": daily_extract_output,
            },
        )
        set_status("step0", "运行中")
        st.session_state.audit_passed = False
        temp_output_path = None
        diagnostics = {}
        try:
            with st.spinner("正在提取生产日报..."):
                final_output_path = Path(normalize_path(daily_extract_output)).expanduser()
                temp_output_path = final_output_path.with_name(
                    f"{final_output_path.stem}.tmp_{datetime.now().strftime('%Y%m%d%H%M%S')}{final_output_path.suffix}"
                )
                result = run_extract_report(
                    daily_report_path,
                    temp_output_path,
                    cell_map_path=CELL_MAP_PATH,
                    logger=ignore_module_log,
                )
                diagnostics = filter_daily_extract_output_by_range(
                    temp_output_path,
                    config.get("start_date", ""),
                    config.get("end_date", ""),
                )
                filtered_rows = diagnostics.get("filtered_rows", 0)
                if filtered_rows <= 0:
                    raise ValueError(
                        f"未提取到{current_date_range(config)}范围内的数据，请检查生产综合日报内容、日期列解析及文件路径。"
                    )
                final_output_path.parent.mkdir(parents=True, exist_ok=True)
                temp_output_path.replace(final_output_path)
            set_status("step0", "已完成")
            set_status("review", "等待运行")
            display_rows = filtered_rows if filtered_rows is not None else result["rows"]
            render_notice(f"提取完成，共 {display_rows} 行", "success")
            append_run_record(
                step="0号日报提取",
                status="成功",
                date_range=current_date_range(config),
                output_files=compact_file_name(daily_extract_output),
                message=f"已完成生产综合日报数据提取，提取行数：{display_rows}",
            )
        except Exception as exc:
            set_status("step0", "失败")
            set_status("review", "失败")
            st.session_state.audit_passed = False
            if temp_output_path and temp_output_path.exists():
                try:
                    temp_output_path.unlink()
                except Exception:
                    pass
            tb = format_exception(exc)
            append_run_record(
                step="0号日报提取",
                status="失败",
                date_range=current_date_range(config),
                message=str(exc),
            )
            render_notice(str(exc), "error")
            st.code(format_extract_debug_info(config, daily_report_path, daily_extract_output, diagnostics))
            st.code(tb)

    output_path_text = normalize_path(st.session_state.get("daily_extract_output_input", ""))
    output_path = Path(str(output_path_text).strip()).expanduser() if str(output_path_text).strip() else None
    preview_df = None
    render_section_title("0号提取结果预览")
    if output_path and output_path.is_file():
        preview_df = safe_read_excel_for_audit(output_path)
        if preview_df is not None:
            with st.container(border=True):
                st.dataframe(preview_df.head(100), width="stretch")
                st.download_button(
                    "另存为 生产日报提取结果.xlsx",
                    data=file_bytes(output_path),
                    file_name=output_path.name,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    type="primary",
                )
    else:
        render_notice("请先运行0号日报提取。", "neutral")

    render_zero_audit_section(extract_config, output_path, preview_df)
    render_log_panel(
        title="0号相关运行记录",
        step_filter={"0号日报提取", "0号结果审核"},
        show_actions=False,
        empty_message="暂无0号相关运行记录。",
    )


def page_run_pipeline():
    config = derive_paths_from_config(get_config().copy())
    render_page_title("一键运行后续流程")
    range_ok, range_message = validate_single_month_range(config.get("start_date", ""), config.get("end_date", ""))
    if not range_ok:
        render_notice(range_message, "error")
    if not st.session_state.audit_passed:
        render_notice("请先完成0号提取结果审核", "warning")

    input_check = check_input_files(config)
    has_required_missing = bool(input_check["required_missing"])
    render_current_task_summary(config, input_check, range_ok)
    render_preflight_summary(input_check)

    lowfreq_main_path_text = normalize_path(config.get("low_freq_main_file", ""))
    lowfreq_main_ready = bool(lowfreq_main_path_text and Path(lowfreq_main_path_text).expanduser().is_file())
    lowfreq_source_folders = expected_lowfreq_month_folders(config)
    if not normalize_path(config.get("low_freq_source_folder", "")) and len(lowfreq_source_folders) == 1:
        config["low_freq_source_folder"] = lowfreq_source_folders[0]
    missing_lowfreq_sources = [folder for folder in lowfreq_source_folders if not Path(folder).expanduser().is_dir()]
    if not lowfreq_source_folders:
        missing_lowfreq_sources = ["未配置低频源文件夹"]

    if st.session_state.audit_passed and not lowfreq_main_ready:
        render_notice("低频主表路径未配置，请在“项目配置”页上传或填写低频主表 Excel 文件。1号流程需要该历史主表作为基准表。", "warning")
    if st.session_state.audit_passed and missing_lowfreq_sources:
        render_notice("未找到低频源文件夹，请检查项目根目录或日期范围。", "error")
    if st.session_state.audit_passed and len(lowfreq_source_folders) > 1:
        render_notice("当前数据处理范围跨月，页面已检查多个低频月份文件夹。请确认 1号流程所需低频源文件已准备完整。", "neutral")

    render_section_title("本次运行进度", compact=True)
    st.markdown(
        f"""
        <div class="stepper">
            <div class="stepper-row"><span class="stepper-title">1号低频数据汇总</span>{render_status_badge(st.session_state.step_status.get("step1", "等待运行"))}</div>
            <div class="stepper-row"><span class="stepper-title">2号秒级核算与异常检测</span>{render_status_badge(st.session_state.step_status.get("step2", "等待运行"))}</div>
            <div class="stepper-row"><span class="stepper-title">3号15min数据聚合</span>{render_status_badge(st.session_state.step_status.get("step3", "等待运行"))}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    can_run_pipeline = st.session_state.audit_passed and range_ok and lowfreq_main_ready and not missing_lowfreq_sources and not has_required_missing
    if st.button("开始运行1号、2号、3号", type="primary", disabled=not can_run_pipeline):
        run_config_snapshot = derive_paths_from_config(get_current_config().copy())
        st.session_state.last_run_config = run_config_snapshot.copy()
        st.session_state.run_in_progress = True
        config = run_config_snapshot
        run_date_range = current_date_range(config)
        pipeline_output_summary = "低频汇总结果；秒级核算结果；异常检测结果；15min聚合结果"
        set_status("step1", "等待运行")
        set_status("step2", "等待运行")
        set_status("step3", "等待运行")
        set_pipeline_summary(
            "运行中",
            run_date_range,
            "",
            "开始运行1号、2号、3号流程",
        )
        append_run_record(
            step="一键运行后续流程",
            status="运行中",
            date_range=run_date_range,
            message="开始运行1号、2号、3号流程",
        )
        try:
            set_status("step1", "运行中")
            current_daily_extract_output = expected_daily_extract_output(config)
            config["daily_extract_output"] = current_daily_extract_output
            with st.spinner("正在运行1号低频数据汇总..."):
                lowfreq_result = run_lowfreq_update(
                    config.get("low_freq_main_file", ""),
                    config.get("low_freq_source_folder", ""),
                    config.get("low_freq_output_folder", ""),
                    config.get("start_date", ""),
                    config.get("end_date", ""),
                    daily_extract_path=current_daily_extract_output,
                    logger=write_process_debug,
                )
                lowfreq_verify = verify_lowfreq_output_for_current_range(
                    lowfreq_result["output_path"],
                    config.get("start_date", ""),
                    config.get("end_date", ""),
                )
            set_status("step1", "已完成")
            config["last_low_freq_output"] = lowfreq_result["output_path"]
            save_config(config)
            render_notice(f"1号完成：{lowfreq_result['output_path']}", "success")
            append_run_record(
                step="1号低频汇总",
                status="成功",
                date_range=run_date_range,
                output_files=compact_file_name(lowfreq_result["output_path"]),
                message=f"已生成低频汇总表，并包含当前日期范围数据（{lowfreq_verify['target_range_rows']} 行）。",
            )
        except Exception as exc:
            set_status("step1", "失败")
            set_status("step2", "未运行")
            set_status("step3", "未运行")
            st.session_state.run_in_progress = False
            tb = format_exception(exc)
            stop_message = "1号低频汇总未成功写入当前日期范围数据，已停止后续2号、3号流程。"
            append_run_record(
                step="1号低频汇总",
                status="失败",
                date_range=run_date_range,
                message=stop_message,
            )
            append_run_record(
                step="一键运行后续流程",
                status="失败",
                date_range=run_date_range,
                message=stop_message,
            )
            set_pipeline_summary(
                "失败",
                run_date_range,
                "",
                stop_message,
            )
            render_notice(stop_message, "error")
            st.code(tb)
            render_pipeline_summary()
            render_pipeline_result_locations(config)
            return

        try:
            set_status("step2", "运行中")
            with st.spinner("正在运行2号秒级核算与异常检测..."):
                second_result = run_second_calc(
                    config.get("high_freq_base_path", ""),
                    config["last_low_freq_output"],
                    config.get("three_channel_path", ""),
                    config.get("second_output_folder", ""),
                    config.get("abnormal_output_folder", ""),
                    config.get("start_date", ""),
                    config.get("end_date", ""),
                    logger=write_process_debug,
                )
            second_success_count = len(second_result.get("success_dates", []))
            second_skipped_count = len(second_result.get("skipped_dates", []))
            second_failed_count = len(second_result.get("failed_dates", []))
            set_status("step2", "已完成")
            config["last_second_outputs"] = second_result["result_files"]
            config["last_abnormal_outputs"] = second_result["abnormal_files"]
            save_config(config)
            render_notice(
                f"2号完成：成功 {second_success_count} 天，跳过 {second_skipped_count} 天，失败 {second_failed_count} 天",
                "success" if second_success_count else "warning",
            )
            second_output_summary = (
                f"秒级核算结果文件夹：{config.get('second_output_folder', '')}；"
                f"异常检测结果文件夹：{config.get('abnormal_output_folder', '')}"
            )
            append_run_record(
                step="2号秒级核算与异常检测",
                status="成功" if second_success_count else "未生成",
                date_range=run_date_range,
                output_files=second_output_summary if second_success_count else "",
                message=(
                    f"批次遍历完成：成功 {second_success_count} 天，跳过 {second_skipped_count} 天，失败 {second_failed_count} 天；"
                    f"三声道：当前范围内 {second_result.get('three_channel_used_days', 0)} 天使用三声道修正，"
                    f"{second_result.get('original_path3_days', 0)} 天使用原始Path3。"
                ),
            )
            if not second_result["result_files"]:
                set_status("step3", "未运行")
                st.session_state.run_in_progress = False
                no_result_message = "2号已完成日期遍历，但没有生成可供3号聚合的秒级结果。"
                append_run_record(
                    step="一键运行后续流程",
                    status="失败",
                    date_range=run_date_range,
                    message=no_result_message,
                )
                set_pipeline_summary("失败", run_date_range, "", no_result_message)
                render_notice(no_result_message, "warning")
                render_pipeline_summary()
                render_pipeline_result_locations(config)
                return
        except Exception as exc:
            set_status("step2", "失败")
            set_status("step3", "未运行")
            st.session_state.run_in_progress = False
            tb = format_exception(exc)
            append_run_record(
                step="2号秒级核算与异常检测",
                status="失败",
                date_range=run_date_range,
                message=str(exc),
            )
            append_run_record(
                step="一键运行后续流程",
                status="失败",
                date_range=run_date_range,
                message=f"2号秒级核算与异常检测失败：{exc}",
            )
            set_pipeline_summary(
                "失败",
                run_date_range,
                "",
                f"2号秒级核算与异常检测失败：{exc}",
            )
            render_notice("2号秒级核算失败", "error")
            st.code(tb)
            render_pipeline_summary()
            render_pipeline_result_locations(config)
            return

        try:
            set_status("step3", "运行中")
            with st.spinner("正在运行3号15min聚合..."):
                agg_result = run_15min_agg(
                    config.get("second_output_folder", ""),
                    config.get("fifteen_output_folder", ""),
                    config.get("start_date", ""),
                    config.get("end_date", ""),
                    input_files=second_result["result_files"],
                    logger=write_process_debug,
                )
            set_status("step3", "已完成")
            config["last_15min_outputs"] = agg_result["output_files"]
            save_config(config)
            render_notice(f"3号完成：生成 {len(agg_result['output_files'])} 个15min结果", "success")
            append_run_record(
                step="3号15min聚合",
                status="成功",
                date_range=run_date_range,
                output_files=f"15min核算结果文件夹：{config.get('fifteen_output_folder', '')}",
                message=f"{run_date_range} 的15min核算结果已全部生成",
            )
            append_run_record(
                step="一键运行后续流程",
                status="成功",
                date_range=run_date_range,
                output_files=pipeline_output_summary,
                message=f"{run_date_range} 的1号、2号、3号流程已全部生成",
            )
            set_pipeline_summary(
                "成功",
                run_date_range,
                pipeline_output_summary,
                f"{run_date_range} 的1号、2号、3号流程已全部生成",
            )
            st.session_state.run_in_progress = False
        except Exception as exc:
            set_status("step3", "失败")
            st.session_state.run_in_progress = False
            tb = format_exception(exc)
            append_run_record(
                step="3号15min聚合",
                status="失败",
                date_range=run_date_range,
                message=str(exc),
            )
            append_run_record(
                step="一键运行后续流程",
                status="失败",
                date_range=run_date_range,
                message=f"3号15min聚合失败：{exc}",
            )
            set_pipeline_summary(
                "失败",
                run_date_range,
                "",
                f"3号15min聚合失败：{exc}",
            )
            render_notice("3号15min聚合失败", "error")
            st.code(tb)
            render_pipeline_summary()
            render_pipeline_result_locations(config)
            return

    render_pipeline_summary()
    render_pipeline_result_locations(config)


def render_download_card(file_type, path):
    path = Path(normalize_path(path))
    if not path.is_file():
        render_notice(f"当前结果路径不是文件，已跳过：{path}", "warning")
        return
    with st.container(border=True):
        col_info, col_action = st.columns([4, 1])
        with col_info:
            st.markdown(
                f"""
                <div class="download-type">{h(file_type)}</div>
                <div class="download-name">{h(path.name)}</div>
                <div class="download-path">当前保存路径：{h(path)}</div>
                """,
                unsafe_allow_html=True,
            )
        with col_action:
            st.download_button(
                "另存为",
                data=file_bytes(path),
                file_name=path.name,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key=f"download_{file_type}_{path}",
                type="primary",
                width="stretch",
            )


def render_download_group(title, files):
    st.markdown(f"**{h(title)}**")
    existing_files = [Path(normalize_path(p)) for p in files if normalize_path(p) and Path(normalize_path(p)).is_file()]
    if not existing_files:
        render_notice("暂无结果，请先运行对应步骤。", "neutral")
        return
    for path in existing_files:
        render_download_card(title, path)


def current_download_config(config):
    current_config = derive_paths_from_config(config.copy(), force_auto=True)
    for key in ["last_low_freq_output", "last_second_outputs", "last_abnormal_outputs", "last_15min_outputs"]:
        if key in config:
            current_config[key] = config[key]
    return current_config


def current_date_strings(config):
    start_date, end_date = date_bounds(config)
    if not start_date:
        return []
    end_date = end_date or start_date
    try:
        return [item.strftime("%Y-%m-%d") for item in pd.date_range(parse_date(start_date), parse_date(end_date), freq="D")]
    except Exception:
        return [start_date]


def as_path_list(value):
    if not value:
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value if item]
    return [part.strip() for part in str(value).split(";") if part.strip()]


def expected_daily_result_paths(config, folder_key, suffix):
    folder = normalize_path(config.get(folder_key, ""))
    if not folder:
        return []
    return [str(Path(folder).expanduser() / f"{date_text}_{suffix}") for date_text in current_date_strings(config)]


def current_daily_result_paths(config, last_key, folder_key, suffix):
    expected_paths = expected_daily_result_paths(config, folder_key, suffix)
    expected_names = {Path(path).name for path in expected_paths}
    last_paths = [
        path
        for path in as_path_list(config.get(last_key, ""))
        if Path(normalize_path(path)).name in expected_names and Path(normalize_path(path)).is_file()
    ]
    return last_paths or expected_paths


def current_lowfreq_result_paths(config):
    expected_path = expected_lowfreq_output(config)
    last_path = normalize_path(config.get("last_low_freq_output", ""))
    if expected_path and last_path and Path(last_path).name == Path(expected_path).name and Path(last_path).is_file():
        return [last_path]
    return [expected_path] if expected_path else []


def current_15min_result_paths(config):
    folder = normalize_path(config.get("fifteen_output_folder", ""))
    if not folder:
        return []
    folder_path = Path(folder).expanduser()
    range_candidates = expected_15min_outputs(config)
    range_existing = [path for path in range_candidates if Path(normalize_path(path)).is_file()]
    if range_existing:
        return range_existing

    daily_candidates = [str(folder_path / f"{date_text}_15minCO2排放结果.xlsx") for date_text in current_date_strings(config)]
    daily_names = {Path(path).name for path in daily_candidates}
    last_daily = [
        path
        for path in as_path_list(config.get("last_15min_outputs", ""))
        if Path(normalize_path(path)).name in daily_names and Path(normalize_path(path)).is_file()
    ]
    return last_daily or daily_candidates


def render_current_download_group(title, files, empty_message):
    st.markdown(f"**{h(title)}**")
    existing_files = [Path(normalize_path(p)) for p in files if normalize_path(p) and Path(normalize_path(p)).is_file()]
    if not existing_files:
        render_notice(empty_message, "neutral")
        return
    for path in existing_files:
        render_download_card(title, path)


def page_downloads():
    config = current_download_config(get_config())
    render_page_title("结果下载")
    render_notice("结果文件已自动保存到默认输出文件夹，如需保存到其他位置可点击另存为。", "neutral")
    render_current_download_group(
        "0号生产日报提取结果",
        [config.get("daily_extract_output", "")],
        "当前配置下尚未生成0号生产日报提取结果。",
    )
    render_current_download_group(
        "1号低频汇总结果",
        current_lowfreq_result_paths(config),
        "当前配置下尚未生成1号低频汇总结果。",
    )
    render_current_download_group(
        "2号秒级 CO2 排放结果",
        current_daily_result_paths(config, "last_second_outputs", "second_output_folder", "秒级CO2排放结果.xlsx"),
        "当前配置下尚未生成2号秒级 CO2 排放结果。",
    )
    render_current_download_group(
        "2号异常检测结果",
        current_daily_result_paths(config, "last_abnormal_outputs", "abnormal_output_folder", "秒级异常检测结果.xlsx"),
        "当前配置下尚未生成2号异常检测结果。",
    )
    render_current_download_group(
        "3号15min聚合结果",
        current_15min_result_paths(config),
        "当前配置下尚未生成3号15min聚合结果。",
    )


def page_plot():
    config = get_config()
    render_page_title("15min图表查看")
    files = list_files(config.get("fifteen_output_folder", ""), "*_15minCO2排放结果.xlsx")
    if not files:
        render_notice("暂无结果，请先运行对应步骤。", "neutral")
        return

    with st.container(border=True):
        selected_file = st.selectbox("选择15min结果文件", options=files, format_func=lambda p: Path(p).name)
        st.markdown(
            render_path_item("图表模块读取15min结果路径", selected_file, "file"),
            unsafe_allow_html=True,
        )
        try:
            df = read_15min_file(selected_file)
        except Exception as exc:
            render_notice("读取15min结果文件失败，请检查 Excel 文件是否存在、是否损坏、格式是否正确。", "error")
            st.exception(exc)
            return
        plot_field_options = discover_numeric_plot_fields(df)
        if not plot_field_options:
            render_notice("当前文件未识别到可绘制的数值字段，请检查15min结果表内容。", "warning")
            selected_fields = []
        else:
            default_fields = [
                field
                for field in DEFAULT_PLOT_FIELDS[:4]
                if field in plot_field_options and pd.to_numeric(df[field], errors="coerce").notna().any()
            ]
            render_notice(
                "默认仅展示核心碳排放字段；其他生产参数、标干流量和监测指标可在上方多选框中自行添加，以避免曲线过多影响阅读。",
                "neutral",
            )
            selected_fields = st.multiselect(
                "请选择需要绘图的字段",
                options=plot_field_options,
                default=default_fields,
                key=f"plot_fields_{Path(selected_file).name}",
            )
    if len(selected_fields) > 15:
        render_notice("当前选择字段较多，图表可能较拥挤。", "warning")

    missing_fields = [field for field in selected_fields if field not in df.columns]
    selected_field_set = set(selected_fields)
    # Keep the original Excel column names and their source order, not click order or display aliases.
    selected_available_fields = [column for column in df.columns if column in selected_field_set]
    if missing_fields:
        render_notice("以下字段在当前15min结果中不存在，已自动跳过：" + "，".join(missing_fields), "warning")

    grouped_fields = group_plot_fields(selected_available_fields)
    any_chart_rendered = False
    for group_name in PLOT_GROUP_ORDER:
        group_fields = grouped_fields.get(group_name, [])
        if not group_fields:
            continue

        fig, _, available_fields, empty_fields = make_15min_figure(
            df,
            group_fields,
            yaxis_title=PLOT_GROUP_Y_AXIS_TITLES[group_name],
        )
        if empty_fields:
            render_notice("字段 " + "，".join(empty_fields) + " 当前无有效数据，已跳过绘图。", "warning")
        if not available_fields:
            continue

        if group_name == "其他监测指标" and len(available_fields) > 1:
            magnitudes = [pd.to_numeric(df[field], errors="coerce").abs().median() for field in available_fields]
            positive = [value for value in magnitudes if pd.notna(value) and value > 0]
            if len(positive) > 1 and max(positive) / min(positive) >= 100:
                render_notice("当前部分监测指标量纲或数量级差异较大，建议分别选择查看。", "neutral")

        render_section_title(group_name, compact=True)
        with st.container(border=True):
            st.plotly_chart(fig, width="stretch")
        any_chart_rendered = True

    if not any_chart_rendered:
        render_notice("当前没有可绘制字段。", "neutral")

    render_section_title("数据预览", compact=True)
    with st.container(border=True):
        # Preview is intentionally independent from chart selection and preserves the Excel schema verbatim.
        preview_df = df.copy()
        st.dataframe(preview_df.head(96), width="stretch", height=300)


def render_cell_map_editor():
    with st.container(border=True):
        render_section_title("参数配置", compact=True)
        st.caption("请先确认日报字段名与单元格位置，再上传生产综合日报运行0号提取。")
        cell_map = load_cell_map(CELL_MAP_PATH)
        df = pd.DataFrame([{"字段名": key, "单元格位置": value or ""} for key, value in cell_map.items()])
        edited = st.data_editor(df, num_rows="dynamic", width="stretch", key="cell_map_editor")
        if st.button("保存提取规则", type="primary", key="save_cell_map_rules"):
            new_map = {}
            for _, row in edited.iterrows():
                field_name = str(row.get("字段名", "")).strip()
                cell_address = str(row.get("单元格位置", "")).strip()
                if not field_name or field_name.lower() == "nan":
                    continue
                if cell_address.lower() == "nan":
                    cell_address = ""
                new_map[field_name] = cell_address or None
            save_cell_map(CELL_MAP_PATH, new_map)
            render_notice("提取规则已保存", "success")


def first_existing_path(candidates):
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def render_usage_image(title, description, candidates):
    render_section_title(title, compact=True)
    st.caption(description)
    image_path = first_existing_path(candidates)
    if image_path:
        st.image(str(image_path), use_container_width=True)
    else:
        render_notice("未找到流程图图片，请检查assets目录。", "warning")


def page_usage():
    render_page_title("使用说明")
    with st.container(border=True):
        st.markdown(
            """
            1. 在“项目配置”中填写项目根目录、数据处理开始日期、数据处理结束日期，并自动填充标准路径。
            2. 在“0号：日报数据提取”中先确认参数配置，再上传生产综合日报，运行0号生成生产日报提取结果。
            3. 在同一页面预览0号提取结果，并完成审核通过或审核不通过。
            4. 审核通过后，在“一键运行后续流程”中查看运行前检查，并依次运行1号、2号、3号。
            5. 结果会自动保存到对应文件夹，也可以在“结果下载”页面点击“另存为”保存副本。
            6. 在“15min图表查看”中选择15min结果文件，并选择所有需要查看的CO2/碳排放字段进行绘图。
            7. 页面底部提供两张思维导图辅助理解。
            """
        )

    render_section_title("流程理解辅助图")
    with st.container(border=True):
        render_usage_image(
            "物理数据路径图",
            "这张图用于理解我们投入了哪些数据、每类数据有什么意义、最终得到哪些排放结果。",
            PHYSICAL_IMAGE_CANDIDATES,
        )
        render_usage_image(
            "代码数据分析流程图",
            "这张图用于理解0、1、2、3号代码的运行顺序和数据流向。",
            FLOW_IMAGE_CANDIDATES,
        )


def main():
    init_state()
    render_header()
    with st.sidebar:
        st.markdown("### 导航")
        st.radio("页面", PAGES, key="current_page", label_visibility="collapsed")
        st.divider()
        st.caption("系统状态")
        st.write("0号审核：" + ("已通过" if st.session_state.audit_passed else "未通过"))

    page = st.session_state.current_page
    if page == "首页 / 工作台":
        page_home()
    elif page == "项目配置":
        page_project_config()
    elif page == "0号：日报数据提取":
        page_extract_report()
    elif page == "一键运行后续流程":
        page_run_pipeline()
    elif page == "结果下载":
        page_downloads()
    elif page == "15min图表查看":
        page_plot()
    elif page == "使用说明":
        page_usage()


if __name__ == "__main__":
    main()
