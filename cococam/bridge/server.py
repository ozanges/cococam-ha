"""Serve the authenticated Ingress panel and gate browser playback."""

import asyncio
import contextlib
import hmac
import os
import re
import secrets
import signal
import sys
from pathlib import Path

from aiohttp import ClientError, ClientSession, ClientTimeout, WSMsgType, web

from .session import Session
from .settings import live_duration, options

HERE = Path(__file__).resolve().parent
STATE = web.AppKey("session", Session)
HTTP = web.AppKey("http", ClientSession)
TOKEN = web.AppKey("token", str)
CONFIGURED = web.AppKey("configured", bool)
INGRESS = web.AppKey("ingress", bool)
MEDIA = web.AppKey("media", str)
MEDIA_TOKEN = web.AppKey("media_token", str)
SAFE_ERRORS = {"credentials", "login", "camera_selection", "stream", "worker", "disconnected"}
MEDIA_FILE = re.compile(r"[a-zA-Z0-9._-]+\.(?:m3u8|mp4|m4s|ts)")


async def terminate(process):
    if process.returncode is not None:
        return
    with contextlib.suppress(ProcessLookupError):
        process.send_signal(signal.SIGINT)
    try:
        await asyncio.wait_for(process.wait(), 7)
    except TimeoutError:
        with contextlib.suppress(ProcessLookupError):
            os.killpg(process.pid, signal.SIGKILL)
        await process.wait()


async def run_camera(http, generation, ready, stop):
    process = await asyncio.create_subprocess_exec(
        sys.executable, "-m", "bridge.worker", generation, "8556",
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL, start_new_session=True,
    )
    notified = False
    try:
        while not stop.is_set() and process.returncode is None:
            if not notified:
                try:
                    async with http.get("http://127.0.0.1:8098/v3/paths/list") as response:
                        response.raise_for_status()
                        rows = (await response.json()).get("items") or []
                    paths = {r["name"] for r in rows if r.get("ready")}
                    if {f"live/{generation}/{lane}" for lane in (0, 1)} <= paths:
                        ready()
                        notified = True
                except (ClientError, TimeoutError):
                    pass
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), .35)
        if stop.is_set():
            return None
        value = (await process.stdout.read()).decode(errors="replace").strip()
        return value if value in SAFE_ERRORS else "worker"
    finally:
        await terminate(process)
        # The worker may have exited abruptly before reaping its FFmpeg children.
        with contextlib.suppress(ProcessLookupError):
            os.killpg(process.pid, signal.SIGKILL)


@web.middleware
async def security(request, handler):
    if request.app[INGRESS] and request.remote != "172.30.32.2":
        raise web.HTTPForbidden()
    result = await handler(request)
    if not result.prepared:
        result.headers["X-Content-Type-Options"] = "nosniff"
        result.headers["Cache-Control"] = "no-store"
        result.headers["Referrer-Policy"] = "no-referrer"
        result.headers["Content-Security-Policy"] = (
            "default-src 'self'; media-src 'self' blob:; worker-src 'self' blob:; "
            "style-src 'self'; frame-ancestors 'self'; object-src 'none'; base-uri 'none'"
        )
    return result


async def index(request):
    views = request.query.get("embed")
    if views is not None and views not in {"1", "2", "both"}:
        raise web.HTTPBadRequest()
    markup = (HERE / "static/index.html").read_text()
    markup = markup.replace("__TOKEN__", request.app[TOKEN]).replace("__LAYOUT__", views or "panel")
    return web.Response(text=markup, content_type="text/html")


async def asset(request):
    match request.match_info["name"]:
        case "panel.js" | "panel.css":
            path = HERE / "static" / request.match_info["name"]
        case "hls.min.js":
            path = Path(os.getenv("COCOCAM_HLS_JS", "/opt/hls/hls.min.js"))
        case _:
            raise web.HTTPNotFound()
    if not path.is_file():
        raise web.HTTPNotFound()
    return web.FileResponse(path)


