import os
import ipaddress
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field
from typing import Optional

from database import init_db, get_db, get_settings, update_settings
from monitor import monitor_engine, ping_ip, send_telegram_message, CATEGORY_EMOJIS

# Lifespan for FastAPI
@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    monitor_engine.start()
    yield
    monitor_engine.stop()

app = FastAPI(title="NetWatch - Network & Device Monitoring", lifespan=lifespan)

# Static files
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
if not os.path.exists(STATIC_DIR):
    os.makedirs(STATIC_DIR, exist_ok=True)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

@app.get("/")
def serve_index():
    index_file = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return {"message": "NetWatch Backend Active. index.html not found."}

# Pydantic Schemas
class DeviceCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    ip: str = Field(..., min_length=1, max_length=100)
    category: str = Field("other")
    location: Optional[str] = ""

class DeviceUpdate(BaseModel):
    name: Optional[str] = None
    ip: Optional[str] = None
    category: Optional[str] = None
    location: Optional[str] = None
    enabled: Optional[int] = None

class SettingsUpdate(BaseModel):
    telegram_bot_token: Optional[str] = None
    telegram_chat_id: Optional[str] = None
    ping_interval: Optional[int] = None
    fail_threshold: Optional[int] = None
    telegram_enabled: Optional[int] = None

class TestTelegramRequest(BaseModel):
    telegram_bot_token: Optional[str] = None
    telegram_chat_id: Optional[str] = None

# --- API ENDPOINTS ---

@app.get("/api/stats")
def get_stats():
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT status, latency FROM devices WHERE enabled = 1")
        rows = cur.fetchall()

        total = len(rows)
        online = sum(1 for r in rows if r["status"] == "UP")
        offline = sum(1 for r in rows if r["status"] == "DOWN")
        unknown = sum(1 for r in rows if r["status"] == "UNKNOWN")

        up_latencies = [r["latency"] for r in rows if r["status"] == "UP" and r["latency"] > 0]
        avg_latency = round(sum(up_latencies) / len(up_latencies), 1) if up_latencies else 0.0

        cur.execute("SELECT COUNT(*) as count FROM incidents WHERE created_at >= date('now', 'localtime')")
        incidents_today = cur.fetchone()["count"]

    return {
        "total": total,
        "online": online,
        "offline": offline,
        "unknown": unknown,
        "avg_latency": avg_latency,
        "incidents_today": incidents_today
    }

@app.get("/api/devices")
def list_devices():
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM devices ORDER BY status ASC, category ASC, id DESC")
        rows = [dict(r) for r in cur.fetchall()]
        return rows

@app.post("/api/devices")
def add_device(dev: DeviceCreate):
    ip_clean = dev.ip.strip()
    name_clean = dev.name.strip()
    category = dev.category.lower().strip()
    if category not in CATEGORY_EMOJIS:
        category = "other"

    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id FROM devices WHERE ip = ?", (ip_clean,))
        if cur.fetchone():
            raise HTTPException(status_code=400, detail=f"IP {ip_clean} sudah terdaftar!")

        cur.execute("""
            INSERT INTO devices (name, ip, category, location, status, consecutive_fails)
            VALUES (?, ?, ?, ?, 'UNKNOWN', 0)
        """, (name_clean, ip_clean, category, dev.location.strip()))
        conn.commit()
        new_id = cur.lastrowid

    # Trigger immediate ping in background or inline
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM devices WHERE id = ?", (new_id,))
        row = dict(cur.fetchone())

    monitor_engine.ping_single_device(row)
    return {"success": True, "id": new_id, "message": f"Perangkat {name_clean} berhasil ditambahkan!"}

@app.put("/api/devices/{device_id}")
def update_device(device_id: int, dev: DeviceUpdate):
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM devices WHERE id = ?", (device_id,))
        existing = cur.fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="Perangkat tidak ditemukan.")

        updates = []
        params = []
        if dev.name is not None:
            updates.append("name = ?")
            params.append(dev.name.strip())
        if dev.ip is not None:
            ip_clean = dev.ip.strip()
            # check duplicate IP
            cur.execute("SELECT id FROM devices WHERE ip = ? AND id != ?", (ip_clean, device_id))
            if cur.fetchone():
                raise HTTPException(status_code=400, detail=f"IP {ip_clean} sudah digunakan perangkat lain.")
            updates.append("ip = ?")
            params.append(ip_clean)
        if dev.category is not None:
            cat = dev.category.lower().strip()
            updates.append("category = ?")
            params.append(cat if cat in CATEGORY_EMOJIS else "other")
        if dev.location is not None:
            updates.append("location = ?")
            params.append(dev.location.strip())
        if dev.enabled is not None:
            updates.append("enabled = ?")
            params.append(int(dev.enabled))

        if updates:
            params.append(device_id)
            cur.execute(f"UPDATE devices SET {', '.join(updates)} WHERE id = ?", params)
            conn.commit()

    return {"success": True, "message": "Perangkat berhasil diperbarui!"}

