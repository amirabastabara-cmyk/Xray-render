FROM alpine:latest

RUN apk add --no-cache bash curl wget unzip

RUN wget https://github.com/XTLS/Xray-core/releases/latest/download/Xray-linux-64.zip && \
    unzip Xray-linux-64.zip -d /usr/local/bin/ && \
    rm Xray-linux-64.zip

COPY config.json /etc/xray/config.json

EXPOSE 10000

CMD ["xray", "run", "-c", "/etc/xray/config.json"]
