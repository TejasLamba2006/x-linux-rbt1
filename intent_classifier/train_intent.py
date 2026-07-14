#!/usr/bin/python3

# Copyright (c) 2025 STMicroelectronics. All rights reserved.
#
# This software component is licensed by ST under BSD 3-Clause license,
# the "License"; You may not use this file except in compliance with the
# License. You may obtain a copy of the License at:
#                        opensource.org/licenses/BSD-3-Clause

"""
Training data generator + CLI for the v2 intent classifier.

Generates 4500+ labeled examples across 9 intents with STT-noise
augmentation, then exports train.json / test.json for downstream
embedding + training (Task 2).

Labels:
  FORWARD, BACKWARD, STRAFE_LEFT, STRAFE_RIGHT,
  ROTATE_LEFT, ROTATE_RIGHT, STOP, PULSE, NOP

Run:
  python train_intent.py generate   # write train.json + test.json
  python train_intent.py test       # run TEST_CASES + STT_NOISE_CASES
"""

import json
import os
import random
import re
import sys

_DIR = os.path.dirname(os.path.abspath(__file__))
TRAIN_PATH = os.path.join(_DIR, "train.json")
TEST_PATH = os.path.join(_DIR, "test.json")

# ---------------------------------------------------------------------------
# Number words / variants
# ---------------------------------------------------------------------------

NUMBER_WORDS = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4,
    "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
    "ten": 10, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
    "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90, "hundred": 100,
}

WORD_VARIANTS = {
    "forwards": "forward",
    "backwards": "backward",
    "lefts": "left",
    "rights": "right",
}

# ---------------------------------------------------------------------------
# Intent keyword banks (English / Hindi-roman / Hinglish)
# ---------------------------------------------------------------------------

_FWD_EN = ["forward", "go ahead", "move forward", "move ahead", "drive forward",
           "drive ahead", "straight", "go straight", "go straight ahead"]
_FWD_HI = ["aage", "aagay", "aagye", "agey", "seedha", "seedhe", "sidha", "sidhe",
           "samne"]
_FWD_HL = ["aage jao", "aage chalo", "seedha chalo", "move karo aage"]

_BWD_EN = ["backward", "go back", "move backward", "reverse", "back up", "go backwards"]
_BWD_HI = ["peeche", "piche", "peechay", "peechay", "ulta"]
_BWD_HL = ["peeche jao", "back karo", "reverse lo"]

_STRAFE_L_EN = ["strafe left", "move left", "go left", "shift left", "slide left",
                "left side", "go to the left"]
_STRAFE_L_HI = ["baayein", "bayen", "bayan", "bayin"]
_STRAFE_L_HL = ["left side jao", "left mein jao"]

_STRAFE_R_EN = ["strafe right", "move right", "go right", "shift right", "slide right",
                "right side", "go to the right"]
_STRAFE_R_HI = ["dayen", "dahine", "dayan", "dayin"]
_STRAFE_R_HL = ["right side jao", "right mein jao"]

_ROT_L_EN = ["rotate left", "turn left", "spin left", "face left", "turn to the left"]
_ROT_L_HI = ["ghuma left", "ghum left", "ghumaao left", "mud ja left", "bayen mud"]
ROTATE_L_HL = ["left ghumo", "left mein mud"]

_ROT_R_EN = ["rotate right", "turn right", "spin right", "face right", "turn to the right"]
_ROT_R_HI = ["ghuma right", "ghum right", "ghumaao right", "mud ja right", "dayen mud"]
ROTATE_R_HL = ["right ghumo", "right mein mud"]

_STOP_EN = ["stop", "halt", "freeze", "stay", "stop moving", "don't move",
            "do not move", "wait", "pause", "brake"]
_STOP_HI = ["ruko", "ruku", "rukna", "rukoo", "thahar", "mat chal", "nahi chal"]
_STOP_HL = ["stop karo", "ruk jao", "rukna hai"]

_PULSE_EN = ["pulse", "nudge", "quick move", "brief pulse", "quick pulse"]
_PULSE_HI = ["jhatka", "ek jhatka"]
_PULSE_HL = ["pulse karo", "jhatka do"]

_NOP_EN = ["nothing", "never mind", "cancel", "nevermind", "scratch that",
           "ignore", "skip", "do nothing", "disregard"]
_NOP_HI = ["kuch nahi", "kuch mat kar", "chhod do", "reekh mat karo"]
_NOP_HL = ["leave it", "leave karo", "skip karo"]

