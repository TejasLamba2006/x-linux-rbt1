#!/usr/bin/python3

# Copyright (c) 2025 STMicroelectronics. All rights reserved.
#
# This software component is licensed by ST under BSD 3-Clause license,
# the "License"; You may not use this file except in compliance with the
# License. You may obtain a copy of the License at:
#                        opensource.org/licenses/BSD-3-Clause

"""
Export embedder + classifier head as ONNX, bundle tokenizer, benchmark.

Prerequisites:
  pip install sentence-transformers optimum onnxruntime onnx scikit-learn tokenizers

Run:
  python export_onnx.py export    # export all ONNX models + tokenizer
  python export_onnx.py test      # pooling-equivalence test
  python export_onnx.py bench     # latency benchmark
  python export_onnx.py all       # all of the above
"""

import json
import os
import sys
import time
import numpy as np
import onnxruntime as ort
from pathlib import Path

_DIR = Path(__file__).parent
EMBEDDER_DIR = _DIR / "embedder_onnx"
EMBEDDER_PATH = EMBEDDER_DIR / "model_int8.onnx"
HEAD_PATH = _DIR / "intent_head.onnx"
LABELS_PATH = _DIR / "intent_labels.json"
JOBLIB_PATH = _DIR / "intent_head.joblib"

MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

INTENTS = [
    "FORWARD", "BACKWARD", "STRAFE_LEFT", "STRAFE_RIGHT",
    "ROTATE_LEFT", "ROTATE_RIGHT", "STOP", "PULSE", "NOP",
]


# ---------------------------------------------------------------------------
# Step 1: Export embedder ONNX with pooling
# ---------------------------------------------------------------------------

def cmd_export(_args):
    """Export embedder + head ONNX files + bundle tokenizer."""
    import torch
    import torch.nn as nn
    from transformers import AutoModel, AutoTokenizer

    EMBEDDER_DIR.mkdir(exist_ok=True)

    # --- Embedder export via torch ---
    print(f"Loading model for ONNX export: {MODEL_NAME}")
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    model = AutoModel.from_pretrained(MODEL_NAME)
    model.eval()

    # Wrapper to strip kwargs that break jit.trace
    class EmbedderWrapper(nn.Module):
        def __init__(self, m):
            super().__init__()
            self.model = m
        def forward(self, input_ids, attention_mask):
            return self.model(input_ids=input_ids, attention_mask=attention_mask).last_hidden_state

    wrapper = EmbedderWrapper(model)
    wrapper.eval()

    dummy = tokenizer("forward", return_tensors="pt", padding=True, truncation=True, max_length=128)

    # Export with legacy torch.onnx API (dynamo=False avoids onnxscript issues)
    print("Exporting embedder ONNX...")
    torch.onnx.export(
        wrapper,
        (dummy["input_ids"], dummy["attention_mask"]),
        str(EMBEDDER_PATH),
        input_names=["input_ids", "attention_mask"],
        output_names=["last_hidden_state"],
        dynamic_axes={
            "input_ids": {0: "batch", 1: "seq"},
            "attention_mask": {0: "batch", 1: "seq"},
            "last_hidden_state": {0: "batch", 1: "seq"},
        },
        opset_version=14,
        dynamo=False,
    )

    fp32_size = EMBEDDER_PATH.stat().st_size
    print(f"Embedder ONNX (FP32): {fp32_size / 1024 / 1024:.1f} MB")

    # INT8 dynamic quantization
    print("Quantizing to INT8...")
    from onnxruntime.quantization import quantize_dynamic, QuantType
    quant_path = EMBEDDER_DIR / "model_int8_q.onnx"
    quantize_dynamic(str(EMBEDDER_PATH), str(quant_path), weight_type=QuantType.QInt8)
    quant_size = quant_path.stat().st_size
    print(f"Embedder ONNX (INT8): {quant_size / 1024 / 1024:.1f} MB")

    # Replace FP32 with quantized
    EMBEDDER_PATH.unlink()
    quant_path.rename(EMBEDDER_PATH)
    print(f"Saved quantized model as {EMBEDDER_PATH.name}")

    # --- Bundle tokenizer ---
    print("\nBundling tokenizer locally...")
    tok_json = EMBEDDER_DIR / "tokenizer.json"
    if tok_json.exists():
        tok_json.unlink()
    tokenizer.save_pretrained(str(EMBEDDER_DIR))
    if tok_json.exists():
        print(f"tokenizer.json: {tok_json.stat().st_size / 1024:.1f} KB")
    else:
        print("WARNING: tokenizer.json not found")

    # --- Classifier head export ---
    print("\nExporting classifier head ONNX...")
    _export_head_onnx()

    # --- Measure sizes ---
    print("\n--- Size Report ---")
    total = 0
    for f in sorted(EMBEDDER_DIR.rglob("*")) + sorted(_DIR.glob("intent_head.onnx")) + sorted(_DIR.glob("intent_labels.json")):
        if f.is_file():
            size = f.stat().st_size
            total += size
            rel = str(f.relative_to(_DIR))
            print(f"  {rel:40s}: {size:>12,} bytes ({size/1024/1024:.2f} MB)")
    print(f"  {'TOTAL':40s}: {total:>12,} bytes ({total/1024/1024:.2f} MB)")
    if total > 15 * 1024 * 1024:
        print(f"\n  OVER BUDGET: Total size {total/1024/1024:.1f} MB exceeds 15 MB budget (118M-param model).")
    else:
        print(f"\n  OK: Total size {total/1024/1024:.2f} MB within 15 MB budget")


