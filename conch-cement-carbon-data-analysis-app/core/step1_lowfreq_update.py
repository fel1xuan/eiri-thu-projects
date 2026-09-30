import os
import calendar
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from utils.date_range_utils import resolve_process_date_range


def _log(logger, message):
    if logger:
        logger(message)
    else:
        print(message)


def _merge_daily_extract(df_target, daily_extract_path, logger):
    """
    将 0号已审核的生产日报提取结果合入目标区间。

    原脚本假设这些日报字段已由人工复制到低频主表；App 中加入这一步，
    是为了替代人工复制过程，不改变后续计算公式。
    """
    if not daily_extract_path:
        return df_target
    path = Path(daily_extract_path)
    if not path.exists():
        _log(logger, f"[1号] 未找到生产日报提取结果：{path}，跳过日报字段合入")
        return df_target

    _log(logger, f"[1号] 正在合入生产日报提取结果：{path}")
    daily_df = pd.read_excel(path)
    _log(logger, f"[1号][诊断] 0号结果读取成功：{daily_df.shape[0]}行，{daily_df.shape[1]}列")
    if "日期" not in daily_df.columns:
        raise ValueError(f"生产日报提取结果缺少日期列：{path}")

    daily_dates = pd.to_datetime(daily_df["日期"], errors="coerce")
    valid_daily_dates = daily_dates.dropna()
    if valid_daily_dates.empty:
        raise ValueError(f"生产日报提取结果日期列无法解析：{path}")
    _log(
        logger,
        "[1号][诊断] 0号结果日期范围："
        f"{valid_daily_dates.min().strftime('%Y-%m-%d')} 至 {valid_daily_dates.max().strftime('%Y-%m-%d')}，"
        f"有效日期{len(valid_daily_dates)}条",
    )
    daily_df["日期"] = daily_dates.dt.date
    daily_df = daily_df.dropna(subset=["日期"]).copy()

    if df_target.empty:
        _log(logger, "[1号][诊断] 历史主表中目标区间为0行，将使用0号结果日期创建目标区间基础行")
        df_target = daily_df[["日期"]].drop_duplicates().reset_index(drop=True)

    before_rows, before_cols = df_target.shape
    _log(logger, f"[1号][诊断] 合入0号前目标区间：{before_rows}行，{before_cols}列")
    for col in daily_df.columns:
        if col == "日期":
            continue
        if col in df_target.columns:
            df_target = df_target.merge(daily_df[["日期", col]], on="日期", how="left", suffixes=("", "_daily"))
            df_target[col] = df_target[f"{col}_daily"].fillna(df_target[col])
            df_target.drop(f"{col}_daily", axis=1, inplace=True)
        else:
            df_target = df_target.merge(daily_df[["日期", col]], on="日期", how="left")

    after_dates = pd.to_datetime(df_target["日期"], errors="coerce").dropna()
    date_range_text = "无有效日期"
    if not after_dates.empty:
        date_range_text = f"{after_dates.min().strftime('%Y-%m-%d')} 至 {after_dates.max().strftime('%Y-%m-%d')}"
    _log(logger, f"[1号] 生产日报字段合入完成")
    _log(logger, f"[1号][诊断] 合入0号后目标区间：{df_target.shape[0]}行，{df_target.shape[1]}列，日期范围：{date_range_text}")
    return df_target


