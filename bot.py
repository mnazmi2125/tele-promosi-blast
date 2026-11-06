#!/usr/bin/env python3
"""
bot.py - Telegram blast bot multi-instance (NON-INTERAKTIF)

Semua parameter dibaca dari file instances/<nama>.json
Session mengikuti field "session" di config (default: nama instance).

Penggunaan:
  python3 bot.py --instance akun1 --login       # sekali saja, login akun baru
  python3 bot.py --instance akun1 --pilih-grup  # pilih grup interaktif (seperti versi lama)
  python3 bot.py --instance akun1 --list-grup   # lihat daftar grup + ID
  python3 bot.py --instance akun1 --test        # kirim 1 siklus lalu keluar
  python3 bot.py --instance akun1               # jalan sesuai config
"""

import argparse
import asyncio
import json
import os
import random
import re
import sys
import time
from datetime import datetime

from telethon import TelegramClient
from telethon.errors import FloodWaitError
from telethon.tl.functions.messages import GetHistoryRequest

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INSTANCES_DIR = os.path.join(BASE_DIR, 'instances')


def log(level, pesan):
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f'[{ts}] [{level}] {pesan}', flush=True)


def parse_telegram_link(link):
    m = re.match(r'https://t\.me/([a-zA-Z0-9_]+)/(\d+)', link)
    if m:
        return m.group(1), int(m.group(2))
    m = re.match(r'https://t\.me/c/(\d+)/(\d+)', link)
    if m:
        return f'-100{m.group(1)}', int(m.group(2))
    return None, None


def get_bold(text):
    special = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '-', '=', '|', '{', '}']
    for char in special:
        text = text.replace(char, '\\' + char)
    return f'**{text}**'


def path_instance(nama):
    return os.path.join(INSTANCES_DIR, f'{nama}.json')


def terapkan_default(cfg, nama):
    cfg.setdefault('session', nama)
    cfg.setdefault('grup', [])
    cfg.setdefault('mode', 'teks')
    cfg.setdefault('delay', 30)
    cfg.setdefault('jam', 720)
    cfg.setdefault('footer', '')
    cfg.setdefault('pesan', '')
    cfg.setdefault('media', '')
    cfg.setdefault('pesan_dari_saved', True)
    cfg.setdefault('forward_link', '')
    cfg.setdefault('running', False)
    return cfg


def load_instance(nama):
    path = path_instance(nama)
    if not os.path.exists(path):
        log('ERROR', f'Config instance tidak ditemukan: {path}')
        sys.exit(1)
    with open(path, 'r') as f:
        cfg = json.load(f)
    for kunci in ('api_id', 'api_hash'):
        if kunci not in cfg:
            log('ERROR', f'Config {path} tidak punya field "{kunci}"')
            sys.exit(1)
    return terapkan_default(cfg, nama)


def save_instance(nama, cfg):
    with open(path_instance(nama), 'w') as f:
        json.dump(cfg, f, indent=2)


def tipe_grup(entity):
    if getattr(entity, 'broadcast', False):
        return 'Channel'
    if getattr(entity, 'megagroup', False):
        return 'Supergroup'
    return 'Group'


async def daftar_grup(client, cfg):
    dialogs = await client.get_dialogs()
    grup = [d for d in dialogs if d.is_group]
    if not grup:
        log('ERROR', 'Tidak ada grup ditemukan di akun ini.')
        return []
    dipilih = set(cfg.get('grup', []))
    log('INFO', 'Daftar Grup Tersedia (✔ = sedang dipilih di config):')
    for i, g in enumerate(grup):
        tanda = '✔' if g.entity.id in dipilih else ' '
        print(f'  [{i + 1}] {tanda} {g.name} ({tipe_grup(g.entity)})  ID:{g.entity.id}')
    return grup


async def pilih_grup_interaktif(client, cfg, nama_instance):
    grup = await daftar_grup(client, cfg)
    if not grup:
        return
    try:
        jawaban = input('Pilih grup (nomor pisahkan koma, kosong = batal): ').strip()
    except EOFError:
        log('ERROR', 'Perintah ini butuh terminal interaktif (jalankan langsung, bukan lewat pm2/systemd).')
        return
    if not jawaban:
        log('INFO', 'Dibatalkan. Tidak ada perubahan.')
        return
    try:
        indeks = [int(x) for x in jawaban.split(',')]
        terpilih = [grup[i - 1] for i in indeks]
    except (ValueError, IndexError):
        log('ERROR', 'Input tidak valid. Pastikan nomornya benar.')
        sys.exit(1)
    cfg['grup'] = [g.entity.id for g in terpilih]
    save_instance(nama_instance, cfg)
    log('OK', f'{len(terpilih)} grup tersimpan ke instances/{nama_instance}.json:')
    for g in terpilih:
        print(f'  - {g.name}')
    log('INFO', 'Perubahan dipakai pada run/siklus berikutnya.')


