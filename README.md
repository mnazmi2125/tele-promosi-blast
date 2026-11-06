# 🎛 Jaseb Blast Panel

Bot Telegram untuk **kirim pesan otomatis berulang ke banyak grup** — mendukung
**banyak akun sekaligus**, semuanya dikendalikan lewat **tombol di chat Telegram**.

## Fitur

- ✔ Panel tombol di Telegram: akun, grup, pesan, delay, MULAI/STOP, status
- ✔ Multi-akun — blast bersamaan, kontrol terpusat
- ✔ Tambah akun (login) langsung dari chat — file & session dibuat otomatis
- ✔ Pilih grup pakai tombol centang (tanpa ketik ID)
- ✔ Auto-restart, auto-start saat VPS reboot, notifikasi & laporan harian
- ✔ Anti-ban: delay beda per akun, delay acak, tangani FLOOD_WAIT

## Kebutuhan

- VPS Linux (Ubuntu/Debian) + akses root
- Python 3 + `pip install telethon`
- Token bot dari [@BotFather](https://t.me/BotFather) → lihat **[BOTFATHER.md](BOTFATHER.md)**
- ID Telegram admin → tanya [@userinfobot](https://t.me/userinfobot)

## Struktur file

```
├── bot.py               ← engine blast
├── panel.py             ← panel kontrol (yang dijalankan)
├── panel.json           ← konfigurasi (token bot, admin)
├── ecosystem.config.js  ← config PM2
├── instances/           ← setting tiap akun (dibuat otomatis)
└── jasebvps.md          ← panduan lengkap
```

## Setup (sekali saja)

**1. Upload file** ke `/root/telegram-bot/` di VPS

**2. Install**
```bash
apt update && apt install -y python3 python3-pip npm
pip3 install telethon
npm install -g pm2
```

**3. Edit `panel.json`**
```json
{
  "bot_token": "TOKEN_DARI_BOTFATHER",
  "admin_ids": [ID_TELEGRAM_ANDA],
  "api_id": "DARI_MY.TELEGRAM.ORG",
  "api_hash": "DARI_MY.TELEGRAM.ORG"
}
```

**4. Test**
```bash
cd /root/telegram-bot
python3 panel.py
```
Lalu buka bot di Telegram → `/start` → menu muncul 🎛

**5. Jalankan 24/7**
```bash
pm2 start ecosystem.config.js
pm2 save
pm2 startup
```

## Cara pakai (dari chat Telegram)

| Tombol | Fungsi |
|---|---|
| ➕ Tambah Akun | Login akun baru: nomor → kode → 2FA |
| ▸ Grup | Centang grup tujuan → 💾 Simpan |
| ▸ Pesan | Saved Messages / teks manual / forward + footer |
| ▸ Delay & Durasi | Jeda antar kirim + lama berjalan |
| ▶ MULAI / ⏹ STOP | Jalankan / hentikan blast |
| 📊 Status | Statistik siklus & pengiriman |

**Urutan pertama kali:**
```
➕ Tambah Akun → login → Pilih Grup → centang → Simpan
→ ▸ Pesan (buat pesan di Saved Messages akun tsb)
→ ▶ MULAI → konfirmasi ✅
```

## Ganti isi blast

Kirim/edit **pesan terakhir di Saved Messages** akun → restart akun dari panel
(atau STOP lalu MULAI lagi).

## Troubleshooting

| Masalah | Solusi |
|---|---|
| Notifikasi gagal / "input entity" | Chat bot dulu: `/start` |
| "Grup belum dipilih" | Menu ▸ Grup → centang → Simpan |
| "Pesan kosong" | Buat pesan di Saved Messages akun |
| Kena FLOOD_WAIT | STOP, naikkan delay, tunggu |
| Bot mati | `pm2 logs panel` |

## ⚠️ Catatan

- Gunakan dengan bertanggung jawab — blast agresif = risiko akun diblokir Telegram
- Atur **delay beda tiap akun** dan grup tidak 100% sama
- `panel.json` & `*.session` = **RAHASIA** (akses penuh ke akun) — jangan dibagikan
