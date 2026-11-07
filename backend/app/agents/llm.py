"""LLM provider abstraction for the investigation agents (Phase 6 Part G).

`get_llm_provider()` is the one place that reads `settings.llm_provider`
and decides which implementation to return. Every provider implements
the same `generate_report` method, so `app/agents/graph.py`'s
ReportWriter node never knows (or cares) which one it's talking to.

`settings.llm_provider` defaults to `"mock"` for reproducible local tests.
Real providers require explicit configuration and their own API keys.
Nothing in this file calls out to a real model unless a real key is
configured, and nothing silently pretends mock output is real: see
`AgentRun.model_provider`/`model_name`, always recorded, always checked
in `docs/agent-security.md`'s "no fabricated inference" test.
"""

import json
import urllib.request
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Protocol

from app.agents.prompts import PROMPT_VERSION, build_report_prompt
from app.core.config import Settings


@dataclass
class ReportInputs:
    # `Sequence[Mapping[...]]`, not `list[dict]`: covariant, so this
    # accepts `list[EvidenceItem]`/`list[NetworkFinding]`
    # (`app/agents/state.py`'s TypedDicts) as well as plain dicts —
    # mypy treats `list[EvidenceItem]` as unrelated to `list[dict]`
    # under invariant generics, even though every `EvidenceItem` *is*
    # structurally a `dict`.
    case_summary: Mapping[str, object]
    evidence: Sequence[Mapping[str, object]]
    network_findings: Sequence[Mapping[str, object]]
    feedback: list[str] = field(default_factory=list)


@dataclass
class GeneratedReport:
    summary: str
    hypotheses: list[dict]
    uncertainties: list[str]
    recommended_next_step: str
    model_provider: str
    model_name: str
    is_mock: bool


class LLMProviderUnavailable(RuntimeError):
    """Raised when a real provider is selected but has no API key
    configured — fails loudly rather than silently falling back to mock,
    so a report is never mislabeled as real inference it never performed.
    """


class LLMProvider(Protocol):
    model_provider: str
    model_name: str

    def generate_report(self, inputs: ReportInputs) -> GeneratedReport: ...


class MockLLMProvider:
    """Deterministic, rule-based report synthesis — no network call, no
    randomness, same input always produces the same output. This is the
    *only* provider this environment can actually exercise; every report
    it produces says so explicitly (`is_mock=True`,
    `model_name="mock-deterministic-v1"`).

    It never treats retrieved text as instructions: every evidence/
    finding/feedback string is only ever copied into a quoted, labeled
    excerpt in the output, never parsed for commands — see
    `docs/agent-security.md` §4 (prompt-injection resistance).
    """

    model_provider = "mock"
    model_name = "mock-deterministic-v1"

    def generate_report(self, inputs: ReportInputs) -> GeneratedReport:
        hypotheses = []
        uncertainties = []

        high_severity = [
            e for e in inputs.evidence if e.get("evidence_type") == "risk_score" and e.get("flag")
        ]
        structural = [f for f in inputs.network_findings if f.get("flag")]

        if high_severity and structural:
            hypotheses.append(
                {
                    "text": (
                        "The scored transaction's elevated risk score coincides with a "
                        "structural pattern (fan-in/out, cycle, or high-velocity "
                        "counterparty activity) in the account's transaction network."
                    ),
                    "confidence": "medium",
                    "evidence_refs": [e["source_reference"] for e in high_severity]
                    + [f["source_reference"] for f in structural],
                }
            )
        elif high_severity:
            hypotheses.append(
                {
                    "text": (
                        "The transaction's risk score is elevated, but no corroborating "
                        "structural signal was found in the bounded account neighborhood "
                        "examined."
                    ),
                    "confidence": "low",
                    "evidence_refs": [e["source_reference"] for e in high_severity],
                }
            )
            uncertainties.append(
                "No structural (graph) corroboration found for the elevated score; this "
                "may reflect a genuinely isolated transaction or a neighborhood bound too "
                "narrow to capture the relevant accounts."
            )
        elif structural:
            hypotheses.append(
                {
                    "text": (
                        "A structural pattern was found in the account's transaction "
                        "network, independent of any elevated model score."
                    ),
                    "confidence": "low",
                    "evidence_refs": [f["source_reference"] for f in structural],
                }
            )
        else:
            uncertainties.append(
                "No elevated risk score and no flagged structural pattern were found "
                "among the evidence collected for this case."
            )

        if not inputs.evidence:
            uncertainties.append(
                "No transaction/account evidence could be retrieved for this case."
            )

        for note in inputs.feedback:
            # The analyst's own revision feedback is quoted verbatim, labeled,
            # and never treated as an instruction to this function itself —
            # it only ever ends up as a string inside `uncertainties`.
            uncertainties.append(f'Analyst feedback considered: "{note}"')

        summary = (
            f"Automated evidence review of {len(inputs.evidence)} evidence item(s) and "
            f"{len(inputs.network_findings)} network finding(s). "
            f"{len(hypotheses)} hypothesis/hypotheses generated, all citing retrieved "
            "evidence. This is a draft assembled by an AI agent for analyst review — "
            "it is not a fraud determination."
        )

        return GeneratedReport(
            summary=summary,
            hypotheses=hypotheses,
            uncertainties=uncertainties,
            recommended_next_step=(
                "Review the cited evidence and structural findings below; escalate to a "
                "senior analyst decision only if corroborated by independent review."
            ),
            model_provider=self.model_provider,
            model_name=self.model_name,
            is_mock=True,
        )


