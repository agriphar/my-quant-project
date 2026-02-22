# -*- coding: utf-8 -*-
"""根据决策（建议类型、评分、溢价偏离度）生成「建议理由」文案。"""


def get_reason_for_signal(
    action: str,
    total_score: float,
    premium_deviation_vetoed: bool,
) -> str:
    """
    根据明日建议类型与评分生成理由文案。
    premium_deviation_vetoed: 是否因溢价偏离度一票否决。
    """
    if action == "极度过热，禁买" or premium_deviation_vetoed:
        return "溢价偏离度>2.5，无论技术面多高均禁止买入"
    if action == "强烈建议补仓":
        return f"综合评分{total_score}分，技术/趋势/溢价面均偏利多"
    if action == "持有观望":
        return f"综合评分{total_score}分，暂无明确加仓或减仓信号"
    if action == "考虑套利/减仓":
        return f"综合评分{total_score}分，技术或溢价面偏空，可考虑兑现部分仓位"
    return ""
