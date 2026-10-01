import os
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd


def _log(logger, message):
    if logger:
        logger(message)
    else:
        print(message)


def _date_stats(df, date_col="日期"):
    if df is None or date_col not in df.columns:
        return {
            "rows": 0 if df is None else len(df),
            "parsed_rows": 0,
            "min_date": None,
            "max_date": None,
        }
    dates = pd.to_datetime(df[date_col], errors="coerce")
    return {
        "rows": len(df),
        "parsed_rows": int(dates.notna().sum()),
        "min_date": dates.min().date() if dates.notna().any() else None,
        "max_date": dates.max().date() if dates.notna().any() else None,
    }


def _format_date(value):
    return value.strftime("%Y-%m-%d") if value else "无"


def _log_date_stats(logger, prefix, path, df):
    stats = _date_stats(df)
    _log(logger, prefix)
    if path:
        _log(logger, f"path = {path}")
    _log(logger, f"rows = {stats['rows']}")
    _log(logger, f"parsed_date_rows = {stats['parsed_rows']}")
    _log(logger, f"min_date = {_format_date(stats['min_date'])}")
    _log(logger, f"max_date = {_format_date(stats['max_date'])}")
    return stats


def _date_range_list(start_dt, end_dt):
    days = (end_dt - start_dt).days
    if days < 0:
        raise ValueError("数据处理结束日期不能早于开始日期。")
    return [start_dt + timedelta(days=offset) for offset in range(days + 1)]


def _coerce_date_column(df, source_name):
    if "日期" not in df.columns and "数据时间" in df.columns:
        df = df.rename(columns={"数据时间": "日期"})
    if "日期" not in df.columns:
        raise ValueError(f"{source_name} 缺少日期列，无法按日期写入低频主表。")

    df = df.copy()
    df["日期"] = pd.to_datetime(df["日期"], errors="coerce").dt.date
    df = df.dropna(subset=["日期"])
    return df


def ensure_date_rows(base_df, start_date, end_date, logger=None):
    """
    确保低频主表中存在本次处理日期范围的完整日期行。

    历史低频主表通常只到上月最后一天；本次月份的数据需要先创建空日期行，
    再由 0号结果和其他低频源文件按日期填充。
    """
    df = _coerce_date_column(base_df, "历史低频主表")
    start_dt = start_date if not isinstance(start_date, str) else datetime.strptime(start_date, "%Y-%m-%d").date()
    end_dt = end_date if not isinstance(end_date, str) else datetime.strptime(end_date, "%Y-%m-%d").date()

    expected_dates = _date_range_list(start_dt, end_dt)
    existing_dates = set(df["日期"].dropna())
    missing_dates = [day for day in expected_dates if day not in existing_dates]

    if missing_dates:
        empty_rows = []
        for day in missing_dates:
            row = {col: np.nan for col in df.columns}
            row["日期"] = day
            empty_rows.append(row)
        df = pd.concat([df, pd.DataFrame(empty_rows, columns=df.columns)], axis=0, ignore_index=True)

    df = df.sort_values("日期").reset_index(drop=True)
    _log(
        logger,
        f"[1号] 当前日期范围行检查完成：应有 {len(expected_dates)} 行，新增 {len(missing_dates)} 行",
    )
    return df


def merge_source_by_date(base_df, source_df, start_date, end_date, source_name, logger=None, require_rows=False):
    """
    按日期把源表字段写入低频主表。

    - 已有日期：源表非空值覆盖原值；
    - 缺失日期：自动新增日期行；
    - 新字段：自动新增列；
    - 空值：不覆盖原有值。
    """
    df = _coerce_date_column(base_df, "低频主表")
    source = _coerce_date_column(source_df, source_name)
    start_dt = start_date if not isinstance(start_date, str) else datetime.strptime(start_date, "%Y-%m-%d").date()
    end_dt = end_date if not isinstance(end_date, str) else datetime.strptime(end_date, "%Y-%m-%d").date()

    source = source[(source["日期"] >= start_dt) & (source["日期"] <= end_dt)].copy()
    source = source.drop_duplicates(subset=["日期"], keep="last").reset_index(drop=True)

    if source.empty:
        message = f"{source_name} 在 {start_dt} 至 {end_dt} 范围内没有可合并数据。"
        if require_rows:
            raise ValueError(message)
        _log(logger, f"[1号] {message} 已跳过。")
        return df, {"source_rows": 0, "target_rows": 0, "added_rows": 0}

    existing_dates = set(df["日期"].dropna())
    missing_dates = [day for day in source["日期"].dropna().unique() if day not in existing_dates]
    if missing_dates:
        empty_rows = []
        for day in missing_dates:
            row = {col: np.nan for col in df.columns}
            row["日期"] = day
            empty_rows.append(row)
        df = pd.concat([df, pd.DataFrame(empty_rows, columns=df.columns)], axis=0, ignore_index=True)

    for col in source.columns:
        if col == "日期":
            continue
        if col not in df.columns:
            df[col] = np.nan
        update_col = f"__{col}_source"
        while update_col in df.columns:
            update_col = f"_{update_col}"
        update_df = source[["日期", col]].rename(columns={col: update_col})
        df = df.merge(update_df, on="日期", how="left")
        df[col] = df[update_col].combine_first(df[col])
        df.drop(update_col, axis=1, inplace=True)

    df = df.sort_values("日期").reset_index(drop=True)
    _log(
        logger,
        f"[1号] {source_name} 按日期合入完成：源数据 {len(source)} 行，新增日期行 {len(missing_dates)} 行",
    )
    return df, {
        "source_rows": len(source),
        "target_rows": len(source),
        "added_rows": len(missing_dates),
    }


