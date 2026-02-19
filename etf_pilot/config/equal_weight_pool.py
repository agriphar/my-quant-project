# -*- coding: utf-8 -*-
"""跨资产等权再平衡策略：精选池配置（默认 5 只长期代表资产）。"""
# 默认精选池：513110 纳指、159655 标普、518880 黄金、513520 日经、159518 标普油气
EQUAL_WEIGHT_POOL = [
    {"code": "513110", "name": "纳斯达克100ETF"},
    {"code": "159655", "name": "标普500ETF"},
    {"code": "518880", "name": "黄金ETF"},
    {"code": "513520", "name": "日经ETF"},
    {"code": "159518", "name": "标普油气ETF嘉实"},
]


def get_pool_codes() -> list[str]:
    return [x["code"] for x in EQUAL_WEIGHT_POOL]


def get_pool_code_to_name() -> dict[str, str]:
    """默认精选池 代码 -> 名称，用于下拉展示。"""
    return {x["code"]: x["name"] for x in EQUAL_WEIGHT_POOL}
