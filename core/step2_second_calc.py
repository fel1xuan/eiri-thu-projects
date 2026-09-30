import os
import calendar
import time
import warnings
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from utils.date_range_utils import resolve_process_date_range


shutdown_start_date = pd.to_datetime("2025-08-11")
shutdown_end_date = pd.to_datetime("2025-10-10")
THREE_CHANNEL_START = datetime.strptime("2025-07-15", "%Y-%m-%d").date()

cu_reduction = 0.055
caf2_reduction = 0.245
carbon_content_2023 = 0.02610
carbon_content_2024 = 0.02618
oxidation_rate = 0.99
molecular_ratio = 44 / 12

ABNORMAL_CHECK_CONFIG = {
    "入磨-A": [0, 10000],
    "入磨-B": [0, 10000],
    "入窑-A磨入分解炉转子秤累计": [0, 10000],
    "入窑-A磨入窑头转子秤累计": [0, 10000],
    "熟料产量": [0, 10000],
    "CO2体积浓度": [15, 40],
    "湿度": [10, 100],
    "烟气温度": [30, 65],
    "烟气压力": [-0.5, 0.5],
    "系统采样": [1, 1],
    "系统反吹": [0, 0],
    "系统故障": [0, 0],
    "系统维护": [0, 0],
    "系统校准": [0, 0],
    "标干流量Path1": [0, 1000000],
    "标干流量Path2": [0, 1000000],
    "标干流量Path3": [0, 1000000],
    "标干流量Path1&3": [0, 1000000],
    "标干流量Path1&2": [0, 1000000],
    "标干流量Path2&3": [0, 1000000],
    "标干流量Path1&2&3": [0, 1000000],
}
REVERSE_BLOW_PARAMS = ["CO2体积浓度", "湿度"]
GROUP1_PARAMS = ["入磨-A", "入磨-B", "入窑-A磨入分解炉转子秤累计", "入窑-A磨入窑头转子秤累计", "熟料产量"]
GROUP2_PARAMS = [
    "CO2体积浓度",
    "湿度",
    "烟气温度",
    "烟气压力",
    "系统采样",
    "系统反吹",
    "系统故障",
    "系统维护",
    "系统校准",
    "标干流量Path1",
    "标干流量Path2",
    "标干流量Path1&2",
]


def _log(logger, message):
    if logger:
        logger(message)
    else:
        print(message)


def generate_date_list(start_date, end_date):
    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")
    date_list = []
    current = start
    while current <= end:
        date_list.append(current.strftime("%Y-%m-%d"))
        current += timedelta(days=1)
    return date_list


def is_shutdown_period(date):
    if pd.isna(date):
        return False
    date = pd.to_datetime(date)
    return shutdown_start_date <= date <= shutdown_end_date


def calculate_abnormal_stats(df_data, check_config, reverse_blow_params):
    param_stats = {}
    total_rows = len(df_data)

    for param, (min_val, max_val) in check_config.items():
        if param not in df_data.columns:
            param_stats[param] = [0, 0, np.nan, total_rows]
            continue

        ser = df_data[param]
        null_num = ser.isna().sum()
        normal_num = ser[(ser.notna()) & (ser >= min_val) & (ser <= max_val)].count()
        abnormal_num = total_rows - normal_num - null_num

        reverse_num = np.nan
        if param in reverse_blow_params and "系统反吹" in df_data.columns:
            reverse_num = ser[(ser.notna()) & (ser < min_val) | (ser > max_val) & (df_data["系统反吹"] == 1)].count()

        param_stats[param] = [normal_num, abnormal_num, reverse_num, null_num]

    return pd.DataFrame(param_stats, index=["正常值", "异常值", "反吹", "空值"])


def calculate_status_column(df_data, group1, group2, check_config):
    def is_single_value_normal(val, min_val, max_val):
        if pd.isna(val):
            return False
        return min_val <= val <= max_val

    status_list = []
    for _, row in df_data.iterrows():
        group1_all_normal = True
        for param in group1:
            if param not in check_config:
                group1_all_normal = False
                break
            min_v, max_v = check_config[param]
            if not is_single_value_normal(row[param], min_v, max_v):
                group1_all_normal = False
                break

        group2_all_normal = True
        for param in group2:
            if param not in check_config:
                group2_all_normal = False
                break
            min_v, max_v = check_config[param]
            if not is_single_value_normal(row[param], min_v, max_v):
                group2_all_normal = False
                break

        if group1_all_normal and group2_all_normal:
            status_list.append(0)
        elif not group1_all_normal and group2_all_normal:
            status_list.append(1)
        elif group1_all_normal and not group2_all_normal:
            status_list.append(2)
        else:
            status_list.append(3)

    df_data["状态"] = status_list
    return df_data


