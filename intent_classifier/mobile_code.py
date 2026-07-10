import re
import json
import joblib

# LOAD MODEL AND VECTORIZER

model = joblib.load(
    r"intent_model1.pkl"
)

vectorizer = joblib.load(
    r"vectorizer_unique1.pkl"
)

# SPOKEN NUMBERS

NUMBER_WORDS = {
    "zero": 0,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "twenty": 20,
    "thirty": 30,
    "forty": 40,
    "fifty": 50,
    "sixty": 60,
    "seventy": 70,
    "eighty": 80,
    "ninety": 90,
    "hundred": 100
}

# EXTRACT VALUE

def extract_value(command):

    match = re.search(r"\d+", command)

    if match:
        return int(match.group())

    words = command.lower().split()

    for word in words:
        if word in NUMBER_WORDS:
            return NUMBER_WORDS[word]

    return 0


# SINGLE COMMAND CLASSIFIER

def classify_single_command(command):

    value = extract_value(command)

    normalized_command = re.sub(
        r"\d+",
        "NUM",
        command.lower()
    )

    for word in NUMBER_WORDS:
        normalized_command = normalized_command.replace(
            word,
            "NUM"
        )

    X_test = vectorizer.transform(
        [normalized_command]
    )

    intent = model.predict(X_test)[0]

    return {
        "intent": intent,
        "value": value
    }


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
        " followed immediately by "
        
    ]

    processed_text = text.lower()

    for sep in separators:
        processed_text = processed_text.replace(
            sep,
            "|"
        )

    commands = [
        cmd.strip()
        for cmd in processed_text.split("|")
        if cmd.strip()
    ]

    return commands

# MULTI COMMAND CLASSIFIER

def classify_multiple_commands(text):

    commands = split_commands(text)

    sequence = []

    step = 1

    for cmd in commands:

        result = classify_single_command(cmd)

        sequence.append(
            {
                "step": step,
                "intent": result["intent"],
                "value": result["value"]
            }
        )

        step += 1

    return {
        "sequence": sequence
    }
# MAIN

if __name__ == "__main__":

    command = input(
        "Enter command : "
    )

    result = classify_multiple_commands(
        command
    )

    print(
        json.dumps(
            result,
            indent=4
        )
    )