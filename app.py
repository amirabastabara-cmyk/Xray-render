import os
import json
import uuid
import time
import subprocess
import psutil
from flask import Flask, render_template, request, jsonify, session

app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "super_secret_key_12345")

ADMIN_USER = os.environ.get("ADMIN_USER", "admin")
ADMIN_PASS = os.environ.get("ADMIN_PASS", "admin123")
CONFIG_PATH = "/etc/xray/config.json"
USERS_DB_PATH = "/etc/xray/users_db.json"

def read_json(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r") as f:
            return json.load(f)
    except:
        return default

def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

def sync_xray_config():
    users = read_json(USERS_DB_PATH, [])
    config = read_json(CONFIG_PATH, {"inbounds": [{"settings": {"clients": []}}]})
    
    active_clients = []
    now = time.time()
    
    for u in users:
        # بررسی انقضای زمانی (اگر زمان گذشته باشد، کاربر به Xray اضافه نمی‌شود)
        if u.get("expire_timestamp") and now > u["expire_timestamp"]:
            u["status"] = "expired"
            continue
        
        u["status"] = "active"
        active_clients.append({
            "id": u["id"],
            "level": 0,
            "email": u["email"]
        })
        
    save_json(USERS_DB_PATH, users)
    config["inbounds"][0]["settings"]["clients"] = active_clients
    save_json(CONFIG_PATH, config)
    
    # ریلود کردن Xray برای اعمال تغییرات
    subprocess.run(["pkill", "-HUP", "xray"])

@app.route("/")
def index():
    if not session.get("logged_in"):
        return render_template("login.html")
    return render_template("dashboard.html")

@app.route("/api/login", methods=["POST"])
def login():
    data = request.json
    if data.get("username") == ADMIN_USER and data.get("password") == ADMIN_PASS:
        session["logged_in"] = True
        return jsonify({"success": True})
    return jsonify({"success": False, "message": "نام کاربری یا رمز عبور اشتباه است"}), 401

@app.route("/api/logout", methods=["POST"])
def logout():
    session.pop("logged_in", None)
    return jsonify({"success": True})

@app.route("/api/stats")
def stats():
    if not session.get("logged_in"):
        return jsonify({"error": "Unauthorized"}), 401
    
    cpu_usage = psutil.cpu_percent(interval=0.5)
    ram = psutil.virtual_memory()
    
    return jsonify({
        "cpu": cpu_usage,
        "ram_percent": ram.percent,
        "ram_used_mb": round(ram.used / (1024 * 1024), 1),
        "ram_total_mb": round(ram.total / (1024 * 1024), 1)
    })

@app.route("/api/clients", methods=["GET"])
def get_clients():
    if not session.get("logged_in"):
        return jsonify({"error": "Unauthorized"}), 401
    
    sync_xray_config()
    users = read_json(USERS_DB_PATH, [])
    now = time.time()
    
    # محاسبه روزهای باقی‌مانده برای هر کاربر
    for u in users:
        if u.get("expire_timestamp"):
            remaining_seconds = u["expire_timestamp"] - now
            u["days_left"] = max(0, int(remaining_seconds // 86400))
        else:
            u["days_left"] = "نامحدود"
            
    return jsonify(users)

@app.route("/api/clients/add", methods=["POST"])
def add_client():
    if not session.get("logged_in"):
        return jsonify({"error": "Unauthorized"}), 401
    
    data = request.json
    email = data.get("email", "").strip() or f"user_{str(uuid.uuid4())[:4]}"
    limit_gb = float(data.get("limit_gb", 0))
    expire_days = int(data.get("expire_days", 30))
    
    new_uuid = str(uuid.uuid4())
    now = time.time()
    expire_timestamp = now + (expire_days * 86400) if expire_days > 0 else None
    
    users = read_json(USERS_DB_PATH, [])
    
    # اگر کاربر دمی وجود نداشت، یک کاربر پیش‌فرض اولیه بساز
    users.append({
        "id": new_uuid,
        "email": email,
        "limit_gb": limit_gb if limit_gb > 0 else "نامحدود",
        "expire_days": expire_days,
        "expire_timestamp": expire_timestamp,
        "created_at": time.strftime("%Y-%m-%d %H:%M")
    })
    
    save_json(USERS_DB_PATH, users)
    sync_xray_config()
    
    return jsonify({"success": True})

@app.route("/api/clients/delete", methods=["POST"])
def delete_client():
    if not session.get("logged_in"):
        return jsonify({"error": "Unauthorized"}), 401
    
    client_id = request.json.get("id")
    users = read_json(USERS_DB_PATH, [])
    
    users = [u for u in users if u["id"] != client_id]
    save_json(USERS_DB_PATH, users)
    sync_xray_config()
    
    return jsonify({"success": True})

if __name__ == "__main__":
    # در اولین اجرا فایل دیتابیس همگام‌سازی می‌شود
    sync_xray_config()
    app.run(host="127.0.0.1", port=5000)