def _process_per_s_day(
    input_date,
    df_low_freq,
    high_freq_base_path,
    three_channel_path,
    output_result_path,
    output_abnormal_path,
    logger=None,
):
    date = input_date
    date_dt = datetime.strptime(date, "%Y-%m-%d").date()
    _log(logger, f"[2号] 正在处理日期：{date}")

    day_low_freq = df_low_freq[df_low_freq["日期_str"] == date].reset_index(drop=True)
    if day_low_freq.empty:
        _log(logger, f"[2号] 日期 {date} 无低频数据，跳过处理")
        return None

    content1 = day_low_freq["铜渣质量分数"].values[0]
    content2 = day_low_freq["萤石质量分数"].values[0]
    content4 = day_low_freq["煤矸石质量分数"].values[0]
    fbl_heat_value = day_low_freq["废纺低位发热量GJ/t"].values[0]
    cu_cao = day_low_freq["铜渣氧化钙含量"].values[0]
    caf2_cao = day_low_freq["萤石氧化钙含量"].values[0]
    cu_mgo = day_low_freq["铜渣氧化镁含量"].values[0]
    caf2_mgo = day_low_freq["萤石氧化镁含量"].values[0]

    calori_grind = day_low_freq["入磨煤低位发热量(GJ/t)"].values[0]
    calori_kiln = day_low_freq["入窑煤低位发热量(GJ/t)"].values[0]
    fbl_data = day_low_freq["废布料消耗量t"].values[0]
    clinker_cao = day_low_freq["熟料_氧化钙含量(%)"].values[0]
    clinker_mgo = day_low_freq["熟料_氧化镁含量(%)"].values[0]

    if content4 == 0:
        content3 = 0.1
    else:
        content3 = 0.3
    _log(logger, "[2号] 当日低频参数读取完成")

    cems_file_map = {
        "湿度.csv": "湿度",
        "烟气温度.csv": "烟气温度",
        "烟气压力.csv": "烟气压力",
        "CO2排放速率Path1.csv": "CO2排放速率Path1",
        "CO2排放速率Path2.csv": "CO2排放速率Path2",
        "CO2排放速率Path3.csv": "CO2排放速率Path3",
        "CO2排放速率Path1&3.csv": "CO2排放速率Path1&3",
        "CO2排放速率Path1&2&3.csv": "CO2排放速率Path1&2&3",
        "标干流量Path1.csv": "标干流量Path1",
        "标干流量Path2.csv": "标干流量Path2",
        "标干流量Path3.csv": "标干流量Path3",
        "标干流量Path1&3.csv": "标干流量Path1&3",
        "标干流量Path1&2&3.csv": "标干流量Path1&2&3",
        "CO2体积浓度.csv": "CO2体积浓度",
    }

    cems_data = pd.DataFrame()
    time_series = pd.date_range(start=date, periods=86400, freq="s")
    cems_data["数据时间"] = time_series
    day_high_freq_path = os.path.join(high_freq_base_path, date)
    _log(logger, "[2号] 正在合并CEMS数据...")

    for file_name, col_name in cems_file_map.items():
        file_path = os.path.join(day_high_freq_path, file_name)
        if os.path.exists(file_path):
            df_tmp = pd.read_csv(file_path, header=None)
            df_tmp.columns = ["数据时间", col_name]
            df_tmp["数据时间"] = pd.to_datetime(df_tmp["数据时间"])
            cems_data = pd.merge(cems_data, df_tmp, on="数据时间", how="outer")

    sys_file_list = [
        ("系统采样.csv", "系统采样"),
        ("系统反吹.csv", "系统反吹"),
        ("系统故障.csv", "系统故障"),
        ("系统维护.csv", "系统维护"),
        ("系统校准.csv", "系统校准"),
    ]
    for file_name, col_name in sys_file_list:
        file_path = os.path.join(day_high_freq_path, file_name)
        if os.path.exists(file_path):
            df_tmp = pd.read_csv(file_path, header=None)
            df_tmp.columns = ["数据时间", col_name]
            df_tmp["数据时间"] = pd.to_datetime(df_tmp["数据时间"])
            cems_data = pd.merge(cems_data, df_tmp, on="数据时间", how="outer")
        else:
            _log(logger, f"[2号] 没有找到{col_name}文件")

    dcs_taos_file_map = {
        "入磨-A.csv": "入磨-A",
        "入磨-B.csv": "入磨-B",
        "入窑-A磨入分解炉转子秤累计.csv": "入窑-A磨入分解炉转子秤累计",
        "入窑-A磨入窑头转子秤累计.csv": "入窑-A磨入窑头转子秤累计",
        "生料消耗量.csv": "生料消耗量",
    }

    dcs_taos_data = pd.DataFrame()
    dcs_taos_data["数据时间"] = time_series
    _log(logger, "[2号] 正在合并DCS高频生产数据...")
    for file_name, col_name in dcs_taos_file_map.items():
        file_path = os.path.join(day_high_freq_path, file_name)
        if os.path.exists(file_path):
            df_tmp = pd.read_csv(file_path, header=None, usecols=[0, 1])
            df_tmp.columns = ["数据时间", col_name]
            df_tmp["数据时间"] = pd.to_datetime(df_tmp["数据时间"])
            df_tmp.sort_values("数据时间", inplace=True)
            dcs_taos_data = pd.merge(dcs_taos_data, df_tmp, on="数据时间", how="outer")

    if date_dt >= THREE_CHANNEL_START:
        three_channel_filename = f"S{date[2:].replace('-', '')}.CSV"
        three_channel_filepath = os.path.join(three_channel_path, three_channel_filename)
        if os.path.exists(three_channel_filepath):
            _log(logger, f"[2号] 正在处理三声道数据：{three_channel_filename}")
            df_3channel = pd.read_csv(three_channel_filepath, header=None, dtype={0: str})
            df_3channel["数据时间"] = pd.to_datetime(f"{date} " + df_3channel[0].astype(str))
            df_3channel["三声道流速"] = pd.to_numeric(df_3channel.iloc[:, 4], errors="coerce")
            df_3channel = pd.merge(df_3channel, cems_data[["数据时间", "湿度", "烟气温度", "烟气压力"]], on="数据时间", how="left")
            df_3channel["湿度"] = pd.to_numeric(df_3channel["湿度"], errors="coerce")
            df_3channel["烟气温度"] = pd.to_numeric(df_3channel["烟气温度"], errors="coerce")
            df_3channel["烟气压力"] = pd.to_numeric(df_3channel["烟气压力"], errors="coerce")
            df_3channel["新标干流量Path3"] = (
                (df_3channel["三声道流速"] * 27.64 * 3600)
                * (273 / (273 + df_3channel["烟气温度"]))
                * ((101325 + df_3channel["烟气压力"]) / 101325)
                * (1 - df_3channel["湿度"] / 100)
            )
            cems_data = pd.merge(cems_data, df_3channel[["数据时间", "新标干流量Path3"]], on="数据时间", how="left")
            cems_data["标干流量Path3"] = cems_data["新标干流量Path3"]
            cems_data["标干流量Path3"] = cems_data["标干流量Path3"].replace([np.inf, -np.inf], np.nan)
            _log(logger, "[2号] 三声道标干流量Path3替换完成")
        else:
            _log(logger, f"[2号] 未找到三声道文件：{three_channel_filename}，使用原始标干流量Path3数据")
    else:
        _log(logger, "[2号] 日期早于2025-07-15，不启用三声道数据")

    cems_data["标干流量Path1&3"] = (cems_data["标干流量Path1"] + cems_data["标干流量Path3"]) / 2
    cems_data["标干流量Path1&2"] = (cems_data["标干流量Path1"] + cems_data["标干流量Path2"]) / 2
    cems_data["标干流量Path2&3"] = (cems_data["标干流量Path2"] + cems_data["标干流量Path3"]) / 2
    cems_data["标干流量Path1&2&3"] = (cems_data["标干流量Path1&3"] + cems_data["标干流量Path2"]) / 2

    dcs_taos_data["入磨煤量"] = dcs_taos_data["入磨-A"] + dcs_taos_data["入磨-B"]
    dcs_taos_data["入窑煤量"] = dcs_taos_data["入窑-A磨入分解炉转子秤累计"] + dcs_taos_data["入窑-A磨入窑头转子秤累计"]
    if (dcs_taos_data["入磨煤量"] < 0).any():
        _log(logger, "[2号] 警告：入磨煤量中存在负值")
    if (dcs_taos_data["入窑煤量"] < 0).any():
        _log(logger, "[2号] 警告：入窑煤量中存在负值")

    dcs_taos_data["入磨煤CO2排放_2023"] = dcs_taos_data["入磨煤量"] * calori_grind * carbon_content_2023 * oxidation_rate * molecular_ratio
    dcs_taos_data["入窑煤CO2排放_2023"] = dcs_taos_data["入窑煤量"] * calori_kiln * carbon_content_2023 * oxidation_rate * molecular_ratio
    dcs_taos_data["入磨煤CO2排放_2024"] = dcs_taos_data["入磨煤量"] * calori_grind * carbon_content_2024 * oxidation_rate * molecular_ratio
    dcs_taos_data["入窑煤CO2排放_2024"] = dcs_taos_data["入窑煤量"] * calori_kiln * carbon_content_2024 * oxidation_rate * molecular_ratio

    fbl_avg_per_s = fbl_data / 86400

    process_emissions = pd.DataFrame()
    process_emissions["数据时间"] = cems_data["数据时间"]
    process_emissions["生料消耗量"] = dcs_taos_data["生料消耗量"]
    process_emissions["非燃料碳排放"] = process_emissions["生料消耗量"] * content3 * molecular_ratio / 100
    process_emissions["熟料产量"] = process_emissions["生料消耗量"] / 1.61
    process_emissions["CaO分解CO2"] = (
        process_emissions["熟料产量"] * clinker_cao / 100 * (44 / 56)
        - (process_emissions["生料消耗量"] * content1 * cu_cao + process_emissions["生料消耗量"] * content2 * caf2_cao) / 100 * (44 / 56)
    )
    process_emissions["MgO分解CO2"] = (
        process_emissions["熟料产量"] * clinker_mgo / 100 * (44 / 40)
        - (process_emissions["生料消耗量"] * content1 * cu_mgo + process_emissions["生料消耗量"] * content2 * caf2_mgo) / 100 * (44 / 40)
    )
    process_emissions["过程排放2023"] = process_emissions["非燃料碳排放"] + process_emissions["CaO分解CO2"] + process_emissions["MgO分解CO2"]
    process_emissions["过程排放2024"] = (
        process_emissions["熟料产量"] * 0.535
        - process_emissions["生料消耗量"] * content1 * cu_reduction
        - process_emissions["生料消耗量"] * content2 * caf2_reduction
    )

    combined_results = pd.DataFrame()
    combined_results["数据时间"] = cems_data["数据时间"]
    combined_results["入磨-A"] = dcs_taos_data["入磨-A"] / 3600
    combined_results["入磨-B"] = dcs_taos_data["入磨-B"] / 3600
    combined_results["入窑-A磨入分解炉转子秤累计"] = dcs_taos_data["入窑-A磨入分解炉转子秤累计"] / 3600
    combined_results["入窑-A磨入窑头转子秤累计"] = dcs_taos_data["入窑-A磨入窑头转子秤累计"] / 3600
    combined_results["入磨煤低位发热量"] = calori_grind
    combined_results["入窑煤低位发热量"] = calori_kiln
    combined_results["废纺低位发热量"] = fbl_heat_value
    combined_results["废纺平均消耗量"] = fbl_avg_per_s
    combined_results["熟料产量"] = process_emissions["熟料产量"] / 3600
    combined_results["熟料中CaO含量%"] = clinker_cao
    combined_results["熟料中MgO含量%"] = clinker_mgo
    combined_results["湿度"] = cems_data["湿度"]
    combined_results["烟气温度"] = cems_data["烟气温度"]
    combined_results["烟气压力"] = cems_data["烟气压力"]
    combined_results["标干流量Path1"] = cems_data["标干流量Path1"] / 3600
    combined_results["标干流量Path2"] = cems_data["标干流量Path2"] / 3600
    combined_results["标干流量Path3"] = cems_data["标干流量Path3"] / 3600
    combined_results["标干流量Path1&3"] = cems_data["标干流量Path1&3"] / 3600
    combined_results["标干流量Path1&2"] = cems_data["标干流量Path1&2"] / 3600
    combined_results["标干流量Path1&2&3"] = cems_data["标干流量Path1&2&3"] / 3600
    combined_results["标干流量Path2&3"] = cems_data["标干流量Path2&3"] / 3600
    combined_results["CO2体积浓度"] = cems_data["CO2体积浓度"]
    combined_results["系统采样"] = cems_data.get("系统采样", np.ones(len(combined_results)))
    combined_results["系统反吹"] = cems_data.get("系统反吹", np.zeros(len(combined_results)))
    combined_results["系统故障"] = cems_data.get("系统故障", np.zeros(len(combined_results)))
    combined_results["系统维护"] = cems_data.get("系统维护", np.zeros(len(combined_results)))
    combined_results["系统校准"] = cems_data.get("系统校准", np.zeros(len(combined_results)))
    combined_results["过程排放2023"] = process_emissions["过程排放2023"] / 3600
    combined_results["过程排放2024"] = process_emissions["过程排放2024"] / 3600
    combined_results["入磨煤CO2排放_2023"] = dcs_taos_data["入磨煤CO2排放_2023"] / 3600
    combined_results["入窑煤CO2排放_2023"] = dcs_taos_data["入窑煤CO2排放_2023"] / 3600
    combined_results["入磨煤CO2排放_2024"] = dcs_taos_data["入磨煤CO2排放_2024"] / 3600
    combined_results["入窑煤CO2排放_2024"] = dcs_taos_data["入窑煤CO2排放_2024"] / 3600
    combined_results["碳排放_2023_入磨"] = combined_results["入磨煤CO2排放_2023"] + combined_results["过程排放2023"]
    combined_results["碳排放_2023_入窑"] = combined_results["入窑煤CO2排放_2023"] + combined_results["过程排放2023"]
    combined_results["碳排放_2024_入磨"] = combined_results["入磨煤CO2排放_2024"] + combined_results["过程排放2024"]
    combined_results["碳排放_2024_入窑"] = combined_results["入窑煤CO2排放_2024"] + combined_results["过程排放2024"]

    combined_results["CO2排放速率Path1"] = cems_data["CO2排放速率Path1"] / 3600
    combined_results["CO2排放速率Path2"] = cems_data["CO2排放速率Path2"] / 3600
    combined_results["CO2排放速率Path3"] = combined_results["CO2排放速率Path1"] * combined_results["标干流量Path3"] / combined_results["标干流量Path1"]
    combined_results["CO2排放速率Path1&3"] = combined_results["CO2排放速率Path1"] * combined_results["标干流量Path1&3"] / combined_results["标干流量Path1"]
    combined_results["CO2排放速率Path1&2"] = combined_results["CO2排放速率Path1"] * combined_results["标干流量Path1&2"] / combined_results["标干流量Path1"]
    combined_results["CO2排放速率Path2&3"] = combined_results["CO2排放速率Path1"] * combined_results["标干流量Path2&3"] / combined_results["标干流量Path1"]
    combined_results["CO2排放速率Path1&2&3"] = combined_results["CO2排放速率Path1"] * combined_results["标干流量Path1&2&3"] / combined_results["标干流量Path1"]
    combined_results["煤矸石CO2排放"] = process_emissions["生料消耗量"] * content4 / 3600 * 8.374 * 0.02541 * 44 / 12

    _log(logger, "[2号] 正在保存异常检测结果...")
    abnormal_stats_df = calculate_abnormal_stats(combined_results, ABNORMAL_CHECK_CONFIG, REVERSE_BLOW_PARAMS)
    abnormal_output_file = os.path.join(output_abnormal_path, f"{date}_秒级异常检测结果.xlsx")
    with pd.ExcelWriter(abnormal_output_file, engine="openpyxl") as writer:
        abnormal_stats_df.to_excel(writer, index=True)
    _log(logger, f"[2号] 异常检测结果保存：{abnormal_output_file}")

    combined_results = calculate_status_column(combined_results, GROUP1_PARAMS, GROUP2_PARAMS, ABNORMAL_CHECK_CONFIG)
    output_file = os.path.join(output_result_path, f"{date}_秒级CO2排放结果.xlsx")
    _log(logger, "[2号] 正在保存秒级结果...")
    with pd.ExcelWriter(output_file, engine="openpyxl", datetime_format="yyyy-mm-dd HH:mm:ss") as writer:
        combined_results.to_excel(writer, index=False)
    _log(logger, f"[2号] 秒级结果保存：{output_file}")

    return {"result_file": output_file, "abnormal_file": abnormal_output_file}


