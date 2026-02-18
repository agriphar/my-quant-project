# -*- coding: utf-8 -*-
"""多因子分类轮动：资产池分组（硬编码）。"""
from typing import Dict

# 分组名称与关键词（按名称匹配）
GROUP_US_EQUITY = "US_Equity"       # 纳指/标普/道指
GROUP_GLOBAL_EX_US = "Global_Ex_US" # 日经/德/法
GROUP_COMMODITIES = "Commodities"   # 黄金/豆粕
GROUP_ASIA_TECH = "Asia_Tech"       # 东南亚/恒生生科

KEYWORDS = [
    (GROUP_US_EQUITY, ("纳指", "标普", "道指", "纳斯达克", "标普500", "道琼斯")),
    (GROUP_GLOBAL_EX_US, ("日经", "德国", "法国", "德指", "法指", "欧洲")),
    (GROUP_COMMODITIES, ("黄金", "豆粕", "原油", "商品")),
    (GROUP_ASIA_TECH, ("东南亚", "恒生", "生科", "恒科", "港股", "中概")),
]


def get_code_to_group(etf_df) -> Dict[str, str]:
    """
    根据 ETF 列表（需有 代码、名称 列）返回 代码 -> 分组。
    未匹配到的归为 Global_Ex_US 以免遗漏。
    """
    import pandas as pd
    code_to_group = {}
    for _, row in etf_df.iterrows():
        code = str(row.get("代码", "")).strip()
        name = str(row.get("名称", "")).strip()
        if not code:
            continue
        group = None
        for g, kws in KEYWORDS:
            if any(kw in name for kw in kws):
                group = g
                break
        code_to_group[code] = group or GROUP_GLOBAL_EX_US
    return code_to_group
