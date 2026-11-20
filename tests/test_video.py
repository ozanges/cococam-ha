import struct
import unittest

from bridge.worker import read_frame


def iframe(lane):
    annexb = b"".join(b"\0\0\0\1" + bytes((nal << 1, 1, 123)) for nal in (32, 33, 34, 19))
    data = bytearray(48)
    data[:4] = b"\0\0\1\xfc"
    struct.pack_into("<IIH", data, 12, len(annexb) + 44, 7, lane)
    return bytes(data) + struct.pack("<III", 400, 0, len(annexb)) + annexb


class VideoTest(unittest.TestCase):
    def test_identical_sequence_is_separate_for_both_lanes(self):
        for lane in (0, 1):
            frame = iframe(lane)
            self.assertEqual(read_frame(frame, bytes), (7, lane, frame[60:], True))

    def test_incomplete_or_unknown_frame(self):
        self.assertIsNone(read_frame(iframe(0)[:-1], bytes))
        self.assertIsNone(read_frame(iframe(2), bytes))
