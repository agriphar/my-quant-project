# -*- coding: utf-8 -*-
"""
Decision Engine 单元测试

测试新架构的决策逻辑。
"""
import pytest
from decision_engine.decision import make_decision
from decision_engine.signal_direction import determine_signal_direction
from decision_engine.risk_constraint import apply_risk_constraint
from decision_engine.confidence_adjustment import apply_confidence_adjustment
from decision_engine.compat import decision_to_legacy_format
from signal_engine import get_signal_states
from risk_engine import evaluate_risk
from confidence_engine import calculate_confidence


class TestSignalDirection:
    """测试信号方向判断（Layer 1）"""
    
    def test_bullish_signals(self):
        """测试看多信号"""
        signal_states = {
            "trend": "UP",
            "valuation": "CHEAP",
            "momentum": "NEUTRAL",
            "volatility": "LOW",
        }
        risk_result = evaluate_risk(signal_states=signal_states)
        
        direction, action = determine_signal_direction(signal_states, risk_result)
        assert direction == "BULLISH"
        assert action == "INCREASE"
    
    def test_bearish_signals(self):
        """测试看空信号"""
        signal_states = {
            "trend": "DOWN",
            "valuation": "EXPENSIVE",
            "momentum": "WEAKENING",
            "volatility": "HIGH",
        }
        risk_result = evaluate_risk(signal_states=signal_states)
        
        direction, action = determine_signal_direction(signal_states, risk_result)
        assert direction == "BEARISH"
        assert action == "REDUCE"
    
    def test_neutral_signals(self):
        """测试中性信号"""
        signal_states = {
            "trend": "SIDEWAYS",
            "valuation": "FAIR",
            "momentum": "NEUTRAL",
            "volatility": "NORMAL",
        }
        risk_result = evaluate_risk(signal_states=signal_states)
        
        direction, action = determine_signal_direction(signal_states, risk_result)
        assert direction in ("NEUTRAL", "BULLISH", "BEARISH")  # 取决于具体判断
        assert action in ("HOLD", "INCREASE", "REDUCE")
    
    def test_unknown_signals(self):
        """测试不确定信号"""
        signal_states = {
            "trend": "UNKNOWN",
            "valuation": "UNKNOWN",
            "momentum": "NEUTRAL",
            "volatility": "NORMAL",
        }
        risk_result = evaluate_risk(signal_states=signal_states)
        
        direction, action = determine_signal_direction(signal_states, risk_result)
        assert direction == "UNKNOWN"
        assert action == "WAIT"


class TestRiskConstraint:
    """测试风险约束（Layer 2）"""
    
    def test_high_risk_constraint(self):
        """测试高风险约束"""
        risk_result = {
            "risk_level": "HIGH",
            "risk_flags": ["high_volatility"],
            "components": {},
        }
        
        action, tags = apply_risk_constraint("INCREASE", risk_result)
        assert action == "HOLD"  # 高风险时禁止增加仓位
        assert "high_risk_constraint" in tags
    
    def test_medium_risk_constraint(self):
        """测试中等风险约束"""
        risk_result = {
            "risk_level": "MEDIUM",
            "risk_flags": [],
            "components": {},
        }
        
        action, tags = apply_risk_constraint("INCREASE", risk_result)
        assert action == "HOLD"  # 中等风险时降低激进程度
        assert "medium_risk_constraint" in tags
    
    def test_low_risk_no_constraint(self):
        """测试低风险不约束"""
        risk_result = {
            "risk_level": "LOW",
            "risk_flags": [],
            "components": {},
        }
        
        action, tags = apply_risk_constraint("INCREASE", risk_result)
        assert action == "INCREASE"  # 低风险时不调整
        assert len(tags) == 0
    
    def test_signal_conflict_force_wait(self):
        """测试信号冲突强制等待"""
        risk_result = {
            "risk_level": "MEDIUM",
            "risk_flags": ["signal_conflict"],
            "components": {},
        }
        
        action, tags = apply_risk_constraint("INCREASE", risk_result)
        assert action == "WAIT"  # 信号冲突时强制等待
        assert "signal_conflict_risk" in tags


class TestConfidenceAdjustment:
    """测试置信度调整（Layer 3）"""
    
    def test_high_confidence(self):
        """测试高置信度"""
        confidence_result = {
            "confidence": "HIGH",
            "confidence_reason": ["high_signal_agreement"],
        }
        
        action, aggressiveness, tags = apply_confidence_adjustment("INCREASE", confidence_result)
        assert action == "INCREASE"
        assert aggressiveness == "HIGH"
        assert "high_confidence" in tags
    
    def test_low_confidence_downgrade(self):
        """测试低置信度降级"""
        confidence_result = {
            "confidence": "LOW",
            "confidence_reason": ["low_signal_agreement"],
        }
        
        action, aggressiveness, tags = apply_confidence_adjustment("INCREASE", confidence_result)
        assert action == "HOLD"  # 低置信度时降级为持有
        assert aggressiveness == "LOW"
        assert "low_confidence" in tags
        assert "low_confidence_adjustment" in tags
    
    def test_medium_confidence(self):
        """测试中等置信度"""
        confidence_result = {
            "confidence": "MEDIUM",
            "confidence_reason": [],
        }
        
        action, aggressiveness, tags = apply_confidence_adjustment("INCREASE", confidence_result)
        assert action == "INCREASE"
        assert aggressiveness == "MEDIUM"


