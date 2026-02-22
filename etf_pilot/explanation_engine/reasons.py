# -*- coding: utf-8 -*-
"""根据决策（建议类型、溢价否决）生成「建议理由」文案；不包含分数描述。"""


def get_reason_for_signal(
    action: str,
    total_score: float,
    premium_deviation_vetoed: bool,
) -> str:
    """
    根据明日建议类型生成理由文案（兼容旧入口，无 regime/signals/risk 时使用）。
    不输出综合评分，仅用自然语言说明原因。
    premium_deviation_vetoed: 是否因溢价偏离度一票否决。
    """
    if action == "极度过热，禁买" or premium_deviation_vetoed:
        return "溢价偏离度过高，无论技术面如何均不建议买入"
    if action == "强烈建议补仓":
        return "技术、趋势与溢价面偏利多，综合判断适合补仓"
    if action == "持有观望":
        return "暂无明确加仓或减仓信号，建议观望"
    if action == "考虑套利/减仓":
        return "技术或溢价面偏空，可考虑兑现部分仓位"
    return ""
