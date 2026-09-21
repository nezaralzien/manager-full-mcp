"""Manager takes images, not PDFs — the server must make that unmissable."""

import struct
import zlib

import pytest

from manager_full_mcp import server as S
from manager_full_mcp.attachments import ConversionError, prepare


def _minimal_pdf(pages: int) -> bytes:
    """A valid, tiny PDF with a correct xref table, built without a PDF library."""
    objects = [
        b"<</Type/Catalog/Pages 2 0 R>>",
        "<</Type/Pages/Kids[{}]/Count {}>>".format(
            " ".join(f"{i + 3} 0 R" for i in range(pages)), pages
        ).encode(),
    ]
    for _ in range(pages):
        objects.append(b"<</Type/Page/Parent 2 0 R/MediaBox[0 0 120 80]>>")

    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"
    start = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += (
        f"trailer\n<</Size {len(objects) + 1}/Root 1 0 R>>\nstartxref\n{start}\n".encode()
        + b"%%EOF\n"
    )
    return bytes(out)


def _tiny_png() -> bytes:
    def chunk(tag, data):
        return (
            struct.pack(">I", len(data)) + tag + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(b"\x00\xff\xff\xff"))
        + chunk(b"IEND", b"")
    )


def test_images_pass_through_untouched(tmp_path):
    image = tmp_path / "receipt.png"
    image.write_bytes(_tiny_png())
    result = prepare(image)
    assert result.converted is False
    assert result.files == [image]


def test_pdf_becomes_one_png_per_page(tmp_path):
    pdf = tmp_path / "Mashreq statement.pdf"
    pdf.write_bytes(_minimal_pdf(3))
    result = prepare(pdf, out_dir=tmp_path / "out")
    assert result.converted is True
    assert result.pages == 3
    assert [f.name for f in result.files] == [
        "Mashreq statement-p1.png",
        "Mashreq statement-p2.png",
        "Mashreq statement-p3.png",
    ]
    for f in result.files:
        assert f.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    assert "never merge pages" in result.note


def test_single_page_pdf_keeps_a_clean_name(tmp_path):
    pdf = tmp_path / "invoice.pdf"
    pdf.write_bytes(_minimal_pdf(1))
    result = prepare(pdf, out_dir=tmp_path / "out")
    assert [f.name for f in result.files] == ["invoice.png"]


def test_dpi_changes_the_rendered_size(tmp_path):
    pdf = tmp_path / "doc.pdf"
    pdf.write_bytes(_minimal_pdf(1))
    small = prepare(pdf, dpi=72, out_dir=tmp_path / "a").files[0]
    large = prepare(pdf, dpi=300, out_dir=tmp_path / "b").files[0]
    width = lambda p: struct.unpack(">I", p.read_bytes()[16:20])[0]  # noqa: E731
    assert width(large) > width(small) * 3


def test_other_file_types_are_refused_with_a_reason(tmp_path):
    doc = tmp_path / "contract.docx"
    doc.write_bytes(b"not an image")
    with pytest.raises(ConversionError, match="images only"):
        prepare(doc)


def test_missing_file_is_named(tmp_path):
    with pytest.raises(ConversionError, match="No such file"):
        prepare(tmp_path / "ghost.pdf")


async def test_tool_returns_paths_ready_to_attach(tmp_path):
    pdf = tmp_path / "bank.pdf"
    pdf.write_bytes(_minimal_pdf(2))
    out = await S.prepare_attachment(str(pdf))
    assert out["ok"] and out["pages"] == 2 and len(out["files"]) == 2


async def test_tool_reports_failure_instead_of_raising(tmp_path):
    out = await S.prepare_attachment(str(tmp_path / "missing.pdf"))
    assert out["ok"] is False and out["error"] == "conversion_failed"
