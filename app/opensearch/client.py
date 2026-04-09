from opensearchpy import AsyncOpenSearch

from app.config import settings

_client: AsyncOpenSearch | None = None


def get_opensearch_client() -> AsyncOpenSearch:
    global _client
    if _client is None:
        _client = AsyncOpenSearch(
            hosts=[settings.opensearch_url],
            use_ssl=False,
            verify_certs=False,
            timeout=30,
            max_retries=3,
            retry_on_timeout=True,
        )
    return _client


async def close_opensearch_client() -> None:
    global _client
    if _client is not None:
        await _client.close()
        _client = None


async def check_opensearch_health() -> dict:
    client = get_opensearch_client()
    return await client.cluster.health()