async def events(request):
    if not hmac.compare_digest(request.query.get("key", "").encode(), request.app[TOKEN].encode()):
        raise web.HTTPForbidden()
    state = request.app[STATE]
    if len(state.viewers) >= 16:
        raise web.HTTPServiceUnavailable()
    ws = web.WebSocketResponse(heartbeat=10, max_msg_size=256)
    await ws.prepare(request)
    state.connect(ws)
    last = None
    try:
        while not ws.closed:
            snapshot = state.status() | {"configured": request.app[CONFIGURED]}
            if snapshot != last:
                await ws.send_json(snapshot)
                last = snapshot
            try:
                message = await ws.receive(timeout=.5)
            except TimeoutError:
                continue
            if message.type == WSMsgType.TEXT and request.app[CONFIGURED]:
                if message.data in {"open", "start", "extend", "stop"}:
                    state.request(ws, message.data)
            elif message.type in {WSMsgType.ERROR, WSMsgType.CLOSE, WSMsgType.CLOSED}:
                break
    except (ConnectionError, asyncio.CancelledError):
        pass
    finally:
        state.disconnect(ws)
    return ws


async def playback(request):
    state = request.app[STATE]
    path = request.match_info
    file = path["file"]
    if state.status()["generation"] != path["generation"] or not MEDIA_FILE.fullmatch(file):
        raise web.HTTPNotFound()
    endpoint = f"{request.app[MEDIA]}/live/{path['generation']}/{path['lane']}/{file}"
    try:
        token = request.app[MEDIA_TOKEN]
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        async with request.app[HTTP].get(
            endpoint, headers=headers, allow_redirects=False, timeout=ClientTimeout(total=15)
        ) as upstream:
            if upstream.status != 200:
                return web.Response(status=upstream.status if upstream.status >= 400 else 502)
            # A new session can start while an old segment was in transit.
            data = await upstream.read()
            if state.status()["generation"] != path["generation"]:
                raise web.HTTPNotFound()
            return web.Response(body=data, headers={"Content-Type": upstream.headers.get(
                "Content-Type", "application/octet-stream"
            )})
    except (ClientError, TimeoutError):
        raise web.HTTPBadGateway() from None


def make_app(config, *, ingress=True, worker=None, clock=None,
             media="http://127.0.0.1:8097", media_token=""):
    app = web.Application(middlewares=[security], client_max_size=1024)
    app[TOKEN] = secrets.token_urlsafe(24)
    app[CONFIGURED] = bool(config.get("email") and config.get("password"))
    app[INGRESS] = ingress
    app[MEDIA] = media
    app[MEDIA_TOKEN] = media_token

    async def lifecycle(application):
        async with ClientSession(timeout=ClientTimeout(total=4)) as http:
            application[HTTP] = http

            async def camera(*args):
                return await run_camera(http, *args)

            kwargs = {"clock": clock} if clock is not None else {}
            state = Session(worker or camera, seconds=live_duration(config), **kwargs)
            application[STATE] = state

            async def check_viewers():
                while True:
                    state.tick()
                    await asyncio.sleep(.25 if state.task else 1)

            watchdog = asyncio.create_task(check_viewers())
            yield
            watchdog.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await watchdog
            await state.close()

    async def shutdown(application):
        await application[STATE].close()
        await asyncio.gather(*(ws.close() for ws in tuple(application[STATE].viewers)))

    app.cleanup_ctx.append(lifecycle)
    app.on_shutdown.append(shutdown)
    app.router.add_get("/", index)
    app.router.add_get("/assets/{name}", asset)
    app.router.add_get("/api/events", events, allow_head=False)
    app.router.add_get(r"/media/{generation:[a-f0-9]{32}}/{lane:[01]}/{file}", playback, allow_head=False)
    return app


async def with_relay():
    token = secrets.token_urlsafe(24)
    app = make_app(
        options(), ingress=os.getenv("COCOCAM_MODE", "ingress") == "ingress",
        media_token=token,
    )

    async def relay(_app):
        child = await asyncio.create_subprocess_exec(
            "mediamtx", str(HERE.parent / "mediamtx.yml"), start_new_session=True,
            env=os.environ | {"MTX_HLSCDNSECRET": token},
        )
        try:
            yield
        finally:
            await terminate(child)

    app.cleanup_ctx.insert(0, relay)
    return app


if __name__ == "__main__":
    web.run_app(with_relay(), host="0.0.0.0", port=8099, access_log=None, print=None)
