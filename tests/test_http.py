import asyncio
import re
import unittest

from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from bridge.server import STATE, make_app

CONFIG = {"email": "local@example.invalid", "password": "unused", "live_seconds": 15}


class HttpTest(unittest.IsolatedAsyncioTestCase):
    async def test_media_only_for_current_generation(self):
        now = [100.0]
        upstream = web.Application()
        seen = []

        async def playlist(request):
            seen.append(request.path)
            return web.Response(text="#EXTM3U\nstream.m3u8\n", content_type="application/mpegurl")

        upstream.router.add_get("/live/{generation}/{lane}/index.m3u8", playlist)

        async def worker(_generation, ready, done):
            ready()
            await done.wait()

        async with TestServer(upstream) as relay:
            app = make_app(CONFIG, ingress=False, worker=worker, clock=lambda: now[0],
                           media=str(relay.make_url("")).rstrip("/"))
            async with TestClient(TestServer(app)) as client:
                self.assertEqual((await client.get("/api/events?key=bad")).status, 403)
                response = await client.get("/")
                key = re.search(r'cococam-key" content="([^"]+)"', await response.text())[1]
                async with client.ws_connect("/api/events", params={"key": key}) as ws:
                    await ws.send_str("open")
                    for _ in range(4):
                        message = await asyncio.wait_for(ws.receive_json(), 2)
                        if message["phase"] == "live":
                            break
                    path = f"/media/{message['generation']}/0/index.m3u8"
                    response = await client.get(path)
                    self.assertEqual(response.status, 200)
                    self.assertIn("#EXTM3U", await response.text())
                    self.assertEqual(response.headers["Cache-Control"], "no-store")
                    now[0] += 16
                    self.assertEqual((await client.get(path)).status, 404)
                    self.assertEqual(len(seen), 1)
                    self.assertEqual(app[STATE].status()["reason"], "timeout")

    async def test_untrusted_ingress_peer_is_denied(self):
        async with TestClient(TestServer(make_app(CONFIG))) as client:
            self.assertEqual((await client.get("/", headers={"X-Forwarded-For": "172.30.32.2"})).status, 403)
