FROM bluenviron/mediamtx:1.21.4@sha256:c730bccdbc8739f8f0c13cefe9bea8b61926f599b88fa4d0d229baa91846c7bc AS relay

FROM alpine:3.24@sha256:f59abe656b692d901e184be3445e084786602108599d2a51d229c0f5a48c71bf AS sources
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

FROM python:3.15-slim-bookworm@sha256:498829c717b1e59fc42f0e7865eafe4e04ca0f70a3769d4ae70ba218df54507c
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
RUN apt-get update && apt-get install --no-install-recommends -y ca-certificates ffmpeg \
    && rm -rf /var/lib/apt/lists/*
COPY --from=relay /mediamtx /usr/local/bin/mediamtx
COPY --from=sources /opt/meari /opt/meari
COPY --from=sources /opt/hls /opt/hls
WORKDIR /opt/cococam
COPY requirements.txt ./
RUN locked_python=$(sed -n 's/^#.* --python-version \([0-9][0-9.]*\) .*/\1/p' requirements.txt) \
    && runtime_python=$(python -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")') \
    && (test "$locked_python" = "$runtime_python" || { echo "Regenerate requirements.txt for Python $runtime_python (locked: $locked_python)" >&2; exit 1; }) \
    && pip install --no-cache-dir --require-hashes --only-binary=:all: -r requirements.txt
COPY bridge ./bridge
COPY mediamtx.yml ./
COPY licenses /usr/share/doc/cococam
EXPOSE 8099
STOPSIGNAL SIGTERM
CMD ["python", "-m", "bridge.server"]