async def resolve_groups(client, ids):
    if not ids:
        log('ERROR', 'Field "grup" kosong di config. Isi dengan daftar ID grup.')
        return []
    dialogs = await client.get_dialogs()
    peta = {d.entity.id: d for d in dialogs if d.is_group}
    ditemukan = [peta[i] for i in ids if i in peta]
    hilang = [i for i in ids if i not in peta]
    for g in ditemukan:
        log('OK', f'Grup terpakai: {g.name}')
    if hilang:
        log('WARN', f'{len(hilang)} grup di config tidak ditemukan (dilewati): {hilang[:10]}')
    return ditemukan


async def _kirim(client, group, pesan):
    if pesan['media']:
        try:
            await client.send_file(
                group.entity, pesan['media'],
                caption=get_bold(pesan['text']), parse_mode='md'
            )
            log('OK', f'Teririm (media) ke {group.name}')
        except FloodWaitError:
            raise
        except Exception as e_media:
            log('WARN', f'Gagal media ke {group.name} ({e_media}) -> fallback teks')
            await client.send_message(group.entity, get_bold(pesan['text']), parse_mode='md')
            log('OK', f'Teririm (teks) ke {group.name}')
    else:
        await client.send_message(group.entity, get_bold(pesan['text']), parse_mode='md')
        log('OK', f'Teririm (teks) ke {group.name}')


async def kirim_ke_grup(client, group, pesan):
    try:
        await _kirim(client, group, pesan)
        return True
    except FloodWaitError as e:
        log('FLOOD', f'FloodWait {e.seconds}s saat kirim ke {group.name} -> menunggu lalu coba ulang')
        await asyncio.sleep(e.seconds + 3)
        try:
            await _kirim(client, group, pesan)
            return True
        except Exception as e2:
            log('ERROR', f'Gagal kirim ke {group.name}: {e2}')
            return False
    except Exception as e:
        log('ERROR', f'Gagal kirim ke {group.name}: {e}')
        return False


async def _forward(client, group, source_peer, message_id):
    try:
        await client.forward_messages(group.entity, message_id, from_peer=source_peer)
        log('OK', f'Forward ke {group.name}')
        return True
    except FloodWaitError:
        raise
    except Exception as e:
        error_text = str(e)
        if 'CHAT_SEND_PHOTOS_FORBIDDEN' in error_text or "You can't write in this chat" in error_text:
            try:
                msg = await client.get_messages(source_peer, ids=message_id)
                if msg.text:
                    await client.send_message(group.entity, get_bold(msg.text), parse_mode='md')
                    log('OK', f'Forward gagal, teks terkirim ke {group.name}')
                    return True
                log('ERROR', f'Forward gagal & pesan asli tanpa teks: {group.name}')
                return False
            except Exception as e2:
                log('ERROR', f'Forward & teks gagal ke {group.name}: {e2}')
                return False
        log('ERROR', f'Gagal forward ke {group.name}: {error_text}')
        return False


async def forward_ke_grup(client, group, source_peer, message_id):
    try:
        return await _forward(client, group, source_peer, message_id)
    except FloodWaitError as e:
        log('FLOOD', f'FloodWait {e.seconds}s saat forward ke {group.name} -> menunggu lalu coba ulang')
        await asyncio.sleep(e.seconds + 3)
        try:
            return await _forward(client, group, source_peer, message_id)
        except Exception as e2:
            log('ERROR', f'Gagal forward ke {group.name}: {e2}')
            return False
    except Exception as e:
        log('ERROR', f'Gagal forward ke {group.name}: {e}')
        return False


async def siapkan_pesan(client, cfg):
    if cfg['mode'] == 'forward':
        peer, mid = parse_telegram_link(cfg.get('forward_link', ''))
        if peer is None or mid is None:
            raise ValueError('Mode forward tapi "forward_link" kosong/tidak valid.')
        log('INFO', f'Mode forward: {cfg["forward_link"]}')
        return None, (peer, mid)

    teks = ''
    media = None
    if cfg.get('pesan_dari_saved'):
        saved = await client(GetHistoryRequest(
            peer='me', limit=1, offset_date=None, offset_id=0,
            add_offset=0, max_id=0, min_id=0, hash=0
        ))
        if saved.messages:
            m = saved.messages[0]
            teks = m.message or ''
            media = m.media
            log('INFO', 'Pesan diambil dari Saved Messages (pesan terakhir).')
        else:
            log('WARN', 'Saved Messages kosong -> pakai teks dari config.')
    if not teks:
        teks = cfg.get('pesan', '')
    if not cfg.get('pesan_dari_saved') and cfg.get('media'):
        media = cfg['media']
    footer = cfg.get('footer', '')
    if footer:
        teks += f'\n\n{footer}'
    if not teks and not media:
        raise ValueError('Pesan kosong. Isi "pesan", kirim pesan ke Saved Messages, atau pakai mode forward.')
    return {'text': teks, 'media': media}, None