@app.delete("/api/devices/{device_id}")
def delete_device(device_id: int):
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM devices WHERE id = ?", (device_id,))
        conn.commit()
    return {"success": True, "message": "Perangkat berhasil dihapus."}

@app.post("/api/devices/{device_id}/ping")
def manual_ping(device_id: int):
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM devices WHERE id = ?", (device_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Perangkat tidak ditemukan.")
        dev = dict(row)

    is_up, latency, reason = monitor_engine.ping_single_device(dev)
    return {
        "success": True,
        "is_up": is_up,
        "latency": latency,
        "reason": reason
    }

@app.get("/api/settings")
def read_settings():
    st = get_settings()
    # Mask bot token for security preview
    raw_token = st.get("telegram_bot_token", "")
    masked_token = ""
    if raw_token and len(raw_token) > 10:
        masked_token = raw_token[:6] + "..." + raw_token[-4:]
    elif raw_token:
        masked_token = "***"

    return {
        "telegram_bot_token": raw_token,
        "telegram_bot_token_masked": masked_token,
        "telegram_chat_id": st.get("telegram_chat_id", ""),
        "ping_interval": int(st.get("ping_interval", 15)),
        "fail_threshold": int(st.get("fail_threshold", 2)),
        "telegram_enabled": int(st.get("telegram_enabled", 1))
    }

@app.post("/api/settings")
def save_settings(data: SettingsUpdate):
    to_update = {}
    if data.telegram_bot_token is not None:
        to_update["telegram_bot_token"] = data.telegram_bot_token.strip()
    if data.telegram_chat_id is not None:
        to_update["telegram_chat_id"] = data.telegram_chat_id.strip()
    if data.ping_interval is not None:
        to_update["ping_interval"] = max(2, data.ping_interval)
    if data.fail_threshold is not None:
        to_update["fail_threshold"] = max(1, data.fail_threshold)
    if data.telegram_enabled is not None:
        to_update["telegram_enabled"] = data.telegram_enabled

    update_settings(to_update)
    return {"success": True, "message": "Pengaturan berhasil disimpan!"}

@app.post("/api/test-telegram")
def test_telegram(payload: Optional[TestTelegramRequest] = None):
    st = get_settings()
    token = (payload.telegram_bot_token if payload and payload.telegram_bot_token else st.get("telegram_bot_token", "")).strip()
    chat_id = (payload.telegram_chat_id if payload and payload.telegram_chat_id else st.get("telegram_chat_id", "")).strip()

    if not token or not chat_id:
        raise HTTPException(status_code=400, detail="Token Bot dan Chat ID harus diisi terlebih dahulu!")

    test_msg = (
        "🔔 <b>TEST NOTIFIKASI NETWATCH BERHASIL!</b>\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "Sistem Automated Network & Device Monitoring berhasil terhubung dengan akun Telegram Anda.\n\n"
        "Notifikasi akan dikirimkan otomatis ke sini jika ada perangkat CCTV, AP, PC, atau Router yang down / kabel bermasalah.\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "✅ <i>Status: Monitoring Active</i>"
    )
    ok = send_telegram_message(token, chat_id, test_msg)
    if ok:
        return {"success": True, "message": "Pesan tes berhasil dikirim ke Telegram! Cek chat Telegram Anda."}
    else:
        raise HTTPException(
            status_code=502,
            detail="Gagal mengirim pesan ke Telegram. Pastikan Bot Token dan Chat ID benar, serta Anda sudah klik /start di bot tersebut."
        )

@app.get("/api/incidents")
def list_incidents(limit: int = 50):
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM incidents ORDER BY id DESC LIMIT ?", (limit,))
        return [dict(r) for r in cur.fetchall()]

@app.post("/api/incidents/clear")
def clear_incidents():
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM incidents")
        conn.commit()
    return {"success": True, "message": "Riwayat incident berhasil dibersihkan."}
