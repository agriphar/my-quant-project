# -*- coding: utf-8 -*-
"""资产分类：Core（宽基/长期牛）与 Tactical（行业/周期）。"""
from config.asset_types import CORE_KEYWORDS

ASSET_TYPE_CORE = "Core"
ASSET_TYPE_TACTICAL = "Tactical"


def get_asset_type(name: str, type_from_excel: str | None = None) -> str:
    """
    返回 'Core' 或 'Tactical'。
    若 Excel 已提供 类型/type 列则优先使用，否则按名称关键词推断。
    """
    if type_from_excel is not None and str(type_from_excel).strip():
        t = str(type_from_excel).strip().lower()
        if t in ("core", "宽基", "长期"):
            return ASSET_TYPE_CORE
        if t in ("tactical", "行业", "周期", "战术"):
            return ASSET_TYPE_TACTICAL
    name = str(name or "")
    for kw in CORE_KEYWORDS:
        if kw in name:
            return ASSET_TYPE_CORE
    return ASSET_TYPE_TACTICAL
