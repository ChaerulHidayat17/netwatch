import subprocess
import re
import time
import threading
import ctypes
import socket
import struct
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import requests
from database import get_db, get_settings, log_incident

# Emoji map for categories
CATEGORY_EMOJIS = {
    "router": "🌐 Router",
    "ap": "📶 Access Point",
    "cctv": "📹 CCTV",
    "pc": "💻 PC / Komputer",
    "server": "🖥️ Server",
    "printer": "🖨️ Printer",
    "other": "🔌 Perangkat"
}

def ping_ip(ip: str, timeout_ms: int = 600):
    """
    Smart Hybrid Probe:
    1. ICMP Ping (standard ping)
    2. Hardware ARP Link-Layer (bypasses Windows Firewall / ICMP block)
    3. TCP Connect Probe (ports 445, 139, 80, 443, 8080, 554)
    Returns (is_up: bool, latency_ms: float, detail: str)
    """
    ip_clean = ip.strip()

    # Special case: localhost / loopback
    if ip_clean in ("127.0.0.1", "localhost", "::1"):
        return True, 0.5, "Localhost (OK)"

    # --- 1. PROBE 1: ICMP Ping ---
    try:
        cmd = ["ping", "-n", "1", "-w", str(timeout_ms), ip_clean]
        res = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=(timeout_ms / 1000.0) + 0.8
        )
        output = res.stdout

        if "TTL=" in output or "ttl=" in output:
            match = re.search(r"(?:time|waktu)[=<](\d+)ms", output, re.IGNORECASE)
            if match:
                latency = float(match.group(1))
            elif "time<1ms" in output.lower() or "waktu<1ms" in output.lower():
                latency = 0.5
            else:
                latency = 1.0
            return True, max(latency, 0.5), "ICMP Ping Reply"
    except Exception:
        pass

    # --- 2. PROBE 2: Hardware Layer-2 ARP (Bypasses Windows Firewall completely) ---
    try:
        dest_ip = struct.unpack('<I', socket.inet_aton(ip_clean))[0]
        mac_addr = (ctypes.c_byte * 6)()
        mac_len = ctypes.c_ulong(6)

        t0 = time.time()
        # SendARP(DestIP, SrcIP, pMacAddr, PhyAddrLen)
        res_arp = ctypes.windll.iphlpapi.SendARP(dest_ip, 0, ctypes.byref(mac_addr), ctypes.byref(mac_len))
        t1 = time.time()

        if res_arp == 0:
            latency = round(max((t1 - t0) * 1000.0, 1.0), 1)
            mac_str = ':'.join(f'{b & 0xff:02X}' for b in mac_addr)
            return True, latency, f"Online via ARP Link-Layer (MAC: {mac_str})"
    except Exception:
        pass

    # --- 3. PROBE 3: TCP Port SYN (SMB, Web, RTSP) ---
    for port in [445, 139, 80, 443, 8080, 554]:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(0.2)
            t0 = time.time()
            ret = s.connect_ex((ip_clean, port))
            t1 = time.time()
            s.close()

            if ret in (0, 10061):
                latency = round(max((t1 - t0) * 1000.0, 1.0), 1)
                return True, latency, f"Online via TCP Port {port}"
        except Exception:
            pass

    # All probes failed -> Device is truly down / cable disconnected
    return False, 0.0, "Request Timed Out / Host Unreachable (Kabel/Daya Putus)"

def send_telegram_message(token: str, chat_id: str, message: str) -> bool:
    """Send HTML-formatted Telegram message."""
    if not token or not chat_id:
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    try:
        resp = requests.post(url, json=payload, timeout=8)
        return resp.status_code == 200
    except Exception as e:
        print(f"[Telegram Error] {e}")
        return False

def format_duration(seconds: float) -> str:
    secs = int(seconds)
    if secs < 60:
        return f"{secs} detik"
    mins = secs // 60
    rem_secs = secs % 60
    if mins < 60:
        return f"{mins} menit {rem_secs} detik"
    hours = mins // 60
    rem_mins = mins % 60
    return f"{hours} jam {rem_mins} menit"

