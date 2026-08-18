"""Local target-face marking for untagged Years in Focus imports."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

import cv2
import numpy as np
from PIL import Image, ImageOps, ImageTk

from facemovie.models import FaceRegion
from facemovie.vision.yunet import YuNetLandmarker


class ManualRegionDialog:
    """Show candidates and let the user explicitly confirm one target per photo."""

    CANVAS_WIDTH = 960
    CANVAS_HEIGHT = 620

    def __init__(
        self, parent: tk.Misc, paths: tuple[Path, ...], model_path: Path, t,
        person_name: str | None = None, initial_regions: dict[str, FaceRegion] | None = None,
        allow_person_name_edit: bool = True, confirm_on_last_image: bool = True,
    ) -> None:
        self.parent, self.paths, self.t = parent, paths, t
        self.detector = YuNetLandmarker(model_path)
        self.index = 0
        self.regions: dict[str, FaceRegion] = dict(initial_regions or {})
        self.result: tuple[str, dict[str, FaceRegion]] | None = None
        self.candidates: list[FaceRegion] = []
        self.confirm_on_last_image = confirm_on_last_image
        self.selected: FaceRegion | None = None
        self.manual_mode = False
        self._drag_start: tuple[float, float] | None = None
        self._image_origin = (0.0, 0.0)
        self._display_scale = 1.0
        self._image_size = (1, 1)
        self._current_image: Image.Image | None = None
        self._photo: ImageTk.PhotoImage | None = None

        self.dialog = tk.Toplevel(parent)
        self.dialog.title(t("manual_faces_title"))
        self.dialog.transient(parent)
        self.dialog.grab_set()
        self.dialog.protocol("WM_DELETE_WINDOW", self.cancel)
        self.dialog.minsize(820, 620)
        header = ttk.Frame(self.dialog, padding=(16, 14, 16, 8))
        header.pack(fill="x")
        ttk.Label(header, text=t("manual_faces_heading"), font=("Segoe UI", 12, "bold")).pack(anchor="w")
        ttk.Label(header, text=t("manual_faces_intro"), foreground="#666", wraplength=900).pack(anchor="w", pady=(3, 8))
        name_row = ttk.Frame(header)
        name_row.pack(fill="x")
        ttk.Label(name_row, text=t("manual_faces_name")).pack(side="left")
        self.person_var = tk.StringVar(value=person_name or t("manual_faces_default_name"))
        if allow_person_name_edit:
            ttk.Entry(name_row, textvariable=self.person_var, width=34).pack(side="left", padx=(8, 0))
        else:
            ttk.Label(name_row, textvariable=self.person_var).pack(side="left", padx=(8, 0))
        self.progress = ttk.Label(header, foreground="#356b8f")
        self.progress.pack(anchor="w", pady=(8, 0))
        self.canvas = tk.Canvas(self.dialog, width=self.CANVAS_WIDTH, height=self.CANVAS_HEIGHT, bg="#202020", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True, padx=16, pady=(0, 8))
        self.canvas.bind("<ButtonPress-1>", self._start_manual_rectangle)
        self.canvas.bind("<B1-Motion>", self._draw_manual_rectangle)
        self.canvas.bind("<ButtonRelease-1>", self._finish_manual_rectangle)
        self.status = ttk.Label(self.dialog, padding=(16, 0, 16, 8), foreground="#666", wraplength=900)
        self.status.pack(fill="x")
        buttons = ttk.Frame(self.dialog, padding=(16, 0, 16, 16))
        buttons.pack(fill="x")
        ttk.Button(buttons, text=t("cancel"), command=self.cancel).pack(side="right")
        ttk.Button(buttons, text=t("manual_faces_next"), command=self.accept_and_next).pack(side="right", padx=(0, 18))
        ttk.Button(buttons, text=t("manual_faces_skip"), command=self.skip).pack(side="right", padx=(0, 6))
        ttk.Button(buttons, text=t("manual_faces_draw"), command=self.enable_manual_mode).pack(side="right", padx=(0, 6))
        self.previous_button = ttk.Button(buttons, text=t("manual_faces_previous"), command=self.previous)
        self.previous_button.pack(side="left")
        self.dialog.update_idletasks()
        self._load_current()

    def show(self) -> tuple[str, dict[str, FaceRegion]] | None:
        self.dialog.wait_window()
        return self.result

    def cancel(self) -> None:
        self.result = None
        self.dialog.destroy()

    def finish(self) -> None:
        if not self.regions:
            messagebox.showinfo(self.t("manual_faces_title"), self.t("manual_faces_none"), parent=self.dialog)
            return
        person = self.person_var.get().strip() or self.t("manual_faces_default_name")
        self.regions = {
            path: FaceRegion(person, region.x, region.y, region.width, region.height,
                             region.coordinate_system, region.source)
            for path, region in self.regions.items()
        }
        self.result = (person, self.regions)
        self.dialog.destroy()

    def _current_path(self) -> Path:
        return self.paths[self.index]

    def _load_current(self) -> None:
        path = self._current_path()
        self.progress.configure(text=self.t.format("manual_faces_progress", current=self.index + 1, total=len(self.paths), filename=path.name))
        self.previous_button.configure(state="normal" if self.index else "disabled")
        self.manual_mode, self._drag_start = False, None
        try:
            with Image.open(path) as original:
                image = ImageOps.exif_transpose(original).convert("RGB")
        except OSError as error:
            self.candidates, self.selected = [], None
            self.status.configure(text=self.t.format("manual_faces_unreadable", error=error), foreground="#a00000")
            return
        self._image_size = image.size
        self._current_image = image
        try:
            bgr = cv2.cvtColor(np.asarray(image), cv2.COLOR_RGB2BGR)
            self.candidates = self.detector.detect_candidates(bgr, self.person_var.get().strip())
        except cv2.error:
            self.candidates = []
        existing_region = self.regions.get(str(path.resolve()))
        self.selected = existing_region
        if self.selected is None and len(self.candidates) == 1:
            self.selected = self.candidates[0]
        if self.selected is not None:
            status, colour = (
                self.t("manual_faces_existing") if existing_region is not None else self.t("manual_faces_selected"),
                "#287c35",
            )
        elif self.candidates:
            status, colour = self.t.format("manual_faces_candidates", count=len(self.candidates)), "#666"
        else:
            status, colour = self.t("manual_faces_no_candidates"), "#a65e00"
        self.status.configure(text=status, foreground=colour)
        self._draw_image(image)

    def _draw_image(self, image: Image.Image) -> None:
        self.canvas.delete("all")
        # On the first Toplevel layout pass Tk can report a 1x1 canvas.  Falling
        # back to the requested size prevents the initial tiny image / black canvas
        # flash; later redraws naturally use the actual resized dimensions.
        canvas_width, canvas_height = self.canvas.winfo_width(), self.canvas.winfo_height()
        available_width = canvas_width if canvas_width >= 400 else self.CANVAS_WIDTH
        available_height = canvas_height if canvas_height >= 300 else self.CANVAS_HEIGHT
        scale = min(available_width / image.width, available_height / image.height, 1.0)
        size = (max(1, round(image.width * scale)), max(1, round(image.height * scale)))
        self._photo = ImageTk.PhotoImage(image.resize(size, Image.Resampling.LANCZOS))
        origin_x, origin_y = (available_width - size[0]) / 2, (available_height - size[1]) / 2
        self._image_origin, self._display_scale = (origin_x, origin_y), scale
        self.canvas.create_image(origin_x, origin_y, image=self._photo, anchor="nw")
        for candidate in self.candidates:
            self._draw_region(candidate, "#b8c1ca", 2)
        if self.selected is not None:
            self._draw_region(self.selected, "#24bb4c", 3)

    def _draw_region(self, region: FaceRegion, colour: str, width: int) -> None:
        x0, y0 = self._image_origin
        scale = self._display_scale
        self.canvas.create_rectangle(x0 + region.x * scale, y0 + region.y * scale, x0 + (region.x + region.width) * scale, y0 + (region.y + region.height) * scale, outline=colour, width=width)

    def _canvas_to_source(self, x: float, y: float) -> tuple[float, float] | None:
        origin_x, origin_y = self._image_origin
        source_x, source_y = (x - origin_x) / self._display_scale, (y - origin_y) / self._display_scale
        width, height = self._image_size
        return (source_x, source_y) if 0 <= source_x <= width and 0 <= source_y <= height else None

    def _redraw_current(self) -> None:
        if self._current_image is not None:
            self._draw_image(self._current_image)

    def enable_manual_mode(self) -> None:
        self.manual_mode = True
        self.status.configure(text=self.t("manual_faces_draw_hint"), foreground="#356b8f")

    def _start_manual_rectangle(self, event: tk.Event) -> None:
        point = self._canvas_to_source(event.x, event.y)
        if point is None:
            return
        if not self.manual_mode:
            for candidate in self.candidates:
                if candidate.x <= point[0] <= candidate.x + candidate.width and candidate.y <= point[1] <= candidate.y + candidate.height:
                    self.selected = candidate
                    # Fast review workflow: a deliberate click on a candidate is
                    # confirmation.  Store it immediately and advance; Back keeps
                    # a simple escape route for accidental clicks.
                    self.accept_and_next()
                    return
            return
        self._drag_start = point

    def _draw_manual_rectangle(self, event: tk.Event) -> None:
        if self._drag_start is None:
            return
        end = self._canvas_to_source(event.x, event.y)
        if end is None:
            return
        self.canvas.delete("manual")
        x0, y0 = self._image_origin
        scale = self._display_scale
        self.canvas.create_rectangle(
            x0 + self._drag_start[0] * scale, y0 + self._drag_start[1] * scale,
            x0 + end[0] * scale, y0 + end[1] * scale,
            outline="#24bb4c", width=3, tags="manual",
        )

    def _finish_manual_rectangle(self, event: tk.Event) -> None:
        if self._drag_start is None:
            return
        end, start = self._canvas_to_source(event.x, event.y), self._drag_start
        self._drag_start = None
        if end is None:
            return
        x1, x2 = sorted((start[0], end[0]))
        y1, y2 = sorted((start[1], end[1]))
        if x2 - x1 < 12 or y2 - y1 < 12:
            self.status.configure(text=self.t("manual_faces_draw_too_small"), foreground="#a65e00")
            return
        self.selected = FaceRegion(self.person_var.get().strip() or self.t("manual_faces_default_name"), x1, y1, x2 - x1, y2 - y1, "pixel_left_top", "yif_manual")
        self.manual_mode = False
        # Completing a manually drawn rectangle is equally an explicit
        # confirmation, so do not require a second button click for every image.
        self.accept_and_next()

    def accept_and_next(self) -> None:
        if self.selected is None:
            messagebox.showinfo(self.t("manual_faces_title"), self.t("manual_faces_choose_first"), parent=self.dialog)
            return
        person = self.person_var.get().strip() or self.t("manual_faces_default_name")
        selected = self.selected
        self.regions[str(self._current_path().resolve())] = FaceRegion(person, selected.x, selected.y, selected.width, selected.height, "pixel_left_top", "yif_manual_confirmed")
        if self.index >= len(self.paths) - 1:
            if self.confirm_on_last_image and not self._confirm_finish_on_last_image():
                return
            self.finish()
            return
        self.index += 1
        self._load_current()

    def skip(self) -> None:
        self.regions.pop(str(self._current_path().resolve()), None)
        if self.index >= len(self.paths) - 1:
            if self.confirm_on_last_image and not self._confirm_finish_on_last_image():
                return
            self.finish()
            return
        self.index += 1
        self._load_current()

    def _confirm_finish_on_last_image(self) -> bool:
        return messagebox.askyesno(
            self.t("manual_faces_title"), self.t("manual_faces_confirm_finish"), parent=self.dialog,
        )

    def previous(self) -> None:
        if self.index:
            self.index -= 1
            self._load_current()
