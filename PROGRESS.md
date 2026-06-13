# ArticleSwap — Progress & Panduan Setup

Dokumen ini ditujukan untuk anggota tim yang **baru pertama kali** masuk ke proyek.
Ikuti dari atas ke bawah; di akhir kamu akan punya sistem yang berjalan di komputermu
dan paham bagian mana yang sudah selesai serta apa langkah berikutnya.

---

## 1. Apa itu ArticleSwap?

Sistem pemrosesan artikel yang **scalable**. Alurnya: User A mengirim artikel → artikel
disimpan → diproses secara paralel (stemming + word cloud) → dikirim ke User B.

Prinsip desain utama yang kami pegang:

- **Asinkron** — artikel tidak diproses langsung saat dikirim. Article Service hanya
  menyimpan lalu menitipkan tugas ke message broker (RabbitMQ). Ini membuat sistem
  responsif dan mudah di-scale (tinggal tambah worker).
- **Graceful degradation** — kalau salah satu pemrosesan gagal, artikel tetap dikirim
  dengan hasil seadanya. Kalau keduanya gagal, artikel mentah tetap dikirim. Sistem
  tidak pernah "menelan" artikel sampai hilang.

---

## 2. Arsitektur singkat

```
User A → Article Service → simpan ke PostgreSQL
                         → publish pesan ke RabbitMQ (exchange fanout)
                                                │
                                  ┌─────────────┴─────────────┐
                                  ▼                           ▼
                            stemming_queue              wordcloud_queue
                                  ▼                           ▼
                           [Worker Stemming]          [Worker Word Cloud]   ← BELUM dibuat (Fase 4)
                                  └─────────────┬─────────────┘
                                                ▼
                                       [Forwarding Service]  ← BELUM dibuat (Fase 5)
                                                ▼
                                            User B
```

Karena exchange bertipe **fanout**, satu artikel menghasilkan dua pesan — satu di tiap
queue — sehingga kedua pemrosesan menerima salinannya masing-masing dan berjalan paralel.

---

## 3. Prasyarat (yang harus diinstal lebih dulu)

| Tool | Versi | Catatan |
|---|---|---|
| Docker Desktop | terbaru | Menjalankan PostgreSQL & RabbitMQ |
| Python | **3.14** | Versi yang dipakai tim saat ini |
| Git | terbaru | Version control |

> **Penting soal Python:** proyek ini berjalan di Python 3.14 dengan driver database
> `psycopg` (versi 3). Awalnya kami mencoba `asyncpg`, tetapi `asyncpg` belum punya
> paket siap-pakai untuk Python 3.14 sehingga gagal saat instalasi. Kalau kamu menemui
> error build saat `pip install`, kemungkinan besar versi Python-mu berbeda. Pakai
> 3.14 agar konsisten dengan tim.

---

## 4. Cara menjalankan dari nol

### 4.1. Clone & masuk folder

```powershell
git clone <url-repo>
cd articleswap
```

### 4.2. Nyalakan infrastruktur (database + message broker)

Dari folder root `articleswap`:

```powershell
docker compose up -d
docker compose ps
```

Kedua container harus berstatus **Up**:
- `articleswap-db` (PostgreSQL, port 5432)
- `articleswap-mq` (RabbitMQ, port 5672 + UI di 15672)

Skema database otomatis dibuat saat container pertama kali jalan (lihat
`database/init.sql`).

> Kalau kamu mengubah `database/init.sql` setelah container pernah jalan, perubahan
> **tidak** otomatis diterapkan. Reset dengan: `docker compose down -v` lalu
> `docker compose up -d` (hati-hati: `-v` menghapus data di database).

### 4.3. Siapkan Article Service

```powershell
cd services\article_service
py -3.14 -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

> Kalau muncul error *"running scripts is disabled"* saat aktivasi venv, jalankan dulu:
> `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` lalu ulangi.

### 4.4. Jalankan Article Service

```powershell
uvicorn main:app --reload --port 8000
```

Tunggu sampai muncul `Application startup complete`. Kalau ada error, cek bagian
Troubleshooting di bawah.

---

## 5. Cara menguji bahwa semuanya jalan

### 5.1. Kirim artikel

Buka terminal **baru** (biarkan uvicorn jalan), lalu:

```powershell
$body = @{
    sender_id    = "user-a"
    recipient_id = "user-b"
    title        = "Artikel Percobaan"
    content      = "Para peneliti sedang berlari mengejar tenggat waktu penelitian mereka."
} | ConvertTo-Json

Invoke-RestMethod -Uri http://localhost:8000/articles -Method Post -Body $body -ContentType "application/json"
```

Harus mengembalikan `article_id` dan `status: accepted`.

### 5.2. Cek status artikel

```powershell
Invoke-RestMethod -Uri http://localhost:8000/articles/<article_id>/status
```

`stemming_status` dan `wordcloud_status` akan `PENDING` (wajar — worker belum dibuat).

### 5.3. Cek pesan masuk ke RabbitMQ

Buka `http://localhost:15672` (login `guest` / `guest`):
- Tab **Exchanges** → harus ada `article_events` bertipe `fanout`.
- Tab **Queues** → `stemming_queue` dan `wordcloud_queue`, kolom **Ready** bertambah
  setiap kali artikel dikirim. Satu artikel = +1 di KEDUA queue.

### 5.4. Cek langsung di database (opsional)