def run_second_calc(
    high_freq_base_path,
    low_freq_file_path,
    three_channel_path,
    output_result_path,
    output_abnormal_path,
    start_date,
    end_date,
    logger=None,
):
    warnings.filterwarnings("ignore", category=UserWarning, module="openpyxl")
    warnings.filterwarnings("ignore", category=FutureWarning)

    high_freq_base = Path(high_freq_base_path).expanduser()
    low_freq_file = Path(low_freq_file_path).expanduser()
    three_channel = Path(three_channel_path).expanduser()
    result_folder = Path(output_result_path).expanduser()
    abnormal_folder = Path(output_abnormal_path).expanduser()

    if not high_freq_base.exists():
        raise FileNotFoundError(f"核心高频数据文件夹不存在：{high_freq_base}")
    if not low_freq_file.exists():
        raise FileNotFoundError(f"低频汇总文件不存在：{low_freq_file}")
    if not three_channel.exists():
        _log(logger, f"[2号] 清华三声道数据文件夹不存在：{three_channel}，涉及启用日期后的三声道替换会跳过")
    result_folder.mkdir(parents=True, exist_ok=True)
    abnormal_folder.mkdir(parents=True, exist_ok=True)

    _log(logger, "[2号] 开始秒级核算...")
    _log(logger, "[2号] 正在读取低频数据...")
    df_low_freq = pd.read_excel(low_freq_file)
    if "日期" not in df_low_freq.columns:
        raise ValueError("低频汇总文件缺少日期列。")
    df_low_freq["日期"] = pd.to_datetime(df_low_freq["日期"]).dt.date
    df_low_freq["日期_str"] = df_low_freq["日期"].astype(str)

    start = time.perf_counter()
    result_files = []
    abnormal_files = []
    for calc_date in generate_date_list(start_date, end_date):
        result = _process_per_s_day(
            calc_date,
            df_low_freq,
            str(high_freq_base),
            str(three_channel),
            str(result_folder),
            str(abnormal_folder),
            logger=logger,
        )
        if result:
            result_files.append(result["result_file"])
            abnormal_files.append(result["abnormal_file"])

    elapsed = time.perf_counter() - start
    if not result_files:
        raise RuntimeError("秒级核算没有生成任何结果，请检查日期区间、低频数据和高频文件夹。")

    _log(logger, f"[2号] 全部日期处理完成，总耗时：{elapsed:.2f} 秒")
    return {"result_files": result_files, "abnormal_files": abnormal_files, "elapsed_seconds": elapsed}


