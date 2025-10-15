import os
import sys
import requests
import argparse

# --- Konfigurasi Awal & Pengambilan Secrets ---
try:
    CF_API_TOKEN = os.environ['1c3c6d5f1141356e712323e1c4a375778e277']
    CF_ZONE_ID = os.environ['cb87f7a001b6320630cfc050eb92321b']
    DOMAIN = os.environ['kaisarstore.dpdns.org']
    TG_BOT_TOKEN = os.environ['7912451318:AAHcUcdFFG4U2D7lF7iSsR3yfpFsBC94KT4']
    TG_CHAT_ID = os.environ['6222865137']
except KeyError as e:
    print(f"❌ Error: Secret {e} belum diatur di Pengaturan Repositori GitHub.")
    sys.exit(1)

API_BASE_URL = f"https://api.cloudflare.com/client/v4/zones/{CF_ZONE_ID}/dns_records"
HEADERS = {
    "Authorization": f"Bearer {CF_API_TOKEN}",
    "Content-Type": "application/json"
}

# --- Fungsi Bantuan ---
def send_telegram_notification(message):
    """Mengirim notifikasi ke Telegram."""
    api_url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
    payload = {'chat_id': TG_CHAT_ID, 'text': message, 'parse_mode': 'Markdown'}
    try:
        requests.post(api_url, json=payload, timeout=10).raise_for_status()
        print("✅ Notifikasi Telegram berhasil dikirim.")
    except requests.exceptions.RequestException as e:
        print(f"⚠️ Gagal mengirim notifikasi Telegram: {e}")

def get_full_name(name):
    """Mengembalikan nama domain lengkap. '@' berarti domain utama."""
    return DOMAIN if name == '@' else f"{name}.{DOMAIN}"

# --- Kelas Utama untuk Manajemen DNS ---
class CloudflareManager:
    def find_record_id(self, record_type, name):
        """Mencari ID dari sebuah record DNS yang sudah ada."""
        full_name = get_full_name(name)
        print(f"Mencari record: Tipe='{record_type}', Nama='{full_name}'...")
        params = {'type': record_type, 'name': full_name}
        try:
            response = requests.get(API_BASE_URL, headers=HEADERS, params=params, timeout=10)
            response.raise_for_status()
            records = response.json().get('result', [])
            if records:
                print(f"Record ditemukan dengan ID: {records[0]['id']}")
                return records[0]['id'], records[0]['content']
            return None, None
        except requests.exceptions.RequestException as e:
            send_telegram_notification(f"❌ *GAGAL!*\n\nTidak dapat mencari record. Error koneksi: `{e}`")
            sys.exit(1)

    def create_or_update(self, record_type, name, content, proxied=True, ttl=1):
        """Membuat atau memperbarui record DNS."""
        record_id, old_content = self.find_record_id(record_type, name)
        full_name = get_full_name(name)
        
        if record_id and old_content == content:
            send_telegram_notification(f"ℹ️ *INFO*\n\nRecord `{record_type}` untuk `{full_name}` sudah menunjuk ke `{content}`. Tidak ada perubahan.")
            return

        payload = {'type': record_type, 'name': full_name, 'content': content, 'ttl': ttl, 'proxied': proxied}

        try:
            if record_id:
                print(f"Memperbarui record {full_name}...")
                response = requests.put(f"{API_BASE_URL}/{record_id}", headers=HEADERS, json=payload, timeout=10)
                action_text = "diperbarui"
            else:
                print(f"Membuat record {full_name}...")
                response = requests.post(API_BASE_URL, headers=HEADERS, json=payload, timeout=10)
                action_text = "dibuat"
            
            response.raise_for_status()
            if response.json().get('success'):
                send_telegram_notification(
                    f"✅ *SUKSES!*\n\nRecord `{record_type}` untuk `{full_name}` berhasil *{action_text}*.\nKonten baru: `{content}`"
                )
            else:
                error = response.json().get('errors', [{}])[0].get('message', 'Unknown error')
                send_telegram_notification(f"❌ *GAGAL!*\n\nCloudflare API error: `{error}`")
        except requests.exceptions.RequestException as e:
            send_telegram_notification(f"❌ *GAGAL!*\n\nError saat {action_text} record: `{e}`")

    def delete(self, record_type, name):
        """Menghapus record DNS."""
        record_id, _ = self.find_record_id(record_type, name)
        full_name = get_full_name(name)

        if not record_id:
            send_telegram_notification(f"ℹ️ *INFO*\n\nRecord `{record_type}` untuk `{full_name}` tidak ditemukan. Tidak ada yang dihapus.")
            return

        try:
            print(f"Menghapus record {full_name} (ID: {record_id})...")
            response = requests.delete(f"{API_BASE_URL}/{record_id}", headers=HEADERS, timeout=10)
            response.raise_for_status()
            if response.json().get('success'):
                send_telegram_notification(f"✅ *SUKSES!*\n\nRecord `{record_type}` untuk `{full_name}` telah berhasil *dihapus*.")
            else:
                error = response.json().get('errors', [{}])[0].get('message', 'Unknown error')
                send_telegram_notification(f"❌ *GAGAL!*\n\nCloudflare API error saat menghapus: `{error}`")
        except requests.exceptions.RequestException as e:
            send_telegram_notification(f"❌ *GAGAL!*\n\nError saat menghapus record: `{e}`")


# --- Logika Utama untuk Menjalankan dari Command Line ---
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Kelola record DNS Cloudflare.")
    subparsers = parser.add_subparsers(dest='action', required=True)

    # Parser untuk action create/update
    parser_update = subparsers.add_parser('update', help='Buat atau perbarui record.')
    parser_update.add_argument('--type', required=True, help='Tipe record (A, CNAME, TXT, dll.)')
    parser_update.add_argument('--name', required=True, help="Nama subdomain ('@' untuk domain utama).")
    parser_update.add_argument('--content', required=True, help='Konten record (IP, domain lain, teks).')
    
    # Parser untuk action delete
    parser_delete = subparsers.add_parser('delete', help='Hapus record.')
    parser_delete.add_argument('--type', required=True, help='Tipe record yang akan dihapus.')
    parser_delete.add_argument('--name', required=True, help='Nama subdomain dari record yang akan dihapus.')

    args = parser.parse_args()
    manager = CloudflareManager()

    if args.action == 'update':
        print(f"🚀 Memulai Aksi: UPDATE untuk {args.name}.{DOMAIN}...")
        is_ip_record = args.type in ['A', 'AAAA']
        manager.create_or_update(args.type, args.name, args.content, proxied=is_ip_record)
    elif args.action == 'delete':
        print(f"🚀 Memulai Aksi: DELETE untuk {args.name}.{DOMAIN}...")
        manager.delete(args.type, args.name)
    
    print("🏁 Proses selesai.")
