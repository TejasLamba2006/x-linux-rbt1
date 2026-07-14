#!/usr/bin/python3

# Copyright (c) 2025 STMicroelectronics. All rights reserved.
#
# This software component is licensed by ST under BSD 3-Clause license,
# the "License"; You may not use this file except in compliance with the
# License. You may obtain a copy of the License at:
#                        opensource.org/licenses/BSD-3-Clause

"""
Multi-command intent classifier (wrapper around infer.py).

Split multi-command text into individual commands, classify each with
the ONNX intent classifier from infer.py, and return a sequence of
(intent, value, confidence) tuples.
"""

import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from infer import classify_single_command

# SPLIT MULTIPLE COMMANDS

def split_commands(text):
    separators = [
        " and then ",
        " then ",
        " after that ",
        " and ",
        ",",
        "also",
        " followed by ",
        " next ",
        " afterwards ",
        " subsequently ",
        " after which ",
        " later ",
        " before ",
        " before that ",
        " meanwhile ",
        " once done ",
        " once completed ",
        " once finished ",
        " proceed to ",
        " continue with ",
        " followed afterwards by ",
        " followed immediately by ",
    ]

    processed_text = text.lower()
    for sep in separators:
        processed_text = processed_text.replace(sep, "|")

    commands = [cmd.strip() for cmd in processed_text.split("|") if cmd.strip()]
    return commands


# MULTI COMMAND CLASSIFIER

def classify_multiple_commands(text):
    commands = split_commands(text)
    sequence = []

    for step, cmd in enumerate(commands, start=1):
        result = classify_single_command(cmd)
        sequence.append({
            "step": step,
            "intent": result["intent"],
            "value": result["value"],
            "confidence": result["confidence"],
        })

    return {"sequence": sequence}


# MAIN

if __name__ == "__main__":
    command = input("Enter command : ")
    result = classify_multiple_commands(command)
    print(json.dumps(result, indent=4))
