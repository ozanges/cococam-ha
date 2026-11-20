ARG BUILD_FROM=python:3.12-slim-bookworm

FROM bluenviron/mediamtx:1.21.4 AS relay

FROM alpine:3.22 AS sources
RUN apk add --no-cache ca-certificates curl git
RUN git init -q /opt/meari \
    && git -C /opt/meari fetch --depth=1 https://github.com/saidtezel/hass-cloudedge-meari.git 4f52459653aa65d246f5d7421fbab8bac0a4af26 \
    && git -C /opt/meari checkout --detach FETCH_HEAD \
    && rm -rf /opt/meari/.git
RUN mkdir -p /opt/hls /tmp/hls \
    && curl -fsSL --retry 3 https://registry.npmjs.org/hls.js/-/hls.js-1.7.4.tgz -o /tmp/hls.tgz \
    && echo '3GlxGdPvT2YHvQYOt+yOzT/DEior/qJVNIylHA77kgeoBTdQQqi70GwefNEUmHQeNGyjC8U62+bruqW/Tpm+tg==' | base64 -d | od -An -v -tx1 | tr -d ' \n' > /tmp/hash \
    && printf '%s  /tmp/hls.tgz\n' "$(cat /tmp/hash)" | sha512sum -c - \
    && tar -xzf /tmp/hls.tgz -C /tmp/hls \
    && cp /tmp/hls/package/dist/hls.min.js /tmp/hls/package/LICENSE /opt/hls/

FROM ${BUILD_FROM}
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
