"""Turn any evidence file into what Manager will actually accept: images.

Manager's Image field silently rejects PDFs, and a multi-page document has to
become one image per page so each page can be attached to its own record. This
module does that conversion itself — no poppler, no ImageMagick, no Pillow — so
the rule cannot fail for want of a tool that is not installed.
"""

from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass
from pathlib import Path

from manager_full_mcp.config import home

IMAGE_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tif", ".tiff"})
DEFAULT_DPI = 150
MAX_DPI = 400


class ConversionError(RuntimeError):
    """The file could not be turned into images."""


def output_dir() -> Path:
    path = home() / "converted"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _png_from_bgr(width: int, height: int, stride: int, buffer: bytes) -> bytes:
    """Encode a tightly packed BGR bitmap as an RGB PNG."""
    rows = bytearray()
    for y in range(height):
        start = y * stride
        row = bytearray(buffer[start : start + width * 3])
        row[0::3], row[2::3] = row[2::3], row[0::3]  # BGR -> RGB
        rows += b"\x00" + row  # filter type 0

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(bytes(rows), 6))
        + chunk(b"IEND", b"")
    )


@dataclass
class Prepared:
    source: Path
    files: list[Path]
    converted: bool
    pages: int
    note: str

    def payload(self) -> dict[str, object]:
        return {
            "ok": True,
            "source": str(self.source),
            "converted": self.converted,
            "pages": self.pages,
            "files": [str(f) for f in self.files],
            "note": self.note,
        }


def prepare(path: str | Path, *, dpi: int = DEFAULT_DPI, out_dir: Path | None = None) -> Prepared:
    source = Path(path).expanduser()
    if not source.is_file():
        raise ConversionError(f"No such file: {source}")
    suffix = source.suffix.casefold()

    if suffix in IMAGE_SUFFIXES:
        return Prepared(
            source=source,
            files=[source],
            converted=False,
            pages=1,
            note="Already an image — attach it as is.",
        )
    if suffix != ".pdf":
        raise ConversionError(
            f"Manager accepts images only, and '{suffix or source.name}' is neither an "
            "image nor a PDF this tool can rasterise. Convert it to PNG or JPEG first."
        )

    dpi = max(72, min(int(dpi), MAX_DPI))
    try:
        import pypdfium2 as pdfium
    except ImportError as exc:  # pragma: no cover - dependency is declared
        raise ConversionError(
            "pypdfium2 is not installed in this environment, so PDFs cannot be "
            "converted. Install it, or convert the file to PNG before attaching."
        ) from exc

    target = Path(out_dir) if out_dir else output_dir()
    target.mkdir(parents=True, exist_ok=True)
    try:
        document = pdfium.PdfDocument(str(source))
        count = len(document)
    except Exception as exc:
        raise ConversionError(f"Could not read {source.name} as a PDF: {exc}") from exc

    stem = source.stem.replace("/", "-")
    written: list[Path] = []
    for index in range(count):
        bitmap = document[index].render(scale=dpi / 72)
        if bitmap.mode != "BGR":  # pragma: no cover - pdfium default is BGR
            raise ConversionError(f"Unexpected bitmap mode {bitmap.mode!r} from pdfium.")
        data = _png_from_bgr(
            bitmap.width, bitmap.height, bitmap.stride, bytes(bitmap.buffer)
        )
        name = f"{stem}.png" if count == 1 else f"{stem}-p{index + 1}.png"
        out = target / name
        out.write_bytes(data)
        written.append(out)

    note = (
        f"PDF rasterised at {dpi} dpi. Manager rejects PDFs, so attach these "
        f"image{'s' if count > 1 else ''} instead of the original file."
    )
    if count > 1:
        note += (
            f" The document has {count} pages: attach one page per record, or all "
            "of them to the record they evidence — never merge pages into one image."
        )
    return Prepared(source=source, files=written, converted=True, pages=count, note=note)
