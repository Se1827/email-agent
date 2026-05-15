"""End-to-end evaluation for the email agent.

The evaluator produces plain Markdown and JSON artifacts that show every
important step: input email, PII masking, prompt sent to the LLM, raw model
output, parsed classification, generated draft, privacy checks, and storage
status. Default mode is offline and deterministic; use --live for real model
calls and --storage-probe for an explicit encrypted PostgreSQL write test.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.models.email import Email  # noqa: E402
from src.services import classifier, drafter  # noqa: E402
from src.services.pii import PrivacyGateway  # noqa: E402
from src.storage import (  # noqa: E402
    generate_encryption_key,
    record_event,
    safe_record_eval_case,
    safe_record_eval_run,
    storage_configured,
)


GOLDEN_PATH = Path(__file__).resolve().parent / "golden.json"
DEFAULT_REPORT_DIR = Path(__file__).resolve().parent / "reports"


async def run_evaluation(
    *,
    live: bool = False,
    golden_path: Path = GOLDEN_PATH,
    report_dir: Path = DEFAULT_REPORT_DIR,
    storage_probe: bool = False,
) -> dict:
    golden = json.loads(golden_path.read_text())
    run_id = str(uuid4())
    case_results = []
    original_chat = classifier.llm.chat
    storage = _storage_status(storage_probe=storage_probe)

    try:
        for item in golden:
            interactions: list[dict] = []
            if not live:
                _install_mock_llm(item, interactions)
            else:
                _install_live_spy(original_chat, interactions)

            email = Email(
                id=item["id"],
                sender=item["sender"],
                recipients=item["recipients"],
                subject=item["subject"],
                body=item["body"],
                timestamp=item["timestamp"],
            )

            privacy = _inspect_privacy(item)
            cls = await classifier.classify(email)
            email.classification = cls
            draft = await drafter.draft_reply(email, cls)

            result = _score_case(item, cls, draft.body, interactions, privacy)
            case_results.append(result)
            safe_record_eval_case(run_id, item["id"], result)
    finally:
        classifier.llm.chat = original_chat
        drafter.llm.chat = original_chat

    summary = _summarize(run_id, case_results, live=live, storage=storage)
    safe_record_eval_run(run_id, summary)
    artifacts = _write_artifacts(report_dir, run_id, summary, case_results)
    summary["artifacts"] = {name: str(path) for name, path in artifacts.items()}
    _print_report(summary, case_results)
    return summary


def _install_mock_llm(item: dict, interactions: list[dict]) -> None:
    responses = [
        json.dumps(item["mock_classification"]),
        item["mock_draft"],
    ]

    async def mock_chat(messages, **kwargs):
        response = responses.pop(0)
        interactions.append(_interaction("classification" if not interactions else "draft", messages, response, kwargs))
        return response

    classifier.llm.chat = mock_chat
    drafter.llm.chat = mock_chat


def _install_live_spy(original_chat, interactions: list[dict]) -> None:
    async def spy_chat(messages, **kwargs):
        stage = "classification" if not interactions else "draft"
        response = await original_chat(messages, **kwargs)
        interactions.append(_interaction(stage, messages, response, kwargs))
        return response

    classifier.llm.chat = spy_chat
    drafter.llm.chat = spy_chat


def _interaction(stage: str, messages: list[dict[str, str]], response: str, kwargs: dict) -> dict:
    return {
        "stage": stage,
        "messages": messages,
        "user_prompt": messages[-1]["content"] if messages else "",
        "raw_output": response,
        "params": kwargs,
    }


def _inspect_privacy(item: dict) -> dict:
    gateway = PrivacyGateway()
    masked = {
        "sender": gateway.mask_text(item["sender"]).text,
        "recipients": gateway.mask_text(", ".join(item["recipients"])).text,
        "subject": gateway.mask_text(item["subject"]).text,
        "body": gateway.mask_text(item["body"]).text,
    }
    return {
        "masked_email": masked,
        "mappings": [
            {
                "token": mapping.token,
                "entity_type": mapping.entity_type,
                "original_preview": _preview_secret(mapping.original),
            }
            for mapping in gateway.mappings
        ],
        "found_types": sorted({_public_type(mapping.entity_type) for mapping in gateway.mappings}),
        "semantic_nlp_loaded": gateway._analyzer is not None or gateway._nlp is not None,
    }


def _score_case(item: dict, cls, draft_body: str, interactions: list[dict], privacy: dict) -> dict:
    all_prompt_text = "\n".join(interaction["user_prompt"] for interaction in interactions)
    priority_ok = cls.priority.value == item["expected_priority"]
    category_ok = cls.category.value == item["expected_category"]
    pii_absent = all(secret not in all_prompt_text for secret in item.get("pii_must_not_reach_llm", []))
    tokens_present = all(token in all_prompt_text for token in item.get("expected_mask_tokens", []))
    prompt_captured = len(interactions) == 2
    draft_intents = _evaluate_draft_expectations(item, draft_body)
    draft_review_ok = all(intent["matched"] for intent in draft_intents) if draft_intents else True

    must_pass_checks = {
        "priority": priority_ok,
        "category": category_ok,
        "pii_prompt_absent": pii_absent,
        "mask_tokens_present": tokens_present,
        "prompt_captured": prompt_captured,
    }
    review_checks = {
        "draft_contains": draft_review_ok,
    }
    all_checks = {**must_pass_checks, **review_checks}
    passed = all(must_pass_checks.values())

    return {
        "case_id": item["id"],
        "input_email": {
            "sender": item["sender"],
            "recipients": item["recipients"],
            "subject": item["subject"],
            "body": item["body"],
            "timestamp": item["timestamp"],
        },
        "privacy": privacy,
        "expected": {
            "priority": item["expected_priority"],
            "category": item["expected_category"],
            "draft_contains": item.get("expected_draft_contains", []),
            "pii_must_not_reach_llm": item.get("pii_must_not_reach_llm", []),
            "mask_tokens": item.get("expected_mask_tokens", []),
        },
        "actual": {
            "priority": cls.priority.value,
            "category": cls.category.value,
            "confidence": cls.confidence,
            "reasoning": cls.reasoning,
            "draft_body": draft_body,
        },
        "llm_interactions": interactions,
        "checks": all_checks,
        "must_pass_checks": must_pass_checks,
        "review_checks": review_checks,
        "draft_fragment_matches": {intent["name"]: intent["matched"] for intent in draft_intents},
        "draft_intent_matches": draft_intents,
        "passed": passed,
        "status": "PASS" if passed else "FAIL",
        "score": sum(all_checks.values()) / len(all_checks),
    }


def _summarize(run_id: str, case_results: list[dict], *, live: bool, storage: dict) -> dict:
    case_count = len(case_results)
    passed = sum(1 for result in case_results if result["passed"])
    must_checks = [
        passed
        for result in case_results
        for passed in result["must_pass_checks"].values()
    ]
    review_checks = [
        passed
        for result in case_results
        for passed in result["review_checks"].values()
    ]
    return {
        "run_id": run_id,
        "mode": "live" if live else "offline",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "case_count": case_count,
        "passed": passed,
        "failed": case_count - passed,
        "must_pass_score": round(sum(must_checks) / len(must_checks), 4) if must_checks else 0,
        "review_score": round(sum(review_checks) / len(review_checks), 4) if review_checks else 0,
        "storage": storage,
    }


def _evaluate_draft_expectations(item: dict, draft_body: str) -> list[dict]:
    expectations = item.get("expected_draft_intents")
    if not expectations:
        expectations = [
            {"name": fragment, "any_of": _phrase_family(fragment)}
            for fragment in item.get("expected_draft_contains", [])
        ]

    normalized = _normalize_text(draft_body)
    results = []
    for expectation in expectations:
        alternatives = expectation.get("any_of", [])
        matched_by = next(
            (phrase for phrase in alternatives if _normalize_text(phrase) in normalized),
            None,
        )
        results.append(
            {
                "name": expectation.get("name", "draft_expectation"),
                "matched": matched_by is not None,
                "matched_by": matched_by,
                "any_of": alternatives,
            }
        )
    return results


def _phrase_family(fragment: str) -> list[str]:
    families = {
        "jumping on this": [
            "jumping on this",
            "investigating",
            "looking into",
            "working on",
            "aware of the issue",
        ],
        "update": [
            "update",
            "provide an update",
            "share an update",
            "as soon as possible",
        ],
        "Thursday EOD": [
            "Thursday EOD",
            "EOD Thursday",
            "end of day on Thursday",
            "by Thursday",
        ],
        "Thanks": [
            "Thanks",
            "Thank you",
            "appreciate",
        ],
        "No response": [
            "No response",
            "not be clicking",
            "not responding",
            "appears to be unsolicited",
            "remove my email address",
        ],
        "confirm": [
            "confirm",
            "notified",
            "provide an update",
            "in touch",
            "once complete",
            "once the process is complete",
        ],
        "invoice #4821": [
            "invoice #4821",
            "invoice 4821",
        ],
        "rotate": [
            "rotate",
            "rotated",
            "new token",
        ],
        "proceed": [
            "proceed",
            "can proceed",
            "process this request",
        ],
    }
    return families.get(fragment, [fragment])


def _normalize_text(value: str) -> str:
    return " ".join(value.lower().replace("-", " ").split())


def _storage_status(*, storage_probe: bool) -> dict:
    status = {
        "configured": storage_configured(),
        "probe_requested": storage_probe,
        "encryption_roundtrip": False,
        "write_probe": "skipped",
    }
    key = generate_encryption_key()
    from src.storage import decrypt_payload, encrypt_payload

    ciphertext = encrypt_payload({"ok": True}, key)
    status["encryption_roundtrip"] = decrypt_payload(ciphertext, key) == {"ok": True}

    if storage_probe:
        if not storage_configured():
            status["write_probe"] = "skipped_not_configured"
        else:
            try:
                record_event("eval.storage_probe", {"ok": True})
                status["write_probe"] = "ok"
            except Exception as exc:
                status["write_probe"] = f"failed: {exc}"
    return status


def _write_artifacts(report_dir: Path, run_id: str, summary: dict, case_results: list[dict]) -> dict[str, Path]:
    report_dir.mkdir(parents=True, exist_ok=True)
    json_path = report_dir / f"{run_id}.json"
    md_path = report_dir / f"{run_id}.md"
    payload = {"summary": summary, "cases": case_results}
    json_path.write_text(json.dumps(payload, indent=2, default=str))
    md_path.write_text(_render_markdown(summary, case_results))
    return {"json": json_path, "markdown": md_path}


def _render_markdown(summary: dict, case_results: list[dict]) -> str:
    lines = [
        f"# Evaluation Run {summary['run_id']}",
        "",
        f"- Mode: `{summary['mode']}`",
        f"- Created: `{summary['created_at']}`",
        f"- Must-pass score: `{summary['must_pass_score']:.0%}`",
        f"- Review score: `{summary['review_score']:.0%}`",
        f"- Passed cases: `{summary['passed']}/{summary['case_count']}`",
        f"- Storage configured: `{summary['storage']['configured']}`",
        f"- Storage encryption roundtrip: `{summary['storage']['encryption_roundtrip']}`",
        f"- Storage write probe: `{summary['storage']['write_probe']}`",
        "",
        "## Case Summary",
        "",
        "| Case | Status | Priority | Category | PII Safe | Draft Review |",
        "|---|---|---|---|---|---|",
    ]
    for result in case_results:
        checks = result["must_pass_checks"]
        lines.append(
            f"| {result['case_id']} | {result['status']} | "
            f"{result['expected']['priority']} -> {result['actual']['priority']} | "
            f"{result['expected']['category']} -> {result['actual']['category']} | "
            f"{checks['pii_prompt_absent'] and checks['mask_tokens_present']} | "
            f"{result['review_checks']['draft_contains']} |"
        )

    for result in case_results:
        lines.extend(_render_case(result))
    return "\n".join(lines) + "\n"


def _render_case(result: dict) -> list[str]:
    email = result["input_email"]
    lines = [
        "",
        f"## {result['case_id']} - {email['subject']}",
        "",
        f"Status: `{result['status']}`",
        "",
        "### Input Email",
        "",
        f"- From: `{email['sender']}`",
        f"- To: `{', '.join(email['recipients'])}`",
        f"- Timestamp: `{email['timestamp']}`",
        "",
        "```text",
        email["body"],
        "```",
        "",
        "### PII Layer",
        "",
        f"- Found types: `{', '.join(result['privacy']['found_types']) or 'none'}`",
        f"- Semantic NLP loaded: `{result['privacy']['semantic_nlp_loaded']}`",
        "",
        "Mappings:",
        "",
        "| Token | Type | Original Preview |",
        "|---|---|---|",
    ]
    mappings = result["privacy"]["mappings"]
    if mappings:
        for mapping in mappings:
            lines.append(f"| `{mapping['token']}` | `{mapping['entity_type']}` | `{mapping['original_preview']}` |")
    else:
        lines.append("| none | none | none |")

    lines.extend([
        "",
        "Masked body:",
        "",
        "```text",
        result["privacy"]["masked_email"]["body"],
        "```",
        "",
        "### Classification",
        "",
        f"- Expected: `{result['expected']['priority']}` / `{result['expected']['category']}`",
        f"- Actual: `{result['actual']['priority']}` / `{result['actual']['category']}`",
        f"- Confidence: `{result['actual']['confidence']}`",
        f"- Reasoning: {result['actual']['reasoning']}",
        "",
        "### Draft",
        "",
        "```text",
        result["actual"]["draft_body"],
        "```",
        "",
        "Draft intent checks:",
        "",
    ])
    if result["draft_intent_matches"]:
        for intent in result["draft_intent_matches"]:
            matched_by = intent["matched_by"] or "none"
            alternatives = "`, `".join(intent["any_of"])
            lines.append(
                f"- `{intent['name']}`: `{intent['matched']}` "
                f"(matched by: `{matched_by}`; alternatives: `{alternatives}`)"
            )
    else:
        lines.append("- none")

    lines.extend([
        "",
        "### Checks",
        "",
    ])
    for name, ok in result["must_pass_checks"].items():
        lines.append(f"- MUST `{name}`: `{ok}`")
    for name, ok in result["review_checks"].items():
        lines.append(f"- REVIEW `{name}`: `{ok}`")

    lines.extend([
        "",
        "### LLM Interactions",
        "",
    ])
    for interaction in result["llm_interactions"]:
        lines.extend([
            f"#### {interaction['stage']}",
            "",
            "Prompt sent to LLM:",
            "",
            "```text",
            interaction["user_prompt"],
            "```",
            "",
            "Raw LLM output:",
            "",
            "```text",
            interaction["raw_output"],
            "```",
            "",
        ])
    return lines


def _print_report(summary: dict, case_results: list[dict]) -> None:
    print(f"\nEvaluation run {summary['run_id']} ({summary['mode']})")
    print(
        f"Must-pass: {summary['must_pass_score']:.0%} | "
        f"Review: {summary['review_score']:.0%} | "
        f"Passed: {summary['passed']}/{summary['case_count']}"
    )
    print(f"Markdown report: {summary['artifacts']['markdown']}")
    print(f"JSON report:     {summary['artifacts']['json']}")
    print("-" * 120)
    print(f"{'ID':<6} {'Status':<8} {'Priority':<19} {'Category':<28} {'PII Safe':<10} {'Draft Review'}")
    print("-" * 120)
    for result in case_results:
        checks = result["must_pass_checks"]
        print(
            f"{result['case_id']:<6} "
            f"{result['status']:<8} "
            f"{result['expected']['priority']}->{result['actual']['priority']:<12} "
            f"{result['expected']['category']}->{result['actual']['category']:<18} "
            f"{str(checks['pii_prompt_absent'] and checks['mask_tokens_present']):<10} "
            f"{result['review_checks']['draft_contains']}"
        )


def _preview_secret(value: str) -> str:
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:2]}***{value[-2:]}"


def _public_type(entity_type: str) -> str:
    return "ssn" if entity_type == "US_SSN" else entity_type.lower()


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate the email agent pipeline.")
    parser.add_argument("--live", action="store_true", help="Call the configured LLM instead of mocks.")
    parser.add_argument("--golden", type=Path, default=GOLDEN_PATH, help="Path to golden dataset JSON.")
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR, help="Directory for Markdown/JSON reports.")
    parser.add_argument("--storage-probe", action="store_true", help="Run an explicit encrypted PostgreSQL write probe.")
    args = parser.parse_args()
    asyncio.run(
        run_evaluation(
            live=args.live,
            golden_path=args.golden,
            report_dir=args.report_dir,
            storage_probe=args.storage_probe,
        )
    )


if __name__ == "__main__":
    main()
