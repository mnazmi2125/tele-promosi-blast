# 📖 JasebVPS — Panduan Lengkap Telegram Blast Bot

Bot Telegram untuk **mengirim pesan otomatis berulang ke banyak grup** dari VPS,
mendukung **banyak akun sekaligus**, jalan otomatis 24/7.

> ⚠️ **Peringatan:** Gunakan secara bertanggung jawab. Blast berlebihan bisa membuat
> akun kena *flood wait* atau banned Telegram. Atur delay dengan wajar.

---

## 🎛 PANEL KONTROL (jalankan semua via tombol di Telegram)

Selain perintah CLI, tersedia **panel kontrol berbasis tombol** (`panel.py`) —
semua setting (akun, grup, pesan, delay, mulai/stop, tambah akun) di-trigger dari chat Telegram.

### Setup panel (sekali saja)

1. Buat bot di **@BotFather** → `/newbot` → salin **token**
2. Dapatkan ID Telegram Anda via **@userinfobot**
3. Edit **`panel.json`**:
```json
{
  "bot_token": "TOKEN_DARI_BOTFATHER",
  "admin_ids": [ID_TELEGRAM_ANDA],
  "api_id": "...",
  "api_hash": "..."
}
```
4. Jalankan:
```bash
python3 panel.py            # test langsung
# atau via PM2 (ecosystem.config.js sudah di-set app "panel"):
pm2 start ecosystem.config.js && pm2 save
```
5. Buka bot → `/start` → muncul menu tombol.

### Menu panel

| Tombol | Fungsi |
|---|---|
| ▸ Akun | Pilih akun aktif (lihat status ●/○) |
| ▸ Grup | Pilih grup pakai tombol centang (paginasi) |
| ▸ Pesan | Mode Saved Messages / teks manual / forward, footer |
| ▸ Delay & Durasi | Tombol cepat 30/45/60 mnt + custom, ∞/24j/30 hari |
| ▶ MULAI / ⏹ STOP | Konfirmasi ringkasan → jalankan / hentikan |
| 📊 Status | Siklus, total terkirim, jadwal berikutnya |
| ➕ Tambah Akun | Login akun baru dari chat → file instance & session dibuat **otomatis** |

- Hanya **admin** (`admin_ids`) yang bisa kontrol — lainnya diabaikan
- Notifikasi otomatis ke admin: mulai/stop, error, FLOOD_WAIT, akun blokir + laporan harian
- Semua akun bisa berjalan **bersamaan**, kontrol **terpusat** di 1 panel
- Saat blast berjalan, pengaturan grup/pesan/delay **terkunci** (STOP dulu)

> **Catatan transisi (VPS yang sudah pakai blast1/blast2 lama):**
> `pm2 delete blast1 blast2` → `pm2 start ecosystem.config.js` (hanya app `panel`).

---

## 📁 Daftar File

### File yang DIPAKAI

| File | Fungsi |
|---|---|
| `bot.py` | Script bot utama (untuk SEMUA akun) — engine blast CLI |
| `panel.py` | 🎛 Panel kontrol Telegram (tombol) — jalankan semua dari chat |
| `panel.json` | Konfigurasi panel (token bot, admin_ids, API) |
| `instances/akun1.json` | Setting akun 1 (grup, delay, pesan) |
| `instances/akun2.json` | Setting akun 2 |
| `ecosystem.config.js` | Config PM2 (app `panel`) |

### File yang TIDAK usah di-upload / diabaikan
`jasebvps.py`, `jasebvps2.py`, `jasebvpssv.py`, `run_bot.sh`, `run_botsv.sh`,
`run_bot.sh.save`, `*.session` (lama), `*_config.json` (lama), `*.log`,
`joingruptele.py`, `telegram-bot.service`, `telegram-botsv.service`

### Struktur folder di VPS

```
/root/telegram-bot/
├── bot.py
├── ecosystem.config.js
├── instances/
│   ├── akun1.json
│   └── akun2.json
├── akun1.session          ← dibuat otomatis saat login
└── akun2.session          ← dibuat otomatis saat login
```

---

## 🛠 Prasyarat

1. **VPS Linux** (Ubuntu/Debian), akses `root`
2. **API Telegram** dari https://my.telegram.org → *API development tools*
   → dapat `api_id` + `api_hash`
   > 1 set API **boleh dipakai semua akun** (API milik developer, bukan akun)
3. **Nomor HP** tiap akun Telegram yang akan dipakai

---

## 🚀 STEP BY STEP

### STEP 1 — Upload file ke VPS

Upload file di atas ke `/root/telegram-bot/`, lalu:

```bash
mkdir -p /root/telegram-bot/instances
```