def run_lowfreq_update(
    main_file_path,
    source_folder_path,
    output_path,
    start_date,
    end_date,
    daily_extract_path=None,
    logger=None,
):
    main_path = Path(main_file_path).expanduser()
    source_folder = Path(source_folder_path).expanduser()
    output_folder = Path(output_path).expanduser()
    if not main_path.exists():
        raise FileNotFoundError(f"低频主表不存在：{main_path}")
    if not source_folder.exists():
        raise FileNotFoundError(f"低频源文件夹不存在：{source_folder}")
    output_folder.mkdir(parents=True, exist_ok=True)

    _log(logger, "[1号] 开始低频数据汇总...")
    _log(logger, f"[1号][诊断] 历史低频主表路径：{main_path}")
    _log(logger, f"[1号][诊断] 当月低频数据路径：{source_folder}")
    _log(logger, f"[1号][诊断] 0号结果路径：{Path(daily_extract_path).expanduser() if daily_extract_path else '未提供'}")
    _log(logger, f"[1号][诊断] 输出目录：{output_folder}")
    _log(logger, "[1号] 正在读取主表【海螺水泥低频数据】...")
    df_main = pd.read_excel(main_path)
    _log(logger, f"[1号][诊断] 历史主表读取成功：{df_main.shape[0]}行，{df_main.shape[1]}列")

    if "数据时间" in df_main.columns:
        df_main.rename(columns={"数据时间": "日期"}, inplace=True)
    if "日期" not in df_main.columns:
        raise ValueError("低频主表缺少日期列或数据时间列。")

    df_main["日期"] = pd.to_datetime(df_main["日期"]).dt.date
    main_dates = pd.to_datetime(df_main["日期"], errors="coerce").dropna()
    if not main_dates.empty:
        _log(
            logger,
            "[1号][诊断] 历史主表日期范围："
            f"{main_dates.min().strftime('%Y-%m-%d')} 至 {main_dates.max().strftime('%Y-%m-%d')}",
        )
    start_dt = datetime.strptime(start_date, "%Y-%m-%d").date()
    end_dt = datetime.strptime(end_date, "%Y-%m-%d").date()

    mask_target = (df_main["日期"] >= start_dt) & (df_main["日期"] <= end_dt)
    df_target = df_main[mask_target].reset_index(drop=True)
    df_keep = df_main[~mask_target].reset_index(drop=True)
    _log(logger, f"[1号] 主表拆分完成：目标区间({start_date}~{end_date}) {len(df_target)}条 | 非目标区间保留 {len(df_keep)}条")

    df_target = _merge_daily_extract(df_target, daily_extract_path, logger)

    source_files = [f for f in os.listdir(source_folder) if f.endswith(".xlsx")]
    _log(logger, f"[1号][诊断] 当月低频目录识别到xlsx文件：{', '.join(sorted(source_files)) if source_files else '无'}")
    dcs_file = None
    copper_slag_file = None
    fluorite_sludge_file = None
    replace_fuel_file = None

    for file_name in source_files:
        full_path = str(source_folder / file_name)
        if dcs_file is None and file_name.startswith("dcs"):
            dcs_file = full_path
        if copper_slag_file is None and "铜渣" in file_name:
            copper_slag_file = full_path
        if fluorite_sludge_file is None and "氟化钙污泥" in file_name:
            fluorite_sludge_file = full_path
        if replace_fuel_file is None and "替代燃料" in file_name:
            replace_fuel_file = full_path

    matched_files = {
        "DCS表": dcs_file,
        "铜渣表": copper_slag_file,
        "氟化钙污泥表": fluorite_sludge_file,
        "替代燃料表": replace_fuel_file,
    }
    for name, path in matched_files.items():
        if path:
            _log(logger, f"[1号] 找到{name}：{os.path.basename(path)}")
        else:
            _log(logger, f"[1号] 未找到{name}，将跳过处理")

    def weighted_avg_by_date(df, weight_col="吨位"):
        numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
        if weight_col in numeric_cols:
            numeric_cols.remove(weight_col)

        agg_dict = {weight_col: "sum"}
        for col in numeric_cols:
            agg_dict[col] = lambda x: np.average(x, weights=df.loc[x.index, weight_col]) if len(x) > 0 else np.nan

        return df.groupby("日期").agg(agg_dict).reset_index()

    if dcs_file:
        _log(logger, "[1号] 正在处理DCS表...")
        dcs_excel = pd.ExcelFile(dcs_file)

        sheet1 = "化验数据-燃料检测-天"
        fuel_cols = ["数据时间", "入磨煤低位发热量(GJ/t)", "入窑煤低位发热量(GJ/t)", "入磨煤全水(%)", "入磨煤内水(%)", "入窑煤内水(%)"]
        df_dcs_fuel = pd.read_excel(dcs_excel, sheet_name=sheet1, usecols=fuel_cols)
        df_dcs_fuel["日期"] = pd.to_datetime(df_dcs_fuel["数据时间"]).dt.date
        df_dcs_fuel.drop("数据时间", axis=1, inplace=True)
        df_dcs_fuel = df_dcs_fuel[(df_dcs_fuel["日期"] >= start_dt) & (df_dcs_fuel["日期"] <= end_dt)]

        for col in df_dcs_fuel.columns:
            if col == "日期":
                continue
            if col in df_target.columns:
                df_target = df_target.merge(df_dcs_fuel[["日期", col]], on="日期", how="left", suffixes=("", "_new"))
                df_target[col] = df_target[f"{col}_new"].fillna(df_target[col])
                df_target.drop(f"{col}_new", axis=1, inplace=True)
            else:
                df_target = df_target.merge(df_dcs_fuel[["日期", col]], on="日期", how="left")

        sheet2 = "化验数据-熟料检测-小时"
        clinker_cols = ["数据时间", "氧化钙含量(%)", "氧化镁含量(%)"]
        df_dcs_clinker = pd.read_excel(dcs_excel, sheet_name=sheet2, usecols=clinker_cols)
        df_dcs_clinker["日期"] = pd.to_datetime(df_dcs_clinker["数据时间"]).dt.date
        df_dcs_clinker = df_dcs_clinker[(df_dcs_clinker["日期"] >= start_dt) & (df_dcs_clinker["日期"] <= end_dt)]
        df_dcs_day = df_dcs_clinker.groupby("日期")[["氧化钙含量(%)", "氧化镁含量(%)"]].mean().reset_index()
        df_dcs_day.rename(columns={"氧化钙含量(%)": "熟料_氧化钙含量(%)", "氧化镁含量(%)": "熟料_氧化镁含量(%)"}, inplace=True)

        for col in df_dcs_day.columns:
            if col == "日期":
                continue
            if col in df_target.columns:
                df_target = df_target.merge(df_dcs_day[["日期", col]], on="日期", how="left", suffixes=("", "_new"))
                df_target[col] = df_target[f"{col}_new"].fillna(df_target[col])
                df_target.drop(f"{col}_new", axis=1, inplace=True)
            else:
                df_target = df_target.merge(df_dcs_day[["日期", col]], on="日期", how="left")
        _log(logger, "[1号] DCS表处理完成")
    else:
        _log(logger, "[1号] 跳过DCS表处理")

    if copper_slag_file:
        _log(logger, "[1号] 正在处理铜渣表...")
        copper_cols = ["日期", "水分", "Fe2O3", "CaO", "MgO", "SO3", "吨位"]
        df_copper = pd.read_excel(copper_slag_file, sheet_name="report", usecols=copper_cols)
        df_copper = df_copper[df_copper["日期"].astype(str).str.match(r"^\d{4}-\d{2}-\d{2}$", na=False)]
        df_copper["日期"] = pd.to_datetime(df_copper["日期"], errors="coerce", format="%Y-%m-%d").dt.date
        df_copper = df_copper[(df_copper["日期"] >= start_dt) & (df_copper["日期"] <= end_dt)].dropna(subset=["日期"])
        df_copper_agg = weighted_avg_by_date(df_copper, weight_col="吨位")
        df_copper_agg.rename(columns={col: f"铜渣_{col}" for col in copper_cols if col != "日期"}, inplace=True)
        for col in df_copper_agg.columns:
            if col == "日期":
                continue
            if col in df_target.columns:
                df_target = df_target.merge(df_copper_agg[["日期", col]], on="日期", how="left", suffixes=("", "_new"))
                df_target[col] = df_target[f"{col}_new"].fillna(df_target[col])
                df_target.drop(f"{col}_new", axis=1, inplace=True)
            else:
                df_target = df_target.merge(df_copper_agg[["日期", col]], on="日期", how="left")
        _log(logger, "[1号] 铜渣表处理完成")
    else:
        _log(logger, "[1号] 跳过铜渣表处理")

    if fluorite_sludge_file:
        _log(logger, "[1号] 正在处理氟化钙污泥表...")
        fluorite_cols = ["日期", "水分", "SiO2", "CaO", "MgO", "K2O", "Na2O", "R2O", "SO3", "CaF2", "吨位"]
        df_fluorite = pd.read_excel(fluorite_sludge_file, sheet_name="report", usecols=fluorite_cols)
        df_fluorite = df_fluorite[df_fluorite["日期"].astype(str).str.match(r"^\d{4}-\d{2}-\d{2}$", na=False)]
        df_fluorite["日期"] = pd.to_datetime(df_fluorite["日期"], errors="coerce", format="%Y-%m-%d").dt.date
        df_fluorite = df_fluorite[(df_fluorite["日期"] >= start_dt) & (df_fluorite["日期"] <= end_dt)].dropna(subset=["日期"])
        df_fluorite_agg = weighted_avg_by_date(df_fluorite, weight_col="吨位")
        df_fluorite_agg.rename(columns={col: f"萤石_{col}" for col in fluorite_cols if col != "日期"}, inplace=True)
        for col in df_fluorite_agg.columns:
            if col == "日期":
                continue
            if col in df_target.columns:
                df_target = df_target.merge(df_fluorite_agg[["日期", col]], on="日期", how="left", suffixes=("", "_new"))
                df_target[col] = df_target[f"{col}_new"].fillna(df_target[col])
                df_target.drop(f"{col}_new", axis=1, inplace=True)
            else:
                df_target = df_target.merge(df_fluorite_agg[["日期", col]], on="日期", how="left")
        _log(logger, "[1号] 氟化钙污泥表处理完成")
    else:
        _log(logger, "[1号] 跳过氟化钙污泥表处理")

    if replace_fuel_file:
        _log(logger, "[1号] 正在处理替代燃料表...")
        fuel_cols = ["日期", "最大粒径", "水分", "内水", "空干基灰分", "空干基挥发分", "空干基全硫", "空干基热值", "收到基热值（大卡）", "CL-", "吨位"]
        df_fuel = pd.read_excel(replace_fuel_file, sheet_name="report", usecols=fuel_cols)
        df_fuel = df_fuel[df_fuel["日期"].astype(str).str.match(r"^\d{4}-\d{2}-\d{2}$", na=False)]
        df_fuel["日期"] = pd.to_datetime(df_fuel["日期"], errors="coerce", format="%Y-%m-%d").dt.date
        df_fuel = df_fuel[(df_fuel["日期"] >= start_dt) & (df_fuel["日期"] <= end_dt)].dropna(subset=["日期"])
        df_fuel_agg = weighted_avg_by_date(df_fuel, weight_col="吨位")
        df_fuel_agg.rename(columns={col: f"废纺_{col}" for col in fuel_cols if col != "日期"}, inplace=True)
        for col in df_fuel_agg.columns:
            if col == "日期":
                continue
            if col in df_target.columns:
                df_target = df_target.merge(df_fuel_agg[["日期", col]], on="日期", how="left", suffixes=("", "_new"))
                df_target[col] = df_target[f"{col}_new"].fillna(df_target[col])
                df_target.drop(f"{col}_new", axis=1, inplace=True)
            else:
                df_target = df_target.merge(df_fuel_agg[["日期", col]], on="日期", how="left")
        _log(logger, "[1号] 替代燃料表处理完成")
    else:
        _log(logger, "[1号] 跳过替代燃料表处理")

    _log(logger, "[1号] 开始计算自定义新变量...")
    df_target = df_target.sort_values("日期").reset_index(drop=True)
    df_calc_base = pd.concat([df_target, df_keep], axis=0).sort_values("日期").reset_index(drop=True)

    def cal_weight_avg_score(row, target_col, full_df):
        current_date = row["日期"]
        full_df_copy = full_df.copy()
        calc_cols_full = ["石灰石混合料t", "铁质材料（铁粉/铜渣）t", "石灰石配料t", "萤石t", "煤矸石t"]
        for col in calc_cols_full:
            if col in full_df_copy.columns:
                full_df_copy[col] = full_df_copy[col].fillna(0)
            else:
                full_df_copy[col] = 0
        full_df_copy["分母合计"] = (
            full_df_copy["石灰石混合料t"]
            + full_df_copy["铁质材料（铁粉/铜渣）t"]
            + full_df_copy["石灰石配料t"]
            + full_df_copy["萤石t"]
            + full_df_copy["煤矸石t"]
        )
        full_df_copy["分母合计"] = full_df_copy["分母合计"].replace(0, 1)

        valid_df = full_df_copy[
            (full_df_copy["生料消耗量t"] != 0)
            & (full_df_copy["生料消耗量t"].notna())
            & (full_df_copy["日期"] >= current_date - timedelta(days=2))
            & (full_df_copy["日期"] <= current_date)
        ].copy()
        if len(valid_df) == 0:
            return np.nan

        valid_df["date_diff"] = valid_df["日期"].apply(lambda x: (current_date - x).days)
        valid_df["权重"] = valid_df["date_diff"].map({0: 0.5, 1: 0.25, 2: 0.25})
        valid_df["单天占比"] = valid_df[target_col] / valid_df["分母合计"]
        return (valid_df["单天占比"] * valid_df["权重"]).sum() / valid_df["权重"].sum()

    def cal_rolling_avg(row, target_col, full_df, window_days=15):
        current_date = row["日期"]
        offset = 1
        min_date_in_table = full_df["日期"].min()

        while True:
            range_end = current_date - timedelta(days=(offset - 1) * window_days + 1)
            range_start = current_date - timedelta(days=offset * window_days)

            if range_start < min_date_in_table:
                mask = (full_df["日期"] >= min_date_in_table) & (full_df["日期"] <= range_end)
                data = full_df.loc[mask, target_col].dropna()
                if len(data) > 0:
                    return data.mean()
                break

            mask = (full_df["日期"] >= range_start) & (full_df["日期"] <= range_end)
            data = full_df.loc[mask, target_col].dropna()
            if len(data) > 0:
                return data.mean()
            offset += 1

        return np.nan

    var_list = [
        ("铜渣质量分数", "铁质材料（铁粉/铜渣）t", cal_weight_avg_score),
        ("萤石质量分数", "萤石t", cal_weight_avg_score),
        ("煤矸石质量分数", "煤矸石t", cal_weight_avg_score),
        ("铜渣氧化钙含量", "铜渣_CaO", cal_rolling_avg),
        ("铜渣氧化镁含量", "铜渣_MgO", cal_rolling_avg),
        ("萤石氧化钙含量", "萤石_CaO", cal_rolling_avg),
        ("萤石氧化镁含量", "萤石_MgO", cal_rolling_avg),
        ("废纺低位发热量GJ/t", "废纺_收到基热值（大卡）", cal_rolling_avg),
    ]

    calc_mask = (df_target["生料消耗量t"].notna()) & (df_target["生料消耗量t"] != 0)
    _log(logger, f"[1号] 目标区间内生料消耗量非空行数量：{calc_mask.sum()} 条")

    for var_name, col_name, func in var_list:
        df_target[var_name] = np.nan
        if col_name in df_calc_base.columns:
            _log(logger, f"[1号] 正在计算：{var_name}")
            df_target.loc[calc_mask, var_name] = df_target[calc_mask].apply(
                lambda x: func(x, col_name, df_calc_base), axis=1
            )
        else:
            _log(logger, f"[1号] 跳过{var_name}计算：缺失列{col_name}")

    if "废纺低位发热量GJ/t" in df_target.columns:
        df_target["废纺低位发热量GJ/t"] = df_target["废纺低位发热量GJ/t"] * 4.187 / 1000

    df_target.drop(["分母合计"], axis=1, inplace=True, errors="ignore")
    _log(logger, "[1号] 自定义变量计算完成")

    _log(logger, "[1号] 正在合并主表数据...")
    df_final = pd.concat([df_target, df_keep], axis=0).sort_values("日期").reset_index(drop=True)
    output_file_name = f"海螺水泥低频数据_{end_date}.xlsx"
    output_full_path = output_folder / output_file_name
    df_final.to_excel(output_full_path, index=False)
    _log(logger, f"[1号] 低频汇总完成：{output_full_path}")

    return {
        "output_path": str(output_full_path),
        "matched_files": matched_files,
        "rows": len(df_final),
    }


