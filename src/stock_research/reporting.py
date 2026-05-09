from typing import Any


def format_daily_report(
    trade_date: str,
    quality: list[dict[str, Any]],
    selections: list[dict[str, Any]],
    log_path: str,
) -> str:
    data_status = "异常" if not quality or any(item.get("status", "unknown") != "ok" for item in quality) else "成功"
    lines = [
        "AI 盯盘与选股日报",
        "",
        f"数据状态：{data_status}",
        f"最新交易日：{trade_date}",
        "",
        "数据质量：",
    ]

    for item in quality:
        check_name = item.get("check_name", "unknown_check")
        status = item.get("status", "unknown")
        metric_value = item.get("metric_value", "unknown")
        lines.append(f"- {check_name}：{status}，值={metric_value}")

    lines.extend(["", "今日候选股票池："])
    if not selections:
        lines.append("- 无候选股票")

    for item in selections:
        rank = item.get("rank", "-")
        asset_id = item.get("asset_id", "UNKNOWN")
        score = item.get("score", "-")
        reason_items = item.get("reasons", [])
        risk_tag_items = item.get("risk_tags", [])
        reasons = "；".join(reason_items) if reason_items else "暂无入选原因"
        risks = "；".join(risk_tag_items) if risk_tag_items else "无明显风险标签"
        lines.append(f"{rank}. {asset_id} 评分：{score}")
        lines.append(f"   入选原因：{reasons}")
        lines.append(f"   风险标签：{risks}")

    lines.extend(["", "日志路径：", log_path])
    return "\n".join(lines)
