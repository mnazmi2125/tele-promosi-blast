# 🤖 Panduan @BotFather (buat bot & token)

Langkah membuat bot kontrol — sekitar 2 menit.

## 1. Buat bot

1. Buka Telegram → cari **[@BotFather](https://t.me/BotFather)** → kirim `/newbot`
2. **Nama tampilan** (bebas): `Jaseb Panel`
3. **Username** (unik, wajib diakhiri `bot`): misal `jaseb_panel_888_bot`
4. BotFather balas **token** — salin, contoh:
   ```
   8123456789:AAF4xYz-abcDEF_ghiJKL
   ```

→ Tempelkan ke `panel.json` field `"bot_token"`.

## 2. Ambil ID admin Anda

Chat **[@userinfobot](https://t.me/userinfobot)** → dia balas ID Anda (angka) →
masukkan ke `panel.json` field `"admin_ids"`.

> Boleh lebih dari 1: `"admin_ids": [123, 456]`

## 3. Perintah penting BotFather

| Perintah | Fungsi |
|---|---|
| `/newbot` | Buat bot baru |
| `/mybots` | Daftar bot Anda |
| `/revoke` | **Ganti token** (jika token bocor) |
| `/setdescription` | Deskripsi bot |
| `/setuserpic` | Foto profil bot |

## ⚠️ Keamanan token

- Token = **kunci kontrol bot** — jangan dibagikan ke siapa pun
- Bocor? langsung `/revoke` di BotFather → token baru → update `panel.json` → restart panel
- Lupa ID admin? tanya [@userinfobot](https://t.me/userinfobot)
