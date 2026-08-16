"""Guideline grilling: finding the ambiguities before they cost a scan.

A brand guideline is written for humans who fill gaps with taste. The Scanner cannot.
So on upload the agent reads the document and asks the brand owner the questions it
would otherwise have to guess at; the answers are appended to the guideline verbatim
as clarifications (domain-model.md decision 3 — never compiled, never lossy).

Grilling happens at upload only. Mid-scan ambiguity is not allowed to block a run.
"""

from google.adk.agents import LlmAgent

from app.agents import prompts
from app.agents.runtime import bytes_part, run_agent
from app.agents.schemas import GuidelineGrilling, PaletteExtraction
from app.config import settings
from app.domain.color import BadHex, normalise_hex
from app.domain.entities import Clarification, Guideline, PaletteEntry, Project, User, now
from app.domain.permissions import Permission, require
from app.imaging.canvas import fit_for_model, to_png_bytes
from app.imaging.documents import pdf_text, render_pdf
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


# --- palette extraction ---------------------------------------------------


def palette_agent() -> LlmAgent:
    """Reads a guideline's palette. Pro model: it runs once and must read swatches."""
    return LlmAgent(
        model=settings.model_pro,
        name="palette_extractor",
        description="Proposes the brand palette a guideline defines.",
        instruction=prompts.load("palette_extractor"),
        output_schema=PaletteExtraction,
        output_key="palette",
    )


async def extract_palette(
    raw_text: str = "", pdf: bytes | None = None, name: str = ""
) -> PaletteExtraction:
    """Propose a palette from a guideline's text, its PDF pages, or both.

    Pages go in as images because a swatch with no printed hex is only readable
    by looking at it, and that is precisely the colour a text-only reading drops.
    """
    images = []
    text = raw_text

    if pdf is not None:
        pages = render_pdf(pdf)
        images = [bytes_part(to_png_bytes(fit_for_model(page))) for page in pages]
        extracted = pdf_text(pdf)
        if extracted:
            text = f"{text}\n\n{extracted}" if text else extracted

    header = f"# Guideline: {name}\n\n" if name else ""
    body = text.strip() or "(no extractable text — read the pages)"
    instruction = (
        f"{header}{body}\n\n"
        + (
            f"The {len(images)} image(s) are the first pages of the document. "
            "Read swatch colours off them.\n\n"
            if images
            else ""
        )
        + "Propose the brand palette this guideline defines."
    )

    return await run_agent(
        palette_agent(), prompt=instruction, images=images, schema=PaletteExtraction
    )


def as_entries(extraction: PaletteExtraction) -> list[PaletteEntry]:
    """Turn a proposal into profile entries, dropping anything unparseable.

    Swatch-read colours get a looser default tolerance than printed ones: the
    reading itself carries error, and a tight tolerance on an uncertain hex would
    manufacture violations.
    """
    entries: list[PaletteEntry] = []
    for colour in extraction.colours:
        try:
            hex_value = normalise_hex(colour.hex)
        except BadHex:
            continue
        entries.append(
            PaletteEntry(
                hex=hex_value,
                role=colour.role.strip(),
                tolerance=3.0 if colour.read_from == "text" else 5.0,
            )
        )
    return entries


def unanswered(guideline: Guideline, questions: list[str]) -> list[str]:
    """Questions not yet answered on this guideline, so a re-grill does not repeat."""
    asked = {c.question.strip().lower() for c in guideline.clarifications}
    return [q for q in questions if q.strip().lower() not in asked]
