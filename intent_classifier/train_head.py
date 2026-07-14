#!/usr/bin/python3

# Copyright (c) 2025 STMicroelectronics. All rights reserved.
#
# This software component is licensed by ST under BSD 3-Clause license,
# the "License"; You may not use this file except in compliance with the
# License. You may obtain a copy of the License at:
#                        opensource.org/licenses/BSD-3-Clause

"""
Embed training data with sentence-transformer, train MLP classifier head,
validate accuracy against TEST_CASES and STT_NOISE_CASES.

Prerequisites:
  pip install sentence-transformers scikit-learn numpy

Run:
  python train_intent.py train
"""

import json
import os
import re
import sys
import time
import numpy as np
from sklearn.neural_network import MLPClassifier
from sklearn.metrics import classification_report, confusion_matrix
from sentence_transformers import SentenceTransformer

_DIR = os.path.dirname(os.path.abspath(__file__))
TRAIN_PATH = os.path.join(_DIR, "train.json")
TEST_PATH = os.path.join(_DIR, "test.json")
MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"

INTENTS = [
    "FORWARD", "BACKWARD", "STRAFE_LEFT", "STRAFE_RIGHT",
    "ROTATE_LEFT", "ROTATE_RIGHT", "STOP", "PULSE", "NOP",
]


def preprocess(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r'[\u0900-\u097F]+', '', text)
    text = re.sub(r'\d+', ' NUM ', text)
    for unit in ['cm', 'mm', 'm', 'meter', 'meters', 'steps', 'step', 'inch', 'inches']:
        text = re.sub(rf'\b{unit}\b', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def cmd_train(_args):
    """Embed + train + validate."""
    print("Loading training data...")
    with open(TRAIN_PATH) as f:
        train_data = json.load(f)
    with open(TEST_PATH) as f:
        test_data = json.load(f)

    print(f"Train: {len(train_data)} examples, Test: {len(test_data)} examples")

    # Preprocess all texts
    train_texts = [preprocess(ex["text"]) for ex in train_data]
    train_labels = [ex["intent"] for ex in train_data]
    test_texts = [preprocess(ex["text"]) for ex in test_data]
    test_labels = [ex["intent"] for ex in test_data]

    # Load sentence-transformer
    print(f"\nLoading model: {MODEL_NAME}")
    model = SentenceTransformer(MODEL_NAME)
    embedding_dim = model.get_sentence_embedding_dimension()
    print(f"Embedding dimension: {embedding_dim}")

    # Embed training data
    print("\nEmbedding training data...")
    t0 = time.time()
    train_embeddings = model.encode(train_texts, show_progress_bar=True, batch_size=64)
    t1 = time.time()
    print(f"Training embeddings: {train_embeddings.shape} in {t1-t0:.1f}s")

    # Embed test data
    print("Embedding test data...")
    test_embeddings = model.encode(test_texts, show_progress_bar=True, batch_size=64)
    print(f"Test embeddings: {test_embeddings.shape}")

    # Train MLP classifier head
    print("\nTraining MLP classifier head...")
    clf = MLPClassifier(
        hidden_layer_sizes=(128, 64),
        activation='relu',
        max_iter=500,
        early_stopping=True,
        validation_fraction=0.15,
        random_state=42,
        verbose=True,
    )
    t0 = time.time()
    clf.fit(train_embeddings, train_labels)
    t1 = time.time()
    print(f"Training time: {t1-t0:.1f}s")
    print(f"Training accuracy: {clf.score(train_embeddings, train_labels):.4f}")
    print(f"Number of iterations: {clf.n_iter_}")

    # Validate on test set
    print("\n--- Test Set Results ---")
    test_pred = clf.predict(test_embeddings)
    test_acc = clf.score(test_embeddings, test_labels)
    print(f"Test accuracy: {test_acc:.4f}")
    print("\nClassification report:")
    print(classification_report(test_labels, test_pred, labels=INTENTS))
    print("Confusion matrix:")
    print(confusion_matrix(test_labels, test_pred, labels=INTENTS))

    # Validate specifically on TEST_CASES
    print("\n--- TEST_CASES Results ---")
    test_case_texts = [t for t, _ in _get_test_cases()]
    test_case_labels = [l for _, l in _get_test_cases()]
    tc_embeddings = model.encode(test_case_texts, batch_size=64)
    tc_pred = clf.predict(tc_embeddings)
    tc_acc = sum(1 for p, l in zip(tc_pred, test_case_labels) if p == l) / len(test_case_labels)
    print(f"TEST_CASES accuracy: {tc_acc:.4f} ({sum(1 for p,l in zip(tc_pred, test_case_labels) if p==l)}/{len(test_case_labels)})")

    # Validate on STT_NOISE_CASES
    print("\n--- STT_NOISE_CASES Results ---")
    stt_texts = [t for t, _ in _get_stt_cases()]
    stt_labels = [l for _, l in _get_stt_cases()]
    stt_embeddings = model.encode(stt_texts, batch_size=64)
    stt_pred = clf.predict(stt_embeddings)
    stt_acc = sum(1 for p, l in zip(stt_pred, stt_labels) if p == l) / len(stt_labels)
    print(f"STT_NOISE_CASES accuracy: {stt_acc:.4f} ({sum(1 for p,l in zip(stt_pred, stt_labels) if p==l)}/{len(stt_labels)})")

    # Save classifier head as joblib for later ONNX export
    import joblib
    clf_path = os.path.join(_DIR, "intent_head.joblib")
    joblib.dump(clf, clf_path)
    print(f"\nSaved classifier head to {clf_path}")

    # Save label order
    labels_path = os.path.join(_DIR, "intent_labels.json")
    with open(labels_path, "w") as f:
        json.dump(clf.classes_.tolist(), f)
    print(f"Saved label order to {labels_path}")

    # Report
    print("\n" + "="*60)
    print("REPORT")
    print("="*60)
    print(f"Model:              {MODEL_NAME}")
    print(f"Embedding dim:      {embedding_dim}")
    print(f"Train accuracy:     {clf.score(train_embeddings, train_labels):.4f}")
    print(f"Test accuracy:      {test_acc:.4f}")
    print(f"TEST_CASES acc:     {tc_acc:.4f}")
    print(f"STT_NOISE acc:      {stt_acc:.4f}")
    print(f"Classifier layers:  {clf.hidden_layer_sizes}")
    print(f"Classifier params:  {sum(w.size for w in clf.coefs_) + sum(w.size for w in clf.intercepts_)}")
    print("="*60)


def _get_test_cases():
    """Import test cases from train_intent.py."""
    sys.path.insert(0, _DIR)
    from train_intent import TEST_CASES
    return TEST_CASES


def _get_stt_cases():
    """Import STT noise cases from train_intent.py."""
    sys.path.insert(0, _DIR)
    from train_intent import STT_NOISE_CASES
    return STT_NOISE_CASES


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] != "train":
        print(f"Usage: {sys.argv[0]} train")
        sys.exit(1)
    cmd_train(sys.argv[2:])
