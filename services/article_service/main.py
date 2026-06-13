from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
import db
import broker
from models import ArticleIn, ArticleAccepted, ArticleStatus

PROCESSING_TIMEOUT_SECONDS = 120


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.init_pool()
    await broker.init_broker()
    yield
    await broker.close_broker()
    await db.close_pool()


app = FastAPI(title="ArticleSwap - Article Service", lifespan=lifespan)


@app.post("/articles", status_code=202, response_model=ArticleAccepted)
async def create_article(article: ArticleIn):
    async with db.pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO articles (sender_id, recipient_id, title, content)
                VALUES (%s, %s, %s, %s)
                RETURNING id
                """,
                (article.sender_id, article.recipient_id,
                 article.title, article.content),
            )
            row = await cur.fetchone()
            article_id = row[0]
            await cur.execute(
                """
                INSERT INTO article_processing (article_id, deadline_at)
                VALUES (%s, now() + make_interval(secs => %s))
                """,
                (article_id, PROCESSING_TIMEOUT_SECONDS),
            )
        # transaksi commit otomatis saat blok 'connection' selesai tanpa error
    # Artikel sudah aman tersimpan di DB. Sekarang coba publish.
    published = await broker.publish_article_event(str(article_id))
    if not published:
        # Broker mungkin sedang down. Artikel tetap PENDING dan akan
        # tertangani oleh mekanisme deadline/timeout di Forwarding Service.
        print(f"[WARN] Gagal publish article {article_id}, mengandalkan deadline.")

    return ArticleAccepted(article_id=str(article_id))


@app.get("/articles/{article_id}/status", response_model=ArticleStatus)
async def get_status(article_id: str):
    async with db.pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT article_id, stemming_status, wordcloud_status,
                       forwarded_at, forwarded_level
                FROM article_processing
                WHERE article_id = %s
                """,
                (article_id,),
            )
            row = await cur.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Article not found")
    return ArticleStatus(
        article_id=str(row[0]),
        stemming_status=row[1],
        wordcloud_status=row[2],
        forwarded=row[3] is not None,
        forwarded_level=row[4],
    )