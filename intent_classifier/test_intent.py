#!/usr/bin/python3
"""pytest tests for intent_classifier (ONNX-based)."""

import sys
import os
import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from infer import classify_single_command


# ── Single-command tests ─────────────────────────────────────────────────────

class TestSingleCommands:

    @pytest.mark.parametrize("text,expected", [
        ("forward", "FORWARD"),
        ("go straight", "FORWARD"),
        ("move ahead", "FORWARD"),
        ("aage badho", "FORWARD"),
        ("aage jao", "FORWARD"),
        ("back", "BACKWARD"),
        ("go back", "BACKWARD"),
        ("peeche jao", "BACKWARD"),
        ("stop", "STOP"),
        ("halt", "STOP"),
        ("ruko", "STOP"),
        ("rotate left", "ROTATE_LEFT"),
        ("turn left", "ROTATE_LEFT"),
        ("left turn", "ROTATE_LEFT"),
        ("rotate right", "ROTATE_RIGHT"),
        ("turn right", "ROTATE_RIGHT"),
        ("strafe left", "STRAFE_LEFT"),
        ("move left", "STRAFE_LEFT"),
        ("strafe right", "STRAFE_RIGHT"),
        ("move right", "STRAFE_RIGHT"),
        ("pulse", "PULSE"),
        ("jaldi aage", "FORWARD"),
        ("nothing", "NOP"),
        ("kuch mat karo", "NOP"),
        ("ignore this", "NOP"),
        ("turn left 90 degrees", "ROTATE_LEFT"),
        ("strafe left 5", "STRAFE_LEFT"),
        ("go back 2 steps", "BACKWARD"),
        ("rotate right 180 degrees", "ROTATE_RIGHT"),
    ])
    def test_single_command(self, text, expected):
        result = classify_single_command(text)
        assert result["intent"] == expected, f"'{text}' -> {result['intent']}, expected {expected}"

    @pytest.mark.parametrize("text", [
        "forward",
        "stop",
        "rotate left",
        "strafe right",
        "pulse",
    ])
    def test_confidence_above_threshold(self, text):
        result = classify_single_command(text)
        assert result["confidence"] >= 0.6, f"'{text}' confidence {result['confidence']:.3f} < 0.6"

    @pytest.mark.parametrize("text", [
        "forward",
        "stop",
        "rotate left",
        "strafe right",
        "pulse",
    ])
    def test_value_is_int(self, text):
        result = classify_single_command(text)
        assert isinstance(result["value"], int)


# ── Value extraction tests ────────────────────────────────────────────────────

class TestValueExtraction:
    """Test that numeric values are extracted correctly from commands."""

    def test_forward_with_number(self):
        result = classify_single_command("forward 5")
        assert result["value"] == 5

    def test_back_3(self):
        result = classify_single_command("back 3")
        assert result["value"] == 3

    def test_no_number(self):
        result = classify_single_command("forward")
        assert result["value"] == 0

    def test_turn_right_90(self):
        result = classify_single_command("turn right 90")
        assert result["value"] == 90

    def test_strafe_left_10(self):
        result = classify_single_command("strafe left 10")
        assert result["value"] == 10


# ── PULSE directionless tests ────────────────────────────────────────────────

class TestPulse:
    """PULSE should be directionless: 'jaldi aage' = FORWARD, not PULSE."""

    def test_jaldi_aage_is_forward(self):
        result = classify_single_command("jaldi aage")
        assert result["intent"] == "FORWARD"

    def test_pulse_is_pulse(self):
        result = classify_single_command("pulse")
        assert result["intent"] == "PULSE"

    def test_nudge_is_pulse(self):
        result = classify_single_command("nudge")
        assert result["intent"] == "PULSE"


# ── STT noise robustness tests ────────────────────────────────────────────────

class TestSTTNoise:
    """Test that the classifier handles common Chrome STT misrecognitions."""

    def test_jaao_jao_gated(self):
        result = classify_single_command("jaao jaao")
        assert result["intent"] == "NOP" or result["confidence"] < 0.6

    def test_ruco_gated(self):
        result = classify_single_command("ruco")
        assert result["intent"] == "NOP" or result["confidence"] < 0.6

    def test_goback(self):
        result = classify_single_command("goback")
        assert result["intent"] == "BACKWARD"

    def test_piche(self):
        result = classify_single_command("piche")
        assert result["intent"] == "BACKWARD"


# ── Nop gate test ─────────────────────────────────────────────────────────────

class TestNopGate:
    """Confidence < 0.6 should return NOP (handled in main.py, not infer.py).
    But infer.py should still return NOP for clearly non-command text."""

    def test_random_text_returns_nop(self):
        result = classify_single_command("what time is it")
        assert result["intent"] == "NOP"

    def test_empty_string(self):
        result = classify_single_command("")
        assert result["intent"] == "NOP"

    def test_hello(self):
        result = classify_single_command("hello")
        assert result["intent"] == "NOP"


# ── Multi-command tests ────────────────────────────────────────────────────────

class TestMultiCommand:
    """Test split_commands + classify_multiple_commands from mobile_code.py."""

    def test_split_two_commands(self):
        from mobile_code import split_commands
        result = split_commands("forward and then stop")
        assert result == ["forward", "stop"]

    def test_split_three_commands(self):
        from mobile_code import split_commands
        result = split_commands("forward 3 then turn left then stop")
        assert len(result) == 3

    def test_classify_multiple(self):
        from mobile_code import classify_multiple_commands
        result = classify_multiple_commands("forward 3 then stop")
        assert len(result["sequence"]) == 2
        assert result["sequence"][0]["intent"] == "FORWARD"
        assert result["sequence"][1]["intent"] == "STOP"

    def test_classify_multiple_with_confidence(self):
        from mobile_code import classify_multiple_commands
        result = classify_multiple_commands("forward then stop")
        for step in result["sequence"]:
            assert "confidence" in step


# ── Main guard ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
