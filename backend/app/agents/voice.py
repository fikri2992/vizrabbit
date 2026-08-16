"""Voice on question threads (phase 14): Gemini Live as an *input mode*.

The owner talks through the queued questions instead of clicking; nothing else
changes. Two design rules keep this honest:

- **The tool list is the model's entire authority.** It can answer a question
  or move between them — the same two moves the buttons offer — and nothing
  else. No approval, no dismissal of ordinary defects, no navigation beyond
  the queue. The gate test asserts this list stays that small.
- **The browser executes the tools through the existing REST endpoints**, with
  the user's own session. A spoken "not a problem" is byte-identical to the
  clicked one because it *is* the clicked one — same endpoint, same service,
  same record. The model never holds credentials to our API at all.

The server's one job is minting a constrained ephemeral token: model, system
instruction and tool list are locked server-side so the browser (or anyone
holding the token) cannot renegotiate what the session is allowed to be.
"""

from datetime import timedelta

from google import genai
from google.genai import types

from app.config import settings
from app.domain.entities import DefectRecord, now

#: The whole tool surface. Names are asserted by the gate test — extending this
#: list is a decision, not a convenience.
TOOL_DECLARATIONS: list[dict] = [
    {
        "name": "answer_question",
        "description": (
            "Record the owner's answer to the current question. Call this only "
            "after the owner has clearly said whether the flagged thing is a "
            "real problem ('it's real') or not ('not a problem')."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "defect_id": {"type": "STRING", "description": "The question's defect id."},
                "confirmed": {
                    "type": "BOOLEAN",
                    "description": "True when the owner says it's a real problem.",
                },
            },
            "required": ["defect_id", "confirmed"],
        },
    },
    {
        "name": "next_question",
        "description": "Move to the next open question in the queue.",
        "parameters": {"type": "OBJECT", "properties": {}},
    },
    {
        "name": "previous_question",
        "description": "Move back to the previous question in the queue.",
        "parameters": {"type": "OBJECT", "properties": {}},
    },
]

SYSTEM_PROMPT = """You are the voice of a visual-QA review session. The owner is
talking through questions the QA agent queued because it was not sure. Your job
is to read each question aloud in one plain sentence, listen, and record the
owner's answer with the answer_question tool.

Rules:
- Work through the questions in order; use next_question / previous_question to move.
- Never answer a question yourself. Only the owner decides; you only record.
- If the owner is ambiguous, ask one short clarifying question, then record.
- Keep every reply under two sentences. This is a work session, not a chat.

The open questions, in order:
{questions}
"""


def question_lines(defects: list[DefectRecord]) -> str:
    """The context the session opens with — id, then the code-stamped comment."""
    return "\n".join(f"- {d.id}: {d.comment}" for d in defects)


def live_config(defects: list[DefectRecord]) -> types.LiveConnectConfig:
    """The locked shape of a voice session: audio out, our prompt, our tools."""
    return types.LiveConnectConfig(
        response_modalities=["AUDIO"],
        system_instruction=SYSTEM_PROMPT.format(questions=question_lines(defects)),
        tools=[{"function_declarations": TOOL_DECLARATIONS}],
    )


async def mint_session_token(defects: list[DefectRecord]) -> str:
    """A single-use token constrained to exactly this session shape.

    The constraints ride the token server-side: whoever holds it can only open
    a Live session with our model, our prompt and our tool list.
    """
    client = genai.Client()
    expiry = now() + timedelta(minutes=settings.voice_token_minutes)
    token = await client.aio.auth_tokens.create(
        config=types.CreateAuthTokenConfig(
            uses=1,
            expire_time=expiry,
            live_connect_constraints=types.LiveConnectConstraints(
                model=settings.model_live,
                config=live_config(defects),
            ),
        )
    )
    return token.name
