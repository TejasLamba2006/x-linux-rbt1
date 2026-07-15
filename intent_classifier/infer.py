#!/usr/bin/python3

# Copyright (c) 2025 STMicroelectronics. All rights reserved.
#
# This software component is licensed by ST under BSD 3-Clause license,
# the "License"; You may not use this file except in compliance with the
# License. You may obtain a copy of the License at:
#                        opensource.org/licenses/BSD-3-Clause

"""
ONNX-backed intent classifier (v2).

Two-stage inference:
  1. Tokenize → ONNX embedder → mean-pool → L2-normalize → 384-dim vector
  2. MLP classifier head → softmax → intent + confidence

Models:
  - embedder_onnx/model_int8.onnx  (sentence-transformers INT8 quantized)
  - intent_head.onnx               (skl2onnx MLP classifier)
  - intent_labels.json             (class order)
  - embedder_onnx/tokenizer.json   (tokenizers lib bundled tokenizer)

Labels: FORWARD, BACKWARD, STRAFE_LEFT, STRAFE_RIGHT, ROTATE_LEFT,
        ROTATE_RIGHT, STOP, PULSE, NOP.
"""

import json
import os
import re

import numpy as np
import onnxruntime as ort

_DIR = os.path.dirname(os.path.abspath(__file__))

# --- Load models at import time ---
_embed_session = ort.InferenceSession(
    os.path.join(_DIR, "embedder_onnx", "model_int8.onnx"),
    providers=["CPUExecutionProvider"],
)
_embed_input_names = [inp.name for inp in _embed_session.get_inputs()]

_head_session = ort.InferenceSession(
    os.path.join(_DIR, "intent_head.onnx"),
    providers=["CPUExecutionProvider"],
)
_head_input_name = _head_session.get_inputs()[0].name

with open(os.path.join(_DIR, "intent_labels.json")) as f:
    LABELS = json.load(f)  # ["BACKWARD", "FORWARD", "NOP", ...]

# --- Load bundled tokenizer (tokenizers lib, not transformers) ---
# The tokenizers package may not export Tokenizer at the top level on older
# Yocto builds.  Try multiple import paths, then fall back to a simple
# regex-based tokenizer that's good enough for short voice commands.
_tokenizer = None
try:
    from tokenizers import Tokenizer as _TkCls
    _tokenizer = _TkCls.from_file(os.path.join(_DIR, "embedder_onnx", "tokenizer.json"))
except (ImportError, AttributeError):
    try:
        from tokenizers.implementations import BaseTokenizer as _TkCls
        _tokenizer = _TkCls.from_file(os.path.join(_DIR, "embedder_onnx", "tokenizer.json"))
    except (ImportError, AttributeError, OSError):
        pass

if _tokenizer is None:
    import warnings
    warnings.warn("[infer] tokenizers.lib unavailable; using regex fallback tokenizer")
    import unicodedata
    _VOCAB_PATH = os.path.join(_DIR, "embedder_onnx", "tokenizer.json")
    with open(_VOCAB_PATH) as _f:
        _model = json.load(_f).get("model", {})
        _raw_vocab = _model.get("vocab", {})
        # vocab may be a {word: id} dict or a [word, ...] list
        if isinstance(_raw_vocab, dict):
            _vocab = _raw_vocab  # already {word: id}
        else:
            _vocab = {w: i for i, w in enumerate(_raw_vocab)}
        _unk_id = _vocab.get("[UNK]", 1)

    class _RegexTokenizer:
        """Minimal regex tokenizer that maps words to vocab IDs."""
        def encode(self, text):
            text = unicodedata.normalize("NFKC", text.lower())
            tokens = re.findall(r"\w+|[^\w\s]", text)
            ids = [_vocab.get(t, _unk_id) for t in tokens]
            return _EncResult(ids)
    class _EncResult:
        def __init__(self, ids):
            self.ids = ids
            self.attention_mask = [1] * len(ids)
    _tokenizer = _RegexTokenizer()

