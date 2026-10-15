# 📡 NetWatch - Automated Network & Device Monitoring

Aplikasi pemantau jaringan & perangkat otomatis (CCTV, Access Point, Router, PC, Server, Printer) dengan Web Dashboard realtime dan notifikasi otomatis ke Telegram saat kabel putus, daya mati, atau perangkat tidak merespons.

---

## 🚀 Cara Menjalankan

1. **Jalankan Aplikasi:**
   - Cukup klik ganda file **`start.bat`** di dalam folder `C:\net-monitor`.
   - Atau jika ingin berjalan senyap di background (tanpa jendela hitam CMD), klik ganda file **`start_background.vbs`**.
2. **Buka Dashboard di Browser:**
   - Dari laptop ini: buka **`http://localhost:8080`**
   - Dari HP / PC lain (dalam satu WiFi / LAN): buka **`http://[IP-Laptop-Ini]:8080`**
3. **Menghentikan Aplikasi:**
   - Jika pakai `start.bat`: tekan `Ctrl + C` di jendela CMD.
   - Jika pakai background: klik ganda **`stop.bat`**.

---

## ⚙️ Pengaturan Notifikasi Telegram

1. Buka dashboard di browser, klik tombol **"Telegram & Setup"** di pojok kanan atas.
2. Dapatkan **Bot Token**:
   - Buka aplikasi Telegram, cari bot **`@BotFather`**, kirim `/newbot`.
   - Ikuti petunjuknya dan copy token yang diberikan (contoh: `7123456789:AAHk...xyz`).
3. Dapatkan **Chat ID**:
   - Cari bot **`@userinfobot`** di Telegram, klik Start / kirim pesan apa saja.
   - Bot akan membalas dengan `Id` akun Anda (contoh: `123456789`).
4. **PENTING:** Buka bot yang baru Anda buat, lalu klik **`/start`** agar bot berhak mengirim pesan ke Anda.
5. Tempelkan **Bot Token** & **Chat ID** ke formulir di dashboard, lalu klik tombol **"Tes Kirim ke Telegram"**.
6. Simpan pengaturan!

---

## 📹 Menambah Perangkat yang Dipantau

1. Klik tombol **"➕ Tambah Device"**.
2. Masukkan:
   - **Nama:** Contoh *"CCTV Kasir Depan"*, *"Router Utama"*, *"PC Kasir 1"*, *"AP Ruang Tamu"*.
   - **IP Address:** Contoh `192.168.1.50`.
   - **Kategori:** Pilih Router, Access Point (AP), CCTV, PC / Komputer, Server, atau Printer.
   - **Lokasi / Catatan (Opsional):** Misal *"Lantai 2 dekat tangga"*.
3. Klik **Simpan**. Sistem akan langsung melakukan uji coba ping pertama.

---

## 💡 Tips untuk Memantau PC Lain (Windows Firewall)
- Perangkat seperti **CCTV, Router, dan Access Point** biasanya langsung bisa diping tanpa perlu konfigurasi apa pun.
- Untuk **PC Windows lain**, jika statusnya selalu *DOWN* padahal kabel sudah tersambung, itu karena firewall default Windows memblokir ping masuk. 
- Cara mengaktifkannya di PC target:
  1. Buka menu Start di PC target, ketik **Windows Defender Firewall with Advanced Security**.
  2. Klik **Inbound Rules** (Aturan Masuk).
  3. Cari dan aktifkan (Enable): **"File and Printer Sharing (Echo Request - ICMPv4-In)"**.
  4. Setelah itu PC target langsung bisa dipantau secara realtime oleh NetWatch.