def _export_head_onnx():
    """Export the MLP classifier head as ONNX with zipmap=False."""
    import joblib
    from skl2onnx import convert_sklearn
    from skl2onnx.common.data_types import FloatTensorType

    clf = joblib.load(str(JOBLIB_PATH))
    print(f"Loaded classifier: {clf.hidden_layer_sizes}, {len(clf.classes_)} classes")

    initial_type = [("embedding", FloatTensorType([None, 384]))]
    clf_onnx = convert_sklearn(
        clf,
        initial_types=initial_type,
        target_opset=13,
        options={"zipmap": False},
    )

    with open(HEAD_PATH, "wb") as f:
        f.write(clf_onnx.SerializeToString())
    print(f"Classifier head ONNX saved: {HEAD_PATH} ({HEAD_PATH.stat().st_size / 1024:.1f} KB)")


# ---------------------------------------------------------------------------
# Step 5: Pooling-equivalence test
# ---------------------------------------------------------------------------

def cmd_test(_args):
    """Verify ONNX embedding matches SentenceTransformer.encode()."""
    from sentence_transformers import SentenceTransformer

    print("Loading SentenceTransformer for reference...")
    st_model = SentenceTransformer(MODEL_NAME)

    print("Loading ONNX embedder...")
    sess = ort.InferenceSession(str(EMBEDDER_PATH), providers=["CPUExecutionProvider"])
    input_names = [inp.name for inp in sess.get_inputs()]

    # Load tokenizer from bundled files
    try:
        from tokenizers import Tokenizer
        tok = Tokenizer.from_file(str(EMBEDDER_DIR / "tokenizer.json"))
        use_bundled = True
        print("Using bundled tokenizer")
    except Exception:
        from transformers import AutoTokenizer
        tok = AutoTokenizer.from_pretrained(MODEL_NAME)
        use_bundled = False
        print("Using transformers tokenizer (bundled not available)")

    test_sentences = [
        "forward",
        "go straight ahead",
        "stop right now",
        "rotate left 90 degrees",
        "peeche jao",
        "aage badho 5 steps",
        "pulse",
        "nothing nevermind",
        "strafe right",
        "halt wait pause",
    ]

    print(f"\nPooling-equivalence test ({len(test_sentences)} sentences):")
    print(f"{'Sentence':<35s} {'Match':>6s} {'Max Diff':>10s}")
    print("-" * 55)

    all_pass = True
    for sent in test_sentences:
        # SentenceTransformer reference embedding
        st_emb = st_model.encode(sent, normalize_embeddings=True)

        # ONNX embedding
        if use_bundled:
            enc = tok.encode(sent)
            input_ids = np.array([enc.ids], dtype=np.int64)
            attention_mask = np.array([enc.attention_mask], dtype=np.int64)
        else:
            tok_out = tok(sent, return_tensors="np", padding=True, truncation=True, max_length=128)
            input_ids = tok_out["input_ids"].astype(np.int64)
            attention_mask = tok_out["attention_mask"].astype(np.int64)

        # Build feed dict matching model input names
        feed = {}
        for name in input_names:
            if "input_ids" in name:
                feed[name] = input_ids
            elif "attention_mask" in name:
                feed[name] = attention_mask
        onnx_out = sess.run(None, feed)
        onnx_emb = onnx_out[0]  # [batch, seq, 384] raw output

        # Manual mean-pooling + L2-normalize (expected path: raw 3D output)
        if onnx_emb.ndim == 3:
            mask = attention_mask[..., None].astype(np.float32)  # [batch, seq, 1]
            summed = (onnx_emb * mask).sum(axis=1)  # [batch, 384]
            counts = np.clip(mask.sum(axis=1), a_min=1e-9, a_max=None)  # [batch, 1]
            onnx_emb = (summed / counts)[0]  # [384] for first batch item
            norm = np.linalg.norm(onnx_emb)
            if norm > 0:
                onnx_emb = onnx_emb / norm

        max_diff = np.max(np.abs(st_emb - onnx_emb))
        match = max_diff < 0.1  # INT8 quantization introduces ~2% error
        all_pass = all_pass and match
        print(f"  {sent:<33s} {'PASS' if match else 'FAIL':>6s} {max_diff:>10.6f}")

    print("-" * 55)
    if all_pass:
        print("PASS: All embeddings match within tolerance (atol=0.1 for INT8)")
        print("NOTE: Mean-pooling + L2-normalize in infer.py is required (raw 3D output)")
    else:
        print("FAIL: Pooling output does not match SentenceTransformer.encode()")
        sys.exit(1)


