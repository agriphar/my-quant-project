# -*- coding: utf-8 -*-
"""兼容：资产分类 re-export 自 market_regime。"""
from market_regime.classification import classify_etfs, get_cached_classification

__all__ = ["classify_etfs", "get_cached_classification"]
