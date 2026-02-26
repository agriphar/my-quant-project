# -*- coding: utf-8 -*-
"""根据决策（建议类型、溢价偏离度）生成「建议理由」文案；不包含分数描述。"""


def get_reason_for_signal(
    action: str,
    total_score: float,
    premium_deviation_val: float | None = None,
    score_result: dict[str, float] | None = None,
) -> str:
    """
    根据明日建议类型生成理由文案（兼容旧入口，无 regime/signals/risk 时使用）。
    不输出综合评分，仅用自然语言说明原因。
    
    premium_deviation_val: 溢价偏离度 z_score，用于判断是否触发溢价过热警告。
    score_result: 评分结果，用于分析得分占比最高的项。
    """
    # 检查是否触发溢价偏离警告
    premium_warning = ""
    if premium_deviation_val is not None:
        z_score = float(premium_deviation_val)
        if z_score > 2.5:
            premium_warning = f"触发溢价极端过热警告 (z-score: {z_score:.2f})，"
        elif z_score > 1.5:
            premium_warning = f"触发溢价偏离警告 (z-score: {z_score:.2f})，"
    
    # 分析得分占比最高的项（用于生成更精准的理由）
    dominant_factor = ""
    if score_result:
        factors = {
            "trend": score_result.get("trend", 0),
            "momentum": score_result.get("momentum", 0),
            "valuation": score_result.get("valuation", 0),
            "volatility": score_result.get("volatility", 0),
        }
        # 找出绝对值最大的因子（可能是负值）
        max_factor = max(factors.items(), key=lambda x: abs(x[1]))
        if abs(max_factor[1]) > 0.5:
            factor_names = {
                "trend": "趋势",
                "momentum": "动量",
                "valuation": "溢价",
                "volatility": "波动",
            }
            if max_factor[1] < 0:
                dominant_factor = f"因{factor_names[max_factor[0]]}面严重拖累（{max_factor[1]:.1f}分），"
            elif max_factor[1] > 2:
                dominant_factor = f"因{factor_names[max_factor[0]]}面走强（{max_factor[1]:.1f}分），"
    
    if action == "强烈建议补仓":
        return f"{premium_warning}{dominant_factor}技术指标走强且溢价安全，综合判断适合补仓"
    if action == "维持观望/持有":
        if premium_warning:
            return f"{premium_warning}当前处于震荡区间，建议维持观望"
        return f"{dominant_factor}当前处于震荡区间或溢价虽高但趋势未坏，建议持有观望"
    if action == "建议套利/减仓":
        if premium_warning:
            return f"{premium_warning}总分降至{total_score:.1f}，建议立即执行套利操作"
        if score_result and score_result.get("valuation", 0) < -2:
            return f"因溢价极端过热（{score_result.get('valuation', 0):.1f}分惩罚），总分降至{total_score:.1f}，建议立即执行套利操作"
        return f"{dominant_factor}技术面破位或溢价过高，总分{total_score:.1f}，建议考虑套利/减仓"
    return ""
