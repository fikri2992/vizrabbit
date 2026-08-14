"""Gate 0 smoke check: one real ADK call, one real image, validated pydantic out.

Not a pytest test — agent quality is measured by the eval harness, not by mocks
(see AGENTS.md). This proves the wiring: credentials, model id, image transport,
structured output.

    uv run python -m app.agents.smoke path/to/image.png
"""

import asyncio
import sys

from google.adk.agents import LlmAgent
from pydantic import BaseModel, Field

from app.agents.runtime import image_part, run_agent
from app.config import settings


class ImageSummary(BaseModel):
    """Deliberately trivial — this checks transport, not detection quality."""

    subject: str = Field(description="What the image depicts, in a few words")
    dominant_colors: list[str] = Field(description="Two or three colour names")
    looks_ai_generated: bool = Field(description="Whether this looks AI-generated")


def build_agent() -> LlmAgent:
    return LlmAgent(
        model=settings.model_flash,
        name="smoke",
        description="Wiring check for the Visual QA pipeline.",
        instruction=(
            "You are a smoke test. Look at the image and describe it. "
            "Respond ONLY with JSON matching the schema."
        ),
        output_schema=ImageSummary,
        output_key="summary",
    )


async def main(path: str) -> int:
    print(f"model : {settings.model_flash}")
    print(f"image : {path}")
    result = await run_agent(
        build_agent(),
        prompt="Describe this image.",
        images=[image_part(path)],
        schema=ImageSummary,
    )
    print(f"result: {result.model_dump_json(indent=2)}")
    print("\nGate 0 agent check: PASS")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        raise SystemExit(2)
    raise SystemExit(asyncio.run(main(sys.argv[1])))
