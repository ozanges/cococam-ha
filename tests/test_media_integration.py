"""Exercise MediaMTX, both HLS routes and the real FFmpeg decoder without a camera."""

import asyncio
import os
import re
import tempfile
import unittest
from contextlib import AsyncExitStack
from pathlib import Path

from aiohttp.test_utils import TestClient, TestServer

from bridge.server import make_app, terminate


async def background(stack, command, *, env=None):
    child = await asyncio.create_subprocess_exec(
        *command, env=env, start_new_session=True, stdout=asyncio.subprocess.DEVNULL,
        stderr=None if os.getenv("COCOCAM_MEDIA_DEBUG") else asyncio.subprocess.DEVNULL,
    )
    stack.push_async_callback(terminate, child)
    return child


@unittest.skipUnless(os.getenv("COCOCAM_MEDIA_TEST") == "1", "requires FFmpeg and MediaMTX")
class MediaIntegrationTest(unittest.IsolatedAsyncioTestCase):
    async def test_two_hls_views_stop_together(self):
        async with AsyncExitStack() as stack:
            fixture = Path(stack.enter_context(tempfile.TemporaryDirectory())) / "sample.hevc"
            producer = await background(stack, [
                "ffmpeg", "-f", "lavfi", "-i", "testsrc2=size=160x96:rate=15",
                "-t", "20", "-an", "-c:v", "libx265", "-preset", "ultrafast",
                "-x265-params", "pools=1:frame-threads=1:keyint=15:bframes=0:repeat-headers=1",
                "-f", "hevc", str(fixture),
            ])
            self.assertEqual(await asyncio.wait_for(producer.wait(), 30), 0)
            token = "test-only-relay-token"
            relay = await background(stack, ["mediamtx", str(
                Path(__file__).resolve().parents[1] / "cococam/mediamtx.yml"
            )], env=os.environ | {"MTX_HLSCDNSECRET": token})
            stopped = asyncio.Event()

            async def fixture_worker(generation, ready, done):
                async with AsyncExitStack() as publishers:
                    for lane in (0, 1):
                        await background(publishers, [
                            "ffmpeg", "-nostdin", "-re", "-framerate", "15", "-i", str(fixture),
                            "-c:v", "copy", "-f", "rtsp", "-rtsp_transport", "tcp",
                            f"rtsp://127.0.0.1:8556/live/{generation}/{lane}",
                        ])
                    await asyncio.sleep(1)
                    ready()
                    await done.wait()
                stopped.set()

            config = {"email": "integration@example.invalid", "password": "unused"}
            client = await stack.enter_async_context(TestClient(TestServer(
                make_app(config, ingress=False, worker=fixture_worker, media_token=token)
            )))
            result = await client.get("/")
            key = re.search(r'cococam-key" content="([^"]+)"', await result.text())[1]
            websocket = await stack.enter_async_context(client.ws_connect("/api/events", params={"key": key}))
            self.assertIsNone(relay.returncode)
            await websocket.send_str("open")
            for _ in range(6):
                message = await asyncio.wait_for(websocket.receive_json(), 3)
                if message["phase"] == "live":
                    break
            self.assertEqual(message["phase"], "live")

            async def read_video(lane):
                path = f"/media/{message['generation']}/{lane}/index.m3u8"
                for _ in range(40):
                    async with client.get(path) as response:
                        playlist = await response.text()
                        if response.status == 200 and "#EXTM3U" in playlist:
                            break
                    await asyncio.sleep(.3)
                self.assertIn("#EXTM3U", playlist, f"{path}: {response.status}")
                if os.getenv("COCOCAM_MEDIA_DEBUG"):
                    print(playlist)
                reader = await asyncio.create_subprocess_exec(
                    "ffmpeg", "-nostdin", "-v", "error", "-i", str(client.make_url(path)),
                    "-frames:v", "5", "-f", "framemd5", "pipe:1", stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE, start_new_session=True,
                )
                stack.push_async_callback(terminate, reader)
                video, errors = await asyncio.wait_for(reader.communicate(), 13)
                self.assertEqual(reader.returncode, 0, errors.decode())
                self.assertEqual(sum(line[:1].isdigit() for line in video.splitlines()), 5)
                return path

            paths = await asyncio.gather(*(read_video(lane) for lane in (0, 1)))
            await websocket.send_str("stop")
            await asyncio.wait_for(stopped.wait(), 8)
            for path in paths:
                async with client.get(path) as response:
                    self.assertEqual(response.status, 404)
