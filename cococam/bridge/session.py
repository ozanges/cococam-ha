"""Own the single camera session and enforce viewing limits server-side."""

import asyncio
import math
import time
import uuid
from contextlib import suppress


class Session:
    def __init__(self, worker, *, seconds=60, startup=110, grace=8, clock=time.monotonic):
        self.worker = worker
        self.seconds, self.startup, self.grace = seconds, startup, grace
        self.clock = clock
        self.phase = "idle"
        self.reason = None
        self.generation = None
        self.deadline = None
        self.empty_deadline = None
        self.viewers = set()
        self.task = None
        self.stop_event = None

    def connect(self, viewer):
        self.viewers.add(viewer)
        self.empty_deadline = None

    def disconnect(self, viewer):
        self.viewers.discard(viewer)
        if not self.viewers and self.task and self.empty_deadline is None:
            self.empty_deadline = self.clock() + self.grace

    def request(self, viewer, action):
        self.tick()
        if viewer not in self.viewers:
            return
        if action == "stop":
            self.stop("manual")
        elif action == "extend" and self.phase == "live":
            self.deadline = self.clock() + self.seconds
        elif not self.task and (action == "start" or (action == "open" and self.phase == "idle")):
            self.generation = uuid.uuid4().hex
            self.phase, self.reason = "opening", None
            self.deadline = self.clock() + self.startup
            self.stop_event = asyncio.Event()
            self.task = asyncio.create_task(self._run(self.generation, self.stop_event))

    async def _run(self, generation, stop):
        def ready():
            self.tick()
            if not stop.is_set() and self.phase == "opening":
                self.phase = "live"
                self.deadline = self.clock() + self.seconds

        try:
            if not stop.is_set():
                error = await self.worker(generation, ready, stop)
                if not stop.is_set():
                    self.phase = "failed"
                    self.reason = error or "disconnected"
        except Exception:
            if not stop.is_set():
                self.phase, self.reason = "failed", "worker"
        finally:
            self.task = None
            self.generation = self.deadline = self.empty_deadline = None
            self.stop_event = None

    def stop(self, reason):
        if self.stop_event and not self.stop_event.is_set():
            self.stop_event.set()
            self.phase, self.reason = ("idle", None) if reason == "empty" else ("paused", reason)
            self.deadline = None

    def tick(self):
        if self.deadline is not None and self.clock() >= self.deadline:
            self.stop("startup_timeout" if self.phase == "opening" else "timeout")
        if self.empty_deadline is not None and self.clock() >= self.empty_deadline:
            self.stop("empty")

    def status(self):
        self.tick()
        return {
            "phase": self.phase,
            "reason": self.reason,
            "generation": self.generation if self.phase == "live" else None,
            "remaining": max(0, math.ceil(self.deadline - self.clock())) if self.deadline else 0,
            "live_seconds": self.seconds,
            "stopping": bool(self.stop_event and self.stop_event.is_set()),
        }

    async def close(self):
        if self.task:
            task = self.task
            self.stop("shutdown")
            with suppress(asyncio.CancelledError):
                await task
