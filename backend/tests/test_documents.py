"""PDF rendering for palette extraction — real PDFs, built here, then read back.

The point of rendering rather than parsing text is swatches: a colour block with
no printed hex is invisible to a text reader. These tests build a PDF containing
exactly that case and prove the rendered page carries the colour.
"""

import io

import pytest
from PIL import Image

from app.domain.color import to_hex
from app.imaging.documents import (
    MAX_PAGES,
    NotAPdf,
    is_pdf,
    page_count,
    pdf_text,
    render_pdf,
)

SWATCH_RGB = (29, 158, 117)


def build_pdf(pages: int = 1, swatch: tuple[int, int, int] | None = SWATCH_RGB) -> bytes:
    """A PDF whose pages carry a colour block and no text naming it."""
    images = []
    for index in range(pages):
        page = Image.new("RGB", (600, 800), (255, 255, 255))
        if swatch:
            shade = tuple(max(0, channel - index * 3) for channel in swatch)
            page.paste(Image.new("RGB", (300, 300), shade), (150, 200))
        images.append(page)

    buffer = io.BytesIO()
    images[0].save(buffer, format="PDF", save_all=True, append_images=images[1:])
    return buffer.getvalue()


def test_a_pdf_is_recognised_by_its_header():
    assert is_pdf(build_pdf())
    assert not is_pdf(b"\x89PNG\r\n\x1a\n")
    assert not is_pdf(b"")


@pytest.mark.parametrize("call", [render_pdf, pdf_text, page_count])
def test_a_non_pdf_is_refused_rather_than_read_as_empty(call):
    with pytest.raises(NotAPdf):
        call(b"just some bytes")


def test_pages_render_to_rgb_images():
    pages = render_pdf(build_pdf(pages=2))
    assert len(pages) == 2
    assert all(page.mode == "RGB" for page in pages)
    assert all(page.width > 0 and page.height > 0 for page in pages)


def test_a_swatch_with_no_printed_hex_survives_rendering():
    """Gate 7's hard case: the colour exists only as a graphic."""
    [page] = render_pdf(build_pdf(pages=1))
    scale_x = page.width / 600
    scale_y = page.height / 800
    sampled = page.getpixel((int(300 * scale_x), int(350 * scale_y)))

    assert to_hex(sampled) == to_hex(SWATCH_RGB)
    # …and it is genuinely absent from the text layer, which is why rendering is needed.
    assert "1d9e75" not in pdf_text(build_pdf()).lower()


def test_the_page_budget_is_a_hard_cap():
    assert len(render_pdf(build_pdf(pages=MAX_PAGES + 4))) == MAX_PAGES


def test_a_smaller_budget_is_honoured():
    assert len(render_pdf(build_pdf(pages=5), max_pages=2)) == 2


def test_page_count_reports_the_whole_document_not_the_budget():
    assert page_count(build_pdf(pages=MAX_PAGES + 4)) == MAX_PAGES + 4


def test_an_image_only_pdf_yields_no_text_rather_than_failing():
    """The common real case: a design-tool export with everything outlined."""
    assert pdf_text(build_pdf()) == ""