def run_step2_second_calc(
    lowfreq_result_file: str,
    second_data_dir: str,
    output_dir: str = "",
    target_month: str = "",
    logger=None,
    process_start_date: str = "",
    process_end_date: str = "",
    result_dir: str = "",
    abnormal_dir: str = "",
) -> dict:
    """
    运行2号秒级核算与异常检测。

    参数：
        lowfreq_result_file: 1号低频汇总结果 Excel 路径
        second_data_dir: 秒级 / 高频数据目录
        output_dir: 输出目录
        target_month: 目标月份，格式 YYYY-MM，可为空

    返回：
        {
            "success": True/False,
            "message": "...",
            "output_files": ["..."]
        }
    """
    try:
        if not str(lowfreq_result_file or "").strip():
            raise ValueError("1号低频汇总结果不能为空")
        if not str(second_data_dir or "").strip():
            raise ValueError("秒级 / 高频数据目录不能为空")
        if not str(result_dir or "").strip() and not str(output_dir or "").strip():
            raise ValueError("秒级核算结果目录不能为空")
        if not str(abnormal_dir or "").strip() and not str(output_dir or "").strip():
            raise ValueError("秒级异常结果目录不能为空")

        lowfreq_path = Path(lowfreq_result_file).expanduser()
        high_freq_base = Path(second_data_dir).expanduser()

        if not lowfreq_path.is_file():
            raise FileNotFoundError(f"1号低频汇总结果不存在：{lowfreq_path}")
        if not high_freq_base.exists():
            raise FileNotFoundError(f"秒级 / 高频数据目录不存在：{high_freq_base}")
        if not high_freq_base.is_dir():
            raise NotADirectoryError(f"秒级 / 高频数据路径不是文件夹：{high_freq_base}")

        result_folder = (
            Path(result_dir).expanduser()
            if str(result_dir or "").strip()
            else Path(output_dir).expanduser() / "2号秒级核算结果"
        )
        abnormal_folder = (
            Path(abnormal_dir).expanduser()
            if str(abnormal_dir or "").strip()
            else Path(output_dir).expanduser() / "2号异常检测结果"
        )
        three_channel_path = _infer_three_channel_path(high_freq_base)
        start_date, end_date = _resolve_step2_date_range(target_month, lowfreq_path, process_start_date, process_end_date)
        _log(logger, f"[2号] 处理日期范围：{start_date} 至 {end_date}")

        result = run_second_calc(
            high_freq_base_path=high_freq_base,
            low_freq_file_path=lowfreq_path,
            three_channel_path=three_channel_path,
            output_result_path=result_folder,
            output_abnormal_path=abnormal_folder,
            start_date=start_date,
            end_date=end_date,
            logger=logger,
        )

        output_files = result.get("result_files", []) + result.get("abnormal_files", [])
        return {
            "success": True,
            "status": "success",
            "message": (
                f"2号秒级核算完成：{len(result.get('result_files', []))} 个秒级结果，"
                f"{len(result.get('abnormal_files', []))} 个异常检测结果；处理日期：{start_date} 至 {end_date}"
            ),
            "output_files": output_files,
            "detail": result,
            "result_dir": str(result_folder),
            "abnormal_dir": str(abnormal_folder),
            "process_start_date": start_date,
            "process_end_date": end_date,
        }
    except Exception as exc:
        return {
            "success": False,
            "status": "failed",
            "message": str(exc),
            "output_files": [],
            "error": str(exc),
        }


