import asyncio
import unittest

from bridge.session import Session


class SessionTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.now = 100.0
        self.workers = []

        async def worker(generation, ready, stop):
            self.workers.append((generation, ready, stop))
            await stop.wait()

        self.state = Session(worker, clock=lambda: self.now, seconds=60, startup=110, grace=8)
        self.addAsyncCleanup(self.state.close)

    async def open(self, viewer="one", *, ready=True):
        self.state.connect(viewer)
        self.state.request(viewer, "open")
        await asyncio.sleep(0)
        task = self.state.task
        if ready:
            self.workers[-1][1]()
        return task

    async def test_expiry_and_reopen_require_explicit_action(self):
        task = await self.open()
        first = self.state.status()["generation"]
        self.now += 60
        self.assertEqual(self.state.status()["reason"], "timeout")
        self.assertIsNone(self.state.status()["generation"])
        await task
        await self.open("reloaded", ready=False)
        self.assertEqual(len(self.workers), 1)
        self.state.request("reloaded", "extend")
        await asyncio.sleep(0)
        self.assertEqual(len(self.workers), 1)
        self.state.request("reloaded", "start")
        await asyncio.sleep(0)
        self.workers[-1][1]()
        self.assertNotEqual(first, self.state.status()["generation"])

    async def test_one_camera_for_two_viewers_and_grace(self):
        task = await self.open()
        self.now += 30
        await self.open("two", ready=False)
        self.assertEqual(len(self.workers), 1)
        self.assertEqual(self.state.status()["remaining"], 30)
        self.state.disconnect("one")
        self.now += 10
        self.assertEqual(self.state.status()["phase"], "live")
        self.state.disconnect("two")
        self.now += 7
        self.assertEqual(self.state.status()["phase"], "live")
        await self.open("three", ready=False)
        self.assertEqual(len(self.workers), 1)
        self.state.disconnect("three")
        self.now += 8
        self.assertEqual(self.state.status()["phase"], "idle")
        await task
        self.assertTrue(self.workers[0][2].is_set())

    async def test_extend_and_startup_timeout(self):
        task = await self.open(ready=False)
        self.now += 109
        self.assertEqual(self.state.status()["phase"], "opening")
        self.workers[-1][1]()
        self.now += 50
        self.state.request("one", "extend")
        self.assertEqual(self.state.status()["remaining"], 60)
        self.state.request("one", "stop")
        await task
        self.state.request("one", "start")
        await asyncio.sleep(0)
        task = self.state.task
        self.now += 111
        self.assertEqual(self.state.status()["reason"], "startup_timeout")
        self.workers[-1][1]()
        await task
        self.assertIsNone(self.state.status()["generation"])

    async def test_stop_before_worker_starts(self):
        self.state.connect("one")
        self.state.request("one", "open")
        task = self.state.task
        self.state.request("one", "stop")
        await task
        self.assertEqual(self.workers, [])