class _HTTPJSONLLMProvider:
    """Shared HTTP-call plumbing for the real providers below. Builds the
    same delimited, labeled prompt (`app/agents/prompts.py`) regardless of
    provider, so prompt-injection hygiene doesn't depend on which model is
    configured. Provider/model provenance is persisted with every report.
    """

    endpoint: str
    model_name: str
    model_provider: str
    api_key: str

    def _headers(self) -> dict[str, str]:
        raise NotImplementedError

    def _body(self, prompt: str) -> dict:
        raise NotImplementedError

    def _extract_text(self, response_json: dict) -> str:
        raise NotImplementedError

    def generate_report(self, inputs: ReportInputs) -> GeneratedReport:
        prompt = build_report_prompt(inputs)
        request = urllib.request.Request(
            self.endpoint,
            data=json.dumps(self._body(prompt)).encode("utf-8"),
            headers=self._headers(),
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
            payload = json.loads(response.read().decode("utf-8"))
        text = self._extract_text(payload)
        parsed = json.loads(text)
        return GeneratedReport(
            summary=parsed["summary"],
            hypotheses=parsed["hypotheses"],
            uncertainties=parsed.get("uncertainties", []),
            recommended_next_step=parsed["recommended_next_step"],
            model_provider=self.model_provider,
            model_name=self.model_name,
            is_mock=False,
        )


class AnthropicLLMProvider(_HTTPJSONLLMProvider):
    model_provider = "anthropic"
    endpoint = "https://api.anthropic.com/v1/messages"

    def __init__(self, api_key: str, model_name: str) -> None:
        self.api_key = api_key
        self.model_name = model_name

    def _headers(self) -> dict[str, str]:
        return {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

    def _body(self, prompt: str) -> dict:
        # Request a structured report rather than parsing Markdown-wrapped text.
        # This tool is only a response schema; it executes no application action.
        strings = {"type": "array", "items": {"type": "string"}}
        return {
            "model": self.model_name,
            "max_tokens": 4096,
            "messages": [{"role": "user", "content": prompt}],
            "tool_choice": {"type": "tool", "name": "submit_report"},
            "tools": [
                {
                    "name": "submit_report",
                    "description": "Return the investigation report for human review.",
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "summary": {"type": "string"},
                            "hypotheses": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "text": {"type": "string"},
                                        "confidence": {
                                            "type": "string",
                                            "enum": ["low", "medium", "high"],
                                        },
                                        "evidence_refs": strings,
                                    },
                                    "required": ["text", "confidence", "evidence_refs"],
                                },
                            },
                            "uncertainties": strings,
                            "recommended_next_step": {"type": "string"},
                        },
                        "required": [
                            "summary",
                            "hypotheses",
                            "uncertainties",
                            "recommended_next_step",
                        ],
                    },
                }
            ],
        }

    def _extract_text(self, response_json: dict) -> str:
        if response_json.get("stop_reason") == "max_tokens":
            raise ValueError("Anthropic report exceeded its output limit; no partial report saved")
        for block in response_json.get("content", []):
            if block.get("type") == "tool_use" and block.get("name") == "submit_report":
                return json.dumps(block["input"])
        raise ValueError("Anthropic returned no structured investigation report")


class OpenAILLMProvider(_HTTPJSONLLMProvider):
    model_provider = "openai"
    endpoint = "https://api.openai.com/v1/chat/completions"

    def __init__(self, api_key: str, model_name: str) -> None:
        self.api_key = api_key
        self.model_name = model_name

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}", "content-type": "application/json"}

    def _body(self, prompt: str) -> dict:
        return {
            "model": self.model_name,
            "messages": [{"role": "user", "content": prompt}],
            "response_format": {"type": "json_object"},
        }

    def _extract_text(self, response_json: dict) -> str:
        return response_json["choices"][0]["message"]["content"]


def get_llm_provider(settings: Settings) -> LLMProvider:
    if settings.llm_provider == "mock":
        return MockLLMProvider()
    if settings.llm_provider == "anthropic":
        if not settings.anthropic_api_key:
            raise LLMProviderUnavailable("LLM_PROVIDER=anthropic but ANTHROPIC_API_KEY is not set")
        return AnthropicLLMProvider(settings.anthropic_api_key, settings.llm_model_name)
    if settings.llm_provider == "openai":
        if not settings.openai_api_key:
            raise LLMProviderUnavailable("LLM_PROVIDER=openai but OPENAI_API_KEY is not set")
        return OpenAILLMProvider(settings.openai_api_key, settings.llm_model_name)
    raise LLMProviderUnavailable(f"unknown LLM_PROVIDER: {settings.llm_provider!r}")


__all__ = [
    "PROMPT_VERSION",
    "GeneratedReport",
    "LLMProvider",
    "LLMProviderUnavailable",
    "MockLLMProvider",
    "ReportInputs",
    "get_llm_provider",
]
