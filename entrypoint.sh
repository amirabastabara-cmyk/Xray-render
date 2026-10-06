#!/bin/bash
export PORT=${PORT:-10000}

# جایگذاری پورت Render در کانفیگ Nginx
envsubst '$PORT' < /app/nginx.conf.template > /etc/nginx/http.d/default.conf

# اجرای Nginx
nginx

# اجرای پنل مدیریت پایتون
python3 /app/app.py &

# نگهدارنده続く بودن کانتینر
while true; do sleep 1; done