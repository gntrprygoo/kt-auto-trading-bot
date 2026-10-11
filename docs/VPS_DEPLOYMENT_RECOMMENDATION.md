# KT Auto Trading Bot - VPS Deployment Recommendation

## Rekomendasi Utama

Gunakan VPS Linux Ubuntu 24.04 LTS di region Singapore.

Spesifikasi awal yang disarankan:

- 2 GB RAM
- 1-2 vCPU
- 50-60 GB SSD
- Public IPv4 static/reserved
- Backup/snapshot aktif

Target biaya wajar: sekitar USD 12-15 per bulan untuk Linux VPS kecil. Jika memakai Windows VPS, biaya biasanya lebih tinggi karena lisensi Windows dan RAM minimum lebih besar.

## Opsi Cepat Jika AWS Suspend

Jika akun AWS masih suspend dan bot perlu dipindahkan hari ini, gunakan DigitalOcean Droplet Ubuntu.

Pilihan praktis:

- Provider: DigitalOcean
- Region: Singapore
- Image: Ubuntu 24.04 LTS
- Plan: Basic Droplet 2 GB RAM, 1 vCPU, 50 GB SSD
- Estimasi biaya: USD 12 per bulan

Alasan:

- Panel lebih sederhana dari AWS
- VPS bisa dibuat cepat
- Public IPv4 tersedia langsung
- Cukup untuk 1 bot admin dan observasi awal

Naikkan ke 2 vCPU/2 GB atau 4 GB RAM jika worker client mulai bertambah.

## Provider Yang Disarankan

### Pilihan 1 - AWS Lightsail Ubuntu

Cocok untuk produksi awal yang profesional.

Kelebihan:

- Brand cloud besar dan stabil
- Region Singapore tersedia
- Snapshot mudah
- Static IP mudah
- Cocok untuk naik kelas ke AWS ecosystem jika produk berkembang

Rekomendasi paket:

- Linux/Unix
- Ubuntu 24.04 LTS
- 2 GB RAM, 2 vCPU, 60 GB SSD

### Pilihan 2 - DigitalOcean Droplet Ubuntu

Cocok jika ingin panel yang sangat sederhana dan developer-friendly.

Kelebihan:

- Panel mudah dipahami
- Harga jelas
- Region Singapore tersedia
- Dokumentasi banyak

Rekomendasi paket:

- Basic Droplet
- Ubuntu 24.04 LTS
- 2 GB RAM, 1 vCPU, 50 GB SSD

### Pilihan 3 - Windows VPS

Hanya dipilih jika operator benar-benar ingin remote desktop seperti laptop Windows.

Kelebihan:

- Lebih familiar untuk pengguna Windows
- Bisa buka PowerShell dan folder seperti biasa

Kekurangan:

- Lebih mahal
- Lebih berat
- Kurang efisien untuk bot Python 24/7

## Arsitektur Operasional

Bot sebaiknya berjalan sebagai service, bukan lewat terminal manual.

Komponen produksi:

- Python virtual environment
- `config.json` berisi API key dan token Telegram
- `systemd` service untuk auto-start saat VPS reboot
- log rotation agar file log tidak membesar tanpa batas
- backup journal harian
- firewall hanya membuka SSH
- Binance API key dibatasi IP VPS

## Keamanan Wajib

- Jangan aktifkan withdraw permission pada Binance API.
- Aktifkan futures permission hanya jika memang dipakai.
- Batasi API key ke IP VPS.
- Gunakan SSH key, bukan password login biasa.
- Simpan `config.json` dengan permission terbatas.
- Buat snapshot sebelum update besar.

## Tahap Migrasi

1. Buat VPS Ubuntu di region Singapore.
2. Pasang Python dan dependency.
3. Upload folder bot ke VPS.
4. Buat `config.json` produksi.
5. Jalankan mode simulate dulu selama 1-2 cycle.
6. Cek `/health`, `/status`, `/positions`, dan log.
7. Set Binance API whitelist ke IP VPS.
8. Jalankan real mode sebagai service.
9. Aktifkan snapshot/backup.
10. Monitor 24 jam pertama.

## Catatan Untuk Semi-SaaS

Untuk 1 akun admin dan beberapa beta tester awal, 2 GB RAM cukup sebagai tahap awal. Jika nanti worker per user bertambah, naikkan ke 4 GB RAM atau pisahkan worker ke VPS lain.

Rekomendasi scaling:

- 1-3 user aktif: 2 GB RAM
- 4-10 user aktif: 4 GB RAM
- lebih dari 10 user aktif: arsitektur multi-worker dan database terpisah
