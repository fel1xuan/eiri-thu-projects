import calendar
from datetime import date, datetime, timedelta


def parse_target_month(target_month: str) -> dict:
    text = str(target_month or "").strip()
    if not text:
        return {"ok": False, "message": "处理月份未填写", "target_month": ""}
    try:
        dt = datetime.strptime(f"{text}-01", "%Y-%m-%d")
    except Exception:
        return {"ok": False, "message": "处理月份格式应为 YYYY-MM", "target_month": text}
    days = calendar.monthrange(dt.year, dt.month)[1]
    return {
        "ok": True,
        "target_month": f"{dt.year:04d}-{dt.month:02d}",
        "year": dt.year,
        "month": dt.month,
        "days": days,
        "start_date": f"{dt.year:04d}-{dt.month:02d}-01",
        "end_date": f"{dt.year:04d}-{dt.month:02d}-{days:02d}",
    }


def month_bounds(target_month: str) -> tuple[str, str]:
    info = parse_target_month(target_month)
    if not info.get("ok"):
        raise ValueError(info.get("message", "处理月份无效"))
    return info["start_date"], info["end_date"]


def parse_date(date_text: str, label: str = "日期") -> date:
    text = str(date_text or "").strip()
    if not text:
        raise ValueError(f"{label}不能为空")
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except Exception as exc:
        raise ValueError(f"{label}格式应为 YYYY-MM-DD：{date_text}") from exc


def resolve_process_date_range(
    target_month: str,
    process_start_date: str = "",
    process_end_date: str = "",
) -> dict:
    month_info = parse_target_month(target_month)
    if not month_info.get("ok"):
        return {
            "ok": False,
            "message": month_info.get("message", "处理月份无效"),
            "target_month": str(target_month or "").strip(),
            "start_date": str(process_start_date or "").strip(),
            "end_date": str(process_end_date or "").strip(),
            "days": 0,
            "dates": [],
        }

    month_start = parse_date(month_info["start_date"], "当月开始日期")
    month_end = parse_date(month_info["end_date"], "当月结束日期")
    start = parse_date(process_start_date or month_info["start_date"], "处理开始日期")
    end = parse_date(process_end_date or month_info["end_date"], "处理结束日期")

    if start > end:
        return _invalid(month_info, start, end, "处理开始日期不能晚于处理结束日期")
    if start < month_start or start > month_end or end < month_start or end > month_end:
        return _invalid(month_info, start, end, "处理日期范围必须属于同一个处理月份，不允许跨月")
    if start.strftime("%Y-%m") != month_info["target_month"] or end.strftime("%Y-%m") != month_info["target_month"]:
        return _invalid(month_info, start, end, "处理日期范围必须属于同一个处理月份，不允许跨月")

    dates = date_texts_between(start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"))
    return {
        "ok": True,
        "message": f"处理日期范围：{dates[0]} 至 {dates[-1]}，共{len(dates)}天",
        "target_month": month_info["target_month"],
        "month_start": month_info["start_date"],
        "month_end": month_info["end_date"],
        "start_date": dates[0],
        "end_date": dates[-1],
        "days": len(dates),
        "dates": dates,
    }


def default_process_range_for_month(target_month: str) -> tuple[str, str]:
    return month_bounds(target_month)


def fill_process_dates(config: dict) -> dict:
    merged = dict(config or {})
    target_month = str(merged.get("target_month", "") or "").strip()
    if not target_month:
        merged.setdefault("process_start_date", "")
        merged.setdefault("process_end_date", "")
        return merged

    resolved = resolve_process_date_range(
        target_month,
        merged.get("process_start_date", ""),
        merged.get("process_end_date", ""),
    )
    if resolved.get("ok"):
        merged["target_month"] = resolved["target_month"]
        merged["process_start_date"] = resolved["start_date"]
        merged["process_end_date"] = resolved["end_date"]
    else:
        start, end = month_bounds(target_month)
        if not str(merged.get("process_start_date", "") or "").strip():
            merged["process_start_date"] = start
        if not str(merged.get("process_end_date", "") or "").strip():
            merged["process_end_date"] = end
    return merged


def date_texts_between(start_date: str, end_date: str) -> list[str]:
    start = parse_date(start_date, "开始日期")
    end = parse_date(end_date, "结束日期")
    if start > end:
        raise ValueError("开始日期不能晚于结束日期")
    dates = []
    current = start
    while current <= end:
        dates.append(current.strftime("%Y-%m-%d"))
        current += timedelta(days=1)
    return dates


def _invalid(month_info, start, end, message):
    return {
        "ok": False,
        "message": message,
        "target_month": month_info.get("target_month", ""),
        "month_start": month_info.get("start_date", ""),
        "month_end": month_info.get("end_date", ""),
        "start_date": start.strftime("%Y-%m-%d") if hasattr(start, "strftime") else str(start),
        "end_date": end.strftime("%Y-%m-%d") if hasattr(end, "strftime") else str(end),
        "days": 0,
        "dates": [],
    }
