FROM bluenviron/mediamtx:1.21.4@sha256:c730bccdbc8739f8f0c13cefe9bea8b61926f599b88fa4d0d229baa91846c7bc AS relay

FROM alpine:3.22@sha256:49340b346798875b5592e5d420241f2f9cfba5f47e62ebb1446a1b34734e898f AS sources
RUN apk add --no-cache ca-certificates git npm
RUN git init -q /opt/meari \
    && git -C /opt/meari fetch --depth=1 https://github.com/saidtezel/hass-cloudedge-meari.git 4f52459653aa65d246f5d7421fbab8bac0a4af26 \
    && git -C /opt/meari checkout --detach FETCH_HEAD \
    && rm -rf /opt/meari/.git
WORKDIR /tmp/player
COPY package.json package-lock.json ./
RUN npm ci --ignore-scripts --no-audit --no-fund \
    && mkdir -p /opt/hls \
    && cp node_modules/hls.js/dist/hls.min.js node_modules/hls.js/LICENSE /opt/hls/

FROM python:3.12-slim-bookworm@sha256:935c3c5b12357a7e10caa9c1e6ca5692344d97cf229832ef584be2cec9fc03df
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
RUN apt-get update && apt-get install --no-install-recommends -y ca-certificates ffmpeg \
    && rm -rf /var/lib/apt/lists/*
COPY --from=relay /mediamtx /usr/local/bin/mediamtx
COPY --from=sources /opt/meari /opt/meari
COPY --from=sources /opt/hls /opt/hls
WORKDIR /opt/cococam
COPY requirements.txt ./
RUN pip install --no-cache-dir --require-hashes -r requirements.txt
COPY bridge ./bridge
COPY mediamtx.yml ./
COPY licenses /usr/share/doc/cococam
EXPOSE 8099
STOPSIGNAL SIGTERM
CMD ["python", "-m", "bridge.server"]
