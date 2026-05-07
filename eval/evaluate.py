"""Evaluate classifier accuracy against the golden dataset.

Usage:
    python eval/evaluate.py
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

# Ensure project root is importable.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.models.email import Email  # noqa: E402
from src.services.classifier import classify  # noqa: E402


GOLDEN_PATH = Path(__file__).resolve().parent / "golden.json"


async def run_evaluation() -> None:
    with open(GOLDEN_PATH) as f:
        golden = json.load(f)

    total = len(golden)
    priority_correct = 0
    category_correct = 0
    results: list[dict] = []

    for item in golden:
        email = Email(
            id=item["id"],
            sender=item["sender"],
            recipients=item["recipients"],
            subject=item["subject"],
            body=item["body"],
            timestamp=item["timestamp"],
        )

        cls = await classify(email)

        p_ok = cls.priority.value == item["expected_priority"]
        c_ok = cls.category.value == item["expected_category"]
        priority_correct += int(p_ok)
        category_correct += int(c_ok)

        status = "OK" if (p_ok and c_ok) else "MISMATCH"
        results.append({
            "id": item["id"],
            "subject": item["subject"][:50],
            "expected_p": item["expected_priority"],
            "got_p": cls.priority.value,
            "expected_c": item["expected_category"],
            "got_c": cls.category.value,
            "status": status,
        })

    # Print results table.
    print(f"\n{'ID':<6} {'Subject':<52} {'Exp P':<10} {'Got P':<10} {'Exp C':<18} {'Got C':<18} {'Status'}")
    print("-" * 130)
    for r in results:
        print(
            f"{r['id']:<6} {r['subject']:<52} {r['expected_p']:<10} {r['got_p']:<10} "
            f"{r['expected_c']:<18} {r['got_c']:<18} {r['status']}"
        )

    print(f"\nPriority accuracy: {priority_correct}/{total} ({priority_correct/total:.0%})")
    print(f"Category accuracy: {category_correct}/{total} ({category_correct/total:.0%})")
    print(f"Overall (both correct): {sum(1 for r in results if r['status'] == 'OK')}/{total}")


def main() -> None:
    asyncio.run(run_evaluation())


if __name__ == "__main__":
    main()
