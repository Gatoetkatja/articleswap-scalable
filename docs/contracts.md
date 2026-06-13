# Kontrak ArticleSwap

## Pesan RabbitMQ
Exchange : article_events (fanout, durable)
Queues   : stemming_queue, wordcloud_queue (durable)
Payload  :
{ "event": "article.created", "article_id": "<uuid>",
  "timestamp": "<ISO8601>", "retry_count": 0 }

## API
POST /articles            -> 202 { article_id, status: "accepted" }
GET  /articles/{id}/status -> 200 { stemming_status, wordcloud_status,
                                     forwarded, forwarded_level }

## Aturan Forwarding (graceful degradation)
Kirim jika BELUM forwarded DAN salah satu terpenuhi:
1. Kedua status IN ('DONE','FAILED')   -> kirim sekarang
2. now() > deadline_at                  -> timeout, kirim apa adanya

Level: FULL (2 hasil), PARTIAL (1 hasil), RAW (0 hasil).
Worker yang masih PENDING/PROCESSING saat timeout dianggap gagal.