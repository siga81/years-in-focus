"""Seekable cards-only rendering using the export's geometry and compositing."""
from bisect import bisect_right
from collections import OrderedDict
import numpy as np
from facemovie.rendering.stack import _card_layer, median_face_ratio
from facemovie.rendering.video import frame_counts


class PreparedDissolve:
    """Reusable float layers; slider rendering needs no image loading or worker."""
    def __init__(self, base, color, alpha, static):
        self.base = base.astype(np.float32)
        self.color = color.astype(np.float32)
        self.alpha = (alpha.astype(np.float32) / 255.0)[..., None]
        self.static = static

    def frame(self, opacity):
        if opacity is None:
            return self.static
        weight = self.alpha * opacity
        result = self.color * weight + self.base * (1.0 - weight)
        return np.clip(result, 0, 255).astype(np.uint8)


class CardTimeline:
    def __init__(self, count, fps, hold, transition, edge_fades=True):
        self.fps = fps
        self.hold_frames, self.transition_frames = frame_counts(fps, hold, transition)
        self.starts = []
        self.length = 0
        for index in range(count):
            self.starts.append(self.length)
            self.length += self.hold_frames + (self.transition_frames if index or edge_fades else 0)
        if not count:
            raise ValueError("Empty card sequence")
        self.edge_fades = edge_fades

    def position(self, frame):
        frame = max(0, min(self.length - 1, int(frame)))
        index = bisect_right(self.starts, frame) - 1
        local = frame - self.starts[index]
        transition = self.transition_frames if index or self.edge_fades else 0
        return index, (local + 1) / transition if local < transition else None

    def hold_position(self, index):
        return self.starts[index] + (self.transition_frames if index or self.edge_fades else 0)


class CardProbeRenderer:
    def __init__(self, entries, project, size, cancelled=lambda: False, progress=lambda *_: None):
        self.entries, self.size = entries, size
        self.project = project
        self.cancelled, self.progress = cancelled, progress
        self.limit = 1 if project.movie_mode == "timelapse" else project.max_visible_cards
        self.ratio = median_face_ratio([e[1] for e in entries], [e[2] for e in entries])
        self.layers = OrderedDict()
        self.checkpoints = OrderedDict()
        self.pair = None
        self.pair_index = None

    def check(self):
        if self.cancelled():
            raise InterruptedError("Rendering cancelled")

    def layer(self, index):
        self.check()
        if index not in self.layers:
            path, landmarks, height = self.entries[index]
            p = self.project
            self.layers[index] = _card_layer(path, landmarks, self.size, p.eye_y, p.eye_distance,
                p.border_pixels if p.border_enabled else 0, p.border_color, self.ratio, 0.0, height)
        self.layers.move_to_end(index)
        while len(self.layers) > 4:
            self.layers.popitem(last=False)
        return self.layers[index]

    def composite(self, last):
        width, height = self.size
        start = max(0, last - self.limit + 1) if self.limit else 0
        result = np.zeros((height, width, 3), np.float32)
        if not self.limit:
            previous = [index for index in self.checkpoints if index <= last]
            if previous:
                checkpoint = max(previous)
                result = self.checkpoints[checkpoint].copy()
                self.checkpoints.move_to_end(checkpoint)
                start = checkpoint + 1
        for index in range(start, last + 1):
            self.check()
            color, alpha = self.layer(index)
            weight = (alpha.astype(np.float32) / 255.0)[..., None]
            result = color.astype(np.float32) * weight + result * (1.0 - weight)
            if not self.limit and (index % 16 == 0 or index == last):
                self.checkpoints[index] = result.copy()
                self.checkpoints.move_to_end(index)
                while len(self.checkpoints) > 4:
                    self.checkpoints.popitem(last=False)
            self.progress(index + 1, last + 1)
        return np.clip(result, 0, 255).astype(np.uint8)

    def frame(self, index, opacity):
        self.check()
        if index != self.pair_index:
            base = self.composite(index - 1)
            card = self.layer(index)
            static = self.composite(index)
            self.pair = base, card, static
            self.dissolve = PreparedDissolve(base, *card, static)
            self.pair_index = index
        return self.dissolve.frame(opacity)
