#!/usr/bin/env python3
"""
panel.py - Panel kontrol Telegram (tombol) + engine blast multi-akun dalam 1 proses.

Setup:
  1. Buat bot di @BotFather -> isi "bot_token" di panel.json
  2. Isi "admin_ids" (ID Telegram Anda, bisa lebih dari 1) -> tanya @userinfobot
  3. Jalankan: python3 panel.py   (atau lewat PM2, app "panel")

Fitur: pilih akun, pilih grup (tombol centang), atur pesan, delay & durasi,
MULAI/STOP, status, tambah akun (login dari chat), notifikasi & laporan harian.
"""

import asyncio
import json
import os
import re
import sys
from datetime import datetime, timedelta

from telethon import TelegramClient, Button, events
from telethon.errors import (
    ApiIdInvalidError,
    FloodWaitError,
    PasswordHashInvalidError,
    PhoneCodeInvalidError,
    PhoneNumberInvalidError,
    SessionPasswordNeededError,
)

from bot import (
    BASE_DIR, INSTANCES_DIR, log, path_instance, terapkan_default, save_instance,
    resolve_groups, siapkan_pesan, loop_kirim, hitung_delay,
    parse_telegram_link, tipe_grup,
)

PANEL_FILE = os.path.join(BASE_DIR, 'panel.json')
MEDIA_DIR = os.path.join(BASE_DIR, 'media')
PER_HALAMAN = 20

PANEL = {}
ADMIN_IDS = []
BOT = None
AKUN = {}   # nama -> {task, client, siklus, kirim, terakhir, hasil, next}
STATE = {}  # uid -> {akun, flow, tahap, nama, phone, client, grup_list, terpilih, halaman, info}


# ────────────────────────── util instance/akun ──────────────────────────

def daftar_akun():
    if not os.path.isdir(INSTANCES_DIR):
        return []
    return sorted(
        os.path.splitext(f)[0] for f in os.listdir(INSTANCES_DIR)
        if f.endswith('.json') and not f.startswith('_')
    )


def baca(nama):
    with open(path_instance(nama), 'r') as f:
        cfg = json.load(f)
    return terapkan_default(cfg, nama)


def entri_akun(nama):
    if nama not in AKUN:
        AKUN[nama] = {'task': None, 'client': None, 'siklus': 0,
                      'kirim': 0, 'terakhir': '-', 'hasil': '-', 'next': None}
    return AKUN[nama]


def berjalan(nama):
    t = AKUN.get(nama, {}).get('task')
    return t is not None and not t.done()


def st_uid(uid):
    if uid not in STATE:
        STATE[uid] = {'akun': daftar_akun()[0] if daftar_akun() else None}
    return STATE[uid]


def akun_aktif(uid):
    st = st_uid(uid)
    if not st.get('akun') or st['akun'] not in daftar_akun():
        daftar = daftar_akun()
        st['akun'] = daftar[0] if daftar else None
    return st.get('akun')


def ambil_info(uid):
    return st_uid(uid).pop('info', None)


def txt_delay(cfg):
    d = int(cfg.get('delay', 30))
    return f'{d} detik' if d < 60 else f'{d // 60} menit'


def txt_durasi(cfg):
    j = float(cfg.get('jam', 0) or 0)
    return 'selamanya' if j <= 0 else f'{j:g} jam'


def txt_preview(cfg):
    if cfg['mode'] == 'forward':
        return f'Forward: {cfg.get("forward_link") or "-"}'
    if cfg.get('pesan_dari_saved'):
        return 'Pesan dari Saved Messages (pesan terakhir akun ini)'
    isi = cfg.get('pesan') or ''
    if cfg.get('media'):
        isi = (isi + f'\n[media: {os.path.basename(cfg["media"])}]').strip()
    isi = isi or '(kosong)'
    return isi[:200] + ('...' if len(isi) > 200 else '')


def mode_label(cfg):
    if cfg['mode'] == 'forward':
        return '🔗 Forward link'
    return '📄 Saved Messages' if cfg.get('pesan_dari_saved') else '✍️ Teks manual'


