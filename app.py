import os
import json
import uuid
import subprocess
import psutil
from flask import Flask, render_template, request, jsonify, session, redirect, url_for

app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "super_secret_key_12345")

ADMIN_USER = os.environ.get("ADMIN_USER", "admin")
ADMIN_PASS = os.environ.get("ADMIN_PASS", "admin123")
CONFIG_PATH = "/etc/xray/config.json"

def read_config():
    with open(CONFIG_PATH, "r") as f:
        return json.load(f)

def save_config(data):
    with open(CONFIG_PATH, "w") as f:
        json.dump(data, f, indent=2)
    # ریستارت کردن پروسه Xray برای اعمال تغییرات
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
    config = read_config()
    clients = config["inbounds"][0]["settings"]["clients"]
    return jsonify(clients)

@app.route("/api/clients/add", methods=["POST"])
def add_client():
    if not session.get("logged_in"):
        return jsonify({"error": "Unauthorized"}), 401
    
    data = request.json
    email = data.get("email", "user_" + str(uuid.uuid4())[:4])
    new_uuid = str(uuid.uuid4())
    
    config = read_config()
    config["inbounds"][0]["settings"]["clients"].append({
        "id": new_uuid,
        "level": 0,
        "email": email
    })
    save_config(config)
    return jsonify({"success": True, "uuid": new_uuid, "email": email})

@app.route("/api/clients/delete", methods=["POST"])
def delete_client():
    if not session.get("logged_in"):
        return jsonify({"error": "Unauthorized"}), 401
    
    client_id = request.json.get("id")
    config = read_config()
    clients = config["inbounds"][0]["settings"]["clients"]
    
    # عدم اجازه حذف کاربر اصلی در صورت وجود تنها یک کاربر
    if len(clients) <= 1:
        return jsonify({"success": False, "message": "حداقل باید یک کاربر فعال وجود داشته باشد"}), 400
        
    config["inbounds"][0]["settings"]["clients"] = [c for c in clients if c["id"] != client_id]
    save_config(config)
    return jsonify({"success": True})

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000)