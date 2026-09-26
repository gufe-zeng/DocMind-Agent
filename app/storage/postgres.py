import asyncpg


async def check_postgres(dsn: str) -> None:
    connection = await asyncpg.connect(dsn=dsn, timeout=3)
    try:
        value = await connection.fetchval("SELECT 1")
        if value != 1:
            raise RuntimeError("PostgreSQL health query returned an unexpected value.")
    finally:
        await connection.close()