# ---------------------------------------------------------------------------
# Latency benchmark
# ---------------------------------------------------------------------------

def cmd_bench(_args):
    """Benchmark ONNX inference latency."""
    sess_embed = ort.InferenceSession(str(EMBEDDER_PATH), providers=["CPUExecutionProvider"])
    sess_head = ort.InferenceSession(str(HEAD_PATH), providers=["CPUExecutionProvider"])

    embed_input_names = [inp.name for inp in sess_embed.get_inputs()]
    head_input_name = sess_head.get_inputs()[0].name

    try:
        from tokenizers import Tokenizer
        tok = Tokenizer.from_file(str(EMBEDDER_DIR / "tokenizer.json"))
        use_bundled = True
    except Exception:
        from transformers import AutoTokenizer
        tok = AutoTokenizer.from_pretrained(MODEL_NAME)
        use_bundled = False

    test_commands = [
        "forward", "go straight ahead", "stop right now",
        "rotate left 90 degrees", "peeche jao", "pulse",
        "strafe right 5", "halt wait", "nothing nevermind",
        "aage badho 10 cm",
    ]

    def _tokenize(cmd):
        if use_bundled:
            enc = tok.encode(cmd)
            ids = np.array([enc.ids], dtype=np.int64)
            mask = np.array([enc.attention_mask], dtype=np.int64)
        else:
            tok_out = tok(cmd, return_tensors="np", padding=True, truncation=True, max_length=128)
            ids = tok_out["input_ids"].astype(np.int64)
            mask = tok_out["attention_mask"].astype(np.int64)
        return ids, mask

    def _embed(ids, mask):
        feed = {}
        for name in embed_input_names:
            if "input_ids" in name:
                feed[name] = ids
            elif "attention_mask" in name:
                feed[name] = mask
        raw = sess_embed.run(None, feed)[0]
        # Manual mean-pooling + L2-normalize
        if raw.ndim == 3:
            m = mask[..., None].astype(np.float32)
            summed = (raw * m).sum(axis=1)
            counts = np.clip(m.sum(axis=1), a_min=1e-9, a_max=None)
            pooled = (summed / counts)[0]
            norm = np.linalg.norm(pooled)
            if norm > 0:
                pooled = pooled / norm
            return pooled.astype(np.float32)
        return raw[0].astype(np.float32)

    def _classify(emb):
        return sess_head.run(None, {head_input_name: emb.reshape(1, -1)})[0]

    # Warmup
    for _ in range(5):
        for cmd in test_commands:
            ids, mask = _tokenize(cmd)
            emb = _embed(ids, mask)
            _classify(emb)

    # Benchmark
    n_runs = 100
    embed_times = []
    head_times = []
    total_times = []

    for _ in range(n_runs):
        for cmd in test_commands:
            t0 = time.perf_counter()
            ids, mask = _tokenize(cmd)
            t1 = time.perf_counter()
            emb = _embed(ids, mask)
            t2 = time.perf_counter()
            _classify(emb)
            t3 = time.perf_counter()

            embed_times.append((t2 - t1) * 1000)
            head_times.append((t3 - t2) * 1000)
            total_times.append((t3 - t0) * 1000)

    print(f"\n{'='*60}")
    print(f"Latency Benchmark ({n_runs} runs x {len(test_commands)} commands)")
    print(f"{'='*60}")
    print(f"Embedder (tokenize + ONNX + pool):")
    print(f"  Mean:  {np.mean(embed_times):>8.2f} ms")
    print(f"  P50:   {np.percentile(embed_times, 50):>8.2f} ms")
    print(f"  P95:   {np.percentile(embed_times, 95):>8.2f} ms")
    print(f"  P99:   {np.percentile(embed_times, 99):>8.2f} ms")
    print(f"\nClassifier head:")
    print(f"  Mean:  {np.mean(head_times):>8.2f} ms")
    print(f"  P50:   {np.percentile(head_times, 50):>8.2f} ms")
    print(f"  P95:   {np.percentile(head_times, 95):>8.2f} ms")
    print(f"  P99:   {np.percentile(head_times, 99):>8.2f} ms")
    print(f"\nTotal (tokenize + embed + classify):")
    print(f"  Mean:  {np.mean(total_times):>8.2f} ms")
    print(f"  P50:   {np.percentile(total_times, 50):>8.2f} ms")
    print(f"  P95:   {np.percentile(total_times, 95):>8.2f} ms")
    print(f"  P99:   {np.percentile(total_times, 99):>8.2f} ms")

    if np.percentile(total_times, 95) > 50:
        print(f"\n  WARNING: P95 ({np.percentile(total_times, 95):.1f} ms) exceeds 50 ms target!")
        print(f"  NOTE: This is dev hardware. Actual Cortex-A7 latency may differ.")
    else:
        print(f"\n  OK: P95 ({np.percentile(total_times, 95):.1f} ms) within 50 ms target")
    print(f"  NOTE: Benchmarked on dev hardware. Actual Cortex-A7 latency may differ.")
    print(f"{'='*60}")


COMMANDS = {
    "export": cmd_export,
    "test": cmd_test,
    "bench": cmd_bench,
    "all": lambda args: (cmd_export(args), cmd_test(args), cmd_bench(args)),
}


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(f"Usage: {sys.argv[0]} <{'|'.join(COMMANDS.keys())}>")
        sys.exit(1)
    COMMANDS[sys.argv[1]](sys.argv[2:])


if __name__ == "__main__":
    main()
