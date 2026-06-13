import os
from psycopg_pool import AsyncConnectionPool

DB_DSN = os.getenv(
    "DATABASE_URL",
    "postgresql://articleswap:devpassword@localhost:5432/articleswap",
)

pool: AsyncConnectionPool | None = None


async def init_pool():
    """Buat connection pool saat aplikasi start."""
    global pool
    pool = AsyncConnectionPool(conninfo=DB_DSN, min_size=2, max_size=10, open=False)
    await pool.open()


async def close_pool():
    """Tutup pool saat aplikasi shutdown."""
    if pool:
        await pool.close()