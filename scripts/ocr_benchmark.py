"""OCR 엔진 품질 벤치마크.

목표: 현재 ``settings.ocr_engine`` (auto / surya / tesseract) 의 실제 인식률을
재현 가능한 수치(CER, Character Error Rate)로 측정한다.

사용법::

    # 운영 서버 (Surya GPU 구동 환경)
    OCR_ENGINE=surya python -m scripts.ocr_benchmark --dataset tests/fixtures/ocr_gt

    # 비교군으로 Tesseract 도 재실행
    OCR_ENGINE=tesseract python -m scripts.ocr_benchmark --dataset tests/fixtures/ocr_gt

Ground truth 데이터셋 구조::

    tests/fixtures/ocr_gt/
      ├── ko/
      │   ├── page_001.png    # 입력 이미지
      │   ├── page_001.txt    # 정답 텍스트 (UTF-8)
      │   └── ...
      └── en/
          ├── page_001.png
          └── page_001.txt

목표치: 전체 문자 에러율(CER) ≤ 0.02 → 정확도 ≥ 98%.

현재 구축 상태: **정답 데이터셋 미구축**. 한국어 단행본 3~5 페이지, 영문 기술서
3~5 페이지 분량을 수작업으로 스캔 + 정답 텍스트 확정 필요.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class PageResult:
    image: str
    language: str
    cer: float
    wer: float
    gt_chars: int
    pred_chars: int
    predicted: str
    ground_truth: str


def _levenshtein(a: str, b: str) -> int:
    """문자 편집 거리 (표준 DP, 메모리 O(len(b)))."""
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        cur = [i] + [0] * len(b)
        for j, cb in enumerate(b, start=1):
            cost = 0 if ca == cb else 1
            cur[j] = min(cur[j - 1] + 1, prev[j] + 1, prev[j - 1] + cost)
        prev = cur
    return prev[-1]


def compute_cer(pred: str, gt: str) -> float:
    """Character Error Rate. 공백/개행은 정규화 후 비교."""
    norm_pred = " ".join(pred.split())
    norm_gt = " ".join(gt.split())
    if not norm_gt:
        return 0.0 if not norm_pred else 1.0
    return _levenshtein(norm_pred, norm_gt) / len(norm_gt)


def compute_wer(pred: str, gt: str) -> float:
    """Word Error Rate — 공백 기준. 한/영 혼용에서는 CER 을 주 지표로 쓰고 WER 은 보조."""
    gt_words = gt.split()
    if not gt_words:
        return 0.0 if not pred.split() else 1.0
    return _levenshtein(" ".join(pred.split()), " ".join(gt_words).replace(" ", "\n")) / len(gt_words)


def iter_ground_truth_pairs(dataset_root: Path) -> list[tuple[Path, Path, str]]:
    """(image_path, gt_txt_path, language) 튜플 리스트."""
    pairs: list[tuple[Path, Path, str]] = []
    for lang_dir in sorted(dataset_root.iterdir()):
        if not lang_dir.is_dir():
            continue
        lang = lang_dir.name
        for img in sorted(lang_dir.glob("*.png")):
            gt = img.with_suffix(".txt")
            if gt.exists():
                pairs.append((img, gt, lang))
    return pairs


def run_benchmark(dataset_root: Path) -> dict:
    from app.config import settings
    from app.parsers.ocr_processor import get_ocr_engine

    engine = get_ocr_engine()
    logger.info("Using engine: %s", engine.name)

    results: list[PageResult] = []
    pairs = iter_ground_truth_pairs(dataset_root)
    if not pairs:
        logger.warning("No ground-truth pairs found under %s", dataset_root)
        return {"engine": engine.name, "samples": 0, "aggregate_cer": None, "results": []}

    total_gt_chars = 0
    total_edits = 0

    for img_path, gt_path, lang in pairs:
        gt_text = gt_path.read_text(encoding="utf-8")
        image_bytes = img_path.read_bytes()
        pred = engine.ocr_image_from_bytes(image_bytes)

        cer = compute_cer(pred, gt_text)
        wer = compute_wer(pred, gt_text)
        gt_norm = " ".join(gt_text.split())
        total_gt_chars += len(gt_norm)
        total_edits += _levenshtein(" ".join(pred.split()), gt_norm)

        results.append(PageResult(
            image=str(img_path.relative_to(dataset_root)),
            language=lang,
            cer=round(cer, 4),
            wer=round(wer, 4),
            gt_chars=len(gt_norm),
            pred_chars=len(" ".join(pred.split())),
            predicted=pred[:200] + ("…" if len(pred) > 200 else ""),
            ground_truth=gt_text[:200] + ("…" if len(gt_text) > 200 else ""),
        ))
        logger.info("%s (%s): CER=%.4f WER=%.4f", img_path.name, lang, cer, wer)

    aggregate_cer = total_edits / total_gt_chars if total_gt_chars else None

    return {
        "engine": engine.name,
        "engine_settings": {
            "ocr_engine": settings.ocr_engine,
            "surya_device": settings.surya_device,
            "surya_langs": settings.surya_langs,
        },
        "samples": len(pairs),
        "aggregate_cer": round(aggregate_cer, 4) if aggregate_cer is not None else None,
        "accuracy_percent": round((1 - aggregate_cer) * 100, 2) if aggregate_cer is not None else None,
        "target_accuracy": 98.0,
        "results": [asdict(r) for r in results],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="OCR quality benchmark")
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path("tests/fixtures/ocr_gt"),
        help="Ground truth 디렉토리 (하위에 ko/, en/ 등 언어 폴더)",
    )
    parser.add_argument("--output", type=Path, default=None, help="결과 JSON 저장 경로")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    if not args.dataset.exists():
        logger.error("Dataset not found: %s", args.dataset)
        logger.error("Ground truth 를 먼저 구축하세요. 파일 헤더 docstring 참고.")
        return 2

    report = run_benchmark(args.dataset)

    print(json.dumps({k: v for k, v in report.items() if k != "results"}, ensure_ascii=False, indent=2))
    if args.output:
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info("Full report written: %s", args.output)

    if report["aggregate_cer"] is None:
        return 0
    return 0 if report["aggregate_cer"] <= 0.02 else 1


if __name__ == "__main__":
    sys.exit(main())
