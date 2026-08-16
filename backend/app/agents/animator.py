"""The animator: turn an approved still into a motion candidate (decision 24).

Same contract shape as the editor: bytes in, bytes out, ``None`` when the
model produced nothing — callers treat that as "no animation today", never as
an error. The animator has no opinions about slots or approval; the service
layer owns who may ask and where the result lands.
"""

import asyncio
import logging

from google import genai
from google.genai import types

from app.agents.retry import with_retry
from app.config import settings

logger = logging.getLogger(__name__)


async def animate(original_png: bytes, brief: str) -> bytes | None:
    """One Veo call from the approved frame + the owner's motion brief.

    Veo is a long-running operation: start it (with retry — starting is where
    quota errors land), then poll until it resolves or the timeout budget runs
    out. Returns the mp4 bytes, or ``None`` when nothing usable came back.
    """

    async def start() -> genai.types.GenerateVideosOperation:
        client = genai.Client()
        return await client.aio.models.generate_videos(
            model=settings.model_video,
            prompt=brief,
            image=types.Image(image_bytes=original_png, mime_type="image/png"),
        )

    def note(attempt_number: int, delay: float, error: BaseException) -> None:
        logger.warning(
            "animator attempt %d failed (%s); retrying in %.1fs",
            attempt_number,
            str(error)[:120],
            delay,
        )

    operation = await with_retry(start, on_retry=note)

    client = genai.Client()
    waited = 0.0
    while not operation.done and waited < settings.animate_timeout_seconds:
        await asyncio.sleep(settings.animate_poll_seconds)
        waited += settings.animate_poll_seconds
        operation = await client.aio.operations.get(operation)

    if not operation.done or operation.response is None:
        logger.warning("animation did not finish within %.0fs", waited)
        return None

    for generated in operation.response.generated_videos or []:
        video = generated.video
        if video is None:
            continue
        if video.video_bytes:  # Vertex returns bytes inline
            return video.video_bytes
        downloaded = await client.aio.files.download(file=video)
        if downloaded:
            return downloaded
    return None
