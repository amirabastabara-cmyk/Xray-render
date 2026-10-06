FROM alpine:latest

RUN apk add --no-cache bash curl wget unzip python3 py3-pip nginx gettext py3-psutil py3-flask

# دانلود و نصب Xray
RUN wget https://github.com/XTLS/Xray-core/releases/latest/download/Xray-linux-64.zip && \
    unzip Xray-linux-64.zip -d /usr/local/bin/ && \
    rm Xray-linux-64.zip

WORKDIR /app

COPY . /app

RUN mkdir -p /etc/xray && cp /app/config.json /etc/xray/config.json
RUN chmod +x /app/entrypoint.sh

EXPOSE 10000

ENTRYPOINT ["/app/entrypoint.sh"]