### STEP 2 — Install Python + dependency (sekali saja)

```bash
apt update && apt install -y python3 python3-pip
pip3 install telethon
```

> Ubuntu 24.04+ error `externally-managed-environment`?
> Jalankan: `pip3 install --break-system-packages telethon`

### STEP 3 — Edit config akun 1

```bash
cd /root/telegram-bot
nano instances/akun1.json
```

Isi 2 baris dengan API milik Anda:
```json
"api_id": "ISI_API_ID",
"api_hash": "ISI_API_HASH",
```
Simpan: `Ctrl+X` → `Y` → `Enter`.

### STEP 4 — Login akun (sekali saja, membuat session baru)

```bash
python3 bot.py --instance akun1 --login
```

Ikuti prompt:
```
Please enter your phone number:      → nomor HP akun 1
Please enter the code you received:  → kode dari Telegram
Please enter your password:          → password 2FA (jika ada)
```
✅ Selesai → file `akun1.session` terbentuk otomatis.
**Perintah ini TIDAK mengirim pesan apa pun.**

### STEP 5 — Pilih grup

```bash
python3 bot.py --instance akun1 --pilih-grup
```

Tampilan:
```
Daftar Grup Tersedia (✔ = sedang dipilih di config):
  [1]   Grup Contoh A (Supergroup)  ID:1315686104
  [2]   Grup Contoh B (Supergroup)  ID:1821780300
  [3]   Grup Contoh C (Group)       ID:2011035622
Pilih grup (nomor pisahkan koma, kosong = batal): 1,2,3
```
→ Ketik nomor (pisah koma) → `Enter` → otomatis tersimpan.
**Perintah ini juga TIDAK mengirim pesan apa pun.**

### STEP 6 — Test kirim (1 siklus, lalu berhenti)

```bash
python3 bot.py --instance akun1 --test
```

Cek log, harus ada baris:
```
[OK] Teririm (teks) ke Grup Contoh A
[OK] Teririm (teks) ke Grup Contoh B
```
✅ Kalau baris `[OK]` muncul = pesan benar-benar terkirim.

> 💡 **Penting — pesan dari Saved Messages:**
> Config default `"pesan_dari_saved": true` = pesan diambil dari **pesan TERAKHIR
> di Saved Messages** Anda. **Pastikan sudah ada pesan di Saved Messages** sebelum test,
> kalau kosong akan muncul error `Pesan kosong`.

### STEP 7 — Jalankan otomatis 24/7 (PM2)

```bash
apt install -y npm && npm install -g pm2
cd /root/telegram-bot
pm2 start ecosystem.config.js     # jalankan SEMUA akun sekaligus
pm2 save                          # simpan daftar (ikut hidup saat reboot)
pm2 startup                       # auto-start saat VPS reboot (sekali saja)
```

> `pm2 startup` akan menampilkan perintah tambahan — **salin & jalankan** jika diminta.

### STEP 8 — Verifikasi

```bash
pm2 list
```
```
│ blast1 │ online │   ← akun1 aktif
│ blast2 │ online │   ← akun2 aktif
```
**`online` semua = SELESAI** ✅ Bot jalan terus-menerus tanpa perlu laptop/terminal terbuka.

---

## ➕ Menambah Akun Baru (ke-3, dst)

Ulangi 4 langkah ini saja:

```bash
# 1. Buat config baru
cd /root/telegram-bot
cp instances/akun1.json instances/akun3.json
nano instances/akun3.json        # hapus baris "_catatan", isi API, atur delay

# 2. Login (nomor HP akun baru)
python3 bot.py --instance akun3 --login

# 3. Pilih grup
python3 bot.py --instance akun3 --pilih-grup

# 4. Test
python3 bot.py --instance akun3 --test
```

**Daftarkan ke PM2** — edit `ecosystem.config.js`, tambah 1 entry (copy, ganti 2 baris):

```js
{ name: 'blast3', script: 'bot.py', interpreter: 'python3',
  args: '--instance akun3', cwd: '/root/telegram-bot',
  autorestart: true, restart_delay: 15000, max_restarts: 20, time: true },
```

Lalu muat ulang:
```bash
pm2 start blast3          # atau: pm2 restart ecosystem.config.js
pm2 save
```

---

## ⚙️ Daftar Semua Perintah `bot.py`

| Perintah | Kirim pesan? | Fungsi |
|---|---|---|
| `--login` | ❌ Tidak | Login sekali → buat session baru |
| `--pilih-grup` | ❌ Tidak | Pilih grup interaktif → simpan ke config |
| `--list-grup` | ❌ Tidak | Lihat semua grup + ID (✔ = terpilih) |
| `--test` | ✅ **Ya, 1 siklus** | Test kirim lalu berhenti |
| *(tanpa flag)* | ✅ Ya, terus-menerus | Blast permanen |

