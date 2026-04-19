"""opensearch-config/index_settings.json 구조/참조 무결성 검증.

실제 OpenSearch 에 띄우기 전 구성 파일의 정합성을 빠르게 잡기 위한 정적 테스트.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

CONFIG_DIR = Path(__file__).parent.parent.parent / "opensearch-config"
SETTINGS_PATH = CONFIG_DIR / "index_settings.json"


@pytest.fixture(scope="module")
def settings_doc() -> dict:
    with open(SETTINGS_PATH) as f:
        return json.load(f)


def test_loads_as_valid_json(settings_doc: dict) -> None:
    assert isinstance(settings_doc, dict)
    assert "documents" in settings_doc
    assert "chunks" in settings_doc


@pytest.mark.parametrize("index_name", ["documents", "chunks"])
def test_index_has_analysis_block(settings_doc: dict, index_name: str) -> None:
    analysis = settings_doc[index_name]["settings"]["analysis"]
    assert "tokenizer" in analysis
    assert "analyzer" in analysis
    assert "filter" in analysis


@pytest.mark.parametrize("index_name", ["documents", "chunks"])
def test_synonym_filters_present(settings_doc: dict, index_name: str) -> None:
    filters = settings_doc[index_name]["settings"]["analysis"]["filter"]
    assert "ko_synonym_graph" in filters
    assert "en_synonym_graph" in filters
    assert filters["ko_synonym_graph"]["type"] == "synonym_graph"
    assert filters["ko_synonym_graph"]["synonyms_path"] == "synonyms_ko.txt"
    assert filters["ko_synonym_graph"].get("lenient") is True


@pytest.mark.parametrize("index_name", ["documents", "chunks"])
def test_user_dictionary_wired(settings_doc: dict, index_name: str) -> None:
    tokenizers = settings_doc[index_name]["settings"]["analysis"]["tokenizer"]
    nori_tokenizers = [t for t in tokenizers.values() if t.get("type") == "nori_tokenizer"]
    assert nori_tokenizers, f"no nori tokenizer in {index_name}"
    for tok in nori_tokenizers:
        assert tok.get("user_dictionary") == "user_dict_ko.txt"


def test_chunks_has_search_analyzer_with_synonyms(settings_doc: dict) -> None:
    content = settings_doc["chunks"]["mappings"]["properties"]["content"]
    # index 시에는 synonym 미적용, search 시에만 적용
    assert content["analyzer"] == "nori_mixed"
    assert content["search_analyzer"] == "nori_mixed_search"

    analyzers = settings_doc["chunks"]["settings"]["analysis"]["analyzer"]
    assert "ko_synonym_graph" not in analyzers["nori_mixed"]["filter"]
    assert "ko_synonym_graph" in analyzers["nori_mixed_search"]["filter"]


def test_documents_title_has_search_analyzer_with_synonyms(settings_doc: dict) -> None:
    title = settings_doc["documents"]["mappings"]["properties"]["title"]
    assert title["analyzer"] == "korean_english"
    assert title["search_analyzer"] == "korean_english_search"

    analyzers = settings_doc["documents"]["settings"]["analysis"]["analyzer"]
    assert "ko_synonym_graph" not in analyzers["korean_english"]["filter"]
    assert "ko_synonym_graph" in analyzers["korean_english_search"]["filter"]


def test_english_subfield_has_synonym_search_analyzer(settings_doc: dict) -> None:
    content_english = (
        settings_doc["chunks"]["mappings"]["properties"]["content"]["fields"]["english"]
    )
    assert content_english["analyzer"] == "english_custom"
    assert content_english["search_analyzer"] == "english_custom_search"

    analyzers = settings_doc["chunks"]["settings"]["analysis"]["analyzer"]
    assert "en_synonym_graph" not in analyzers["english_custom"]["filter"]
    assert "en_synonym_graph" in analyzers["english_custom_search"]["filter"]


def test_all_referenced_analyzers_exist(settings_doc: dict) -> None:
    """필드 매핑에서 참조된 analyzer/search_analyzer 이름이 analysis.analyzer 에 모두 정의되어야 한다."""
    for index_name in ["documents", "chunks"]:
        defined = set(settings_doc[index_name]["settings"]["analysis"]["analyzer"].keys())
        # 빌트인 analyzer 이름은 무시 (standard/english/whitespace/keyword/stop/simple)
        builtins = {"standard", "english", "whitespace", "keyword", "stop", "simple"}

        def check(mapping: dict) -> None:
            for field, cfg in mapping.items():
                if not isinstance(cfg, dict):
                    continue
                for key in ("analyzer", "search_analyzer"):
                    val = cfg.get(key)
                    if val:
                        assert val in defined or val in builtins, (
                            f"{index_name}:{field} references undefined analyzer {val!r}"
                        )
                sub = cfg.get("fields")
                if sub:
                    check(sub)
                sub_props = cfg.get("properties")
                if sub_props:
                    check(sub_props)

        check(settings_doc[index_name]["mappings"]["properties"])


def test_all_referenced_filters_exist(settings_doc: dict) -> None:
    """analyzer 의 filter 배열에 쓰인 이름이 filter 섹션 또는 빌트인 필터에 존재해야 한다."""
    builtin_filters = {
        "lowercase",
        "nori_readingform",
        "nori_number",
        "nori_part_of_speech",
        "standard",
    }
    for index_name in ["documents", "chunks"]:
        analysis = settings_doc[index_name]["settings"]["analysis"]
        defined_filters = set(analysis.get("filter", {}).keys()) | builtin_filters
        for a_name, a_cfg in analysis["analyzer"].items():
            for f in a_cfg.get("filter", []):
                assert f in defined_filters, (
                    f"{index_name}:{a_name} uses undefined filter {f!r}"
                )


def test_synonym_files_exist_and_nonempty() -> None:
    for name in ["synonyms_ko.txt", "synonyms_en.txt", "user_dict_ko.txt"]:
        p = CONFIG_DIR / name
        assert p.exists(), f"missing {name}"
        # 주석 외 실제 항목이 하나 이상 있어야 함
        non_comment_lines = [
            ln.strip() for ln in p.read_text().splitlines()
            if ln.strip() and not ln.lstrip().startswith("#")
        ]
        assert non_comment_lines, f"{name} has no actual entries"