def _merge_daily_extract(df_target, daily_extract_path, logger, start_dt, end_dt):
    """
    将 0号已审核的生产日报提取结果合入目标区间。

    原脚本假设这些日报字段已由人工复制到低频主表；App 中加入这一步，
    是为了替代人工复制过程，不改变后续计算公式。
    """
    if not daily_extract_path:
        raise FileNotFoundError("未配置0号生产日报提取结果路径，1号无法合入当前月份日报数据。")
    path = Path(daily_extract_path)
    if not path.exists():
        raise FileNotFoundError(f"未找到生产日报提取结果：{path}")

    _log(logger, f"[1号] 正在合入生产日报提取结果：{path}")
    daily_df = pd.read_excel(path)
    if "日期" not in daily_df.columns:
        raise ValueError(f"生产日报提取结果缺少日期列：{path}")

    daily_df = _coerce_date_column(daily_df, "0号生产日报提取结果")
    daily_stats_all = _log_date_stats(logger, "[FIRST INPUT] zero_output_file", path, daily_df)
    df_target, merge_info = merge_source_by_date(
        df_target,
        daily_df,
        start_dt,
        end_dt,
        "0号生产日报提取结果",
        logger=logger,
        require_rows=True,
    )

    _log(logger, "[1号] 生产日报字段合入完成")
    return df_target, {
        "zero_output_rows": daily_stats_all["rows"],
        "zero_output_min_date": daily_stats_all["min_date"],
        "zero_output_max_date": daily_stats_all["max_date"],
        "added_rows": merge_info.get("added_rows", 0),
        "merged_rows": merge_info.get("target_rows", 0),
    }


def _validate_merged_df_before_save(df, start_dt, end_dt, logger):
    if "日期" not in df.columns:
        raise RuntimeError("1号低频汇总失败：合并后的低频主表缺少日期列。")

    check_df = df.copy()
    check_df["日期"] = pd.to_datetime(check_df["日期"], errors="coerce").dt.date
    expected_dates = set(_date_range_list(start_dt, end_dt))
    actual_dates = set(check_df["日期"].dropna())
    missing_dates = sorted(expected_dates - actual_dates)
    target_rows = int(check_df["日期"].isin(expected_dates).sum())

    _log(logger, "[FIRST PRE-SAVE VERIFY]")
    _log(logger, f"expected_target_rows = {len(expected_dates)}")
    _log(logger, f"actual_target_rows = {target_rows}")
    if missing_dates:
        _log(logger, "missing_dates = " + "；".join(day.strftime("%Y-%m-%d") for day in missing_dates))

    if missing_dates or target_rows != len(expected_dates):
        raise RuntimeError("1号低频汇总失败：合并后的低频主表未包含当前日期范围数据。")


