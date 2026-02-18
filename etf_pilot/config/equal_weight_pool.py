# -*- coding: utf-8 -*-
"""跨资产等权再平衡策略：精选 5 只长期代表资产。"""
# 513100 纳指、513500 标普、518880 黄金、513520 日经、510880 红利ETF
EQUAL_WEIGHT_POOL = [
    {"code": "513100", "name": "纳指ETF"},
    {"code": "513500", "name": "标普500ETF"},
    {"code": "518880", "name": "黄金ETF"},
    {"code": "513520", "name": "日经ETF"},
    {"code": "510880", "name": "红利ETF"},
]


def get_pool_codes() -> list[str]:
    return [x["code"] for x in EQUAL_WEIGHT_POOL]