async def notif(teks):
    for uid in ADMIN_IDS:
        try:
            await BOT.send_message(uid, teks)
        except Exception as e:
            log('WARN', f'Gagal notif ke {uid}: {e}')


# ────────────────────────── client & engine ──────────────────────────

def path_session(cfg, nama):
    s = cfg.get('session', nama)
    if not os.path.isabs(s):
        s = os.path.join(BASE_DIR, s)
    return s


async def dapatkan_client(nama):
    st = entri_akun(nama)
    c = st.get('client')
    if c and c.is_connected():
        return c
    cfg = baca(nama)
    s = path_session(cfg, nama)
    if not os.path.exists(s + '.session'):
        raise RuntimeError('Session belum ada. Login dulu via menu ➕ Tambah Akun.')
    c = TelegramClient(s, int(cfg['api_id']), str(cfg['api_hash']))
    await c.connect()
    if not await c.is_user_authorized():
        await c.disconnect()
        raise RuntimeError('Session tidak valid — hapus file session lalu login ulang via ➕ Tambah Akun.')
    st['client'] = c
    return c


async def mulai_blast(nama):
    if berjalan(nama):
        return False, f'{nama} sudah berjalan.'
    cfg = baca(nama)
    if not cfg.get('grup'):
        return False, 'Grup belum dipilih.'
    client = await dapatkan_client(nama)
    groups = await resolve_groups(client, cfg['grup'])
    if not groups:
        return False, 'Tidak ada grup valid (cek menu Grup).'
    try:
        pesan, forward = await siapkan_pesan(client, cfg)
    except ValueError as e:
        return False, str(e)
    st = entri_akun(nama)
    st.update({'siklus': 0, 'kirim': 0, 'terakhir': '-', 'hasil': '-', 'next': None})
    cfg['running'] = True
    save_instance(nama, cfg)
    st['task'] = asyncio.create_task(jalankan_engine(nama, client, groups, pesan, cfg, forward))
    return True, f'🚀 Blast {nama} dimulai ({len(groups)} grup).'


def hentikan(nama):
    st = entri_akun(nama)
    t = st.get('task')
    if t and not t.done():
        t.cancel()
        try:
            cfg = baca(nama)
            cfg['running'] = False
            save_instance(nama, cfg)
        except Exception:
            pass
        return True
    return False


async def jalankan_engine(nama, client, groups, pesan, cfg, forward):
    st = entri_akun(nama)

    def on_cycle(siklus, ok, total):
        st['siklus'] = siklus
        st['kirim'] += ok
        st['terakhir'] = datetime.now().strftime('%H:%M')
        st['hasil'] = f'{ok}/{total}'
        try:
            st['next'] = datetime.now() + timedelta(seconds=hitung_delay(cfg))
        except Exception:
            st['next'] = None

    try:
        await loop_kirim(client, groups, pesan, cfg, forward, on_cycle=on_cycle)
        await notif(f'⏰ Blast {nama} selesai (sesuai durasi).')
    except asyncio.CancelledError:
        await notif(f'⏹ Blast {nama} dihentikan.')
    except Exception as e:
        log('ERROR', f'Engine {nama} error: {e}')
        await notif(f'⚠️ {nama} error: {e}')
    finally:
        st['task'] = None
        try:
            c = baca(nama)
            c['running'] = False
            save_instance(nama, c)
        except Exception:
            pass


async def resume_berjalan():
    for nama in daftar_akun():
        try:
            if baca(nama).get('running'):
                ok, msg = await mulai_blast(nama)
                await notif(msg if ok else f'⚠️ Resume {nama} gagal: {msg}')
        except Exception as e:
            log('ERROR', f'Resume {nama} gagal: {e}')
            await notif(f'⚠️ Resume {nama} gagal: {e}')


# ────────────────────────── layar / tombol ──────────────────────────

