#!/bin/bash
# setup_models.sh — Generate ONNX intent classifier models
#
# Run this on a machine with Python 3.10+ and pip packages:
#   pip install torch transformers onnxruntime sentence-transformers scikit-learn tokenizers
#
# After running, copy intent_classifier/embedder_onnx/ to the board:
#   rsync -avz intent_classifier/embedder_onnx/ root@<board-ip>:/usr/local/x-linux-rbt1/intent_classifier/embedder_onnx/

set -e
cd "$(dirname "$0")"

echo "=== Step 1: Generate training data ==="
python3 train_intent.py generate

echo ""
echo "=== Step 2: Train MLP on ONNX embeddings ==="
python3 train_head.py --onnx

echo ""
echo "=== Step 3: Export to ONNX + quantize ==="
python3 export_onnx.py export

echo ""
echo "=== Step 4: Run tests ==="
python3 export_onnx.py test

echo ""
echo "=== Done! ==="
echo "Models generated in embedder_onnx/"
echo ""
echo "To deploy to board:"
echo "  rsync -avz embedder_onnx/ root@<board-ip>:/usr/local/x-linux-rbt1/intent_classifier/embedder_onnx/"
