"""OpenSearch 인덱스 초기화 스크립트.

사용법:
    python -m scripts.init_opensearch
    python -m scripts.init_opensearch --recreate
"""

import argparse
import asyncio

from app.opensearch.client import close_opensearch_client, get_opensearch_client
from app.opensearch.index_manager import CHUNKS_INDEX, DOCUMENTS_INDEX, create_index, recreate_index


async def init_indices(recreate: bool = False) -> None:
    client = get_opensearch_client()

    try:
        health = await client.cluster.health()
        print(f"OpenSearch cluster: {health['cluster_name']} ({health['status']})")
    except Exception as e:
        print(f"Failed to connect to OpenSearch: {e}")
        return

    for index_name in [DOCUMENTS_INDEX, CHUNKS_INDEX]:
        try:
            if recreate:
                result = await recreate_index(index_name, client)
            else:
                result = await create_index(index_name, client)
            print(f"  {index_name}: {result['status']}")
        except Exception as e:
            print(f"  {index_name}: ERROR - {e}")

    await close_opensearch_client()


def main() -> None:
    parser = argparse.ArgumentParser(description="Initialize OpenSearch indices")
    parser.add_argument("--recreate", action="store_true", help="Delete and recreate existing indices")
    args = parser.parse_args()

    asyncio.run(init_indices(recreate=args.recreate))


if __name__ == "__main__":
    main()
