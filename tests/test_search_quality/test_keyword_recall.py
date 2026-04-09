"""검색 품질 recall 테스트.

이 테스트는 OpenSearch가 실행 중이고 인덱싱된 데이터가 있어야 합니다.
로컬 단위 테스트로는 실행되지 않으며, Docker 환경에서 실행됩니다.

사용법:
    python -m pytest tests/test_search_quality/ -v --run-integration
"""

import json
from pathlib import Path

import pytest

GROUND_TRUTH_PATH = Path(__file__).parent / "ground_truth.json"


@pytest.fixture
def ground_truth() -> dict:
    with open(GROUND_TRUTH_PATH) as f:
        return json.load(f)


@pytest.mark.skip(reason="Requires running OpenSearch with indexed data")
async def test_keyword_recall(ground_truth: dict) -> None:
    from app.services.search_service import search_chunks

    total_cases = len(ground_truth["test_cases"])
    found = 0

    for tc in ground_truth["test_cases"]:
        result = await search_chunks(query=tc["query"], size=50)

        for expected in tc["expected_results"]:
            if not expected.get("must_exist"):
                continue

            file_name_pattern = expected.get("file_name_contains", "")
            match = any(
                file_name_pattern in str(r.get("doc_id", ""))
                for r in result["results"]
            )

            if match:
                found += 1
            else:
                print(f"  MISS: {tc['id']} query='{tc['query']}' expected={file_name_pattern}")

    recall = found / total_cases if total_cases > 0 else 0
    print(f"\nRecall: {found}/{total_cases} = {recall:.2%}")

    assert recall >= 0.98, f"Recall {recall:.2%} is below 98% target"