# --- Constants ---
CONFIDENCE_THRESHOLD = 0.6
MAX_LENGTH = 128

NUMBER_WORDS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4,
    "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
    "ten": 10, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
    "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90, "hundred": 100,
}

DEVANAGARI_RE = re.compile(r"[\u0900-\u097F]+")
DIGIT_RE = re.compile(r"\d+")
WHITESPACE_RE = re.compile(r"\s+")

# Units to strip from value extraction
UNITS_RE = re.compile(
    r"\b(cm|mm|m|km|inch|inches|ft|feet|degree|degrees|deg|steps?|step)\b",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Preprocessing
# ---------------------------------------------------------------------------

def _preprocess(text: str) -> str:
    """Normalize raw speech text for embedding model."""
    text = text.lower()
    text = DEVANAGARI_RE.sub("", text)        # strip Devanagari script
    text = DIGIT_RE.sub(" NUM ", text)         # replace digits
    text = UNITS_RE.sub("", text)              # remove units
    text = WHITESPACE_RE.sub(" ", text).strip()
    return text


# ---------------------------------------------------------------------------
# Value extraction
# ---------------------------------------------------------------------------

def extract_value(command: str) -> int:
    """Pull a numeric magnitude (digits or spelled-out) out of a command."""
    match = re.search(r"\d+", command)
    if match:
        return int(match.group())
    for word in command.lower().split():
        if word in NUMBER_WORDS:
            return NUMBER_WORDS[word]
    return 0


# ---------------------------------------------------------------------------
# Embedding (ONNX + manual mean-pooling + L2-normalize)
# ---------------------------------------------------------------------------

def _embed(text: str) -> np.ndarray:
    """Tokenize → ONNX embedder → mean-pool → L2-normalize → [384] float32."""
    enc = _tokenizer.encode(text)
    input_ids = np.array([enc.ids], dtype=np.int64)
    attention_mask = np.array([enc.attention_mask], dtype=np.int64)

    feed = {}
    for name in _embed_input_names:
        if "input_ids" in name:
            feed[name] = input_ids
        elif "attention_mask" in name:
            feed[name] = attention_mask

    raw = _embed_session.run(None, feed)[0]  # [1, seq, 384]

    # Mean-pool over non-padding tokens
    mask = attention_mask[..., None].astype(np.float32)  # [1, seq, 1]
    summed = (raw * mask).sum(axis=1)                     # [1, 384]
    counts = np.clip(mask.sum(axis=1), a_min=1e-9, a_max=None)
    pooled = (summed / counts)[0]                         # [384]

    # L2-normalize
    norm = np.linalg.norm(pooled)
    if norm > 0:
        pooled = pooled / norm
    return pooled.astype(np.float32)


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

def classify_single_command(text: str) -> dict:
    """Classify one command string.

    Returns:
        {"intent": str, "value": int, "confidence": float}

    Confidence threshold: if max softmax prob < CONFIDENCE_THRESHOLD and
    intent is not NOP, return NOP with that confidence.
    """
    value = extract_value(text)
    preprocessed = _preprocess(text)

    # Embed
    embedding = _embed(preprocessed).reshape(1, -1)

    # Classify — head outputs [label, probabilities] with zipmap=False
    outputs = _head_session.run(None, {_head_input_name: embedding})
    probs = outputs[1][0]  # [9] softmax probabilities

    best_idx = int(np.argmax(probs))
    confidence = float(probs[best_idx])
    intent = LABELS[best_idx]

    # Safety gate
    if confidence < CONFIDENCE_THRESHOLD and intent != "NOP":
        intent = "NOP"

    return {"intent": intent, "value": value, "confidence": confidence}


if __name__ == "__main__":
    while True:
        try:
            text = input("Command: ")
        except (EOFError, KeyboardInterrupt):
            break
        print(classify_single_command(text))
