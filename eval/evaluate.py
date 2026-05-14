"""End-to-end evaluation for classification, drafting, and PII safety.

Default mode is offline and deterministic: the LLM client is mocked from the
golden dataset while the real prompt-building, PII gateway, parsing, and draft
rehydration code still run. Use --live to call the configured model.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.models.email import Email  # noqa: E402
from src.services import classifier, drafter  # noqa: E402
from src.storage import safe_record_eval_case, safe_record_eval_run  # noqa: E402


GOLDEN_PATH = Path(__file__).resolve().parent / "golden.json"


async def run_evaluation(*, live: bool = False, golden_path: Path = GOLDEN_PATH) -> dict:
    golden = json.loads(golden_path.read_text())
    run_id = str(uuid4())
    case_results = []
    original_chat = classifier.llm.chat

    try:
        for item in golden:
            captured_prompts: list[str] = []
            if not live:
                _install_mock_llm(item, captured_prompts)
            else:
                _install_live_spy(original_chat, captured_prompts)

            email = Email(
                id=item["id"],
                sender=item["sender"],
                recipients=item["recipients"],
                subject=item["subject"],
                body=item["body"],
                timestamp=item["timestamp"],
            )

            cls = await classifier.classify(email)
            email.classification = cls
            draft = await drafter.draft_reply(email, cls)
            prompts = captured_prompts if captured_prompts else []

            result = _score_case(item, cls, draft.body, prompts)
            case_results.append(result)
            safe_record_eval_case(run_id, item["id"], result)
    finally:
        classifier.llm.chat = original_chat
        drafter.llm.chat = original_chat

    summary = _summarize(run_id, case_results, live=live)
    safe_record_eval_run(run_id, summary)
    _print_report(summary, case_results)
    return summary


def _install_mock_llm(item: dict, captured_prompts: list[str]) -> None:
    responses = [
        json.dumps(item["mock_classification"]),
        item["mock_draft"],
    ]

    async def mock_chat(messages, **kwargs):
        captured_prompts.append(messages[-1]["content"])
        return responses.pop(0)

    classifier.llm.chat = mock_chat
    drafter.llm.chat = mock_chat


def _install_live_spy(original_chat, captured_prompts: list[str]) -> None:
    async def spy_chat(messages, **kwargs):
        captured_prompts.append(messages[-1]["content"])
        return await original_chat(messages, **kwargs)

    classifier.llm.chat = spy_chat
    drafter.llm.chat = spy_chat


def _score_case(item: dict, cls, draft_body: str, prompts: list[str]) -> dict:
    all_prompt_text = "\n".join(prompts)
    priority_ok = cls.priority.value == item["expected_priority"]
    category_ok = cls.category.value == item["expected_category"]
    draft_ok = all(fragment.lower() in draft_body.lower() for fragment in item.get("expected_draft_contains", []))
    pii_absent = all(secret not in all_prompt_text for secret in item.get("pii_must_not_reach_llm", []))
    tokens_present = all(token in all_prompt_text for token in item.get("expected_mask_tokens", []))
    prompt_captured = bool(prompts)

    checks = {
        "priority": priority_ok,
        "category": category_ok,
        "draft": draft_ok,
        "pii_prompt_absent": pii_absent,
        "mask_tokens_present": tokens_present,
        "prompt_captured": prompt_captured,
    }
    passed = all(checks.values())
    return {
        "case_id": item["id"],
        "subject": item["subject"],
        "expected_priority": item["expected_priority"],
        "actual_priority": cls.priority.value,
        "expected_category": item["expected_category"],
        "actual_category": cls.category.value,
        "draft_body": draft_body,
        "checks": checks,
        "passed": passed,
        "score": sum(checks.values()) / len(checks),
    }


def _summarize(run_id: str, case_results: list[dict], *, live: bool) -> dict:
    case_count = len(case_results)
    passed = sum(1 for result in case_results if result["passed"])
    avg_score = sum(result["score"] for result in case_results) / case_count if case_count else 0
    return {
        "run_id": run_id,
        "mode": "live" if live else "offline",
        "case_count": case_count,
        "passed": passed,
        "failed": case_count - passed,
        "score": round(avg_score, 4),
    }


def _print_report(summary: dict, case_results: list[dict]) -> None:
    print(f"\nEvaluation run {summary['run_id']} ({summary['mode']})")
    print(f"Score: {summary['score']:.0%} | Passed: {summary['passed']}/{summary['case_count']}")
    print("-" * 112)
    print(f"{'ID':<6} {'Priority':<19} {'Category':<28} {'PII Safe':<10} {'Status'}")
    print("-" * 112)
    for result in case_results:
        checks = result["checks"]
        print(
            f"{result['case_id']:<6} "
            f"{result['expected_priority']}->{result['actual_priority']:<12} "
            f"{result['expected_category']}->{result['actual_category']:<18} "
            f"{str(checks['pii_prompt_absent'] and checks['mask_tokens_present']):<10} "
            f"{'OK' if result['passed'] else 'FAIL'}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate the email agent pipeline.")
    parser.add_argument("--live", action="store_true", help="Call the configured LLM instead of mocks.")
    parser.add_argument("--golden", type=Path, default=GOLDEN_PATH, help="Path to golden dataset JSON.")
    args = parser.parse_args()
    asyncio.run(run_evaluation(live=args.live, golden_path=args.golden))


if __name__ == "__main__":
    main()
