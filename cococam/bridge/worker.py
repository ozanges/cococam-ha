"""Own a single authenticated CloudEdge connection and its two publishers."""

import logging
import re
import signal
import struct
import subprocess
import sys
import threading
from contextlib import suppress

from .cloud import cloud_client, select_camera
from .settings import options

START_CODE = re.compile(rb"\x00\x00(?:\x00)?\x01")


def read_frame(chunk, decrypt):
    if chunk[:4] == b"\0\0\1\xfc":
        header, length_offset, extra = 48, 12, 16
    elif chunk[:4] == b"\0\0\1\xfd":
        header, length_offset, extra = 40, 4, 8
    else:
        return None
    if len(chunk) < header + 12 or struct.unpack_from("<I", chunk, length_offset)[0] + extra != len(chunk):
        return None
    index, lane = struct.unpack_from("<IH", chunk, header - 32)
    if lane not in (0, 1):
        return None

    for encrypted in (False, True):
        data = decrypt(bytearray(chunk)) if encrypted else chunk
        payload = bytes(data[header + 12:])
        if struct.unpack_from("<I", data, header + 8)[0] != len(payload):
            continue
        starts = list(START_CODE.finditer(payload))
        if not starts or starts[0].start() != 0:
            continue
        types = set()
        for start in starts:
            nal = payload[start.end():start.end() + 2]
            if len(nal) != 2 or nal[0] & 0x80 or not nal[1] & 7:
                break
            nal_type = (nal[0] >> 1) & 0x3f
            if nal_type > 40:
                break
            types.add(nal_type)
        else:
            irap = {32, 33, 34} <= types and bool(types.intersection(range(16, 24)))
            if (header == 48 and irap) or (header == 40 and bool(types.intersection(range(32)))):
                return index, lane, payload, irap
    return None


def command(generation, lane, rtsp_port):
    url = f"rtsp://127.0.0.1:{rtsp_port}/live/{generation}/{lane}"
    return [
        "ffmpeg", "-nostdin", "-loglevel", "error", "-analyzeduration", "500000", "-probesize", "65536",
        "-f", "hevc", "-framerate", "15", "-i", "pipe:0", "-map", "0:v:0", "-an",
        "-c:v", "copy", "-f", "rtsp", "-rtsp_transport", "tcp", url,
    ]


class Outputs:
    def __init__(self, generation, rtsp_port):
        self.generation, self.rtsp_port = generation, rtsp_port
        self.index = {}
        self.awaiting = {0, 1}
        self.publishers = {}

    def write(self, index, lane, payload, irap):
        previous = self.index.get(lane)
        if previous is not None and index != (previous + 1) & 0xffffffff:
            if index == previous and not irap:
                return
            self.awaiting.add(lane)
        self.index[lane] = index
        if irap:
            self.awaiting.discard(lane)
        if lane in self.awaiting:
            return
        if lane not in self.publishers:
            self.publishers[lane] = subprocess.Popen(
                command(self.generation, lane, self.rtsp_port), stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        self.publishers[lane].stdin.write(payload)
        self.publishers[lane].stdin.flush()

    def close(self):
        for process in self.publishers.values():
            if process.poll() is None:
                process.terminate()
        for process in self.publishers.values():
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            try:
                process.stdin.close()
            except BrokenPipeError:
                pass


def main(generation, rtsp_port):
    logging.disable(logging.CRITICAL)
    stop = threading.Event()
    for signum in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signum, lambda *_: stop.set())
    output = Outputs(generation, rtsp_port)
    failure = []

    def receive():
        phase = "worker"
        try:
            config = options()
            if not config.get("email") or not config.get("password"):
                failure.append("credentials")
                return
            api, mods = cloud_client(config)
            from custom_components.cloudplus.p2p_streamer.codec import decrypt_stream_frame

            phase = "login"
            api.login()
            if stop.is_set():
                return
            phase = "camera_selection"
            device = select_camera(api, config)
            if device is None:
                failure.append(phase)
                return
            phase = "stream"
            api.vvp_stream_flag = 24
            base = mods["p2p_streamer"].P2PStreamer

            class CameraStream(base):
                def _parse_stream_chunk(self, chunk):
                    if not stop.is_set():
                        frame = read_frame(chunk, decrypt_stream_frame)
                        if frame:
                            output.write(*frame)
                    return super()._parse_stream_chunk(chunk)

            streamer = CameraStream(api=api, device=device, vvp_quality=105)
            active.append(streamer)
            if not stop.is_set():
                streamer.run_session()
        except Exception:
            failure.append(phase)

    active = []
    thread = threading.Thread(target=receive, daemon=True)
    thread.start()
    while thread.is_alive() and not stop.wait(.15):
        pass
    if stop.is_set() and active:
        with suppress(OSError, RuntimeError):
            active[0].request_stop()
    thread.join(timeout=2)
    output.close()
    print(failure[0] if failure else "disconnected", flush=True)


if __name__ == "__main__":
    main(sys.argv[1], int(sys.argv[2]))