Ganti `akun1` dengan `akun2`, `akun3`, ... untuk akun lain.

---

## ⏱ Pengaturan Waktu (di `instances/akunN.json`)

| Field | Arti | Contoh |
|---|---|---|
| `delay` | Jeda **ANTAR SIKLUS** (detik) | `1800` = 30 menit |
| `jam` | Total durasi blast | `0` = selamanya, `720` = 30 hari |
| `delay_random` | Jeda acak (opsional, menimpa `delay`) | `[1500, 2100]` |

### Cara kerja 1 siklus (PENTING)

> **Semua grup dikirim SEKALIGUS (bersamaan), bukan antre 1 per 1.**
> `delay` hanya jeda sebelum **mengulang lagi** ke grup-grup yang sama.

Contoh: akun1 pilih **30 grup**, `delay: 1800` (30 menit):

```
00:00  →  🔫 30 grup SEKALIGUS
00:00  →  ⏳ tunggu 30 menit
00:30  →  🔫 30 grup SEKALIGUS
00:30  →  ⏳ tunggu 30 menit
          ... berulang terus (karena jam: 0)
```

---

## 📝 Pengaturan Pesan (di `instances/akunN.json`)

| Ingin | Setting |
|---|---|
| Pesan dari Saved Messages (pesan TERAKHIR) | `"pesan_dari_saved": true` |
| Pesan teks manual | `"pesan_dari_saved": false` + isi `"pesan"` |
| Footer setelah pesan | `"footer": "Teks promo..."` |
| Lampiran foto/video | `"media": "/root/foto.jpg"` |
| Forward pesan orang lain | `"mode": "forward"` + `"forward_link": "https://t.me/xxx/15"` |

**Ganti isi blast** = ubah pesan terakhir di Saved Messages → `pm2 restart blastN`

Setelah edit config apapun → **restart**:
```bash
pm2 restart blast1        # atau blast2, blast3...
```

---

## 🛡 Tips Anti-Ban (wajib baca untuk multi-akun)

1. **Delay beda tiap akun** — akun1: `30`, akun2: `45`, akun3: `60` (detik)
2. Pakai `"delay_random": [30, 60]` supaya tidak pola mekanis
3. Grup tiap akun **boleh beda** (pakai `--pilih-grup`)
4. Log ada `FLOOD_WAIT` → **stop**, naikkan delay, tunggu
5. **Jangan** jalankan 2 proses dengan session yang sama

---

## 📋 Perintah Harian PM2

```bash
pm2 list                # cek status semua akun
pm2 logs blast1         # log realtime akun1 (Ctrl+C keluar)
pm2 logs blast2         # log realtime akun2
pm2 restart blast1      # restart (setelah ubah config/pesan)
pm2 stop blast1         # jeda sementara
pm2 start blast1        # nyalakan lagi
```

---

## ❓ Troubleshooting

| Masalah | Solusi |
|---|---|
| `Session belum ada` | `python3 bot.py --instance akunN --login` |
| `Field "grup" kosong` | `python3 bot.py --instance akunN --pilih-grup` |
| `Pesan kosong` | Buat pesan di Saved Messages, ATAU isi `"pesan"` di config |
| Test sukses tapi pesan tidak ada | Lihat baris `[ERROR]` di log → cek alasan setelah `:` |
| `CHAT_WRITE_FORBIDDEN` | Akun bukan anggota / tidak ada izin kirim di grup |
| `FLOOD_WAIT N seconds` | Tunggu N detik, naikkan delay, jangan dipaksa |
| `PeerFloodError` | Akun kena blokir spam → STOP & istirahatkan akun |
| Grup tidak ditemukan | ID grup berubah → jalankan ulang `--pilih-grup` |
| Bot mati di pm2 | `pm2 logs blastN` → baca error |
| Pesan terkirim tapi dicek tidak ada | Pastikan cek grup dari **akun yang benar** (akun yang di-login) |
| `pm2` bilang sudah jalan | `pm2 delete blastN` lalu start ulang |

---

## ✅ Checklist Singkat (untuk akun baru)

```
[ ] 1. Buat file instances/akunN.json
[ ] 2. Isi api_id + api_hash
[ ] 3. python3 bot.py --instance akunN --login
[ ] 4. python3 bot.py --instance akunN --pilih-grup
[ ] 5. Buat pesan di Saved Messages
[ ] 6. python3 bot.py --instance akunN --test   → cek [OK]
[ ] 7. Tambah entry blastN di ecosystem.config.js
[ ] 8. pm2 start blastN && pm2 save
[ ] 9. pm2 list → status online
```
