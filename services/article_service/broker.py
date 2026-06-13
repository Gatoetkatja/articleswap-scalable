import os
import json
import aio_pika

RABBIT_URL = os.getenv("RABBIT_URL", "amqp://guest:guest@localhost:5672/")

EXCHANGE_NAME = "article_events"

connection: aio_pika.abc.AbstractRobustConnection | None = None
channel: aio_pika.abc.AbstractChannel | None = None
exchange: aio_pika.abc.AbstractExchange | None = None


async def init_broker():
    """Sambung ke RabbitMQ dan deklarasikan topologi (exchange + queues)."""
    global connection, channel, exchange
    connection = await aio_pika.connect_robust(RABBIT_URL)
    channel = await connection.channel()

    # Exchange fanout: setiap pesan disalin ke SEMUA queue yang terikat
    exchange = await channel.declare_exchange(
        EXCHANGE_NAME, aio_pika.ExchangeType.FANOUT, durable=True
    )

    # Dua queue durable, masing-masing untuk satu worker
    for queue_name in ("stemming_queue", "wordcloud_queue"):
        queue = await channel.declare_queue(queue_name, durable=True)
        await queue.bind(exchange)


async def close_broker():
    if connection:
        await connection.close()


async def publish_article_event(article_id: str) -> bool:
    """
    Publish event 'article.created'. Mengembalikan True jika sukses,
    False jika gagal (mis. broker down) tanpa melempar error.
    """
    if exchange is None:
        return False
    try:
        message_body = json.dumps({
            "event": "article.created",
            "article_id": article_id,
            "retry_count": 0,
        }).encode()
        message = aio_pika.Message(
            body=message_body,
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,  # pesan bertahan jika broker restart
        )
        await exchange.publish(message, routing_key="")
        return True
    except Exception:
        return False