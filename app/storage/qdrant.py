from qdrant_client import AsyncQdrantClient


async def check_qdrant(url: str, api_key: str | None = None) -> None:
    client = AsyncQdrantClient(
        url=url,
        api_key=api_key or None,
        timeout=3,
    )
    try:
        await client.get_collections()
    finally:
        await client.close()