def _log_save_diagnostics(
    logger,
    start_dt,
    end_dt,
    month_ym,
    main_path,
    daily_extract_path,
    source_folder,
    output_full_path,
    historical_stats,
    daily_merge_info,
    merged_df,
):
    merged_stats = _date_stats(merged_df)
    merged_dates = pd.to_datetime(merged_df["日期"], errors="coerce").dt.date if "日期" in merged_df.columns else pd.Series(dtype=object)
    target_mask = (merged_dates >= start_dt) & (merged_dates <= end_dt) if len(merged_dates) else pd.Series(dtype=bool)
    target_range_rows = int(target_mask.sum()) if len(target_mask) else 0
    contains_start = bool((merged_dates == start_dt).any()) if len(merged_dates) else False
    contains_end = bool((merged_dates == end_dt).any()) if len(merged_dates) else False

    _log(logger, "[FIRST SAVE DIAGNOSTICS]")
    _log(logger, f"start_date = {start_dt}")
    _log(logger, f"end_date = {end_dt}")
    _log(logger, f"month_ym = {month_ym}")
    _log(logger, f"historical_file = {main_path}")
    _log(logger, f"zero_output_file = {daily_extract_path}")
    _log(logger, f"source_folder = {source_folder}")
    _log(logger, f"output_file = {output_full_path}")
    _log(logger, f"historical_rows = {historical_stats.get('rows', 0)}")
    _log(logger, f"historical_min_date = {_format_date(historical_stats.get('min_date'))}")
    _log(logger, f"historical_max_date = {_format_date(historical_stats.get('max_date'))}")
    _log(logger, f"zero_output_rows = {daily_merge_info.get('zero_output_rows', 0)}")
    _log(logger, f"zero_output_min_date = {_format_date(daily_merge_info.get('zero_output_min_date'))}")
    _log(logger, f"zero_output_max_date = {_format_date(daily_merge_info.get('zero_output_max_date'))}")
    _log(logger, f"merged_rows = {len(merged_df)}")
    _log(logger, f"merged_min_date = {_format_date(merged_stats.get('min_date'))}")
    _log(logger, f"merged_max_date = {_format_date(merged_stats.get('max_date'))}")
    _log(logger, f"target_range_rows = {target_range_rows}")
    _log(logger, f"contains_start_date = {contains_start}")
    _log(logger, f"contains_end_date = {contains_end}")


