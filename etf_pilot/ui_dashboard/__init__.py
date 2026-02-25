# -*- coding: utf-8 -*-
"""仪表盘 UI：布局、表格与图表展示、样式。"""
from .styling import (
    filter_by_category,
    sort_for_dashboard,
    add_明日建议_warning_prefix,
    style_dashboard_table,
    style_radar_rsi,
)
from .algorithm_text import ALGORITHM_MARKDOWN
from .etf_drilldown import render_etf_drilldown

__all__ = [
    "filter_by_category",
    "sort_for_dashboard",
    "add_明日建议_warning_prefix",
    "style_dashboard_table",
    "style_radar_rsi",
    "ALGORITHM_MARKDOWN",
    "render_etf_drilldown",
]