def run_step1_lowfreq_update(
    step0_output_file: str,
    history_lowfreq_file: str,
    lowfreq_current_path: str,
    output_dir: str,
    target_month: str = "",
    logger=None,
    process_start_date: str = "",
    process_end_date: str = "",
) -> dict:
    """
    运行1号低频数据汇总。

    参数：
        step0_output_file: 0号日报提取结果 Excel 路径
        history_lowfreq_file: 历史低频主表文件路径
        lowfreq_current_path: 当月低频数据文件或文件夹路径
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
        if not str(step0_output_file or "").strip():
            raise ValueError("0号日报提取结果不能为空")
        if not str(history_lowfreq_file or "").strip():
            raise ValueError("历史低频主表文件不能为空")
        if not str(lowfreq_current_path or "").strip():
            raise ValueError("当月低频数据路径不能为空")
        if not str(output_dir or "").strip():
            raise ValueError("输出目录不能为空")

        step0_path = Path(step0_output_file).expanduser()
        history_path = Path(history_lowfreq_file).expanduser()
        current_path = Path(lowfreq_current_path).expanduser()
        result_dir = Path(output_dir).expanduser()

        if not step0_path.is_file():
            raise FileNotFoundError(f"0号日报提取结果不存在：{step0_path}")
        if not history_path.is_file():
            raise FileNotFoundError(f"历史低频主表不存在：{history_path}")
        if not current_path.exists():
            raise FileNotFoundError(f"当月低频数据路径不存在：{current_path}")

        source_folder = current_path if current_path.is_dir() else current_path.parent
        start_date, end_date = _resolve_target_date_range(target_month, step0_path, process_start_date, process_end_date)
        _log(logger, f"[1号][诊断] run_step1_lowfreq_update 接收 step0_output_file：{step0_path}")
        _log(logger, f"[1号][诊断] run_step1_lowfreq_update 接收 history_lowfreq_file：{history_path}")
        _log(logger, f"[1号][诊断] run_step1_lowfreq_update 接收 lowfreq_current_path：{current_path}")
        _log(logger, f"[1号][诊断] lowfreq_current_path 类型：{'文件夹' if current_path.is_dir() else '文件'}")
        _log(logger, f"[1号][诊断] 实际传给 run_lowfreq_update 的 source_folder_path：{source_folder}")
        _log(logger, f"[1号][诊断] 目标日期区间：{start_date} 至 {end_date}")
        result = run_lowfreq_update(
            main_file_path=history_path,
            source_folder_path=source_folder,
            output_path=result_dir,
            start_date=start_date,
            end_date=end_date,
            daily_extract_path=step0_path,
            logger=logger,
        )

        output_path = result["output_path"]
        validation = _validate_step1_output(output_path, start_date, end_date)
        result["validation"] = validation
        if not validation["success"]:
            _log(logger, f"[1号] 输出校验失败：{validation['message']}")
            return {
                "success": False,
                "status": "failed",
                "message": validation["message"],
                "output_files": [output_path],
                "detail": result,
            }

        _log(logger, f"[1号] 输出校验通过：{validation['message']}")
        return {
            "success": True,
            "status": "success",
            "message": f"1号低频汇总完成：{output_path}",
            "output_files": [output_path],
            "detail": result,
        }
    except Exception as exc:
        return {
            "success": False,
            "status": "failed",
            "message": str(exc),
            "output_files": [],
            "error": str(exc),
        }


def _validate_step1_output(output_path, start_date, end_date):
    output_file = Path(output_path).expanduser()
    month_label = start_date[:7]
    if not output_file.is_file():
        return {
            "success": False,
            "message": f"1号低频汇总结果文件不存在：{output_file}",
        }

    try:
        df = pd.read_excel(output_file)
    except Exception as exc:
        return {
            "success": False,
            "message": f"1号低频汇总结果无法读取：{exc}",
        }

    if df.empty:
        return {
            "success": False,
            "message": "1号低频汇总结果为空，流程停止",
            "rows": 0,
            "cols": 0,
        }

    date_col = _find_date_column(df)
    if not date_col:
        return {
            "success": False,
            "message": "1号低频汇总结果未识别到日期列，流程停止",
            "rows": int(df.shape[0]),
            "cols": int(df.shape[1]),
        }

    parsed_dates = pd.to_datetime(df[date_col], errors="coerce")
    valid_dates = parsed_dates.dropna()
    if valid_dates.empty:
        return {
            "success": False,
            "message": "1号低频汇总结果日期列无法解析，流程停止",
            "rows": int(df.shape[0]),
            "cols": int(df.shape[1]),
            "date_col": str(date_col),
        }

    start_ts = pd.Timestamp(start_date)
    end_ts = pd.Timestamp(end_date)
    expected_dates = [date.strftime("%Y-%m-%d") for date in pd.date_range(start_ts, end_ts)]
    target_dates = valid_dates[(valid_dates >= start_ts) & (valid_dates <= end_ts)]
    target_date_texts = target_dates.dt.strftime("%Y-%m-%d")
    present_dates = sorted(set(target_date_texts.tolist()))
    missing_dates = [date for date in expected_dates if date not in present_dates]
    duplicate_counts = target_date_texts.value_counts()
    duplicate_dates = sorted(duplicate_counts[duplicate_counts > 1].index.tolist())

    detail = {
        "success": True,
        "message": "",
        "rows": int(df.shape[0]),
        "cols": int(df.shape[1]),
        "date_col": str(date_col),
        "valid_dates": int(valid_dates.shape[0]),
        "min_date": valid_dates.min().strftime("%Y-%m-%d"),
        "max_date": valid_dates.max().strftime("%Y-%m-%d"),
        "target_month": month_label,
        "target_rows": int(target_dates.shape[0]),
        "expected_date_count": len(expected_dates),
        "present_date_count": len(present_dates),
        "missing_dates": missing_dates,
        "duplicate_dates": duplicate_dates,
        "all_empty_cols": [str(col) for col in df.columns[df.isna().all()].tolist()],
    }

    if detail["target_rows"] == 0:
        detail["success"] = False
        detail["message"] = f"1号低频汇总结果未包含处理日期范围{start_date}至{end_date}，流程停止"
        return detail

    if missing_dates:
        shown = ", ".join(missing_dates[:10])
        suffix = f" 等{len(missing_dates)}天" if len(missing_dates) > 10 else ""
        detail["success"] = False
        detail["message"] = f"1号低频汇总结果缺少处理日期：{shown}{suffix}，流程停止"
        return detail

    if pd.Timestamp(valid_dates.max()) < end_ts:
        detail["success"] = False
        detail["message"] = f"1号低频汇总结果日期最大值未达到{end_date}，流程停止"
        return detail

    detail["message"] = (
        f"1号低频汇总结果包含处理日期范围{start_date}至{end_date}，"
        f"目标区间行数{detail['target_rows']}，有效日期{detail['present_date_count']}天"
    )
    return detail


def _find_date_column(df):
    for col in df.columns:
        text = str(col).lower()
        if "日期" in str(col) or "时间" in str(col) or "date" in text:
            return col
    return df.columns[0] if len(df.columns) else None


def _resolve_target_date_range(target_month, step0_path, process_start_date="", process_end_date=""):
    if str(target_month or "").strip():
        range_info = resolve_process_date_range(target_month, process_start_date, process_end_date)
        if not range_info.get("ok"):
            raise ValueError(range_info.get("message", "处理日期范围无效"))
        return range_info["start_date"], range_info["end_date"]

    year, month = _infer_year_month_from_step0_output(step0_path)
    days = calendar.monthrange(year, month)[1]
    range_info = resolve_process_date_range(f"{year:04d}-{month:02d}", process_start_date, process_end_date)
    if range_info.get("ok"):
        return range_info["start_date"], range_info["end_date"]
    return f"{year:04d}-{month:02d}-01", f"{year:04d}-{month:02d}-{days:02d}"


def _parse_target_month(target_month):
    text = str(target_month).strip()
    try:
        dt = pd.to_datetime(f"{text}-01", format="%Y-%m-%d", errors="raise")
    except Exception as exc:
        raise ValueError(f"目标月份格式应为 YYYY-MM，例如 2026-05。当前值：{target_month}") from exc
    return int(dt.year), int(dt.month)


def _infer_year_month_from_step0_output(step0_path):
    df = pd.read_excel(step0_path)
    date_col = "日期" if "日期" in df.columns else df.columns[0]
    dates = pd.to_datetime(df[date_col], errors="coerce").dropna()
    if dates.empty:
        raise ValueError("未填写目标月份，且无法从0号日报提取结果中识别月份")
    first = dates.min()
    return int(first.year), int(first.month)
