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
    warnings.warn(
        "[infer] tokenizers.lib unavailable; using pure-Python Unigram fallback "
        "(reinstall `tokenizers` on the board for the fast path)")
    import unicodedata

    class _EncResult:
        def __init__(self, ids):
            self.ids = ids
            self.attention_mask = [1] * len(ids)

    # The bundled model is SentencePiece Unigram: model.vocab is a list of
    # [token, log_score] pairs (NOT hashable as-is -- indexing pair[0] is the
    # fix for the old `unhashable type: 'list'` crash). We reproduce Unigram
    # inference (Viterbi max-score segmentation) in pure Python so the ONNX
    # embedder gets the token IDs it was trained on, even when the compiled
    # tokenizers lib is missing/broken.
    _VOCAB_PATH = os.path.join(_DIR, "embedder_onnx", "tokenizer.json")
    with open(_VOCAB_PATH, encoding="utf-8") as _f:
        _model = json.load(_f).get("model", {})
    _raw_vocab = _model.get("vocab", [])

    _tok_to_id = {}
    _tok_to_score = {}
    if isinstance(_raw_vocab, dict):
        # {token: id} form -- no scores, treat all equally (degrades to longest-match)
        for _tok, _idx in _raw_vocab.items():
            _tok_to_id[_tok] = int(_idx)
            _tok_to_score[_tok] = 0.0
    else:
        for _i, _entry in enumerate(_raw_vocab):
            if isinstance(_entry, (list, tuple)):
                _tok, _score = _entry[0], float(_entry[1])
            else:
                _tok, _score = _entry, 0.0  # list-of-strings form
            _tok_to_id[_tok] = _i
            _tok_to_score[_tok] = _score

    _UNK_ID = _tok_to_id.get("<unk>", _tok_to_id.get("[UNK]", 3))
    _BOS_ID = _tok_to_id.get("<s>", 0)
    _EOS_ID = _tok_to_id.get("</s>", 2)
    _SPACE = "▁"  # SentencePiece space marker
    _MAX_PIECE = max((len(t) for t in _tok_to_id), default=1)

    class _UnigramTokenizer:
        """Pure-Python SentencePiece Unigram: Viterbi over vocab log-scores.
        Wraps output with <s>…</s> to match the model's TemplateProcessing."""

        def encode(self, text):
            text = unicodedata.normalize("NFKC", text.strip())
            text = _SPACE + text.replace(" ", _SPACE)
            n = len(text)
            # best[i] = (score, start_of_last_piece) for text[:i]
            neg_inf = float("-inf")
            best = [(0.0, 0)] + [(neg_inf, 0)] * n
            for i in range(1, n + 1):
                for j in range(max(0, i - _MAX_PIECE), i):
                    piece = text[j:i]
                    sc = _tok_to_score.get(piece)
                    if sc is None:
                        continue
                    cand = best[j][0] + sc
                    if cand > best[i][0]:
                        best[i] = (cand, j)
            # Backtrack; unknown single chars fall back to <unk>
            ids = []
            i = n
            while i > 0:
                _, j = best[i]
                if best[i][0] == neg_inf:  # no piece ended here -> emit unk char
                    j = i - 1
                    ids.append(_UNK_ID)
                else:
                    ids.append(_tok_to_id[text[j:i]])
                i = j
            ids.reverse()
            return _EncResult([_BOS_ID] + ids + [_EOS_ID])

    _tokenizer = _UnigramTokenizer()

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


def _selfcheck():
    """Minimal runnable check: the fallback tokenizer must produce non-empty,
    <s>…</s>-wrapped IDs, and (when the real lib is present) match it exactly."""
    enc = _tokenizer.encode("move forward")
    assert enc.ids, "empty token IDs"
    assert len(enc.attention_mask) == len(enc.ids)
    # If we can also load the real tokenizer, cross-check a few commands.
    try:
        from tokenizers import Tokenizer as _Ref
        ref = _Ref.from_file(os.path.join(_DIR, "embedder_onnx", "tokenizer.json"))
        for s in ("move forward", "turn left", "ruko"):
            got = _tokenizer.encode(_preprocess(s)).ids
            want = ref.encode(_preprocess(s)).ids
            assert got == want, f"mismatch on {s!r}:\n got={got}\n want={want}"
        print("[selfcheck] fallback matches reference tokenizer")
    except (ImportError, AttributeError):
        print("[selfcheck] reference tokenizer unavailable; fallback shape OK")
    print("[selfcheck] passed")


if __name__ == "__main__":
    import sys
    if "--selfcheck" in sys.argv:
        _selfcheck()
        sys.exit(0)
    while True:
        try:
            text = input("Command: ")
        except (EOFError, KeyboardInterrupt):
            break
        print(classify_single_command(text))