```powershell
docker exec -it articleswap-db psql -U articleswap -d articleswap -c "SELECT a.title, p.stemming_status, p.wordcloud_status, p.deadline_at FROM articles a JOIN article_processing p ON p.article_id = a.id;"
```

---

## 6. Struktur folder

```
articleswap\
├── docker-compose.yml          # definisi container PostgreSQL & RabbitMQ
├── PROGRESS.md                 # dokumen ini
├── .gitignore                  # berisi venv/ dan .venv/
├── database\
│   └── init.sql                # skema DB (tabel + enum), jalan otomatis
├── docs\
│   └── contracts.md            # kontrak: format pesan, API, aturan forwarding
└── services\
    └── article_service\        # Service penerima artikel (Fase 2-3)
        ├── requirements.txt
        ├── db.py               # connection pool ke PostgreSQL (psycopg)
        ├── broker.py           # koneksi & publish ke RabbitMQ (aio-pika)
        ├── models.py           # skema request/response (Pydantic)
        └── main.py             # endpoint API + lifespan
```

---

## 7. Skema data (acuan singkat)

**Tabel `articles`** — artikel mentah, tidak pernah diubah worker:
`id` (UUID), `sender_id`, `recipient_id`, `title`, `content`, `created_at`.

**Tabel `article_processing`** — state pemrosesan, satu baris per artikel:
- `stemming_status`, `wordcloud_status` — enum: `PENDING` / `PROCESSING` / `DONE` / `FAILED`.
  Status **terpisah per pipeline** supaya kedua worker tidak saling timpa (hindari race condition).
- `stemmed_content`, `wordcloud_data` — hasil pemrosesan (diisi worker nanti).
- `deadline_at` — batas waktu tunggu. Lewat ini, Forwarding Service mengirim apa adanya.
- `forwarded_at`, `forwarded_level` — penanda sudah dikirim & tingkatnya (FULL/PARTIAL/RAW).

Detail lengkap kontrak ada di `docs/contracts.md`.

---

## 8. Status pengerjaan

| Fase | Deskripsi | Status |
|---|---|---|
| 1 | Desain skema DB, docker-compose, kontrak sistem | ✅ Selesai |
| 2 | Article Service (FastAPI) + connection pooling | ✅ Selesai |
| 3 | Integrasi RabbitMQ — publish pesan saat artikel masuk | ✅ Selesai |
| 4 | **Worker Stemming & Word Cloud** (consumer) | ⬜ Berikutnya |
| 5 | Forwarding Service (logika graceful degradation) | ⬜ Belum |
| 6 | API Gateway + failover | ⬜ Belum |
| 7 | Load Balancer + containerisasi penuh | ⬜ Belum |
| 8 | Uji fault tolerance & beban | ⬜ Belum |

### Apa yang sudah bekerja sekarang
Artikel bisa dikirim lewat API, tersimpan atomik di PostgreSQL, dan memicu dua pesan
di RabbitMQ (satu per queue). Kegagalan publish ke RabbitMQ **tidak** menggagalkan
penyimpanan artikel — artikel tetap aman dengan status `PENDING` dan akan tertangani
mekanisme deadline nanti.

### Langkah berikutnya (Fase 4)
Membuat dua service consumer terpisah yang:
1. Mengambil pesan dari queue masing-masing (`stemming_queue` / `wordcloud_queue`).
2. Mengambil konten artikel dari DB berdasarkan `article_id` di pesan.
3. Memproses (stemming pakai Sastrawi; word cloud = hitung frekuensi kata).
4. Menulis hasil ke DB & meng-update status pipeline-nya sendiri.
5. Mengirim ACK manual **setelah** sukses (kalau worker crash di tengah, pesan kembali
   ke queue untuk diproses ulang).

---

## 9. Troubleshooting

**`ModuleNotFoundError: No module named 'aio_pika'` (atau modul lain)**
Library belum terpasang di venv yang aktif. Pastikan prompt berawalan `(venv)`, lalu
`pip install -r requirements.txt`. Cek interpreter dengan `where.exe python` — harus
menunjuk ke `services\article_service\venv\Scripts\`.

**Error build saat `pip install` (banyak baris C/compiler)**
Versi Python tidak cocok dengan library. Pastikan pakai Python 3.14 dan driver
`psycopg` (bukan `asyncpg`). Cek isi `requirements.txt`.

**`GET / HTTP/1.1" 404 Not Found` di log uvicorn**
Bukan error. Kita memang tidak punya endpoint `/`. Gunakan `/docs` untuk Swagger UI,
atau endpoint `/articles`.

**Tabel tidak terbentuk / perubahan `init.sql` tidak muncul**
`init.sql` hanya jalan saat volume database masih kosong. Reset dengan
`docker compose down -v` lalu `docker compose up -d`.

**Container tidak Up**
`docker compose logs postgres` atau `docker compose logs rabbitmq` untuk lihat
penyebabnya. Pastikan port 5432, 5672, 15672 tidak dipakai aplikasi lain.

---

## 10. Endpoint API (ringkas)

| Method | Path | Fungsi |
|---|---|---|
| POST | `/articles` | Kirim artikel baru. Body: `sender_id`, `recipient_id`, `title`, `content`. Balas `202` + `article_id`. |
| GET | `/articles/{id}/status` | Cek status pemrosesan sebuah artikel. |
| GET | `/docs` | Swagger UI (dokumentasi interaktif, bisa untuk uji manual). |