# ---------------------------------------------------------------------------
# Noise / augmentation
# ---------------------------------------------------------------------------

STT_HOMOPHONES = {
    "stop": ["shop", "stap", "top"],
    "shop": ["stop"],
    "left": ["lift", "lyft", "lif"],
    "right": ["write", "rite", "wright"],
    "forward": ["for ward", "four ward", "for word"],
    "backward": ["back ward", "back word", "back word"],
    "straight": ["straight", "strait", "streight"],
    "pulse": ["pals", "puls", "pulse"],
    "nothing": ["nutting", "nuffin"],
    "wait": ["weight", "whait"],
    "halt": ["hot", "hault"],
    "pause": ["paws", "pore"],
    "freeze": ["freez", "freaze"],
    "spin": ["spyn", "spinn"],
    "rotate": ["roate", "rootate"],
    "reverse": ["reverce", "revurse"],
}

STT_HOMOPHONE_INTENTS = {
    "stop": "STOP",
    "shop": "STOP",
    "left": "STRAFE_LEFT",
    "lift": "NOP",
    "lyft": "NOP",
    "write": "NOP",
    "rite": "NOP",
    "forward": "FORWARD",
    "backward": "BACKWARD",
    "straight": "FORWARD",
    "pulse": "PULSE",
    "pals": "NOP",
    "nothing": "NOP",
    "nutting": "NOP",
    "nuffin": "NOP",
    "wait": "STOP",
    "weight": "NOP",
    "halt": "STOP",
    "hot": "NOP",
    "pause": "STOP",
    "paws": "NOP",
    "freeze": "STOP",
    "freez": "NOP",
    "spin": "NOP",
    "roate": "NOP",
    "reverse": "BACKWARD",
    "reverce": "NOP",
}

INTENTS = [
    "FORWARD", "BACKWARD", "STRAFE_LEFT", "STRAFE_RIGHT",
    "ROTATE_LEFT", "ROTATE_RIGHT", "STOP", "PULSE", "NOP",
]


# ---------------------------------------------------------------------------
# Preprocessing (same as infer.py, used for canonical training examples)
# ---------------------------------------------------------------------------