class NetworkMonitorEngine:
    def __init__(self):
        self.running = False
        self.thread = None
        self._lock = threading.Lock()

    def start(self):
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()
        print("✅ Network Monitoring Engine started.")

    def stop(self):
        self.running = False

    def ping_single_device(self, dev):
        dev_id = dev["id"]
        ip = dev["ip"]
        name = dev["name"]
        category = dev["category"]
        prev_status = dev["status"]
        fails = dev["consecutive_fails"]
        down_since = dev["down_since"]

        settings = get_settings()
        fail_threshold = int(settings.get("fail_threshold", 2))
        telegram_enabled = settings.get("telegram_enabled", "1") == "1"
        bot_token = settings.get("telegram_bot_token", "")
        chat_id = settings.get("telegram_chat_id", "")

        is_up, latency, reason = ping_ip(ip)
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        with get_db() as conn:
            cur = conn.cursor()

            if is_up:
                # Device is UP
                if prev_status == "DOWN":
                    # Device recovered!
                    downtime_text = ""
                    if down_since:
                        try:
                            down_dt = datetime.strptime(down_since, "%Y-%m-%d %H:%M:%S")
                            duration = (datetime.now() - down_dt).total_seconds()
                            downtime_text = format_duration(duration)
                        except Exception:
                            downtime_text = "Beberapa saat"

                    cur.execute("""
                        UPDATE devices 
                        SET status = 'UP', latency = ?, last_seen = ?, last_checked = ?, 
                            consecutive_fails = 0, down_since = NULL 
                        WHERE id = ?
                    """, (latency, now_str, now_str, dev_id))
                    conn.commit()

                    cat_label = CATEGORY_EMOJIS.get(category, "Perangkat")
                    msg_log = f"Device pulih kembali. Latensi: {latency:.1f}ms. Downtime: {downtime_text or '-'}"
                    log_incident(dev_id, name, ip, category, "RECOVERED", msg_log)

                    if telegram_enabled and bot_token and chat_id:
                        tg_msg = (
                            f"✅ <b>DEVICE RECOVERED / UP!</b>\n"
                            f"━━━━━━━━━━━━━━━━━━━\n"
                            f"🖥️ <b>Perangkat:</b> {name}\n"
                            f"🌐 <b>IP Address:</b> <code>{ip}</code>\n"
                            f"🏷️ <b>Kategori:</b> {cat_label}\n"
                            f"⚡ <b>Latensi:</b> {latency:.1f} ms\n"
                            f"⏱️ <b>Downtime:</b> {downtime_text}\n"
                            f"⏰ <b>Waktu Pulih:</b> {now_str}\n"
                            f"━━━━━━━━━━━━━━━━━━━\n"
                            f"Status: Normal & Terhubung kembali."
                        )
                        send_telegram_message(bot_token, chat_id, tg_msg)
                else:
                    # Normal UP
                    cur.execute("""
                        UPDATE devices 
                        SET status = 'UP', latency = ?, last_seen = ?, last_checked = ?, consecutive_fails = 0 
                        WHERE id = ?
                    """, (latency, now_str, now_str, dev_id))
                    conn.commit()

            else:
                # Device is DOWN / Unreachable
                new_fails = fails + 1
                if new_fails >= fail_threshold:
                    if prev_status != "DOWN":
                        # State changed to DOWN!
                        cur.execute("""
                            UPDATE devices 
                            SET status = 'DOWN', latency = 0.0, last_checked = ?, 
                                consecutive_fails = ?, down_since = ? 
                            WHERE id = ?
                        """, (now_str, new_fails, now_str, dev_id))
                        conn.commit()

                        cat_label = CATEGORY_EMOJIS.get(category, "Perangkat")
                        msg_log = f"Device DOWN: {reason} (Gagal {new_fails}x)"
                        log_incident(dev_id, name, ip, category, "DOWN", msg_log)

                        if telegram_enabled and bot_token and chat_id:
                            tg_msg = (
                                f"🚨 <b>ALERT: DEVICE DOWN / KABEL PUTUS!</b>\n"
                                f"━━━━━━━━━━━━━━━━━━━\n"
                                f"🖥️ <b>Perangkat:</b> {name}\n"
                                f"🌐 <b>IP Address:</b> <code>{ip}</code>\n"
                                f"🏷️ <b>Kategori:</b> {cat_label}\n"
                                f"⚠️ <b>Penyebab:</b> {reason}\n"
                                f"🔁 <b>Gagal Uji:</b> {new_fails}x berturut-turut\n"
                                f"⏰ <b>Waktu:</b> {now_str}\n"
                                f"━━━━━━━━━━━━━━━━━━━\n"
                                f"Segera periksa kabel LAN, switch, atau daya perangkat!"
                            )
                            send_telegram_message(bot_token, chat_id, tg_msg)
                    else:
                        # Already DOWN, update counter and last_checked
                        cur.execute("""
                            UPDATE devices 
                            SET last_checked = ?, consecutive_fails = ? 
                            WHERE id = ?
                        """, (now_str, new_fails, dev_id))
                        conn.commit()
                else:
                    # Still below threshold, keep previous status but update fail count
                    cur.execute("""
                        UPDATE devices 
                        SET last_checked = ?, consecutive_fails = ? 
                        WHERE id = ?
                    """, (now_str, new_fails, dev_id))
                    conn.commit()

        return is_up, latency, reason

    def _run_loop(self):
        while self.running:
            try:
                settings = get_settings()
                interval = int(settings.get("ping_interval", 15))
                if interval < 2:
                    interval = 2

                # Fetch enabled devices
                with get_db() as conn:
                    cur = conn.cursor()
                    cur.execute("SELECT * FROM devices WHERE enabled = 1")
                    devices = [dict(row) for row in cur.fetchall()]

                if devices:
                    # Ping concurrently up to 25 devices at once
                    with ThreadPoolExecutor(max_workers=min(25, len(devices))) as executor:
                        executor.map(self.ping_single_device, devices)

            except Exception as e:
                print(f"[Monitor Loop Error] {e}")

            # Sleep interval
            for _ in range(interval):
                if not self.running:
                    break
                time.sleep(1)

monitor_engine = NetworkMonitorEngine()
