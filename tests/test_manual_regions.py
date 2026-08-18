from __future__ import annotations

import unittest

import numpy as np

from facemovie.vision.yunet import YuNetLandmarker


class _Detector:
    def __init__(self) -> None:
        self.size: tuple[int, int] | None = None

    def setInputSize(self, size: tuple[int, int]) -> None:
        self.size = size

    def detect(self, _image):
        return None, np.asarray([
            [10, 20, 30, 40, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0.9],
            [95, 90, 30, 30, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0.8],
        ], dtype=np.float32)


class ManualRegionCandidateTests(unittest.TestCase):
    def test_candidates_keep_source_coordinates_and_clip_to_image(self) -> None:
        detector = _Detector()
        landmarker = YuNetLandmarker.__new__(YuNetLandmarker)
        landmarker.detector = detector
        candidates = landmarker.detect_candidates(np.zeros((100, 100, 3), dtype=np.uint8), "Test person")
        self.assertEqual(detector.size, (100, 100))
        self.assertEqual(len(candidates), 2)
        self.assertEqual(candidates[0].name, "Test person")
        self.assertEqual(candidates[0].source, "yunet_candidate")
        self.assertEqual((candidates[1].x, candidates[1].y, candidates[1].width, candidates[1].height), (95.0, 90.0, 5.0, 10.0))