def layar_utama(uid):
    nama = akun_aktif(uid)
    if not nama:
        return ('🎛 PANEL KONTROL BLAST\n\nBelum ada akun. Tap ➕ Tambah Akun untuk login akun pertama.',
                [[Button.inline('➕ Tambah Akun', b'tambah:mulai')]])
    info = ambil_info(uid)
    status = '🟢 Berjalan' if berjalan(nama) else '⏹ Berhenti'
    teks = f'🎛 PANEL KONTROL BLAST\n\nAkun aktif: {nama}\nStatus: {status}'
    if info:
        teks += f'\nℹ️ {info}'
    aksi = Button.inline('⏹ STOP', b'main:stop') if berjalan(nama) else Button.inline('▶ MULAI', b'main:open')
    tomb = [
        [Button.inline('▸ Akun', b'akun:list'), Button.inline('▸ Grup', b'grup:open')],
        [Button.inline('▸ Pesan', b'pesan:open'), Button.inline('▸ Delay & Durasi', b'delay:open')],
        [aksi, Button.inline('📊 Status', b'status')],
        [Button.inline('➕ Tambah Akun', b'tambah:mulai')],
    ]
    return teks, tomb


def layar_akun(uid):
    daftar = daftar_akun()
    if not daftar:
        return ('Belum ada akun. Tap ➕ Tambah Akun.',
                [[Button.inline('➕ Tambah Akun', b'tambah:mulai')],
                 [Button.inline('◀ Kembali', b'utama')]])
    teks = 'PILIH AKUN:\n● = sedang berjalan'
    tomb = [[Button.inline(f'{"●" if berjalan(n) else "○"} {n}', f'akun:pilih:{n}'.encode())]
            for n in daftar]
    tomb.append([Button.inline('◀ Kembali', b'utama')])
    return teks, tomb


