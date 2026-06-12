"""Supervisor agent — triages incoming emails and decides the agent plan.

The supervisor is a lightweight LLM call that examines the email's subject,
sender, and a snippet of the body to decide which specialist agents should
be invoked and in what order. It does NOT classify or draft — it only
produces an execution plan.
"""

from __future__ import annotations

import json
import logging

from src.llm import client as llm
from src.llm.prompts import SUPERVISOR_SYSTEM, SUPERVISOR_USER
from src.models.email import Email
from src.services.agents.context import AgentPlan, AgentStep, AgentType

log = logging.getLogger(__name__)


async def run_supervisor(email: Email) -> AgentPlan:
    """Produce an AgentPlan by asking the LLM which agents are needed.

    Always returns a valid plan — on LLM failure, returns the default
    full-pipeline plan.
    """
    body_snippet = email.body[:300].replace("\n", " ")
    user_msg = SUPERVISOR_USER.format(
        sender=email.sender,
        subject=email.subject,
        body_snippet=body_snippet,
        timestamp=email.timestamp.isoformat(),
    )

    try:
        raw = await llm.chat(
            messages=[
                {"role": "system", "content": SUPERVISOR_SYSTEM},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.1,
            max_tokens=300,
        )

        text = raw.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            text = "\n".join(lines[1:-1])

        data = json.loads(text)
        steps = []
        for agent_name in data.get("agents", []):
            try:
                agent_type = AgentType(agent_name)
                reason = data.get("reasoning", {}).get(agent_name, "Selected by supervisor")
                steps.append(AgentStep(agent=agent_type, reason=reason))
            except ValueError:
                log.warning("supervisor_unknown_agent", extra={"agent": agent_name})

        if not steps:
            steps = _default_steps()

        plan = AgentPlan(
            steps=steps,
            email_summary=data.get("summary", email.subject[:80]),
            triage_reasoning=data.get("triage_reasoning", ""),
        )

        log.info(
            "supervisor_plan",
            extra={
                "email_id": email.id,
                "agents": [s.agent.value for s in plan.steps],
                "reasoning": plan.triage_reasoning[:120],
            },
        )
        return plan

    except Exception as exc:
        log.warning(
            "supervisor_fallback",
            extra={"error": str(exc), "email_id": email.id},
        )
        return AgentPlan(
            steps=_default_steps(),
            email_summary=email.subject[:80],
            triage_reasoning=f"Supervisor fallback due to: {exc}",
        )


def _default_steps() -> list[AgentStep]:
    """The full pipeline: calendar → classification → draft."""
    return [
        AgentStep(agent=AgentType.CALENDAR, reason="Default: check calendar availability"),
        AgentStep(agent=AgentType.CLASSIFICATION, reason="Default: classify email"),
        AgentStep(agent=AgentType.DRAFT, reason="Default: generate draft reply"),
    ]