def _resolve_step2_date_range(target_month, lowfreq_path, process_start_date="", process_end_date=""):
    if str(target_month or "").strip():
        range_info = resolve_process_date_range(target_month, process_start_date, process_end_date)
        if not range_info.get("ok"):
            raise ValueError(range_info.get("message", "处理日期范围无效"))
        return range_info["start_date"], range_info["end_date"]

    df = pd.read_excel(lowfreq_path)
    if "日期" not in df.columns:
        raise ValueError("低频汇总文件缺少日期列，且未填写目标月份")
    dates = pd.to_datetime(df["日期"], errors="coerce").dropna()
    if dates.empty:
        raise ValueError("未填写目标月份，且无法从低频汇总结果中识别日期")
    return dates.min().strftime("%Y-%m-%d"), dates.max().strftime("%Y-%m-%d")


def _parse_target_month(target_month):
    text = str(target_month).strip()
    try:
        dt = pd.to_datetime(f"{text}-01", format="%Y-%m-%d", errors="raise")
    except Exception as exc:
        raise ValueError(f"目标月份格式应为 YYYY-MM，例如 2026-05。当前值：{target_month}") from exc
    return int(dt.year), int(dt.month)


def _infer_three_channel_path(high_freq_base):
    raw_data_root = high_freq_base.parent
    candidates = [
        raw_data_root / "(2)清华三声道数据",
        raw_data_root / "(2) 清华三声道数据",
        raw_data_root / "(3)声道三数据",
        raw_data_root / "(3) 声道三数据",
        raw_data_root / "(3)三声道数据",
        raw_data_root / "(3) 三声道数据",
    ]
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    return candidates[0]