def layar_grup(uid):
    st = st_uid(uid)
    nama = st.get('akun')
    lst = st.get('grup_list', [])
    sel = st.get('terpilih', set())
    total_hal = max(1, (len(lst) + PER_HALAMAN - 1) // PER_HALAMAN)
    hal = st['halaman'] = min(st.get('halaman', 0), total_hal - 1)
    info = ambil_info(uid)
    teks = f'GRUP — {nama}: {len(sel)} dipilih dari {len(lst)}\n✔ = terpilih'
    if info:
        teks += f'\nℹ️ {info}'
    tomb = []
    halaman = lst[hal * PER_HALAMAN:(hal + 1) * PER_HALAMAN]
    for i in range(0, len(halaman), 2):
        baris = []
        for gid, gnama, _tipe in halaman[i:i + 2]:
            label = ('✔ ' if gid in sel else '▫️ ') + (gnama or '(tanpa nama)')[:16]
            baris.append(Button.inline(label, f'grup:tgl:{gid}'.encode()))
        tomb.append(baris)
    if total_hal > 1:
        nav = []
        if hal > 0:
            nav.append(Button.inline('◀', b'grup:nav:-1'))
        nav.append(Button.inline(f'{hal + 1}/{total_hal}', b'grup:nav:0'))
        if hal < total_hal - 1:
            nav.append(Button.inline('▶', b'grup:nav:1'))
        tomb.append(nav)
    tomb.append([Button.inline(f'💾 Simpan ({len(sel)})', b'grup:simpan'),
                 Button.inline('⟳ Muat Ulang', b'grup:muat')])
    tomb.append([Button.inline('◀ Kembali', b'utama')])
    return teks, tomb


def layar_pesan(uid):
    nama = akun_aktif(uid)
    cfg = baca(nama)
    info = ambil_info(uid)
    teks = f'PESAN — {nama}\nMode: {mode_label(cfg)}\n\nIsi:\n{txt_preview(cfg)}'
    if cfg.get('footer'):
        teks += f'\n\nFooter: {cfg["footer"]}'
    if info:
        teks += f'\nℹ️ {info}'
    tanda = lambda aktif: '✔ ' if aktif else '▫️ '
    tomb = [[
        Button.inline(tanda(cfg['mode'] != 'forward' and cfg.get('pesan_dari_saved')) + 'Saved Messages',
                      b'pesan:mode:saved'),
        Button.inline(tanda(cfg['mode'] != 'forward' and not cfg.get('pesan_dari_saved')) + 'Teks manual',
                      b'pesan:mode:manual'),
    ], [
        Button.inline(tanda(cfg['mode'] == 'forward') + 'Forward link', b'pesan:mode:forward'),
    ]]
    if cfg['mode'] == 'forward':
        tomb.append([Button.inline('🔗 Ganti Link', b'pesan:link')])
    else:
        tomb.append([Button.inline('📝 Ganti Pesan', b'pesan:ganti'),
                     Button.inline('⌨ Footer', b'pesan:footer')])
    tomb.append([Button.inline('◀ Kembali', b'utama')])
    return teks, tomb


def layar_delay(uid):
    nama = akun_aktif(uid)
    cfg = baca(nama)
    info = ambil_info(uid)
    teks = f'PENGATURAN — {nama}\n\nDelay antar siklus: {txt_delay(cfg)}\nDurasi: {txt_durasi(cfg)}'
    if cfg.get('delay_random'):
        teks += f'\n(delay acak {cfg["delay_random"]} menit aktif — di-set via JSON)'
    if info:
        teks += f'\nℹ️ {info}'
    tomb = [
        [Button.inline('30 mnt', b'delay:set:30'), Button.inline('45 mnt', b'delay:set:45'),
         Button.inline('60 mnt', b'delay:set:60')],
        [Button.inline('⌨ Custom (menit)', b'delay:custom')],
        [Button.inline('∞ Selamanya', b'durasi:set:0'), Button.inline('24 jam', b'durasi:set:24'),
         Button.inline('30 hari', b'durasi:set:720')],
        [Button.inline('◀ Kembali', b'utama')],
    ]
    return teks, tomb


def layar_konfirmasi(uid):
    nama = akun_aktif(uid)
    cfg = baca(nama)
    n_grup = len(cfg.get('grup', []))
    teks = (f'▶ MULAI BLAST — {nama}\n\n'
            f'Grup  : {n_grup} grup\n'
            f'Delay : {txt_delay(cfg)}\n'
            f'Durasi: {txt_durasi(cfg)}\n'
            f'Pesan : {txt_preview(cfg)}')
    return (teks, [[Button.inline('✅ Ya, Mulai', b'main:ya'), Button.inline('❌ Batal', b'main:batal')]])


def layar_status(uid):
    info = ambil_info(uid)
    teks = '📊 STATUS'
    if info:
        teks += f'\nℹ️ {info}'
    for nama in daftar_akun():
        st = AKUN.get(nama) or {}
        if berjalan(nama):
            baris = (f'\n\n🟢 {nama}\n   Siklus #{st["siklus"]} | terakhir {st["hasil"]} @ {st["terakhir"]}'
                     f'\n   Total terkirim: {st["kirim"]}')
            if st.get('next'):
                baris += f'\n   Siklus berikutnya ~ {st["next"].strftime("%H:%M")}'
        else:
            baris = f'\n\n⏹ {nama}: berhenti'
        teks += baris
    return (teks, [[Button.inline('◀ Kembali', b'utama')]])


def terkunci(nama):
    return berjalan(nama)


# ────────────────────────── tambah akun (login dari chat) ──────────────────────────

def nama_akun_baru():
    ada = set(daftar_akun())
    n = 1
    while f'akun{n}' in ada:
        n += 1
    return f'akun{n}'


async def proses_login(uid, ev, text, st):
    tahap = st.get('tahap')
    if tahap == 'phone':
        phone = text.strip()
        if not phone.startswith('+'):
            await ev.respond('❌ Format nomor harus diawali + (contoh: +62812xxxx).\nKetik ulang nomornya:')
            return
        phone = re.sub(r'[^0-9+]', '', phone)
        try:
            client = TelegramClient(os.path.join(BASE_DIR, st['nama']),
                                    int(PANEL['api_id']), str(PANEL['api_hash']))
            await client.connect()
            await client.send_code_request(phone)
            st['client'] = client
            st['phone'] = phone
            st['tahap'] = 'code'
            await ev.respond('📨 Kode verifikasi sudah dikirim ke akun Telegram tersebut.\nKetik kodenya:')
        except PhoneNumberInvalidError:
            await ev.respond('❌ Nomor tidak valid. Ketik ulang:')
        except FloodWaitError as e:
            await ev.respond(f'⏳ Telegram minta tunggu {e.seconds} detik. Ketik nomor lagi nanti.')
        except ApiIdInvalidError:
            await ev.respond('❌ api_id/api_hash di panel.json salah.')
        except Exception as e:
            await ev.respond(f'❌ Gagal: {e}')
    elif tahap == 'code':
        try:
            await st['client'].sign_in(phone=st['phone'], code=text.strip())
            await selesaikan_login(uid, ev, st)
        except SessionPasswordNeededError:
            st['tahap'] = 'password'
            await ev.respond('🔐 Akun ini pakai 2FA. Ketik password-nya:')
        except PhoneCodeInvalidError:
            await ev.respond('❌ Kode salah. Ketik ulang:')
        except Exception as e:
            await ev.respond(f'❌ Gagal: {e}')
    elif tahap == 'password':
        try:
            await st['client'].sign_in(password=text)
            await selesaikan_login(uid, ev, st)
        except PasswordHashInvalidError:
            await ev.respond('❌ Password salah. Ketik ulang:')
        except Exception as e:
            await ev.respond(f'❌ Gagal: {e}')


async def selesaikan_login(uid, ev, st):
    nama = st['nama']
    try:
        await st['client'].disconnect()
    except Exception:
        pass
    cfg = terapkan_default({
        'api_id': PANEL['api_id'], 'api_hash': PANEL['api_hash'],
        'delay': 30, 'jam': 0, 'grup': [], 'running': False,
        'telepon': st.get('phone', ''),
    }, nama)
    save_instance(nama, cfg)
    entri_akun(nama)
    st.update({'flow': None, 'tahap': None, 'client': None, 'akun': nama})
    await ev.respond(
        f'✅ Akun {nama} berhasil ditambahkan!',
        buttons=[[Button.inline(f'📥 Pilih Grup {nama}', b'grup:open')],
                 [Button.inline('◀ Menu Utama', b'utama')]],
    )


# ────────────────────────── input teks (flow) ──────────────────────────

async def proses_input(uid, ev, text):
    st = st_uid(uid)
    flow = st.get('flow')

    if flow == 'login':
        await proses_login(uid, ev, text, st)
        return

    nama = akun_aktif(uid)
    if not nama:
        st['flow'] = None
        await ev.respond('❌ Tidak ada akun aktif.')
        return
    if terkunci(nama):
        st['flow'] = None
        await ev.respond(f'⛔ {nama} sedang berjalan — STOP dulu untuk ubah pengaturan.')
        return

    if flow == 'pesan':
        cfg = baca(nama)
        media_path = None
        if ev.message.media:
            try:
                media_path = await BOT.download_media(ev.message, file=MEDIA_DIR)
            except Exception as e:
                await ev.respond(f'⚠️ Gagal simpan media: {e}')
        if not text and not media_path:
            await ev.respond('❌ Kosong. Kirim teks atau foto/video sebagai pesan blast:')
            return
        if text:
            cfg['pesan'] = text
        if media_path:
            cfg['media'] = media_path
        cfg['pesan_dari_saved'] = False
        cfg['mode'] = 'teks'
        save_instance(nama, cfg)
        st['flow'] = None
        teks, tomb = layar_pesan(uid)
        await ev.respond('✅ Pesan disimpan.', buttons=tomb)
        await ev.respond(teks, buttons=tomb)
        return

    if flow == 'link':
        peer, mid = parse_telegram_link(text)
        if peer is None:
            await ev.respond('❌ Link tidak valid. Contoh: https://t.me/namachannel/123')
            return
        cfg = baca(nama)
        cfg['forward_link'] = text
        cfg['mode'] = 'forward'
        save_instance(nama, cfg)
        st['flow'] = None
        teks, tomb = layar_pesan(uid)
        await ev.respond('✅ Link forward disimpan.', buttons=tomb)
        await ev.respond(teks, buttons=tomb)
        return

    if flow == 'footer':
        cfg = baca(nama)
        cfg['footer'] = '' if text == '-' else text
        save_instance(nama, cfg)
        st['flow'] = None
        teks, tomb = layar_pesan(uid)
        await ev.respond('✅ Footer disimpan.' if text != '-' else '✅ Footer dihapus.', buttons=tomb)
        await ev.respond(teks, buttons=tomb)
        return

    if flow == 'delay':
        angka = re.sub(r'[^0-9]', '', text)
        if not angka or not 1 <= int(angka) <= 10080:
            await ev.respond('❌ Masukkan angka menit (1–10080):')
            return
        cfg = baca(nama)
        cfg['delay'] = int(angka) * 60
        cfg.pop('delay_random', None)
        save_instance(nama, cfg)
        st['flow'] = None
        teks, tomb = layar_delay(uid)
        await ev.respond(f'✅ Delay: {angka} menit.', buttons=tomb)
        await ev.respond(teks, buttons=tomb)
        return

    st['flow'] = None


# ────────────────────────── handler tombol ──────────────────────────

async def tangani_klik(uid, data):
    st = st_uid(uid)
    parts = data.split(':')
    cmd = parts[0]
    nama = akun_aktif(uid)

    if cmd == 'utama':
        st['flow'] = None
        return layar_utama(uid)

    if cmd == 'status':
        return layar_status(uid)

    # ── akun ──
    if cmd == 'akun' and parts[1] == 'list':
        return layar_akun(uid)
    if cmd == 'akun' and parts[1] == 'pilih':
        st['akun'] = parts[2]
        st['info'] = f'Akun aktif: {parts[2]}'
        return layar_utama(uid)

    # ── grup ──
    if cmd == 'grup':
        if parts[1] == 'open':
            if not nama:
                return ('Belum ada akun.', [[Button.inline('➕ Tambah Akun', b'tambah:mulai')]])
            if terkunci(nama):
                st['info'] = f'⛔ {nama} sedang berjalan — STOP dulu.'
                return layar_utama(uid)
            try:
                client = await dapatkan_client(nama)
                dialogs = await client.get_dialogs()
            except Exception as e:
                return (f'❌ {e}', [[Button.inline('◀ Kembali', b'utama')]])
            grup = [(d.entity.id, d.name or '(tanpa nama)', tipe_grup(d.entity))
                    for d in dialogs if d.is_group]
            if not grup:
                return ('❌ Tidak ada grup di akun ini.',
                        [[Button.inline('◀ Kembali', b'utama')]])
            st.update({'flow': None, 'grup_list': grup,
                       'terpilih': set(baca(nama).get('grup', [])), 'halaman': 0})
            return layar_grup(uid)
        if parts[1] == 'tgl':
            gid = int(parts[2])
            sel = st.setdefault('terpilih', set())
            if gid in sel:
                sel.discard(gid)
            else:
                sel.add(gid)
            return layar_grup(uid)
        if parts[1] == 'nav':
            if parts[2] != '0':
                st['halaman'] = max(0, st.get('halaman', 0) + int(parts[2]))
            return layar_grup(uid)
        if parts[1] == 'simpan':
            sel = st.get('terpilih', set())
            cfg = baca(nama)
            cfg['grup'] = sorted(sel)
            save_instance(nama, cfg)
            st['info'] = f'✅ {len(sel)} grup tersimpan'
            return layar_grup(uid)
        if parts[1] == 'muat':
            return await tangani_klik(uid, 'grup:open')

    # ── pesan ──
    if cmd == 'pesan':
        if parts[1] == 'open':
            if not nama:
                return ('Belum ada akun.', [[Button.inline('➕ Tambah Akun', b'tambah:mulai')]])
            if terkunci(nama):
                st['info'] = f'⛔ {nama} sedang berjalan — STOP dulu.'
                return layar_utama(uid)
            return layar_pesan(uid)
        if parts[1] == 'mode':
            if terkunci(nama):
                st['info'] = f'⛔ {nama} sedang berjalan — STOP dulu.'
                return layar_utama(uid)
            mode = parts[2]
            cfg = baca(nama)
            if mode == 'saved':
                cfg['mode'] = 'teks'
                cfg['pesan_dari_saved'] = True
            elif mode == 'manual':
                cfg['mode'] = 'teks'
                cfg['pesan_dari_saved'] = False
            else:
                cfg['mode'] = 'forward'
            save_instance(nama, cfg)
            return layar_pesan(uid)
        if parts[1] == 'ganti':
            st['flow'] = 'pesan'
            return ('Kirim pesan blast SEKARANG (teks, foto, atau video) ke chat ini:',
                    [[Button.inline('❌ Batal', b'pesan:open')]])
        if parts[1] == 'link':
            st['flow'] = 'link'
            return ('Kirim link pesan yang akan di-forward:\nContoh: https://t.me/namachannel/123',
                    [[Button.inline('❌ Batal', b'pesan:open')]])
        if parts[1] == 'footer':
            st['flow'] = 'footer'
            return ('Kirim footer (teks tambahan setelah pesan).\nKirim "-" untuk menghapus footer:',
                    [[Button.inline('❌ Batal', b'pesan:open')]])

    # ── delay & durasi ──
    if cmd == 'delay':
        if parts[1] == 'open':
            if not nama:
                return ('Belum ada akun.', [[Button.inline('➕ Tambah Akun', b'tambah:mulai')]])
            if terkunci(nama):
                st['info'] = f'⛔ {nama} sedang berjalan — STOP dulu.'
                return layar_utama(uid)
            return layar_delay(uid)
        if parts[1] == 'set':
            if terkunci(nama):
                st['info'] = f'⛔ {nama} sedang berjalan — STOP dulu.'
                return layar_utama(uid)
            cfg = baca(nama)
            cfg['delay'] = int(parts[2]) * 60
            cfg.pop('delay_random', None)
            save_instance(nama, cfg)
            st['info'] = f'Delay: {parts[2]} menit'
            return layar_delay(uid)
        if parts[1] == 'custom':
            st['flow'] = 'delay'
            return ('Kirim delay dalam MENIT (contoh: 45):',
                    [[Button.inline('❌ Batal', b'delay:open')]])
    if cmd == 'durasi' and parts[1] == 'set':
        if terkunci(nama):
            st['info'] = f'⛔ {nama} sedang berjalan — STOP dulu.'
            return layar_utama(uid)
        cfg = baca(nama)
        cfg['jam'] = int(parts[2])
        save_instance(nama, cfg)
        st['info'] = 'Durasi: ' + ('selamanya' if int(parts[2]) == 0 else f'{parts[2]} jam')
        return layar_delay(uid)

    # ── mulai / stop ──
    if cmd == 'main':
        if parts[1] == 'open':
            if not nama:
                return ('Belum ada akun.', [[Button.inline('➕ Tambah Akun', b'tambah:mulai')]])
            cfg = baca(nama)
            if not cfg.get('grup'):
                st['info'] = 'Grup belum dipilih — pilih dulu via ▸ Grup.'
                return layar_utama(uid)
            return layar_konfirmasi(uid)
        if parts[1] == 'ya':
            try:
                ok, msg = await mulai_blast(nama)
            except Exception as e:
                ok, msg = False, str(e)
            st['info'] = msg
            return layar_utama(uid)
        if parts[1] == 'stop':
            if hentikan(nama):
                st['info'] = '⏹ Menghentikan...'
            else:
                st['info'] = f'{nama} tidak sedang berjalan.'
            return layar_utama(uid)
        if parts[1] == 'batal':
            st['info'] = 'Dibatalkan.'
            return layar_utama(uid)

    # ── tambah akun ──
    if cmd == 'tambah':
        if parts[1] == 'mulai':
            st.update({'flow': 'login', 'tahap': 'phone', 'nama': nama_akun_baru()})
            return (f'➕ TAMBAH AKUN — akan dibuat sebagai "{st["nama"]}"\n\n'
                    'Ketik nomor HP akun Telegram baru\n(format +628xxxx, kode dikirim ke akun itu):',
                    [[Button.inline('❌ Batal', b'tambah:batal')]])
        if parts[1] == 'batal':
            if st.get('client'):
                try:
                    await st['client'].disconnect()
                except Exception:
                    pass
            st.update({'flow': None, 'tahap': None, 'client': None})
            return layar_utama(uid)

    return layar_utama(uid)


async def on_klik(ev):
    uid = ev.sender_id
    if uid not in ADMIN_IDS:
        try:
            await ev.answer('⛔ Anda bukan admin.', alert=True)
        except Exception:
            pass
        return
    try:
        hasil = await tangani_klik(uid, ev.data.decode())
    except Exception as e:
        log('ERROR', f'Klik {ev.data!r} error: {e}')
        hasil = (f'⚠️ Error: {e}', [[Button.inline('◀ Menu Utama', b'utama')]])
    try:
        await ev.answer()
    except Exception:
        pass
    if hasil:
        teks, tomb = hasil
        try:
            await ev.edit(teks, buttons=tomb)
        except Exception:
            try:
                await ev.delete()
            except Exception:
                pass
            try:
                await ev.respond(teks, buttons=tomb)
            except Exception:
                pass


async def on_pesan(ev):
    if ev.out:
        return
    uid = ev.sender_id
    if uid not in ADMIN_IDS:
        if ev.is_private:
            try:
                await ev.respond('⛔ Anda bukan admin panel ini.')
            except Exception:
                pass
        return
    text = (ev.raw_text or '').strip()
    if text in ('/start', '/menu'):
        STATE[uid] = {'akun': akun_aktif(uid)}
        teks, tomb = layar_utama(uid)
        await ev.respond(teks, buttons=tomb)
        return
    st = st_uid(uid)
    if not st.get('flow'):
        return
    await proses_input(uid, ev, text)


# ────────────────────────── laporan harian ──────────────────────────

async def laporan_harian():
    while True:
        now = datetime.now()
        target = now.replace(hour=8, minute=0, second=0, microsecond=0)
        if target <= now:
            target += timedelta(days=1)
        await asyncio.sleep((target - now).total_seconds())
        baris = ['📈 LAPORAN HARIAN']
        for nama in daftar_akun():
            st = AKUN.get(nama) or {}
            baris.append(f'{nama}: {st.get("kirim", 0)} pesan ({st.get("siklus", 0)} siklus terakhir)')
            st['kirim'] = 0
        try:
            await notif('\n'.join(baris))
        except Exception as e:
            log('WARN', f'Laporan harian gagal: {e}')


# ────────────────────────── main ──────────────────────────

def muat_config_panel():
    if not os.path.exists(PANEL_FILE):
        print('ERROR: file panel.json tidak ditemukan. Buat dulu (lihat contoh di repo).')
        sys.exit(1)
    with open(PANEL_FILE, 'r') as f:
        cfg = json.load(f)
    token = str(cfg.get('bot_token', '')).strip()
    if not token or 'GANTI' in token:
        print('ERROR: isi "bot_token" di panel.json (dapatkan dari @BotFather).')
        sys.exit(1)
    ids = cfg.get('admin_ids') or []
    if not ids:
        print('ERROR: isi "admin_ids" di panel.json (ID Telegram Anda — tanya @userinfobot).')
        sys.exit(1)
    if not cfg.get('api_id') or not cfg.get('api_hash'):
        print('ERROR: isi "api_id" & "api_hash" di panel.json (dari https://my.telegram.org).')
        sys.exit(1)
    cfg['bot_token'] = token
    cfg['admin_ids'] = [int(x) for x in ids]
    return cfg


async def main():
    global PANEL, ADMIN_IDS, BOT
    PANEL = muat_config_panel()
    ADMIN_IDS = PANEL['admin_ids']
    os.makedirs(MEDIA_DIR, exist_ok=True)
    os.makedirs(INSTANCES_DIR, exist_ok=True)

    for nama in daftar_akun():
        entri_akun(nama)

    BOT = TelegramClient(os.path.join(BASE_DIR, 'panel_bot'),
                         int(PANEL['api_id']), str(PANEL['api_hash']))
    await BOT.start(bot_token=PANEL['bot_token'])
    BOT.add_event_handler(on_klik, events.CallbackQuery())
    BOT.add_event_handler(on_pesan, events.NewMessage(incoming=True))

    me = await BOT.get_me()
    log('INFO', f'Panel aktif sebagai @{me.username or me.id} | admin: {ADMIN_IDS}')
    log('INFO', f'Akun terdeteksi: {daftar_akun() or "(belum ada)"}')

    await notif('🎛 Panel kontrol aktif.')
    await resume_berjalan()
    asyncio.create_task(laporan_harian())

    await BOT.run_until_disconnected()


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log('INFO', 'Panel dihentikan (Ctrl+C).')
