"""The image editor: turn a verdict into a candidate fix (decision 21).

One narrow job: given the original image and the defects' instructions, return
an edited image — or None when the model produced no image, which callers treat
as "no draft today", never as an error. The editor never decides *what* to fix;
the whitelist in ``services/drafts.py`` owns that.
"""

import logging

from google import genai
from google.genai import types

from app.agents.retry import with_retry
from app.config import settings

logger = logging.getLogger(__name__)

PROMPT = """Edit this image to fix ONLY the specific defects listed below.
Change nothing else: keep the composition, style, colours, lighting, text and
dimensions identical everywhere the defects do not require a change.

Defects to fix:
{instructions}

Return the edited image."""


async def draft_fix(original_png: bytes, instructions: list[str]) -> bytes | None:
    """One edit call, all instructions aggregated — the per-image cost cap."""
    prompt = PROMPT.format(instructions="\n".join(f"- {line}" for line in instructions))

    async def attempt() -> bytes | None:
        client = genai.Client()
        response = await client.aio.models.generate_content(
            model=settings.model_image_edit,
            contents=[
                types.Part(text=prompt),
                types.Part.from_bytes(data=original_png, mime_type="image/png"),
            ],
        )
        for candidate in response.candidates or []:
            for part in (candidate.content and candidate.content.parts) or []:
                if part.inline_data and part.inline_data.data:
                    return part.inline_data.data
        return None

    def note(attempt_number: int, delay: float, error: BaseException) -> None:
        logger.warning(
            "editor attempt %d failed (%s); retrying in %.1fs",
            attempt_number,
            str(error)[:120],
            delay,
        )

    return await with_retry(attempt, on_retry=note)