def preprocess(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r'[\u0900-\u097F]+', '', text)
    text = re.sub(r'\d+', ' NUM ', text)
    for unit in ['cm', 'mm', 'm', 'meter', 'meters', 'steps', 'step', 'inch', 'inches']:
        text = re.sub(rf'\b{unit}\b', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


# ---------------------------------------------------------------------------
# Generator
# ---------------------------------------------------------------------------

def _pick(list_, k):
    return random.sample(list_, min(k, len(list_)))


def _apply_stt_noise(text: str, p: float = 0.10) -> str:
    """Randomly swap a word for a homophone to simulate STT error."""
    words = text.split()
    out = []
    for w in words:
        if w in STT_HOMOPHONES and random.random() < p:
            out.append(random.choice(STT_HOMOPHONES[w]))
        else:
            out.append(w)
    return " ".join(out)


def _random_value():
    """Return a random numeric value (digit string) that might appear in a command."""
    return str(random.choice([1, 2, 3, 4, 5, 8, 10, 15, 20, 30, 50, 100]))


def generate_examples():
    """Generate training examples across all 9 intents.

    Target distribution:
      English: 55%, Hindi-roman: 25%, Hinglish: 10%, STT-noise: 10%
      Per intent: ~500 examples (4500+ total)
    """
    examples = []

    intent_banks = {
        "FORWARD":        (_FWD_EN, _FWD_HI, _FWD_HL),
        "BACKWARD":       (_BWD_EN, _BWD_HI, _BWD_HL),
        "STRAFE_LEFT":    (_STRAFE_L_EN, _STRAFE_L_HI, _STRAFE_L_HL),
        "STRAFE_RIGHT":   (_STRAFE_R_EN, _STRAFE_R_HI, _STRAFE_R_HL),
        "ROTATE_LEFT":    (_ROT_L_EN, _ROT_L_HI, ROTATE_L_HL),
        "ROTATE_RIGHT":   (_ROT_R_EN, _ROT_R_HI, ROTATE_R_HL),
        "STOP":           (_STOP_EN, _STOP_HI, _STOP_HL),
        "PULSE":          (_PULSE_EN, _PULSE_HI, _PULSE_HL),
        "NOP":            (_NOP_EN, _NOP_HI, _NOP_HL),
    }

    TARGET_PER_INTENT = 600

    for intent, (en, hi, hl) in intent_banks.items():
        all_en = en
        all_hi = hi
        all_hl = hl
        total_phrases = len(all_en) + len(all_hi) + len(all_hl)

        # Target counts per language group
        n_en = int(TARGET_PER_INTENT * 0.55)
        n_hi = int(TARGET_PER_INTENT * 0.25)
        n_hl = TARGET_PER_INTENT - n_en - n_hi

        # English examples
        per_phrase_en = max(1, n_en // max(1, len(all_en)))
        for phrase in all_en:
            for _ in range(per_phrase_en):
                val = _random_value() if random.random() < 0.3 and intent != "PULSE" else ""
                text = f"{phrase} {val}".strip() if val else phrase
                examples.append({"text": text, "intent": intent})

        # Hindi-roman examples
        per_phrase_hi = max(1, n_hi // max(1, len(all_hi)))
        for phrase in all_hi:
            for _ in range(per_phrase_hi):
                val = _random_value() if random.random() < 0.3 and intent != "PULSE" else ""
                text = f"{phrase} {val}".strip() if val else phrase
                examples.append({"text": text, "intent": intent})

        # Hinglish examples
        per_phrase_hl = max(1, n_hl // max(1, len(all_hl)))
        for phrase in all_hl:
            for _ in range(per_phrase_hl):
                val = _random_value() if random.random() < 0.3 and intent != "PULSE" else ""
                text = f"{phrase} {val}".strip() if val else phrase
                examples.append({"text": text, "intent": intent})

    # Ensure we have enough examples per intent
    print(f"Before balancing: {len(examples)} examples")
    intent_counts = {}
    for ex in examples:
        intent_counts[ex["intent"]] = intent_counts.get(ex["intent"], 0) + 1
    print("Per-intent counts:", intent_counts)

    # Pad under-represented intents to reach TARGET_PER_INTENT
    for intent in INTENTS:
        current = intent_counts.get(intent, 0)
        if current < TARGET_PER_INTENT:
            needed = TARGET_PER_INTENT - current
            bank = intent_banks[intent][0]  # use English bank
            for _ in range(needed):
                phrase = random.choice(bank) if bank else intent.lower()
                val = _random_value() if random.random() < 0.3 and intent != "PULSE" else ""
                text = f"{phrase} {val}".strip() if val else phrase
                examples.append({"text": text, "intent": intent})

    # Shuffle
    random.shuffle(examples)
    return examples


def add_stt_noise(examples):
    """Add STT-noise variants (10% of dataset)."""
    noisy = list(examples)  # keep all originals
    for ex in examples:
        if random.random() < 0.10:
            noisy_text = _apply_stt_noise(ex["text"], p=0.30)
            words = noisy_text.split()
            new_intent = ex["intent"]
            for w in words:
                if w in STT_HOMOPHONE_INTENTS:
                    new_intent = STT_HOMOPHONE_INTENTS[w]
                    break
            noisy.append({"text": noisy_text, "intent": new_intent})
    return noisy



# ---------------------------------------------------------------------------
# Test cases (clean, no augmentation — used for validation)
# ---------------------------------------------------------------------------

TEST_CASES = [
    # FORWARD
    ("forward", "FORWARD"),
    ("go forward", "FORWARD"),
    ("move forward", "FORWARD"),
    ("go ahead", "FORWARD"),
    ("move ahead", "FORWARD"),
    ("drive forward", "FORWARD"),
    ("drive ahead", "FORWARD"),
    ("straight", "FORWARD"),
    ("go straight", "FORWARD"),
    ("go straight ahead", "FORWARD"),
    ("forward 5", "FORWARD"),
    ("aage badho", "FORWARD"),
    ("aage jao", "FORWARD"),
    ("aage chalo", "FORWARD"),
    ("seedha chalo", "FORWARD"),
    ("seedha jao", "FORWARD"),
    ("aage", "FORWARD"),
    ("seedha", "FORWARD"),

    # BACKWARD
    ("backward", "BACKWARD"),
    ("go back", "BACKWARD"),
    ("move backward", "BACKWARD"),
    ("reverse", "BACKWARD"),
    ("back up", "BACKWARD"),
    ("go backwards", "BACKWARD"),
    ("backward 10", "BACKWARD"),
    ("peeche", "BACKWARD"),
    ("piche", "BACKWARD"),
    ("ulta", "BACKWARD"),
    ("peeche jao", "BACKWARD"),

    # STRAFE_LEFT
    ("strafe left", "STRAFE_LEFT"),
    ("move left", "STRAFE_LEFT"),
    ("go left", "STRAFE_LEFT"),
    ("shift left", "STRAFE_LEFT"),
    ("slide left", "STRAFE_LEFT"),
    ("left side", "STRAFE_LEFT"),
    ("go to the left", "STRAFE_LEFT"),
    ("left 3", "STRAFE_LEFT"),
    ("baayein", "STRAFE_LEFT"),
    ("bayen", "STRAFE_LEFT"),
    ("left side jao", "STRAFE_LEFT"),
    ("left mein jao", "STRAFE_LEFT"),

    # STRAFE_RIGHT
    ("strafe right", "STRAFE_RIGHT"),
    ("move right", "STRAFE_RIGHT"),
    ("go right", "STRAFE_RIGHT"),
    ("shift right", "STRAFE_RIGHT"),
    ("slide right", "STRAFE_RIGHT"),
    ("right side", "STRAFE_RIGHT"),
    ("go to the right", "STRAFE_RIGHT"),
    ("right 5", "STRAFE_RIGHT"),
    ("dayen", "STRAFE_RIGHT"),
    ("dahine", "STRAFE_RIGHT"),
    ("right side jao", "STRAFE_RIGHT"),
    ("right mein jao", "STRAFE_RIGHT"),

    # ROTATE_LEFT
    ("rotate left", "ROTATE_LEFT"),
    ("turn left", "ROTATE_LEFT"),
    ("spin left", "ROTATE_LEFT"),
    ("face left", "ROTATE_LEFT"),
    ("turn to the left", "ROTATE_LEFT"),
    ("rotate left 45", "ROTATE_LEFT"),
    ("ghuma left", "ROTATE_LEFT"),
    ("mud ja left", "ROTATE_LEFT"),
    ("bayen mud", "ROTATE_LEFT"),
    ("left ghumo", "ROTATE_LEFT"),

    # ROTATE_RIGHT
    ("rotate right", "ROTATE_RIGHT"),
    ("turn right", "ROTATE_RIGHT"),
    ("spin right", "ROTATE_RIGHT"),
    ("face right", "ROTATE_RIGHT"),
    ("turn to the right", "ROTATE_RIGHT"),
    ("rotate right 90", "ROTATE_RIGHT"),
    ("ghuma right", "ROTATE_RIGHT"),
    ("mud ja right", "ROTATE_RIGHT"),
    ("dayen mud", "ROTATE_RIGHT"),
    ("right ghumo", "ROTATE_RIGHT"),

    # STOP
    ("stop", "STOP"),
    ("halt", "STOP"),
    ("freeze", "STOP"),
    ("stay", "STOP"),
    ("stop moving", "STOP"),
    ("don't move", "STOP"),
    ("do not move", "STOP"),
    ("wait", "STOP"),
    ("pause", "STOP"),
    ("brake", "STOP"),
    ("ruko", "STOP"),
    ("thahar", "STOP"),
    ("mat chal", "STOP"),
    ("stop karo", "STOP"),
    ("ruk jao", "STOP"),

    # PULSE
    ("pulse", "PULSE"),
    ("nudge", "PULSE"),
    ("quick move", "PULSE"),
    ("brief pulse", "PULSE"),
    ("quick pulse", "PULSE"),
    ("jhatka", "PULSE"),
    ("pulse karo", "PULSE"),

    # NOP
    ("nothing", "NOP"),
    ("never mind", "NOP"),
    ("cancel", "NOP"),
    ("nevermind", "NOP"),
    ("scratch that", "NOP"),
    ("ignore", "NOP"),
    ("skip", "NOP"),
    ("do nothing", "NOP"),
    ("disregard", "NOP"),
    ("kuch nahi", "NOP"),
    ("kuch mat kar", "NOP"),
    ("chhod do", "NOP"),
    ("leave it", "NOP"),
    ("leave karo", "NOP"),
    ("skip karo", "NOP"),

    # Homophone edge cases
    ("shop", "STOP"),          # STT: "shop" -> STOP
    ("write", "NOP"),          # STT: "write" -> NOP (not right)
    ("lift", "NOP"),           # STT: "lift" -> NOP (not left)
    ("nutting", "NOP"),
    ("nuffin", "NOP"),
    ("paws", "NOP"),
    ("weight", "NOP"),
    ("hot", "NOP"),
]

STT_NOISE_CASES = [
    # STT-noise test cases (these are already noisy inputs)
    # Expected intent is based on STT_HOMOPHONE_INTENTS mapping
    ("shop", "STOP"),
    ("stap", "STOP"),
    ("top", "NOP"),
    ("lift", "NOP"),
    ("lyft", "NOP"),
    ("lif", "NOP"),
    ("write", "NOP"),
    ("rite", "NOP"),
    ("wright", "NOP"),
    ("for ward", "FORWARD"),
    ("four ward", "NOP"),
    ("back ward", "BACKWARD"),
    ("back word", "NOP"),
    ("straight", "FORWARD"),
    ("strait", "NOP"),
    ("streight", "NOP"),
    ("pals", "NOP"),
    ("puls", "NOP"),
    ("nutting", "NOP"),
    ("nuffin", "NOP"),
    ("weight", "NOP"),
    ("whait", "NOP"),
    ("hot", "NOP"),
    ("hault", "NOP"),
    ("paws", "NOP"),
    ("pore", "NOP"),
    ("freez", "NOP"),
    ("freaze", "NOP"),
    ("spyn", "NOP"),
    ("roate", "NOP"),
    ("rootate", "NOP"),
    ("reverce", "NOP"),
    ("revurse", "NOP"),
]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def cmd_generate(_args):
    """Generate train.json + test.json."""
    random.seed(42)  # reproducible

    examples = generate_examples()
    examples = add_stt_noise(examples)

    # Final shuffle
    random.shuffle(examples)

    # Stratified split: 85% train, 15% test, preserving intent distribution
    by_intent = {}
    for ex in examples:
        by_intent.setdefault(ex["intent"], []).append(ex)

    train, test = [], []
    for intent in INTENTS:
        items = by_intent.get(intent, [])
        random.shuffle(items)
        split_idx = int(len(items) * 0.85)
        train.extend(items[:split_idx])
        test.extend(items[split_idx:])

    # Inject all TEST_CASES + STT_NOISE_CASES into test split
    test_keys = {(ex["text"].lower(), ex["intent"]) for ex in test}
    for text, intent in TEST_CASES:
        if (text.lower(), intent) not in test_keys:
            test.append({"text": text, "intent": intent})
    for text, intent in STT_NOISE_CASES:
        if (text.lower(), intent) not in test_keys:
            test.append({"text": text, "intent": intent})

    random.shuffle(train)
    random.shuffle(test)

    with open(TRAIN_PATH, "w") as f:
        json.dump(train, f, indent=2)
    with open(TEST_PATH, "w") as f:
        json.dump(test, f, indent=2)

    print(f"Generated {len(train)} train + {len(test)} test examples")
    print(f"Train path: {TRAIN_PATH}")
    print(f"Test path:  {TEST_PATH}")

    # Summary per intent
    train_counts = {}
    test_counts = {}
    for ex in train:
        train_counts[ex["intent"]] = train_counts.get(ex["intent"], 0) + 1
    for ex in test:
        test_counts[ex["intent"]] = test_counts.get(ex["intent"], 0) + 1
    print("\nTrain distribution:")
    for intent in INTENTS:
        print(f"  {intent:15s}: {train_counts.get(intent, 0)}")
    print("\nTest distribution:")
    for intent in INTENTS:
        print(f"  {intent:15s}: {test_counts.get(intent, 0)}")


def cmd_test(_args):
    """Print test cases for manual inspection."""
    print("=== TEST_CASES ===")
    for text, expected in TEST_CASES:
        print(f"  {text:35s} -> {expected}")
    print(f"\nTotal: {len(TEST_CASES)} test cases")
    print(f"\n=== STT_NOISE_CASES ===")
    for text, expected in STT_NOISE_CASES:
        print(f"  {text:35s} -> {expected}")
    print(f"\nTotal: {len(STT_NOISE_CASES)} STT-noise cases")


COMMANDS = {
    "generate": cmd_generate,
    "test": cmd_test,
}


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(f"Usage: {sys.argv[0]} <{'|'.join(COMMANDS.keys())}>")
        sys.exit(1)
    COMMANDS[sys.argv[1]](sys.argv[2:])


if __name__ == "__main__":
    main()
