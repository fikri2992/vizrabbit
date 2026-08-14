"""Check the guideline griller against a realistically vague brand document.

A guideline like this is the normal case: written for humans, full of judgement
calls a model cannot make. The questions should target the parts that would
actually change a verdict, and should not repeat what has already been answered.

    uv run python -m scripts.check_grilling
"""

import asyncio
import sys

from app.domain.entities import Clarification, Guideline
from app.services.guidelines import grill

SAMPLE = Guideline(
    id="g-check",
    project_id="p-check",
    name="Acme brand guideline",
    raw_text="""
# Acme visual identity

## Logo
The Acme wordmark must always be prominent and surrounded by ample clearspace. Never
distort, recolour or crop the logo. On busy imagery, place it where it remains legible.

## Colour
Use our core palette. Accent colours may be used sparingly. Imagery should feel warm
and premium, never clinical.

## People
Models should look natural and relatable. Skin tones must be represented authentically.
Avoid poses that feel staged.

## Typography
Straplines use Acme Sans. Keep copy short. Text must be legible.

## Product
The product is the hero. Packaging must be shown accurately and must never be obscured.
""".strip(),
)


async def main() -> int:
    print(f"guideline: {SAMPLE.name} ({len(SAMPLE.raw_text)} chars)\n")

    result = await grill(SAMPLE)
    for index, question in enumerate(result.questions, start=1):
        print(f"{index}. {question.question}")
        if question.why_it_matters:
            print(f"   why: {question.why_it_matters}")

    failures = []
    if not 3 <= len(result.questions) <= 6:
        failures.append(f"expected 3-6 questions, got {len(result.questions)}")
    if any(not q.question.strip().endswith("?") for q in result.questions):
        failures.append("a question was not phrased as a question")

    # Second pass: with those answered, it must not simply ask them again.
    answered = SAMPLE.model_copy(
        update={
            "clarifications": [
                Clarification(question=q.question, answer="Answered: see brand book p.12.")
                for q in result.questions
            ]
        }
    )
    second = await grill(answered)
    print(f"\nsecond pass after answering: {len(second.questions)} question(s)")
    for question in second.questions:
        print(f"  - {question.question}")

    repeated = {q.question.strip().lower() for q in result.questions} & {
        q.question.strip().lower() for q in second.questions
    }
    if repeated:
        failures.append(f"{len(repeated)} question(s) repeated verbatim after being answered")

    if failures:
        for failure in failures:
            print(f"\nFAIL: {failure}")
        return 1

    print("\nGrilling check: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
