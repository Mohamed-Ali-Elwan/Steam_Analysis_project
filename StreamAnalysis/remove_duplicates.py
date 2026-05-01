"""
Remove Duplicate Reviews
========================
Reads a JSONL file line by line, deduplicates reviews based on
a composite key (app_id + review identifier), and writes the
cleaned output to a new file.

Works for both:
  - reviews_data.json      (keyed on app_id + review_text)
  - reviews_timestamps.json (keyed on app_id + recommendationid)

Usage:
    python remove_duplicates.py
"""

import sys
import json
import os

sys.stdout.reconfigure(encoding="utf-8")

INPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "output")

FILES_TO_CLEAN = [
    {
        "input":  "reviews_data.json",
        "output": "reviews_data_clean.json",
        "key_fields": ["app_id", "review_text"],
    },
    {
        "input":  "reviews_timestamps.json",
        "output": "reviews_timestamps_clean.json",
        "key_fields": ["app_id", "recommendationid"],
    },
]


def deduplicate(input_path, output_path, key_fields):
    """
    Read JSONL, keep only the first occurrence of each unique
    combination of key_fields, write cleaned JSONL.
    """
    seen = set()
    total = 0
    kept = 0
    duplicates = 0

    with open(input_path, "r", encoding="utf-8") as infile, \
         open(output_path, "w", encoding="utf-8") as outfile:

        for line in infile:
            line = line.strip()
            if not line:
                continue

            total += 1
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                print(f"  Skipping malformed JSON at line {total}")
                continue

            # Build a composite key from the specified fields
            key = tuple(str(item.get(f, "")) for f in key_fields)

            if key not in seen:
                seen.add(key)
                outfile.write(json.dumps(item, ensure_ascii=False) + "\n")
                kept += 1
            else:
                duplicates += 1

    return total, kept, duplicates


def main():
    print("=" * 50)
    print("  Remove Duplicate Reviews")
    print("=" * 50)

    for file_config in FILES_TO_CLEAN:
        input_path = os.path.join(INPUT_DIR, file_config["input"])
        output_path = os.path.join(INPUT_DIR, file_config["output"])

        if not os.path.exists(input_path):
            print(f"\n[SKIP] {file_config['input']} not found.")
            continue

        print(f"\nProcessing: {file_config['input']}")
        print(f"  Key fields: {file_config['key_fields']}")

        total, kept, duplicates = deduplicate(
            input_path, output_path, file_config["key_fields"]
        )

        print(f"  Total lines read:    {total:,}")
        print(f"  Unique lines kept:   {kept:,}")
        print(f"  Duplicates removed:  {duplicates:,}")
        print(f"  Saved to: {file_config['output']}")

    print("\n" + "=" * 50)
    print("  Done!")
    print("=" * 50)


if __name__ == "__main__":
    main()
