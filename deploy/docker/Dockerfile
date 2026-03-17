FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1
ENV ECNU_NET_CONFIG=/data/config.ini
ENV ECNU_NET_KEY_PATH=/data/config.key
ENV ECNU_KEEPER_EVENT_LOG=/logs/keeper-events.log
ENV ECNU_KEEPER_STATE_PATH=/data/keeper-state.json
ENV ECNU_KEEPER_INTERVAL=120

WORKDIR /app

COPY ecnu_network_keeper ./ecnu_network_keeper
COPY README.md ./README.md

VOLUME /data
VOLUME /logs

CMD ["python", "-m", "ecnu_network_keeper", "--login", "--daemon", "--store-password", "--verbose"]
