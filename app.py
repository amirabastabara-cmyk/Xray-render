import os
import json
import uuid
import time
import base64
import subprocess
import psutil
from flask import Flask, render_template, request, jsonify, session, Response

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

def restart_xray():
    """ریستارت ایمن Xray بدون ایجاد ارور Hangup"""
    try:
        subprocess.run(["pkill", "-9", "xray"], check=False)
        time.sleep(0.5)
        subprocess.Popen(["/usr/local/bin/xray", "run", "-c", CONFIG_PATH])
    except Exception as e:
        print(f"Error restarting Xray: {e}")

def get_xray_traffic():
    """دریافت ترافیک آنلاین کاربران از API داخلی Xray"""
    traffic = {}
    try:
        cmd = ["/usr/local/bin/xray", "api", "statsquery", "--server=127.0.0.1:10085"]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=2)
        if res.returncode == 0 and res.stdout:
            data = json.loads(res.stdout)
            for item in data.get("stat", []):
                parts = item.get("name", "").split(">>>")
                if len(parts) == 4 and parts[0] == "user":
                    email = parts[1]
                    val = int(item.get("value", 0))
                    traffic[email] = traffic.get(email, 0) + val
    except Exception:
        pass
    return traffic

def sync_xray_config():
    users = read_json(USERS_DB_PATH, [])
    config = read_json(CONFIG_PATH, {"inbounds": [{"settings": {"clients": []}}]})
    
    live_traffic = get_xray_traffic()
    now = time.time()
    active_clients = []
    
    for u in users:
        email = u["email"]
        
        # بروزرسانی مصرف حجم واقعی (بایت)
        if email in live_traffic:
            u["used_bytes"] = u.get("used_bytes", 0) + live_traffic[email]
            
        used_gb = u.get("used_bytes", 0) / (1024 ** 3)
        limit_gb = float(u.get("limit_gb", 0)) if str(u.get("limit_gb")).replace('.','',1).isdigit() else 0
        
        # بررسی انقضای زمانی و حجمی
        is_time_expired = u.get("expire_timestamp") and now > u["expire_timestamp"]
        is_volume_expired = limit_gb > 0 and used_gb >= limit_gb
        
        if is_time_expired or is_volume_expired:
            u["status"] = "expired"
            continue
            
        u["status"] = "active"
        active_clients.append({
            "id": u["id"],
            "level": 0,
            "email": u["email"]
        })
        
    save_json(USERS_DB_PATH, users)
    
    # بروزرسانی لیست کلاینت‌های مجاز در اینباند اصلی
    for inbound in config.get("inbounds", []):
        if inbound.get("protocol") == "vless":
            inbound["settings"]["clients"] = active_clients
            
    save_json(CONFIG_PATH, config)

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
    return jsonify({"success": False, "message": "اطلاعات ورود اشتباه است"}), 401

@app.route("/api/logout", methods=["POST"])
def logout():
    session.pop("logged_in", None)
    return jsonify({"success": True})

@app.route("/api/stats")
def stats():
    if not session.get("logged_in"):
        return jsonify({"error": "Unauthorized"}), 401
    
    ram = psutil.virtual_memory()
    return jsonify({
        "cpu": psutil.cpu_percent(interval=0.2),
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
    
    for u in users:
        # روزهای باقی‌مانده
        if u.get("expire_timestamp"):
            rem_sec = u["expire_timestamp"] - now
            u["days_left"] = max(0, int(rem_sec // 86400))
        else:
            u["days_left"] = "نامحدود"
            
        # حجم مصرفی فرمت‌شده
        used_mb = u.get("used_bytes", 0) / (1024 * 1024)
        if used_mb >= 1024:
            u["used_formatted"] = f"{round(used_mb / 1024, 2)} GB"
        else:
            u["used_formatted"] = f"{round(used_mb, 1)} MB"
            
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
    users.append({
        "id": new_uuid,
        "email": email,
        "limit_gb": limit_gb if limit_gb > 0 else 0,
        "used_bytes": 0,
        "expire_days": expire_days,
        "expire_timestamp": expire_timestamp,
        "created_at": time.strftime("%Y-%m-%d %H:%M")
    })
    
    save_json(USERS_DB_PATH, users)
    sync_xray_config()
    restart_xray()
    
    return jsonify({"success": True})

@app.route("/api/clients/delete", methods=["POST"])
def delete_client():
    if not session.get("logged_in"):
        return jsonify({"error": "Unauthorized"}), 401
    
    client_id = request.json.get("id")
    users = [u for u in read_json(USERS_DB_PATH, []) if u["id"] != client_id]
    save_json(USERS_DB_PATH, users)
    sync_xray_config()
    restart_xray()
    
    return jsonify({"success": True})

# --- روت لینک سابسکریپشن (ویژه نرم‌افزارهای V2Ray) ---
@app.route("/sub/<user_id>")
def sub(user_id):
    users = read_json(USERS_DB_PATH, [])
    user = next((u for u in users if u["id"] == user_id), None)
    
    if not user:
        return "User not found", 404
        
    host = request.host
    vless_link = f"vless://{user['id']}@{host}:443?path=%2Fvless&security=tls&encryption=none&type=ws#{user['email']}"
    b64_content = base64.b64encode(vless_link.encode("utf-8")).decode("utf-8")
    
    limit_gb = float(user.get("limit_gb", 0))
    total_bytes = int(limit_gb * 1024 * 1024 * 1024) if limit_gb > 0 else 0
    used_bytes = int(user.get("used_bytes", 0))
    expire_ts = int(user.get("expire_timestamp", 0) or 0)
    
    res = Response(b64_content, mimetype="text/plain; charset=utf-8")
    # هدر استاندارد برای نمایش حجم و زمان مانده در v2rayNG / NekoBox / Streisand
    res.headers["Subscription-Userinfo"] = f"upload=0; download={used_bytes}; total={total_bytes}; expire={expire_ts}"
    return res

if __name__ == "__main__":
    sync_xray_config()
    restart_xray()
    app.run(host="127.0.0.1", port=5000)