def _verify_output_file(output_full_path, start_dt, end_dt, logger):
    verify_df = pd.read_excel(output_full_path)
    if "日期" not in verify_df.columns:
        raise ValueError(f"1号输出文件缺少日期列：{output_full_path}")
    verify_df["日期"] = pd.to_datetime(verify_df["日期"], errors="coerce").dt.date
    stats = _log_date_stats(logger, "[FIRST OUTPUT VERIFY]", output_full_path, verify_df)
    expected_dates = set(_date_range_list(start_dt, end_dt))
    target_mask = (verify_df["日期"] >= start_dt) & (verify_df["日期"] <= end_dt)
    target_range_rows = int(target_mask.sum())
    has_start = bool((verify_df["日期"] == start_dt).any())
    has_end = bool((verify_df["日期"] == end_dt).any())
    actual_dates = set(verify_df["日期"].dropna())
    missing_dates = sorted(expected_dates - actual_dates)
    status = (
        "PASS"
        if target_range_rows == len(expected_dates)
        and has_start
        and has_end
        and not missing_dates
        and stats["max_date"]
        and stats["max_date"] >= end_dt
        else "FAIL"
    )
    _log(logger, f"target_range_rows = {target_range_rows}")
    _log(logger, f"contains_start_date = {has_start}")
    _log(logger, f"contains_end_date = {has_end}")
    if missing_dates:
        _log(logger, "missing_dates = " + "；".join(day.strftime("%Y-%m-%d") for day in missing_dates))
    _log(logger, f"status = {status}")
    if status != "PASS":
        raise RuntimeError(
            f"1号低频汇总失败：输出文件中未检测到{start_dt}至{end_dt}的数据，请检查0号输出是否成功参与合并。"
        )
    stats.update(
        {
            "target_range_rows": target_range_rows,
            "contains_start_date": has_start,
            "contains_end_date": has_end,
        }
    )
    return verify_df, stats


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
    _log(logger, "[1号] 正在读取主表【海螺水泥低频数据】...")
    df_main = pd.read_excel(main_path)

    if "数据时间" in df_main.columns:
        df_main.rename(columns={"数据时间": "日期"}, inplace=True)
    if "日期" not in df_main.columns:
        raise ValueError("低频主表缺少日期列或数据时间列。")

    df_main["日期"] = pd.to_datetime(df_main["日期"]).dt.date
    start_dt = datetime.strptime(start_date, "%Y-%m-%d").date()
    end_dt = datetime.strptime(end_date, "%Y-%m-%d").date()
    historical_stats = _log_date_stats(logger, "[FIRST INPUT] historical_file", main_path, df_main)

    mask_target = (df_main["日期"] >= start_dt) & (df_main["日期"] <= end_dt)
    df_target = df_main[mask_target].reset_index(drop=True)
    df_keep = df_main[~mask_target].reset_index(drop=True)
    _log(logger, f"[1号] 主表拆分完成：目标区间({start_date}~{end_date}) {len(df_target)}条 | 非目标区间保留 {len(df_keep)}条")

    target_rows_before_date_fill = len(df_target)
    df_target = ensure_date_rows(df_target, start_dt, end_dt, logger=logger)
    date_rows_added = max(0, len(df_target) - target_rows_before_date_fill)
    df_target, daily_merge_info = _merge_daily_extract(df_target, daily_extract_path, logger, start_dt, end_dt)

    source_files = [f for f in os.listdir(source_folder) if f.endswith(".xlsx")]
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
        df_target, _ = merge_source_by_date(
            df_target,
            df_dcs_fuel,
            start_dt,
            end_dt,
            "DCS燃料检测",
            logger=logger,
        )

        sheet2 = "化验数据-熟料检测-小时"
        clinker_cols = ["数据时间", "氧化钙含量(%)", "氧化镁含量(%)"]
        df_dcs_clinker = pd.read_excel(dcs_excel, sheet_name=sheet2, usecols=clinker_cols)
        df_dcs_clinker["日期"] = pd.to_datetime(df_dcs_clinker["数据时间"]).dt.date
        df_dcs_clinker = df_dcs_clinker[(df_dcs_clinker["日期"] >= start_dt) & (df_dcs_clinker["日期"] <= end_dt)]
        df_dcs_day = df_dcs_clinker.groupby("日期")[["氧化钙含量(%)", "氧化镁含量(%)"]].mean().reset_index()
        df_dcs_day.rename(columns={"氧化钙含量(%)": "熟料_氧化钙含量(%)", "氧化镁含量(%)": "熟料_氧化镁含量(%)"}, inplace=True)
        df_target, _ = merge_source_by_date(
            df_target,
            df_dcs_day,
            start_dt,
            end_dt,
            "DCS熟料检测",
            logger=logger,
        )
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
        df_target, _ = merge_source_by_date(
            df_target,
            df_copper_agg,
            start_dt,
            end_dt,
            "铜渣表",
            logger=logger,
        )
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
        df_target, _ = merge_source_by_date(
            df_target,
            df_fluorite_agg,
            start_dt,
            end_dt,
            "氟化钙污泥表",
            logger=logger,
        )
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
        df_target, _ = merge_source_by_date(
            df_target,
            df_fuel_agg,
            start_dt,
            end_dt,
            "替代燃料表",
            logger=logger,
        )
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
    df_final_before_dedup = pd.concat([df_target, df_keep], axis=0).sort_values("日期").reset_index(drop=True)
    merged_before_stats = _date_stats(df_final_before_dedup)
    df_final = df_final_before_dedup.drop_duplicates(subset=["日期"], keep="last").sort_values("日期").reset_index(drop=True)
    merged_after_stats = _date_stats(df_final)
    _log(logger, "[FIRST MERGE]")
    _log(logger, f"merged_rows_before_dedup = {len(df_final_before_dedup)}")
    _log(logger, f"merged_rows_after_dedup = {len(df_final)}")
    _log(logger, f"added_rows = {date_rows_added}")
    _log(logger, f"merged_min_date = {_format_date(merged_after_stats['min_date'])}")
    _log(logger, f"merged_max_date = {_format_date(merged_after_stats['max_date'])}")
    output_file_name = f"海螺水泥低频数据_{end_date}.xlsx"
    output_full_path = output_folder / output_file_name
    _log_save_diagnostics(
        logger,
        start_dt,
        end_dt,
        start_dt.strftime("%Y%m"),
        main_path,
        daily_extract_path,
        source_folder,
        output_full_path,
        historical_stats,
        daily_merge_info,
        df_final,
    )
    _validate_merged_df_before_save(df_final, start_dt, end_dt, logger)
    df_final.to_excel(output_full_path, index=False)
    _log(logger, f"[1号] 低频汇总完成：{output_full_path}")
    _, output_stats = _verify_output_file(output_full_path, start_dt, end_dt, logger)

    return {
        "output_path": str(output_full_path),
        "matched_files": matched_files,
        "rows": len(df_final),
        "historical_stats": historical_stats,
        "daily_merge_info": daily_merge_info,
        "merged_rows_before_dedup": len(df_final_before_dedup),
        "merged_rows_after_dedup": len(df_final),
        "added_rows": date_rows_added,
        "output_stats": output_stats,
    }
