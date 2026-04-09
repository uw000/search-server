from pathlib import Path

from app.parsers.base import BaseParser, ParseResult


class HwpParser(BaseParser):
    def supported_extensions(self) -> list[str]:
        return [".hwp", ".hwpx"]

    def parse(self, file_path: Path) -> ParseResult:
        raise NotImplementedError(
            "HWP 파싱은 아직 지원되지 않습니다. "
            "향후 pyhwp 또는 LibreOffice CLI를 활용하여 구현 예정입니다."
        )
