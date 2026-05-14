"""Local PII gateway for semantic masking and safe rehydration.

The gateway prefers Microsoft Presidio plus spaCy when those libraries are
installed, and always keeps a focused regex layer as a fast local fallback.
It masks only high-signal sensitive values, preserving enough email context
for classification and drafting.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Iterable

try:  # Optional at import time so tests still run before deps are installed.
    from presidio_analyzer import AnalyzerEngine, Pattern, PatternRecognizer
    from presidio_analyzer.nlp_engine import NlpArtifacts, NlpEngine
except Exception:  # pragma: no cover - exercised only when dependency missing.
    AnalyzerEngine = None  # type: ignore[assignment]
    NlpArtifacts = None  # type: ignore[assignment]
    NlpEngine = object  # type: ignore[assignment,misc]
    Pattern = None  # type: ignore[assignment]
    PatternRecognizer = None  # type: ignore[assignment]

try:
    import spacy
except Exception:  # pragma: no cover - exercised only when dependency missing.
    spacy = None


SUPPORTED_ENTITIES = [
    "PERSON",
    "EMAIL_ADDRESS",
    "PHONE_NUMBER",
    "CREDIT_CARD",
    "US_SSN",
    "BANK_ACCOUNT",
    "ROUTING_NUMBER",
    "API_KEY",
]


@dataclass(frozen=True)
class PiiFinding:
    start: int
    end: int
    entity_type: str
    score: float
    source: str


@dataclass(frozen=True)
class MaskMapping:
    token: str
    original: str
    entity_type: str


@dataclass
class PrivacyFilterResult:
    text: str
    found_types: list[str] = field(default_factory=list)
    findings: list[PiiFinding] = field(default_factory=list)
    mappings: list[MaskMapping] = field(default_factory=list)

    @property
    def was_redacted(self) -> bool:
        return bool(self.mappings)


# Backward-compatible name used by older tests and call sites.
RedactionResult = PrivacyFilterResult


@dataclass(frozen=True)
class _RegexRule:
    entity_type: str
    pattern: re.Pattern[str]
    score: float
    requires_context: bool = False


_REGEX_RULES = [
    _RegexRule(
        "EMAIL_ADDRESS",
        re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE),
        0.9,
    ),
    _RegexRule(
        "US_SSN",
        re.compile(r"\b(?!000|666|9\d\d)\d{3}-(?!00)\d{2}-(?!0000)\d{4}\b"),
        0.95,
    ),
    _RegexRule(
        "PHONE_NUMBER",
        re.compile(
            r"(?<!\w)(?:\+?1[-.\s]?)?(?:\(\d{3}\)|\d{3})[-.\s]?\d{3}[-.\s]?\d{4}(?!\w)"
        ),
        0.78,
    ),
    _RegexRule(
        "CREDIT_CARD",
        re.compile(r"\b(?:\d[ -]*?){13,19}\b"),
        0.92,
    ),
    _RegexRule(
        "ROUTING_NUMBER",
        re.compile(r"\b(?:routing|aba)\s*(?:number|#|:)?\s*(\d{9})\b", re.IGNORECASE),
        0.95,
    ),
    _RegexRule(
        "BANK_ACCOUNT",
        re.compile(
            r"\b(?:account|acct|bank account)\s*(?:number|#|:)?\s*([A-Z]{0,2}\d[\d -]{7,22})\b",
            re.IGNORECASE,
        ),
        0.88,
    ),
    _RegexRule(
        "API_KEY",
        re.compile(
            r"\b(?:api[_ -]?key|token|secret)\s*(?:=|:)\s*([A-Za-z0-9_\-]{20,})\b",
            re.IGNORECASE,
        ),
        0.88,
    ),
]


class PrivacyGateway:
    """Detect, mask, and rehydrate PII without sending raw values to the LLM."""

    def __init__(self, *, language: str = "en") -> None:
        self.language = language
        self._analyzer = _get_presidio_analyzer(language)
        self._nlp = _get_spacy_pipeline(language)
        self._counters: dict[str, int] = {}
        self._original_to_token: dict[tuple[str, str], str] = {}
        self._mappings: dict[str, MaskMapping] = {}

    def mask_text(self, text: str) -> PrivacyFilterResult:
        """Return text with sensitive spans replaced by semantic tokens."""
        if not text:
            return PrivacyFilterResult(text=text)

        findings = self._resolve_overlaps(self._detect(text))
        masked = text
        result_mappings: list[MaskMapping] = []

        for finding in sorted(findings, key=lambda item: item.start, reverse=True):
            original = text[finding.start:finding.end]
            token = self._token_for(finding.entity_type, original)
            masked = masked[:finding.start] + token + masked[finding.end:]
            result_mappings.append(self._mappings[token])

        result_mappings.reverse()
        found_types = _ordered_unique(_public_type(mapping.entity_type) for mapping in result_mappings)
        return PrivacyFilterResult(
            text=masked,
            found_types=found_types,
            findings=findings,
            mappings=result_mappings,
        )

    def rehydrate_text(self, text: str) -> str:
        """Replace locally held placeholders with their original values."""
        for token, mapping in sorted(
            self._mappings.items(),
            key=lambda item: len(item[0]),
            reverse=True,
        ):
            text = text.replace(token, mapping.original)
        return text

    @property
    def mappings(self) -> list[MaskMapping]:
        return list(self._mappings.values())

    def _detect(self, text: str) -> list[PiiFinding]:
        findings = self._detect_with_regex(text)
        findings.extend(self._detect_with_presidio(text))
        findings.extend(self._detect_with_spacy(text))
        return findings

    def _detect_with_regex(self, text: str) -> list[PiiFinding]:
        findings: list[PiiFinding] = []
        for rule in _REGEX_RULES:
            for match in rule.pattern.finditer(text):
                start, end = _sensitive_group_span(match)
                value = text[start:end]
                if rule.entity_type == "CREDIT_CARD" and not _looks_like_credit_card(value):
                    continue
                if rule.entity_type == "PHONE_NUMBER" and _looks_like_date(value):
                    continue
                findings.append(PiiFinding(start, end, rule.entity_type, rule.score, "regex"))
        return findings

    def _detect_with_presidio(self, text: str) -> list[PiiFinding]:
        if self._analyzer is None:
            return []
        try:
            results = self._analyzer.analyze(
                text=text,
                language=self.language,
                entities=SUPPORTED_ENTITIES,
            )
        except Exception:
            return []
        return [
            PiiFinding(result.start, result.end, result.entity_type, result.score, "presidio")
            for result in results
            if result.score >= 0.55
        ]

    def _detect_with_spacy(self, text: str) -> list[PiiFinding]:
        if self._nlp is None:
            return []
        try:
            doc = self._nlp(text)
        except Exception:
            return []

        findings: list[PiiFinding] = []
        for ent in doc.ents:
            if ent.label_ in {"PERSON", "ORG"}:
                entity_type = "PERSON" if ent.label_ == "PERSON" else "ORGANIZATION"
                if self._should_mask_named_entity(text, ent.start_char, ent.end_char):
                    findings.append(
                        PiiFinding(ent.start_char, ent.end_char, entity_type, 0.65, "spacy")
                    )
        return findings

    def _token_for(self, entity_type: str, original: str) -> str:
        key = (entity_type, original)
        if key in self._original_to_token:
            return self._original_to_token[key]

        self._counters[entity_type] = self._counters.get(entity_type, 0) + 1
        token = f"[[{entity_type}_{self._counters[entity_type]}]]"
        mapping = MaskMapping(token=token, original=original, entity_type=entity_type)
        self._original_to_token[key] = token
        self._mappings[token] = mapping
        return token

    @staticmethod
    def _should_mask_named_entity(text: str, start: int, end: int) -> bool:
        window = text[max(0, start - 40): min(len(text), end + 40)].lower()
        context_markers = (
            "my name is",
            "contact",
            "customer",
            "client",
            "patient",
            "employee",
            "candidate",
            "passport",
            "account holder",
        )
        return any(marker in window for marker in context_markers)

    @staticmethod
    def _resolve_overlaps(findings: Iterable[PiiFinding]) -> list[PiiFinding]:
        ranked = sorted(
            findings,
            key=lambda item: (item.score, item.end - item.start),
            reverse=True,
        )
        selected: list[PiiFinding] = []
        for candidate in ranked:
            if candidate.start >= candidate.end:
                continue
            if any(_overlaps(candidate, existing) for existing in selected):
                continue
            selected.append(candidate)
        return sorted(selected, key=lambda item: item.start)


def redact(text: str) -> RedactionResult:
    """Backward-compatible one-shot redaction helper."""
    return PrivacyGateway().mask_text(text)


def rehydrate(text: str, mappings: Iterable[MaskMapping]) -> str:
    """Rehydrate text using explicit mappings from a previous masking pass."""
    for mapping in sorted(mappings, key=lambda item: len(item.token), reverse=True):
        text = text.replace(mapping.token, mapping.original)
    return text


def _custom_presidio_recognizers() -> list[object]:
    if Pattern is None or PatternRecognizer is None:
        return []

    return [
        PatternRecognizer(
            supported_entity="BANK_ACCOUNT",
            patterns=[
                Pattern(
                    "contextual_bank_account",
                    r"\b(?:account|acct|bank account)\s*(?:number|#|:)?\s*([A-Z]{0,2}\d[\d -]{7,22})\b",
                    0.88,
                )
            ],
        ),
        PatternRecognizer(
            supported_entity="ROUTING_NUMBER",
            patterns=[
                Pattern(
                    "contextual_routing_number",
                    r"\b(?:routing|aba)\s*(?:number|#|:)?\s*(\d{9})\b",
                    0.95,
                )
            ],
        ),
        PatternRecognizer(
            supported_entity="API_KEY",
            patterns=[
                Pattern(
                    "api_key_or_token",
                    r"\b(?:api[_ -]?key|token|secret)\s*(?:=|:)\s*([A-Za-z0-9_\-]{20,})\b",
                    0.88,
                )
            ],
        ),
    ]


@lru_cache(maxsize=4)
def _get_presidio_analyzer(language: str):
    if AnalyzerEngine is None:
        return None
    try:
        analyzer = AnalyzerEngine()
    except Exception:
        try:
            analyzer = AnalyzerEngine(
                nlp_engine=_PatternOnlyNlpEngine(language),
                supported_languages=[language],
                context_aware_enhancer=None,
            )
        except Exception:
            return None
    registry = analyzer.registry
    for recognizer in _custom_presidio_recognizers():
        registry.add_recognizer(recognizer)
    return analyzer


@lru_cache(maxsize=4)
def _get_spacy_pipeline(language: str):
    if spacy is None:
        return None
    for model in ("en_core_web_sm", "en_core_web_md"):
        try:
            return spacy.load(model)
        except Exception:
            continue
    try:
        return spacy.blank(language)
    except Exception:
        return None


class _PatternOnlyNlpEngine(NlpEngine):
    """Minimal NLP engine so Presidio pattern recognizers work without a model."""

    def __init__(self, language: str) -> None:
        self.language = language
        self._nlp = spacy.blank(language) if spacy is not None else None

    def load(self) -> None:
        return None

    def is_loaded(self) -> bool:
        return self._nlp is not None

    def process_text(self, text: str, language: str):
        if self._nlp is None or NlpArtifacts is None:
            raise RuntimeError("spaCy is required for Presidio pattern-only mode")
        doc = self._nlp(text)
        return NlpArtifacts(
            entities=[],
            tokens=doc,
            tokens_indices=[token.idx for token in doc],
            lemmas=[token.text.lower() for token in doc],
            nlp_engine=self,
            language=language,
        )

    def process_batch(self, texts, language: str, batch_size: int = 1, n_process: int = 1, **kwargs):
        for text in texts:
            yield text, self.process_text(text, language)

    def is_stopword(self, word: str, language: str) -> bool:
        return False

    def is_punct(self, word: str, language: str) -> bool:
        return len(word) == 1 and not word.isalnum()

    def get_supported_entities(self) -> list[str]:
        return []

    def get_supported_languages(self) -> list[str]:
        return [self.language]


def _sensitive_group_span(match: re.Match[str]) -> tuple[int, int]:
    if match.lastindex:
        return match.start(match.lastindex), match.end(match.lastindex)
    return match.start(), match.end()


def _looks_like_credit_card(value: str) -> bool:
    digits = re.sub(r"\D", "", value)
    if not 13 <= len(digits) <= 19:
        return False
    total = 0
    reverse_digits = digits[::-1]
    for index, char in enumerate(reverse_digits):
        number = int(char)
        if index % 2 == 1:
            number *= 2
            if number > 9:
                number -= 9
        total += number
    return total % 10 == 0


def _looks_like_date(value: str) -> bool:
    return bool(re.fullmatch(r"\d{4}[-/]\d{1,2}[-/]\d{1,2}", value))


def _overlaps(left: PiiFinding, right: PiiFinding) -> bool:
    return left.start < right.end and right.start < left.end


def _ordered_unique(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value not in result:
            result.append(value)
    return result


def _public_type(entity_type: str) -> str:
    aliases = {
        "US_SSN": "ssn",
    }
    return aliases.get(entity_type, entity_type.lower())
