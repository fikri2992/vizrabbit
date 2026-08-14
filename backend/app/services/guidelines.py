"""Guideline grilling: finding the ambiguities before they cost a scan.

A brand guideline is written for humans who fill gaps with taste. The Scanner cannot.
So on upload the agent reads the document and asks the brand owner the questions it
would otherwise have to guess at; the answers are appended to the guideline verbatim
as clarifications (domain-model.md decision 3 — never compiled, never lossy).

Grilling happens at upload only. Mid-scan ambiguity is not allowed to block a run.
"""

from google.adk.agents import LlmAgent

from app.agents import prompts
from app.agents.runtime import run_agent
from app.agents.schemas import GuidelineGrilling
from app.config import settings
from app.domain.entities import Clarification, Guideline, Project, User, now
from app.domain.permissions import Permission, require
from app.infra import repository as repo
from app.infra.store import Store


def griller_agent() -> LlmAgent:
    """Reads a guideline for ambiguity. Uses the Pro model: this runs once per
    document, and a bad question costs the brand owner's patience."""
    return LlmAgent(
        model=settings.model_pro,
        name="guideline_griller",
        description="Finds ambiguities in a brand guideline and asks about them.",
        instruction=prompts.load("guideline_griller"),
        output_schema=GuidelineGrilling,
        output_key="grilling",
    )


async def grill(guideline: Guideline) -> GuidelineGrilling:
    """Ask what this guideline leaves open.

    Already-answered clarifications are included so a second pass does not repeat
    itself after the owner has replied.
    """
    answered = "\n".join(
        f"- Q: {c.question}\n  A: {c.answer}" for c in guideline.clarifications
    )
    context = (
        f"# Guideline: {guideline.name}\n\n{guideline.raw_text}"
        + (f"\n\n# Already clarified — do not ask these again\n\n{answered}" if answered else "")
    )

    return await run_agent(
        griller_agent(),
        prompt=f"{context}\n\nWhat does this leave ambiguous?",
        schema=GuidelineGrilling,
    )


async def answer(
    store: Store,
    project: Project,
    guideline: Guideline,
    user: User,
    question: str,
    reply: str,
) -> Guideline:
    """Record the brand owner's answer against the guideline.

    Only the owner may answer: a guideline with two voices contradicts itself, and
    the whole point of one accountable owner is that its clarifications are binding.
    """
    require(project, user.id, Permission.ANSWER_GRILLING)
    if not reply.strip():
        raise ValueError("an answer cannot be blank")

    guideline.clarifications.append(
        Clarification(question=question, answer=reply.strip(), answered_by=user.id)
    )
    guideline.updated_at = now()
    await repo.save(store, guideline)
    return guideline


def unanswered(guideline: Guideline, questions: list[str]) -> list[str]:
    """Questions not yet answered on this guideline, so a re-grill does not repeat."""
    asked = {c.question.strip().lower() for c in guideline.clarifications}
    return [q for q in questions if q.strip().lower() not in asked]
