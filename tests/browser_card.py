"""Exercise the dashboard module and embedded player in Chromium with a fake camera."""

import asyncio
import base64
import os
import tempfile
from pathlib import Path

from aiohttp import web
from aiohttp.test_utils import TestServer
from playwright.async_api import async_playwright, expect

from bridge.server import STATE, make_app

ROOT = Path(__file__).resolve().parents[1]
PREFIX = "/api/hassio_ingress/test-token/"
COOKIE = "test-session"
HLS = """
window.Hls = class {
  static isSupported() { return true; }
  static Events = {ERROR: 'error', MANIFEST_PARSED: 'manifest'};
  on() {}
  attachMedia() {}
  destroy() {}
  async loadSource(source) { await fetch(source); }
};
"""


async def check(hls_path):
    os.environ["COCOCAM_HLS_JS"] = str(hls_path)
    now = [100.0]
    starts, stops, lanes = [], [], []
    relay = web.Application()

    async def playlist(request):
        lanes.append(request.match_info["lane"])
        return web.Response(text="#EXTM3U\n", content_type="application/mpegurl")

    relay.router.add_get("/live/{generation}/{lane}/index.m3u8", playlist)

    async def worker(generation, ready, stop):
        starts.append(generation)
        ready()
        await stop.wait()
        stops.append(generation)

    @web.middleware
    async def authenticate(request, handler):
        if request.path.startswith(PREFIX) and request.cookies.get("ingress_session") != COOKIE:
            raise web.HTTPUnauthorized()
        return await handler(request)

    resource = base64.b64encode((ROOT / "dashboard/cococam-card.js").read_bytes()).decode()

    async def dashboard(request):
        view = request.match_info["view"]
        assert view in {"1", "2", "both", "panel", "passive"}
        if view in {"panel", "passive"}:
            query = "?embed=both" if view == "passive" else ""
            return web.Response(text=f'<iframe src="{PREFIX}{query}"></iframe>', content_type="text/html")
        return web.Response(text=f"""
            <cococam-card></cocam-card>
            <script type="module">
            import "data:text/javascript;base64,{resource}";
            const card = document.querySelector("cococam-card");
            card.setConfig({{view: "{view}"}});
            window.calls = [];
            card.hass = {{callWS: async (message) => {{
                window.calls.push(message.type);
                if (message.type === "supervisor/ingress/info") {{
                    return {{state: "started", ingress_url: "{PREFIX.rstrip('/')}"}};
                }}
                if (message.type === "supervisor/ingress/session") return {{session: "{COOKIE}"}};
                throw new Error(message.type);
            }}}};
            </script>
        """, content_type="text/html")

    async def until(predicate):
        async with asyncio.timeout(5):
            while not predicate():
                await asyncio.sleep(.03)

    async with TestServer(relay) as media, async_playwright() as driver:
        bridge = make_app({"email": "test@example.invalid", "password": "unused", "live_seconds": 15},
                          ingress=False, worker=worker, clock=lambda: now[0],
                          media=str(media.make_url("")).rstrip("/"))
        mock = web.Application(middlewares=[authenticate])
        mock.router.add_get("/dashboard/{view}", dashboard)
        mock.add_subapp(PREFIX, bridge)
        async with TestServer(mock) as site:
            browser = await driver.chromium.launch()
            try:
                page = await browser.new_page()
                await page.add_init_script("HTMLMediaElement.prototype.canPlayType = () => ''")
                page_errors = []
                page.on("pageerror", lambda error: page_errors.append(str(error)))
                for view, expected in (("1", {"0"}), ("2", {"1"}), ("both", {"0", "1"})):
                    count = len(starts)
                    lanes.clear()
                    await page.goto(str(site.make_url(f"/dashboard/{view}")))
                    launcher = page.get_by_role("button", name="Voir le direct")
                    await expect(launcher).to_be_visible()
                    assert await page.evaluate("window.calls") == []
                    assert len(starts) == count
                    await launcher.click()
                    iframe = page.frame_locator("iframe")
                    await expect(iframe.locator("#status")).to_have_text("En direct")
                    assert await page.evaluate("window.calls") == [
                        "supervisor/ingress/info", "supervisor/ingress/session",
                    ]
                    await until(lambda: len(lanes) >= len(expected))
                    assert set(lanes) == expected, lanes
                    assert len(starts) == count + 1
                    for lane in ("0", "1"):
                        tile = iframe.locator(f"#lane-{lane}")
                        if lane in expected:
                            await expect(tile).to_be_visible()
                        else:
                            await expect(tile).to_be_hidden()

                    now[0] += 5
                    await expect(iframe.locator("#timer")).to_have_text("10 s")
                    await iframe.get_by_role("button", name="Prolonger").click()
                    await expect(iframe.locator("#timer")).to_have_text("15 s")
                    now[0] += 16
                    await expect(iframe.locator("#status")).to_have_text("Temps écoulé.")
                    await until(lambda: len(stops) == count + 1)
                    assert len(starts) == count + 1
                    await iframe.get_by_role("button", name="Rouvrir le direct").click()
                    await expect(iframe.locator("#status")).to_have_text("En direct")
                    assert len(starts) == count + 2
                    if view == "both":
                        await page.locator("cococam-card").evaluate("card => card.remove()")
                        await until(lambda: bridge[STATE].empty_deadline is not None)
                        now[0] += 9
                    else:
                        await iframe.get_by_role("button", name="Couper").click()
                        await expect(iframe.locator("#status")).to_have_text("Direct coupé.")
                    await until(lambda: len(stops) == count + 2)

                count = len(starts)
                await page.goto(str(site.make_url("/dashboard/passive")))
                await expect(page.frame_locator("iframe").locator("#status")).to_have_text("Caméra au repos.")
                assert len(starts) == count
                await page.goto(str(site.make_url("/dashboard/panel")))
                iframe = page.frame_locator("iframe")
                await expect(iframe.locator("#status")).to_have_text("En direct")
                assert len(starts) == count + 1
                await iframe.get_by_role("button", name="Couper").click()
                assert not page_errors, page_errors
            finally:
                await browser.close()


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as directory:
        script = Path(directory) / "hls.js"
        script.write_text(HLS)
        asyncio.run(check(script))
    print("Carte COCOCAM : trois sélections, lecture au clic, arrêt et panneau vérifiés.")