class TestMakeDecision:
    """测试完整决策流程"""
    
    def test_bullish_low_risk_high_confidence(self):
        """测试看多信号 + 低风险 + 高置信度"""
        signal_states = {
            "trend": "UP",
            "valuation": "CHEAP",
            "momentum": "NEUTRAL",
            "volatility": "LOW",
        }
        risk_result = evaluate_risk(signal_states=signal_states)
        confidence_result = calculate_confidence(
            signal_states=signal_states,
            risk_result=risk_result,
        )
        
        decision = make_decision(
            signal_states=signal_states,
            risk_result=risk_result,
            confidence_result=confidence_result,
        )
        
        assert decision["action"] == "INCREASE"
        assert decision["aggressiveness"] == "HIGH"
        assert "bullish_signals" in decision["reason_tags"]
        assert "high_confidence" in decision["reason_tags"]
    
    def test_bullish_high_risk_low_confidence(self):
        """测试看多信号 + 高风险 + 低置信度"""
        signal_states = {
            "trend": "UP",
            "valuation": "FAIR",
            "momentum": "ACCELERATING",
            "volatility": "HIGH",  # 高波动导致高风险
        }
        risk_result = evaluate_risk(signal_states=signal_states)
        confidence_result = calculate_confidence(
            signal_states=signal_states,
            risk_result=risk_result,
        )
        
        decision = make_decision(
            signal_states=signal_states,
            risk_result=risk_result,
            confidence_result=confidence_result,
        )
        
        # 高风险应该限制操作
        assert decision["action"] in ("HOLD", "WAIT")
        assert decision["aggressiveness"] == "LOW"
        assert "high_risk_constraint" in decision["reason_tags"]
    
    def test_bearish_medium_risk_medium_confidence(self):
        """测试看空信号 + 中等风险 + 中等置信度"""
        signal_states = {
            "trend": "DOWN",
            "valuation": "EXPENSIVE",
            "momentum": "WEAKENING",
            "volatility": "NORMAL",
        }
        risk_result = evaluate_risk(signal_states=signal_states)
        confidence_result = calculate_confidence(
            signal_states=signal_states,
            risk_result=risk_result,
        )
        
        decision = make_decision(
            signal_states=signal_states,
            risk_result=risk_result,
            confidence_result=confidence_result,
        )
        
        assert decision["action"] == "REDUCE"
        assert decision["aggressiveness"] == "MEDIUM"
        assert "bearish_signals" in decision["reason_tags"]


class TestCompatibility:
    """测试向后兼容性"""
    
    def test_decision_to_legacy_format(self):
        """测试决策结果转换为旧格式"""
        decision = {
            "action": "INCREASE",
            "aggressiveness": "HIGH",
            "reason_tags": ["bullish_signals", "high_confidence"],
            "risk_result": {
                "risk_flags": [],
                "components": {
                    "signal_disagreement": "LOW",
                },
            },
        }
        
        result = decision_to_legacy_format(decision)
        action_cn, reason, display_label, confidence_band, conflicting_signals, total_score = result
        
        assert action_cn == "强烈建议补仓"
        assert "信号看多" in reason or "高置信度" in reason
        assert display_label == "偏多，可考虑补仓"
        assert confidence_band == "high"
        assert conflicting_signals == False
        assert total_score == 0.0  # 已废弃


class TestLayerIndependence:
    """测试层独立性"""
    
    def test_decision_engine_only_uses_previous_layers(self):
        """测试 Decision Engine 只使用前序层的输出"""
        # 创建完整的信号状态
        signal_states = {
            "trend": "UP",
            "valuation": "CHEAP",
            "momentum": "NEUTRAL",
            "volatility": "LOW",
        }
        
        # 确保 Risk Engine 和 Confidence Engine 的输出可用
        risk_result = evaluate_risk(signal_states=signal_states)
        confidence_result = calculate_confidence(
            signal_states=signal_states,
            risk_result=risk_result,
        )
        
        # Decision Engine 应该能够使用这些输出
        decision = make_decision(
            signal_states=signal_states,
            risk_result=risk_result,
            confidence_result=confidence_result,
        )
        
        # 验证输出格式
        assert "action" in decision
        assert "aggressiveness" in decision
        assert "reason_tags" in decision
        assert decision["action"] in ("INCREASE", "HOLD", "REDUCE", "WAIT")
        assert decision["aggressiveness"] in ("LOW", "MEDIUM", "HIGH")
    
    def test_no_recomputation(self):
        """测试不重新计算前序层的指标"""
        # 这个测试主要验证架构原则
        # 实际验证需要检查代码，确保 Decision Engine 不重新计算信号
        
        signal_states = {
            "trend": "UP",
            "valuation": "CHEAP",
            "momentum": "NEUTRAL",
            "volatility": "LOW",
        }
        
        risk_result = evaluate_risk(signal_states=signal_states)
        
        # 验证 Risk Engine 的输出包含 signal_disagreement
        assert "components" in risk_result
        assert "signal_disagreement" in risk_result["components"]
        
        # Decision Engine 应该使用这个输出，而不是重新计算
        direction, _ = determine_signal_direction(signal_states, risk_result)
        assert direction in ("BULLISH", "BEARISH", "NEUTRAL", "UNKNOWN")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