def hitung_delay(cfg):
    dr = cfg.get('delay_random')
    if isinstance(dr, list) and len(dr) == 2:
        return random.randint(int(dr[0]), int(dr[1]))
    return int(cfg.get('delay', 30))


async def loop_kirim(client, groups, pesan, cfg, forward_info, test=False, on_cycle=None):
    mode_forward = cfg['mode'] == 'forward'
    jam = float(cfg.get('jam', 0) or 0)
    batas_waktu = time.time() + jam * 3600 if jam > 0 else None
    durasi_txt = 'test 1 siklus' if test else (f'durasi {jam:g} jam' if jam > 0 else 'tanpa batas (selamanya)')
    log('INFO', f'Mulai blast: {len(groups)} grup | mode {"forward" if mode_forward else "teks"} | {durasi_txt}')

    siklus = 1
    while True:
        if batas_waktu and time.time() >= batas_waktu:
            log('INFO', 'Durasi habis. Program selesai.')
            break
        log('INFO', f'Siklus ke-{siklus} -> kirim ke {len(groups)} grup')
        if mode_forward:
            peer, mid = forward_info
            tasks = [forward_ke_grup(client, g, peer, mid) for g in groups]
        else:
            tasks = [kirim_ke_grup(client, g, pesan) for g in groups]
        hasil = await asyncio.gather(*tasks)
        if on_cycle:
            try:
                on_cycle(siklus, sum(1 for r in hasil if r), len(hasil))
            except Exception as e_cb:
                log('WARN', f'Callback on_cycle error: {e_cb}')

        if test:
            log('INFO', 'Mode test selesai 1 siklus.')
            break
        if batas_waktu:
            sisa = batas_waktu - time.time()
            if sisa <= 0:
                break
        delay = hitung_delay(cfg)
        if batas_waktu and (batas_waktu - time.time()) < delay:
            log('INFO', 'Sisa waktu kurang dari delay -> berhenti.')
            break
        log('INFO', f'Tunggu {delay} detik sampai siklus berikutnya...')
        await asyncio.sleep(delay)
        siklus += 1


async def main():
    parser = argparse.ArgumentParser(description='Telegram blast bot multi-instance')
    parser.add_argument('--instance', required=True, help='nama instance (file instances/<nama>.json)')
    parser.add_argument('--test', action='store_true', help='kirim 1 siklus lalu keluar')
    parser.add_argument('--login', action='store_true', help='login interaktif untuk instance baru')
    parser.add_argument('--pilih-grup', dest='pilih_grup', action='store_true',
                        help='pilih grup secara interaktif lalu simpan ke config')
    parser.add_argument('--list-grup', dest='list_grup', action='store_true',
                        help='tampilkan daftar grup + ID lalu keluar')
    args = parser.parse_args()

    cfg = load_instance(args.instance)

    nama_session = cfg.get('session', args.instance)
    if not os.path.isabs(nama_session):
        nama_session = os.path.join(BASE_DIR, nama_session)
    file_session = nama_session + '.session'

    if not args.login and not os.path.exists(file_session):
        log('ERROR', f'Session belum ada: {file_session}')
        log('ERROR', f'Login dulu sekali: python3 bot.py --instance {args.instance} --login')
        sys.exit(1)

    client = TelegramClient(nama_session, int(cfg['api_id']), str(cfg['api_hash']))
    try:
        await client.start()
    except EOFError:
        log('ERROR', 'Session butuh login interaktif. Jalankan: '
            f'python3 bot.py --instance {args.instance} --login')
        sys.exit(1)
    log('INFO', f'Instance "{args.instance}" terhubung ke Telegram.')

    if args.login:
        log('INFO', f'Login selesai. Session baru tersimpan: {file_session}')
        log('INFO', f'Selanjutnya pilih grup: python3 bot.py --instance {args.instance} --pilih-grup')
        await client.disconnect()
        return

    if args.list_grup or args.pilih_grup:
        if args.pilih_grup:
            await pilih_grup_interaktif(client, cfg, args.instance)
        else:
            await daftar_grup(client, cfg)
        await client.disconnect()
        return

    groups = await resolve_groups(client, cfg['grup'])
    if not groups:
        log('ERROR', 'Tidak ada grup yang bisa digunakan.')
        sys.exit(1)

    try:
        pesan, forward_info = await siapkan_pesan(client, cfg)
    except ValueError as e:
        log('ERROR', str(e))
        sys.exit(1)
    await loop_kirim(client, groups, pesan, cfg, forward_info, test=args.test)
    await client.disconnect()


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log('INFO', 'Dihentikan oleh user (Ctrl+C).')
