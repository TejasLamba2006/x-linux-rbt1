#!/usr/bin/python3

# Copyright (c) 2025 STMicroelectronics. All rights reserved.
#
# This software component is licensed by ST under BSD 3-Clause license,
# the "License"; You may not use this file except in compliance with the
# License. You may obtain a copy of the License at:
#                        opensource.org/licenses/BSD-3-Clause

"""
ONNX-backed intent classifier.

robot_intent_5.onnx is a full sklearn pipeline (TfIdfVectorizer + linear
classifier) exported via skl2onnx, so it takes raw text and returns the
predicted intent label directly -- no separate vectorizer.pkl needed (unlike
mobile_code.py's older joblib-based path, which this replaces).

Labels: FORWARD, BACKWARD, LEFT, RIGHT, TURN_LEFT, TURN_RIGHT, ROTATE_LEFT,
ROTATE_RIGHT, STOP.
"""

import os
import re

import numpy as np
import onnxruntime as ort

MODEL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "robot_intent_5.onnx")

_session = ort.InferenceSession(MODEL_PATH, providers=["CPUExecutionProvider"])
_input_name = _session.get_inputs()[0].name

NUMBER_WORDS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4,
    "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
    "ten": 10, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
    "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90, "hundred": 100,
}

# The model's TF-IDF vocab was built from exact training tokens (forward,
# backward, left, right, ...). Web Speech API commonly transcribes these with
# a trailing "s" (forwards/backwards); unseen tokens get zero TF-IDF weight
# and the classifier falls back to its bias term, misfiring as BACKWARD/RIGHT.
# Normalize known speech-recognition variants back to the trained tokens.
WORD_VARIANTS = {
    "forwards": "forward",
    "backwards": "backward",
    "lefts": "left",
    "rights": "right",
}


def _apply_word_variants(text: str) -> str:
    return re.sub(
        r"\b(" + "|".join(WORD_VARIANTS) + r")\b",
        lambda m: WORD_VARIANTS[m.group(1)],
        text,
    )


def extract_value(command: str) -> int:
    """Pull a numeric magnitude (digits or spelled-out) out of a command."""
    match = re.search(r"\d+", command)
    if match:
        return int(match.group())

    for word in command.lower().split():
        if word in NUMBER_WORDS:
            return NUMBER_WORDS[word]

    return 0


def classify_single_command(command: str) -> dict:
    """Classify one command string -> {"intent": str, "value": int}."""
    value = extract_value(command)

    normalized = re.sub(r"\d+", "NUM", command.lower())
    normalized = _apply_word_variants(normalized)
    for word in NUMBER_WORDS:
        normalized = normalized.replace(word, "NUM")

    X = np.array([[normalized]], dtype=object)
    label = _session.run(None, {_input_name: X})[0][0]

    return {"intent": str(label), "value": value}


if __name__ == "__main__":
    while True:
        try:
            text = input("Command: ")
        except (EOFError, KeyboardInterrupt):
            break
        print(classify_single_command(text))
