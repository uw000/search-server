import json
from pathlib import Path

from opensearchpy import AsyncOpenSearch

from app.opensearch.client import get_opensearch_client

INDEX_SETTINGS_PATH = Path(__file__).parent.parent.parent / "opensearch-config" / "index_settings.json"

DOCUMENTS_INDEX = "documents"
CHUNKS_INDEX = "chunks"


def _load_index_settings() -> dict:
    with open(INDEX_SETTINGS_PATH) as f:
        return json.load(f)


async def create_index(index_name: str, client: AsyncOpenSearch | None = None) -> dict:
    client = client or get_opensearch_client()
    all_settings = _load_index_settings()

    if index_name not in all_settings:
        raise ValueError(f"Unknown index: {index_name}. Available: {list(all_settings.keys())}")

    index_config = all_settings[index_name]

    if await client.indices.exists(index=index_name):
        return {"status": "already_exists", "index": index_name}

    result = await client.indices.create(index=index_name, body=index_config)
    return {"status": "created", "index": index_name, "result": result}


async def delete_index(index_name: str, client: AsyncOpenSearch | None = None) -> dict:
    client = client or get_opensearch_client()

    if not await client.indices.exists(index=index_name):
        return {"status": "not_found", "index": index_name}

    result = await client.indices.delete(index=index_name)
    return {"status": "deleted", "index": index_name, "result": result}


async def recreate_index(index_name: str, client: AsyncOpenSearch | None = None) -> dict:
    client = client or get_opensearch_client()
    await delete_index(index_name, client)
    return await create_index(index_name, client)


async def create_all_indices(client: AsyncOpenSearch | None = None) -> list[dict]:
    results = []
    for index_name in [DOCUMENTS_INDEX, CHUNKS_INDEX]:
        result = await create_index(index_name, client)
        results.append(result)
    return results
