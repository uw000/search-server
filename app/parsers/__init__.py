from pathlib import Path

from app.parsers.base import BaseParser, ParseResult
from app.parsers.docx_parser import DocxParser
from app.parsers.epub_parser import EpubParser
from app.parsers.hwp_parser import HwpParser
from app.parsers.pdf_parser import PdfParser
from app.parsers.txt_parser import TxtParser

_PARSERS: dict[str, BaseParser] = {}


def _init_parsers() -> None:
    for parser_cls in [TxtParser, PdfParser, EpubParser, DocxParser, HwpParser]:
        parser = parser_cls()
        for ext in parser.supported_extensions():
            _PARSERS[ext] = parser


def get_parser(file_path: Path) -> BaseParser:
    if not _PARSERS:
        _init_parsers()
    ext = file_path.suffix.lower()
    if ext not in _PARSERS:
        raise ValueError(f"Unsupported file format: {ext}")
    return _PARSERS[ext]


__all__ = [
    "BaseParser",
    "ParseResult",
    "get_parser",
    "DocxParser",
    "EpubParser",
    "HwpParser",
    "PdfParser",
    "TxtParser",
]
