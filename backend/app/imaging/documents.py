"""Turning an uploaded guideline document into pages the model can look at.

A brand guideline states half its palette in printed hex and the other half in
swatch blocks with no value beside them. Text extraction alone finds the first
half and silently misses the second, which is the half worth catching — so pages
are rendered to images and read visually.

Page budget is a hard cap, not a suggestion: guidelines run to eighty pages and
the palette is always near the front.
"""

import io

from PIL import Image

#: Palette sections live in the first pages. Beyond this the cost stops buying
#: colours and starts buying photography.
MAX_PAGES = 8

#: Enough to read a swatch and its caption without shipping print resolution.
RENDER_SCALE = 1.6


class NotAPdf(ValueError):
    pass


def is_pdf(data: bytes) -> bool:
    return data[:5] == b"%PDF-"


def render_pdf(data: bytes, max_pages: int = MAX_PAGES) -> list[Image.Image]:
    """Render the first pages of a PDF to RGB images, in order.

    Raises ``NotAPdf`` rather than returning an empty list, so a mis-typed upload
    is reported to the user instead of quietly proposing no colours.
    """
    if not is_pdf(data):
        raise NotAPdf("that file is not a PDF")

    import pypdfium2

    document = pypdfium2.PdfDocument(io.BytesIO(data))
    try:
        pages = []
        for index in range(min(len(document), max_pages)):
            page = document[index]
            pages.append(page.render(scale=RENDER_SCALE).to_pil().convert("RGB"))
        return pages
    finally:
        document.close()


def pdf_text(data: bytes, max_pages: int = MAX_PAGES) -> str:
    """Whatever text the PDF carries, for the pages rendered.

    Sent alongside the page images: a hex printed as text should be read as text,
    and only genuinely unlabelled swatches sampled by eye.
    """
    if not is_pdf(data):
        raise NotAPdf("that file is not a PDF")

    import pypdfium2

    document = pypdfium2.PdfDocument(io.BytesIO(data))
    try:
        chunks = []
        for index in range(min(len(document), max_pages)):
            textpage = document[index].get_textpage()
            chunks.append(textpage.get_text_range())
            textpage.close()
        return "\n\n".join(chunk.strip() for chunk in chunks if chunk.strip())
    finally:
        document.close()


def page_count(data: bytes) -> int:
    if not is_pdf(data):
        raise NotAPdf("that file is not a PDF")

    import pypdfium2

    document = pypdfium2.PdfDocument(io.BytesIO(data))
    try:
        return len(document)
    finally:
        document.close()
