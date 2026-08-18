"""Local Tkinter UI for Years in Focus storyboard selection."""

from __future__ import annotations

import ctypes
import json
import math
import os
import queue
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import tkinter as tk
import webbrowser
from configparser import ConfigParser
from configparser import Error as ConfigParserError
from collections.abc import Callable
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from tkinter import colorchooser, filedialog, messagebox, ttk

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageOps, ImageTk

from facemovie import __version__
from facemovie.alignment import eye_geometry, similarity_matrix
from facemovie.branding import PRODUCT_NAME, tagline
from facemovie.digikam import (
    DigiKamConnection,
    DigiKamPerson,
    discover_digikam_connection,
    list_people,
    person_collection_subpaths,
    person_images,
)
from facemovie.i18n import Translator, localize_widget_tree
from facemovie.importing import ImportScan, scan_import_paths
from facemovie.manual_regions import ManualRegionDialog
from facemovie.metadata.xmp import find_region
from facemovie.models import FaceRegion, Landmarks
from facemovie.project import StoryboardCard, StoryboardProject
from facemovie.quality import assess
from facemovie.relink import RelinkSearch, find_unique_matches, normalised_path
from facemovie.rendering.audio import audio_duration_seconds, format_audio_duration
from facemovie.runtime import application_root, bundled_asset_root, bundled_cli_path
from facemovie.settings import (
    load_digikam_profile,
    load_language,
    load_recent_projects,
    load_show_quick_guide,
    save_digikam_profile,
    save_language,
    save_recent_project,
    save_show_quick_guide,
)
from facemovie.thumbnail_cache import ThumbnailCache
from facemovie.vision.mediapipe_landmarker import MediaPipeFaceLandmarker
from facemovie.vision.yunet import YuNetLandmarker

LARGE_IMPORT_THRESHOLD = 300
CARD_PAGE_SIZE = 240
KOFI_URL = "https://ko-fi.com/siga81"


def build_export_command(
    python_executable: str,
    workspace_root: Path,
    project_path: Path,
    project: StoryboardProject,
    output_path: Path,
    width: int | None = None,
    height: int | None = None,
    overwrite: bool = False,
) -> list[str]:
    """Build the reproducible command used by the storyboard export button."""
    # GUI builds keep shared models under `_internal`; the one-file CLI can
    # safely read that absolute path when it is launched as a helper.
    model_path = bundled_asset_root() / "models" / "mediapipe" / "face_landmarker.task"
    if getattr(sys, "frozen", False):
        command = [
            str(bundled_cli_path()),
            "render-project-video",
            "--project",
            str(project_path.resolve()),
            "--output",
            str(output_path.resolve()),
            "--width",
            str(width or project.output_width),
            "--height",
            str(height or project.output_height),
            "--mediapipe-model",
            str(model_path),
            "--person",
            project.person_name,
            "--eye-anchor",
            "iris",
            "--progress",
        ]
        if overwrite:
            command.append("--overwrite")
        return command
    command = [
        python_executable,
        "-m",
        "facemovie.cli",
        "render-project-video",
        "--project",
        str(project_path.resolve()),
        "--output",
        str(output_path.resolve()),
        "--width",
        str(width or project.output_width),
        "--height",
        str(height or project.output_height),
        "--mediapipe-model",
        str(model_path),
        "--person",
        project.person_name,
        "--eye-anchor",
        "iris",
        "--progress",
    ]
    if overwrite:
        command.append("--overwrite")
    return command


class StoryboardApp:
    def __init__(self, root: tk.Tk, project: StoryboardProject, project_path: Path) -> None:
        self.root = root
        self.project = project
        self.project_path = project_path
        self._thumbnail_disk_cache = ThumbnailCache(project_path)
        self.selected_index = 0
        self._thumb_cache: dict[tuple[str, int, int], ImageTk.PhotoImage] = {}
        self._thumbnail_prepare_messages: queue.Queue[tuple[str, int, int]] = queue.Queue()
        self._thumbnail_prepare_active = False
        self._thumbnail_prepare_current = 0
        self._thumbnail_prepare_total = 0
        self._thumbnail_prepare_last_ui_update = 0.0
        self._selected_preview_messages: queue.Queue[tuple[int, Image.Image | None, str | None]] = queue.Queue()
        self._selected_preview_token = 0
        self._selected_preview_source: str | None = None
        self._selected_preview_size: tuple[int, int] | None = None
        self._selected_preview_image: ImageTk.PhotoImage | None = None
        self._selected_preview_loading = False
        self._preview_resize_after_id: str | None = None
        self._preview_window: tk.Toplevel | None = None
        self.preview_label: tk.Label | None = None
        self._preview_context_menu: tk.Menu | None = None
        self._preview_alive = True
        self._card_widgets: list[tuple[tk.Frame, tk.Button, tk.Label, tk.Label]] = []
        self._last_styled_selected_index: int | None = None
        self._analysis_by_path: dict[str, dict] | None = None
        self._quality_tooltip: tk.Toplevel | None = None
        # Widget slots are a filtered projection of the project card list.
        # Keep the original indices so selection and drag/drop never change
        # meaning just because the view is filtered.
        self._visible_card_indices: list[int] = []
        self._filtered_card_indices: list[int] = []
        self._card_page = 0
        self._settings_vars: dict[str, tk.Variable] = {}
        self._export_process: subprocess.Popen[str] | None = None
        self._import_process: subprocess.Popen[str] | None = None
        self._import_cancelled = False
        self._export_cancelled = False
        self._import_lines: queue.Queue[str] = queue.Queue()
        self._export_lines: queue.Queue[str] = queue.Queue()
        self._import_log: list[str] = []
        self._export_log: list[str] = []
        self._relink_messages: queue.Queue[RelinkSearch | Exception] = queue.Queue()
        self._column_count = 3
        self._card_zoom = 1.0
        self._resize_after_id: str | None = None
        self._building_card_grid = False
        self._grid_rebuild_pending = False
        self._grid_build_state: tuple[list[int], int, int, int, int] | None = None
        self._year_separator_widgets: list[tuple[str, tk.Widget]] = []
        self._drag_source: int | None = None
        self._drag_start: tuple[int, int] | None = None
        self._drag_preview: tk.Toplevel | None = None
        self._drag_preview_image: ImageTk.PhotoImage | None = None
        self._digikam_profile = load_digikam_profile()
        self.t = Translator(load_language())
        self._show_quick_guide_var = tk.BooleanVar(value=load_show_quick_guide())
        self.preview_enabled_var = tk.BooleanVar(value=self.project.preview_enabled)
        self.year_separators_var = tk.BooleanVar(value=self.project.show_year_separators)
        self.advanced_output_var = tk.BooleanVar(value=self.project.advanced_output_options)
        self._saved_project_signature = self._project_signature()
        if self.project_path.is_file():
            save_recent_project(self.project_path)
        self._recent_projects = load_recent_projects()
        self._digikam_password = ""
        self._application_icon: tk.PhotoImage | None = None
        self.root.title(f"{PRODUCT_NAME} – {project.title}")
        self._set_application_icon()
        self.root.geometry("1260x820")
        self.root.minsize(980, 640)
        self._configure_application_style()
        self._build()
        localize_widget_tree(self.root, self.t)
        self._build_card_grid(chunked=len(self.project.cards) > 500)
        self.refresh_inspector()
        self.root.protocol("WM_DELETE_WINDOW", self._request_close)
        # The first Canvas <Configure> can arrive while the panes are still
        # negotiating their width. Ensure an empty initial grid is rebuilt once
        # geometry has settled, even when the computed column count is unchanged.
        self.root.after(140, self._ensure_initial_card_grid)
        self.root.after_idle(self._offer_missing_original_relink)
        if self._show_quick_guide_var.get():
            self.root.after(280, self.show_help)

    def _set_application_icon(self) -> None:
        """Use the bundled YiF icon for source runs and all Tk windows."""
        icon_path = bundled_asset_root() / "assets" / "YiF-Icon.png"
        try:
            self._application_icon = tk.PhotoImage(file=str(icon_path))
            self.root.iconphoto(True, self._application_icon)
        except tk.TclError:
            # A missing cosmetic asset must never prevent the storyboard from opening.
            self._application_icon = None

    def _configure_application_style(self) -> None:
        """Apply the shared, calm Windows visual language used by the suite."""
        background = "#f4f6f8"
        header_background = "#e8f1f8"
        self.root.configure(background=background)
        style = ttk.Style(self.root)
        if "vista" in style.theme_names():
            style.theme_use("vista")
        style.configure("TFrame", background=background)
        style.configure("Workspace.TFrame", background="#ffffff")
        style.configure("Footer.TFrame", background="#ffffff")
        style.configure(
            "Footer.TLabel",
            background="#ffffff",
            foreground="#435867",
            font=("Segoe UI", 10),
        )
        style.configure("Header.TFrame", background=header_background)
        style.configure(
            "TLabel",
            background=background,
            foreground="#263746",
            font=("Segoe UI", 10),
        )
        style.configure(
            "HeaderTitle.TLabel",
            background=header_background,
            foreground="#163b57",
            font=("Segoe UI Semibold", 20),
        )
        style.configure(
            "HeaderSubtitle.TLabel",
            background=header_background,
            foreground="#536b7d",
            font=("Segoe UI", 10),
        )
        style.configure(
            "HeaderStatus.TLabel",
            background=header_background,
            foreground="#536b7d",
            font=("Segoe UI", 10),
        )
        style.configure(
            "DialogTitle.TLabel",
            background=background,
            foreground="#1d597f",
            font=("Segoe UI Semibold", 11),
        )
        style.configure(
            "DialogBody.TLabel",
            background=background,
            foreground="#536b7d",
            font=("Segoe UI", 10),
        )
        style.configure(
            "TButton",
            font=("Segoe UI", 10),
            padding=(9, 5),
        )
        style.configure(
            "Page.TButton",
            font=("Segoe UI Symbol", 13),
            padding=(8, 2),
        )
        style.configure("TCheckbutton", background=background, font=("Segoe UI", 9))
        style.configure(
            "YiF.TRadiobutton",
            background=background,
            foreground="#263746",
            font=("Segoe UI", 10),
            padding=0,
        )
        style.map(
            "YiF.TRadiobutton",
            background=[("active", background), ("!active", background)],
            foreground=[("disabled", "#8a959d"), ("!disabled", "#263746")],
        )
        style.configure("TLabelframe", background=background, borderwidth=1, relief="solid")
        style.configure(
            "TLabelframe.Label",
            background=background,
            foreground="#1d597f",
            font=("Segoe UI Semibold", 11),
        )
        style.configure("TCombobox", padding=(5, 3))
        style.configure("TScrollbar", background="#e9eef2")
        style.configure(
            "Accent.Horizontal.TProgressbar",
            background="#1479b8",
            troughcolor="#e1e8ee",
            bordercolor="#c5d2dc",
            lightcolor="#1479b8",
            darkcolor="#1479b8",
        )

    def _build(self) -> None:
        self._build_menu()
        self.header = ttk.Frame(self.root, style="Header.TFrame", padding=(20, 14, 20, 12))
        self.header.pack(fill="x")
        header_left = ttk.Frame(self.header, style="Header.TFrame")
        header_left.pack(fill="x")
        title_row = ttk.Frame(header_left, style="Header.TFrame")
        title_row.pack(fill="x")
        ttk.Label(title_row, text=PRODUCT_NAME, style="HeaderTitle.TLabel").pack(side="left")
        ttk.Label(title_row, text=tagline(self.t.language), style="HeaderSubtitle.TLabel").pack(side="left", padx=(14, 0), pady=(7, 0))
        self._card_filter_states = {
            key: tk.BooleanVar(value=False)
            for key in ("used_only", "suitable", "borderline", "unsuitable")
        }
        self.inspector = ttk.Frame(header_left, style="Header.TFrame")
        self.inspector.pack(anchor="w", pady=(8, 0))
        self._build_context_header()

        self.outer_paned = ttk.PanedWindow(self.root, orient="horizontal")
        self.outer_paned.pack(fill="both", expand=True, padx=16, pady=(16, 12))
        self.cards_frame = ttk.Frame(self.outer_paned, style="Workspace.TFrame", padding=8)
        self.inspector_shell = ttk.Frame(self.outer_paned, style="Workspace.TFrame")
        self.outer_paned.add(self.cards_frame, weight=4)
        self.outer_paned.add(self.inspector_shell, weight=0)
        self._inspector_collapsed = False
        self._inspector_clamp_after_id: str | None = None
        self.outer_paned.bind("<ButtonRelease-1>", self._clamp_inspector_sash, add="+")
        self.root.bind("<Configure>", self._schedule_inspector_clamp, add="+")

        cards_view = ttk.Frame(self.cards_frame, style="Workspace.TFrame")
        cards_view.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(cards_view, background="#ffffff", highlightthickness=0)
        self.cards_scroll = ttk.Scrollbar(cards_view, orient="vertical", command=self.canvas.yview)
        self.grid = ttk.Frame(self.canvas)
        self.grid.bind("<Configure>", lambda _: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.create_window((0, 0), window=self.grid, anchor="nw")
        self.canvas.configure(yscrollcommand=self._on_cards_yview)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.cards_scroll.pack(side="right", fill="y")
        self.sticky_year_label = tk.Label(
            cards_view,
            background="#e9eef2",
            foreground="#435867",
            font=("Segoe UI", 9, "bold"),
            padx=8,
            pady=3,
        )
        self.grid_loading_overlay = ttk.Frame(cards_view, padding=16, relief="solid", borderwidth=1)
        self.grid_loading_title = ttk.Label(self.grid_loading_overlay, text=self.t("building_storyboard"), font=("Segoe UI", 11, "bold"))
        self.grid_loading_title.pack()
        self.grid_loading_status = ttk.Label(self.grid_loading_overlay, foreground="#666")
        self.grid_loading_status.pack(pady=(5, 8))
        self.grid_loading_progress = ttk.Progressbar(self.grid_loading_overlay, length=260, mode="determinate")
        self.grid_loading_progress.pack()
        self.canvas.bind("<Configure>", self._schedule_responsive_grid)
        self._build_card_size_control()

        # Tabs keep the card workflow separate from the growing film controls.
        # Existing settings remain project-bound; this is intentionally a layout-only change.
        self._configure_inspector_tab_style()
        self._build_project_summary_header()
        self.inspector_tabs = ttk.Notebook(self.inspector_shell, style="YiF.TNotebook")
        self.inspector_tabs.pack(fill="both", expand=True)
        self.general_tab = ttk.Frame(self.inspector_tabs, padding=(16, 12, 16, 16))
        self.selection_tab = ttk.Frame(self.inspector_tabs)
        self.movie_tab = ttk.Frame(self.inspector_tabs)
        self.audio_tab = ttk.Frame(self.inspector_tabs)
        self.export_tab = ttk.Frame(self.inspector_tabs, padding=(16, 12, 16, 16))
        self.inspector_tabs.add(self.general_tab, text=self.t("tab_general"))
        self.inspector_tabs.add(self.selection_tab, text=self.t("tab_storyboard"))
        self.inspector_tabs.add(self.movie_tab, text=self.t("tab_film"))
        self.inspector_tabs.add(self.audio_tab, text=self.t("tab_audio_slides"))
        self.inspector_tabs.add(self.export_tab, text=self.t("tab_export"))

        # Storyboard and Film can be taller than a compact application window.
        selection_shell = ttk.Frame(self.selection_tab)
        selection_shell.pack(fill="both", expand=True)
        self.selection_canvas = tk.Canvas(selection_shell, highlightthickness=0)
        selection_scroll = ttk.Scrollbar(selection_shell, orient="vertical", command=self.selection_canvas.yview)
        self.selection_panel = ttk.Frame(self.selection_canvas, padding=(16, 12, 16, 16))
        self.selection_panel.bind("<Configure>", lambda _: self._update_selection_scrollregion())
        self._selection_window = self.selection_canvas.create_window((0, 0), window=self.selection_panel, anchor="nw")
        self.selection_scroll = selection_scroll
        self.selection_canvas.configure(yscrollcommand=selection_scroll.set)
        self.selection_canvas.bind("<Configure>", self._resize_selection)
        self.selection_canvas.pack(side="left", fill="both", expand=True)
        selection_scroll.pack(side="right", fill="y")

        audio_shell = ttk.Frame(self.audio_tab)
        audio_shell.pack(fill="both", expand=True)
        self.audio_canvas = tk.Canvas(audio_shell, highlightthickness=0)
        audio_scroll = ttk.Scrollbar(audio_shell, orient="vertical", command=self.audio_canvas.yview)
        self.audio_panel = ttk.Frame(self.audio_canvas, padding=(16, 12, 16, 16))
        self.audio_panel.bind("<Configure>", lambda _: self._update_audio_scrollregion())
        self._audio_window = self.audio_canvas.create_window((0, 0), window=self.audio_panel, anchor="nw")
        self.audio_scroll = audio_scroll
        self.audio_canvas.configure(yscrollcommand=audio_scroll.set)
        self.audio_canvas.bind("<Configure>", self._resize_audio)
        self.audio_canvas.pack(side="left", fill="both", expand=True)
        audio_scroll.pack(side="right", fill="y")

        settings_shell = ttk.Frame(self.movie_tab)
        settings_shell.pack(fill="both", expand=True)
        self.inspector_canvas = tk.Canvas(settings_shell, highlightthickness=0)
        inspector_scroll = ttk.Scrollbar(settings_shell, orient="vertical", command=self.inspector_canvas.yview)
        self.settings_panel = ttk.Frame(self.inspector_canvas, padding=(16, 0, 16, 16))
        self.settings_panel.bind("<Configure>", lambda _: self._update_settings_scrollregion())
        self._inspector_window = self.inspector_canvas.create_window((0, 0), window=self.settings_panel, anchor="nw")
        self.inspector_scroll = inspector_scroll
        self.inspector_canvas.configure(yscrollcommand=inspector_scroll.set)
        self.inspector_canvas.bind("<Configure>", self._resize_inspector)
        self.inspector_canvas.pack(side="left", fill="both", expand=True)
        inspector_scroll.pack(side="right", fill="y")
        self.root.bind_all("<MouseWheel>", self._mousewheel)

        self._build_general_settings()
        self._build_selection_context(self.selection_panel)
        self._build_selection_controls(self.selection_panel)
        self._build_movie_settings()
        self._build_audio_settings()
        self._build_export_settings()
        self.root.after_idle(self._clamp_inspector_sash)
        if self.project.preview_enabled:
            self.root.after_idle(self._open_preview_window)

    def _build_context_header(self) -> None:
        """Show the selected file as a quiet, compact status line."""
        self.name_label = ttk.Label(self.inspector, style="HeaderStatus.TLabel", wraplength=720)
        self.name_label.pack(anchor="w")
        self.preview_face_region_var = tk.BooleanVar(value=self.project.preview_show_face_region)

    def _build_project_summary_header(self) -> None:
        """Keep project-wide totals with the settings they influence."""
        summary = ttk.Frame(self.inspector_shell, padding=(16, 0, 16, 7))
        summary.pack(fill="x")
        self.project_count_label = ttk.Label(summary, foreground="#666")
        self.project_count_label.pack(anchor="w")
        self.header_duration_label = ttk.Label(summary, foreground="#356b8f", font=("Segoe UI", 9, "bold"))
        self.header_duration_label.pack(anchor="w", pady=(2, 0))

    def _set_inspector_visible(self, visible: bool) -> None:
        """Give the cards the complete workspace without allowing an unusably thin pane."""
        if visible and self._inspector_collapsed:
            self.outer_paned.add(self.inspector_shell, weight=0)
            self._inspector_collapsed = False
            self.root.after_idle(self._clamp_inspector_sash)
        elif not visible and not self._inspector_collapsed:
            self.outer_paned.forget(self.inspector_shell)
            self._inspector_collapsed = True
        if hasattr(self, "inspector_visible_var"):
            self.inspector_visible_var.set(not self._inspector_collapsed)
        self._schedule_responsive_grid()

    def _schedule_inspector_clamp(self, _event: tk.Event | None = None) -> None:
        if self._inspector_collapsed:
            return
        if self._inspector_clamp_after_id is not None:
            self.root.after_cancel(self._inspector_clamp_after_id)
        self._inspector_clamp_after_id = self.root.after(90, self._clamp_inspector_sash)

    def _clamp_inspector_sash(self, _event: tk.Event | None = None) -> None:
        self._inspector_clamp_after_id = None
        if self._inspector_collapsed or not self.outer_paned.winfo_ismapped():
            return
        total = self.outer_paned.winfo_width()
        if total <= 1:
            return
        minimum = 470
        maximum = max(minimum, total // 2)
        try:
            current = total - self.outer_paned.sashpos(0)
            target = min(maximum, max(minimum, current))
            if abs(target - current) >= 2:
                self.outer_paned.sashpos(0, total - target)
        except tk.TclError:
            return

    def _configure_inspector_tab_style(self) -> None:
        """Give the four work areas a deliberately legible, spacious tab treatment."""
        style = ttk.Style(self.root)
        style.configure("YiF.TNotebook", tabmargins=(5, 8, 5, 0))
        style.configure(
            "YiF.TNotebook.Tab",
            padding=(15, 7),
            font=("Segoe UI", 9, "bold"),
        )
        style.map(
            "YiF.TNotebook.Tab",
            background=[("selected", "#dbeaf6"), ("!selected", "#edf1f4")],
            foreground=[("selected", "#173f5f"), ("!selected", "#4e5b65")],
        )

    def _build_selection_context(self, parent: tk.Widget) -> None:
        """Keep link and quality context close to card decisions, not in the header."""
        box = ttk.LabelFrame(parent, text=self.t("image_details"), padding=(12, 10))
        box.pack(fill="x", pady=(0, 14))
        self.digikam_link_label = ttk.Label(box, foreground="#356b8c", wraplength=420)
        self.digikam_link_label.pack(anchor="w")
        self.warning_label = ttk.Label(box, wraplength=420, foreground="#a65e00")
        self.warning_label.pack(anchor="w", pady=(5, 0))

    def _build_menu(self) -> None:
        menu = tk.Menu(self.root)
        project_menu = tk.Menu(menu, tearoff=False)
        project_menu.add_command(label=self.t("new_project"), command=self.new_project, accelerator="Strg+N")
        project_menu.add_command(label=self.t("open_project"), command=self.open_project, accelerator="Strg+O")
        recent_menu = tk.Menu(project_menu, tearoff=False)
        recent_paths = [Path(value) for value in self._recent_projects if Path(value).is_file()]
        if recent_paths:
            for path in recent_paths:
                label = f"{path.stem}  —  {path.parent.name}"
                recent_menu.add_command(label=label, command=lambda value=path: self._open_recent_project(value))
        else:
            recent_menu.add_command(label=self.t("no_recent_projects"), state="disabled")
        project_menu.add_cascade(label=self.t("recent_projects"), menu=recent_menu)
        project_menu.add_separator()
        project_menu.add_command(label=self.t("save_project"), command=self.save, accelerator="Strg+S")
        project_menu.add_command(label=self.t("save_as"), command=self.save_as)
        project_menu.add_separator()
        project_menu.add_command(label=self.t("quit"), command=self._request_close)
        menu.add_cascade(label=self.t("project"), menu=project_menu)

        import_menu = tk.Menu(menu, tearoff=False)
        import_menu.add_command(label=self.t("import_images"), command=self.import_images)
        import_menu.add_separator()
        digikam_menu = tk.Menu(import_menu, tearoff=False)
        digikam_menu.add_command(label=self.t("import_digikam"), command=self.import_digikam)
        digikam_menu.add_command(label=self.t("update_digikam"), command=self.update_digikam_project)
        digikam_menu.add_separator()
        digikam_menu.add_command(label=self.t("configure_digikam"), command=self.configure_digikam_source)
        import_menu.add_cascade(label=self.t("digikam_menu"), menu=digikam_menu)
        import_menu.add_separator()
        import_menu.add_command(label=self.t("relink_missing_images"), command=self.relink_missing_images)
        menu.add_cascade(label=self.t("images"), menu=import_menu)

        view_menu = tk.Menu(menu, tearoff=False)
        view_menu.add_checkbutton(
            label=self.t("show_preview"), variable=self.preview_enabled_var,
            command=self._toggle_preview,
        )
        view_menu.add_checkbutton(
            label=self.t("show_year_separators"), variable=self.year_separators_var,
            command=self._toggle_year_separators,
        )
        self.inspector_visible_var = tk.BooleanVar(value=True)
        view_menu.add_checkbutton(
            label=self.t("show_settings_panel"), variable=self.inspector_visible_var,
            command=lambda: self._set_inspector_visible(self.inspector_visible_var.get()),
        )
        view_menu.add_separator()
        view_menu.add_checkbutton(
            label=self.t("advanced_output_options"), variable=self.advanced_output_var,
            command=self._toggle_advanced_output_options,
        )
        menu.add_cascade(label=self.t("view"), menu=view_menu)

        help_menu = tk.Menu(menu, tearoff=False)
        help_menu.add_command(label=self.t("quick_help"), command=self.show_help)
        help_menu.add_separator()
        help_menu.add_command(label=self.t("about"), command=self.show_about)
        menu.add_cascade(label=self.t("help"), menu=help_menu)
        language_menu = tk.Menu(help_menu, tearoff=False)
        self._language_var = tk.StringVar(value=self.t.language)
        language_menu.add_radiobutton(label="Deutsch", value="de", variable=self._language_var, command=lambda: self._change_language("de"))
        language_menu.add_radiobutton(label="English", value="en", variable=self._language_var, command=lambda: self._change_language("en"))
        help_menu.add_separator()
        help_menu.add_cascade(label=self.t("language"), menu=language_menu)
        self.root.configure(menu=menu)
        self.root.bind("<Control-n>", lambda _event: self.new_project())
        self.root.bind("<Control-o>", lambda _event: self.open_project())
        self.root.bind("<Control-s>", lambda _event: self.save())

    def _change_language(self, language: str) -> None:
        """Persist the choice; rebuilding an active Tk view risks losing edits."""
        save_language(language)
        if language != self.t.language:
            messagebox.showinfo(self.t("language_restart_title"), self.t("language_restart"), parent=self.root)

    def _build_card_size_control(self) -> None:
        """Keep card zoom near its canvas instead of competing with project actions."""
        footer = ttk.Frame(self.cards_frame, style="Footer.TFrame", padding=(6, 7, 6, 0))
        footer.pack(fill="x")
        ttk.Label(footer, text=self.t("card_size"), style="Footer.TLabel").pack(side="left")
        self._card_size_var = tk.StringVar(value=self.t("medium"))
        self._card_size_box = ttk.Combobox(
            footer, state="readonly", width=9, textvariable=self._card_size_var,
            values=(self.t("small"), self.t("medium"), self.t("large")),
        )
        self._card_size_box.pack(side="left", padx=(8, 0))
        self._card_size_box.bind("<<ComboboxSelected>>", self._set_card_size_from_choice)
        ttk.Separator(footer, orient="vertical").pack(side="left", fill="y", padx=14)
        ttk.Label(footer, text=self.t("sort"), style="Footer.TLabel").pack(side="left")
        self._sort_var = tk.StringVar(value=self.t("date"))
        self._sort_box = ttk.Combobox(
            footer, state="readonly", width=10, textvariable=self._sort_var,
            values=(self.t("date"), self.t("filename")),
        )
        self._sort_box.pack(side="left", padx=(8, 0))
        self._sort_box.bind("<<ComboboxSelected>>", self._set_sort_from_choice)
        ttk.Label(footer, text=self.t("show"), style="Footer.TLabel").pack(side="left", padx=(20, 4))
        self._card_filter_label = tk.StringVar(value=self.t("all_cards"))
        filter_menu = tk.Menu(footer, tearoff=False)
        for key in ("used_only", "suitable", "borderline", "unsuitable"):
            filter_menu.add_checkbutton(
                label=self.t(key), variable=self._card_filter_states[key], command=self._apply_card_filter
            )
        self._filter_menu = filter_menu
        self._filter_button = ttk.Menubutton(footer, textvariable=self._card_filter_label, menu=filter_menu, width=19)
        self._filter_button.pack(side="left")
        self._filter_button.bind("<Button-1>", self._post_filter_menu)
        navigation = ttk.Frame(footer, style="Footer.TFrame")
        navigation.pack(side="right")
        self._page_next_button = ttk.Button(
            navigation, text="›", width=3, style="Page.TButton", command=lambda: self._set_card_page(1),
        )
        self._page_next_button.pack(side="right")
        self._page_label = ttk.Label(navigation, width=12, anchor="center", style="Footer.TLabel")
        self._page_label.pack(side="left")
        self._page_previous_button = ttk.Button(
            navigation, text="‹", width=3, style="Page.TButton", command=lambda: self._set_card_page(-1),
        )
        self._page_previous_button.pack(side="left")

    def _post_filter_menu(self, event: tk.Event) -> str:
        """Open the card filter above its button when the taskbar leaves no room."""
        menu = self._filter_menu
        menu.update_idletasks()
        x = event.widget.winfo_rootx()
        down_y = event.widget.winfo_rooty() + event.widget.winfo_height()
        menu_height = menu.winfo_reqheight()
        if down_y + menu_height > self.root.winfo_screenheight():
            y = max(0, event.widget.winfo_rooty() - menu_height)
        else:
            y = down_y
        try:
            menu.tk_popup(x, y)
        finally:
            menu.grab_release()
        return "break"

    def _set_card_page(self, direction: int) -> None:
        page_count = max(1, (len(self._filtered_card_indices) + CARD_PAGE_SIZE - 1) // CARD_PAGE_SIZE)
        next_page = max(0, min(page_count - 1, self._card_page + direction))
        if next_page != self._card_page:
            self._card_page = next_page
            self._build_card_grid()

    def _update_card_page_controls(self) -> None:
        if not hasattr(self, "_page_label"):
            return
        total = len(self._filtered_card_indices)
        pages = max(1, (total + CARD_PAGE_SIZE - 1) // CARD_PAGE_SIZE)
        self._card_page = max(0, min(self._card_page, pages - 1))
        if total <= CARD_PAGE_SIZE:
            self._page_label.configure(text="")
            self._page_previous_button.configure(state="disabled")
            self._page_next_button.configure(state="disabled")
            return
        start = self._card_page * CARD_PAGE_SIZE + 1
        end = min(total, start + CARD_PAGE_SIZE - 1)
        self._page_label.configure(text=f"{start}–{end} / {total}")
        self._page_previous_button.configure(state="normal" if self._card_page else "disabled")
        self._page_next_button.configure(state="normal" if self._card_page < pages - 1 else "disabled")

    def _set_card_size_from_choice(self, _event: tk.Event | None = None) -> None:
        value = self._card_size_var.get()
        internal = {
            self.t("small"): "Klein",
            self.t("medium"): "Mittel",
            self.t("large"): "Gross",
        }.get(value, "Mittel")
        self._set_card_size(internal)

    def _set_sort_from_choice(self, _event: tk.Event | None = None) -> None:
        self.sort_cards("date" if self._sort_var.get() == self.t("date") else "name")

    def show_help(self) -> None:
        """Show the short guide as a scannable, application-styled dialog."""
        dialog = tk.Toplevel(self.root)
        dialog.title(self.t("quick_guide_title"))
        dialog.transient(self.root)
        dialog.resizable(False, False)
        dialog.configure(background="#f6f8fa")

        header = tk.Frame(dialog, background="#e8f2fa", padx=22, pady=17)
        header.pack(fill="x")
        tk.Label(
            header, text=self.t("quick_guide_title"), background="#e8f2fa",
            foreground="#173f5f", font=("Segoe UI", 15, "bold"),
        ).pack(anchor="w")
        tk.Label(
            header,
            text="Von Bildern zur fertigen Erinnerung" if self.t.language == "de" else "From photos to a finished memory",
            background="#e8f2fa", foreground="#52718a", font=("Segoe UI", 9),
        ).pack(anchor="w", pady=(3, 0))

        body = ttk.Frame(dialog, padding=(18, 14, 18, 10))
        body.pack(fill="both", expand=True)
        for section in self.t("quick_guide").split("\n\n"):
            heading, _, text = section.partition("\n")
            step = ttk.LabelFrame(body, text=heading, padding=(11, 7))
            step.pack(fill="x", pady=(0, 8))
            ttk.Label(step, text=text, wraplength=500, justify="left").pack(anchor="w")

        actions = ttk.Frame(dialog, padding=(18, 0, 18, 15))
        actions.pack(fill="x")
        ttk.Checkbutton(
            actions, text=self.t("quick_guide_show_at_start"),
            variable=self._show_quick_guide_var,
            command=lambda: save_show_quick_guide(self._show_quick_guide_var.get()),
        ).pack(side="left")
        ttk.Button(actions, text=self.t("quick_guide_close"), command=dialog.destroy).pack(side="right")
        dialog.bind("<Escape>", lambda _event: dialog.destroy())
        dialog.update_idletasks()
        dialog.geometry(f"+{self.root.winfo_rootx() + 60}+{self.root.winfo_rooty() + 60}")
        dialog.grab_set()

    def show_about(self) -> None:
        dialog = tk.Toplevel(self.root)
        dialog.title(self.t("about"))
        dialog.transient(self.root)
        dialog.resizable(False, False)
        content = ttk.Frame(dialog, padding=(28, 24, 28, 10))
        content.pack(fill="both", expand=True)
        icon_path = bundled_asset_root() / "assets" / "YiF-Icon.png"
        try:
            image = Image.open(icon_path).convert("RGBA")
            image.thumbnail((164, 164), Image.Resampling.LANCZOS)
            about_icon = ImageTk.PhotoImage(image)
            icon_label = ttk.Label(content, image=about_icon)
            icon_label.image = about_icon
            icon_label.pack(pady=(0, 12))
        except (OSError, tk.TclError):
            pass
        ttk.Label(
            content, text=self.t.format("about_text", version=__version__), justify="center",
            font=("Segoe UI", 10),
        ).pack()
        actions = ttk.Frame(dialog, padding=(28, 14, 28, 14))
        actions.pack(fill="x")
        ttk.Button(
            actions, text=self.t("support_on_kofi"),
            command=lambda: webbrowser.open(KOFI_URL),
        ).pack(side="left")
        ttk.Button(actions, text="OK", command=dialog.destroy).pack(side="right")
        self._center_dialog(dialog)

    def _build_selection_controls(self, parent: tk.Widget) -> None:
        """Give selection and burst decisions their own calm, readable groups."""
        box = ttk.LabelFrame(parent, text=self.t("selection_for_movie"), padding=(12, 10))
        box.pack(fill="x", pady=(0, 14))
        enabled_cards = sum(card.enabled for card in self.project.cards)
        desired = self.project.desired_image_count or enabled_cards
        desired = max(1, desired) if self.project.cards else 0
        self.desired_count_var = tk.IntVar(value=desired)
        desired_row = ttk.Frame(box)
        desired_row.pack(fill="x")
        ttk.Label(desired_row, text=self.t("desired_count")).pack(side="left")
        self.desired_spinbox = ttk.Spinbox(
            desired_row, from_=1, to=1, increment=1,
            textvariable=self.desired_count_var, width=5,
        )
        self.desired_spinbox.pack(side="left", padx=(7, 0))
        self.desired_total_label = ttk.Label(desired_row, foreground="#666")
        self.desired_total_label.pack(side="left", padx=(6, 0))
        self.desired_spinbox.bind("<Return>", lambda _event: self.apply_desired_image_count())
        ttk.Label(box, text=self.t("selection_quality")).pack(anchor="w", pady=(7, 0))
        self._integer_setting_scale(
            box, "selection_quality_level", 0, 2,
            lambda value: self.t(("selection_quality_green", "selection_quality_yellow", "selection_quality_red")[value]),
            on_change=lambda _value: self._refresh_selection_controls(),
        )
        self._setting_heading(box, self.t("maximum_side_view"), "help_maximum_side_view", pady=(10, 0))
        self._setting_scale(
            box, "maximum_side_view_degrees", 10.0, 45.0, 1.0,
            lambda value: f"{value:.0f}°",
            on_change=lambda _value: self._refresh_selection_controls(),
        )
        ttk.Button(
            box, text=self.t("distribute_selection"), command=self.apply_desired_image_count,
        ).pack(anchor="w", pady=(7, 0))

        burst_box = ttk.LabelFrame(parent, text=self.t("series_title"), padding=(12, 10))
        burst_box.pack(fill="x")
        self._setting_heading(burst_box, self.t("series_gap"), "help_series_gap")
        self._setting_scale(
            burst_box, "series_minimum_gap_minutes", 0.0, 15.0, 0.5,
            lambda value: self.t("off") if value == 0 else f"{value:g} {'minutes' if self.t.language == 'en' else 'Minuten'}",
        )
        ttk.Button(
            burst_box, text=self.t("reduce_series"), command=self.reduce_series,
        ).pack(anchor="w", pady=(7, 0))
        self._refresh_selection_controls()

    def _refresh_selection_controls(self) -> None:
        """Keep the desired-count denominator tied to the active filters."""
        if not hasattr(self, "desired_spinbox"):
            return
        allowed_cards = len(self._eligible_cards_for_target())
        self.desired_spinbox.configure(to=max(1, allowed_cards))
        try:
            desired = int(self.desired_count_var.get())
        except tk.TclError:
            desired = 0
        if allowed_cards:
            self.desired_count_var.set(min(max(1, desired), allowed_cards))
        else:
            self.desired_count_var.set(0)
        self.desired_total_label.configure(
            text=(
                f"of {allowed_cards} allowed"
                if self.t.language == "en"
                else f"von {allowed_cards} passend"
            )
        )
        self._update_duration_label()

    def _build_movie_settings(self) -> None:
        self._movie_settings_ready = False
        box = ttk.LabelFrame(self.settings_panel, text=self.t("movie_settings"), padding=8)
        box.pack(fill="x", pady=(12, 0))
        ttk.Label(box, text=self.t("movie_mode")).pack(anchor="w")
        mode_row = ttk.Frame(box)
        mode_row.pack(fill="x", pady=(3, 8))
        if self.project.movie_mode not in {"years_in_focus", "timelapse"}:
            self.project.movie_mode = "years_in_focus"
        self._movie_mode_var = tk.StringVar(value=self.project.movie_mode)
        ttk.Radiobutton(
            mode_row, text=self.t("movie_mode_yif"), value="years_in_focus",
            variable=self._movie_mode_var, command=self._set_movie_mode, style="YiF.TRadiobutton",
        ).pack(side="left")
        ttk.Radiobutton(
            mode_row, text=self.t("movie_mode_timelapse"), value="timelapse",
            variable=self._movie_mode_var, command=self._set_movie_mode, style="YiF.TRadiobutton",
        ).pack(side="left", padx=(16, 0))

        self.standard_movie_settings = ttk.Frame(box)
        self.standard_movie_settings.pack(fill="x")
        self._setting_heading(self.standard_movie_settings, self.t("face_size"), "help_face_size")
        self._setting_scale(
            self.standard_movie_settings, "eye_distance", 0.01, 0.065, 0.001,
            lambda value: f"{value * 100:.1f}%  ({'4.0% = default' if self.t.language == 'en' else '4,0% = Standard'})",
        )
        self._setting_heading(self.standard_movie_settings, self.t("eye_line"), "help_eye_line", pady=(8, 0))
        self._setting_scale(
            self.standard_movie_settings, "eye_y", 0.20, 0.45, 0.001, self._eye_line_label,
        )
        self._setting_heading(self.standard_movie_settings, self.t("hold_time"), "help_hold_time", pady=(8, 0))
        self._setting_scale(self.standard_movie_settings, "hold_seconds", 1.0, 8.0, 0.1, lambda value: f"{value:.1f} {'seconds' if self.t.language == 'en' else 'Sekunden'}")
        self._setting_heading(self.standard_movie_settings, self.t("transition"), "help_transition", pady=(8, 0))
        self._setting_scale(self.standard_movie_settings, "transition_seconds", 0.2, 2.0, 0.1, lambda value: f"{value:.1f} {'seconds' if self.t.language == 'en' else 'Sekunden'}")
        ttk.Separator(self.standard_movie_settings).pack(fill="x", pady=10)
        ttk.Label(self.standard_movie_settings, text=self.t("card_border")).pack(anchor="w")
        ttk.Label(self.standard_movie_settings, text=self.t("border_width")).pack(anchor="w", pady=(6, 0))
        if not self.project.border_enabled:
            self.project.border_pixels = 0
        self._integer_setting_scale(
            self.standard_movie_settings, "border_pixels", 0, 40,
            lambda value: self.t("none") if value == 0 else f"{value} {'pixels' if self.t.language == 'en' else 'Pixel'}",
            on_change=lambda value: setattr(self.project, "border_enabled", value > 0),
        )
        color_row = ttk.Frame(self.standard_movie_settings)
        color_row.pack(fill="x", pady=(5, 0))
        ttk.Label(color_row, text=self.t("border_color")).pack(side="left")
        color_button = tk.Button(color_row, width=4, relief="solid", background=self.project.border_color)
        color_button.pack(side="right")

        def choose_border_color() -> None:
            _rgb, selected = colorchooser.askcolor(self.project.border_color, parent=self.root, title=self.t("border_color"))
            if selected:
                self.project.border_color = selected
                color_button.configure(background=selected)

        color_button.configure(command=choose_border_color)

        self.timelapse_settings = ttk.LabelFrame(box, text=self.t("timelapse_settings"), padding=8)
        ttk.Label(self.timelapse_settings, text=self.t("timelapse_frames_per_image")).pack(anchor="w")
        self._integer_setting_scale(
            self.timelapse_settings, "timelapse_frames_per_image", 1, 12,
            lambda value: f"{value} {'frames' if self.t.language == 'en' else 'Frames'}",
            on_change=lambda _value: self._update_timelapse_summary(),
        )
        ttk.Label(self.timelapse_settings, text=self.t("timelapse_transition_frames"),).pack(anchor="w", pady=(8, 0))
        self._integer_setting_scale(
            self.timelapse_settings, "timelapse_transition_frames", 0, 6,
            lambda value: self.t("none") if value == 0 else f"{value} {'frames' if self.t.language == 'en' else 'Frames'}",
            on_change=lambda _value: self._update_timelapse_summary(),
        )
        ttk.Label(self.timelapse_settings, text=self.t("timelapse_max_images_per_year")).pack(anchor="w", pady=(8, 0))
        self._integer_setting_scale(
            self.timelapse_settings, "timelapse_max_images_per_year", 0, 240,
            lambda value: self.t("all") if value == 0 else f"{value} {'images' if self.t.language == 'en' else 'Bilder'}",
            on_change=lambda _value: self._update_timelapse_summary(),
        )
        self.timelapse_frontal_only_var = tk.BooleanVar(value=self.project.timelapse_frontal_only)
        frontal_row = ttk.Frame(self.timelapse_settings)
        frontal_row.pack(anchor="w", pady=(8, 0))
        ttk.Checkbutton(
            frontal_row, text=self.t("timelapse_frontal_only"),
            variable=self.timelapse_frontal_only_var,
            command=self._set_timelapse_frontal_only,
        ).pack(side="left")
        frontal_help = tk.Label(frontal_row, text="?", foreground="#246fa8", cursor="question_arrow", font=("Segoe UI", 9, "bold"))
        frontal_help.pack(side="left", padx=(5, 0))
        frontal_help.bind("<Enter>", lambda event: self._show_quality_tooltip(event, self.t("timelapse_frontal_help")))
        frontal_help.bind("<Leave>", self._hide_quality_tooltip)
        self.timelapse_summary_label = ttk.Label(self.timelapse_settings, style="Hint.TLabel", wraplength=400)
        self.timelapse_summary_label.pack(anchor="w", pady=(8, 0))
        ttk.Label(
            self.timelapse_settings, text=self.t("timelapse_prototype_hint"), style="Hint.TLabel", wraplength=400,
        ).pack(anchor="w", pady=(8, 0))
        self._set_movie_mode()
        self._movie_settings_ready = True
        self.root.after_idle(self._update_timelapse_summary)

    def _set_timelapse_frontal_only(self) -> None:
        self.project.timelapse_frontal_only = self.timelapse_frontal_only_var.get()
        if self._movie_settings_ready:
            self._update_timelapse_summary()

    def _set_movie_mode(self) -> None:
        """Show only the controls relevant to the selected film workflow."""
        mode = self._movie_mode_var.get()
        self.project.movie_mode = mode
        if mode == "timelapse":
            self.standard_movie_settings.pack_forget()
            self.timelapse_settings.pack(fill="x")
        else:
            self.timelapse_settings.pack_forget()
            self.standard_movie_settings.pack(fill="x")
        self._update_timelapse_summary()
        self._update_duration_label()

    def _update_timelapse_summary(self) -> None:
        """Show the same filter impact the timelapse exporter will apply."""
        if not hasattr(self, "timelapse_summary_label"):
            return
        enabled = [card for card in self.project.cards if card.enabled]
        by_year: dict[str, int] = {}
        for card in enabled:
            quality, _colour, _text = self._card_quality(card)
            if {"green": 0, "yellow": 1, "red": 2}[quality] > self.project.selection_quality_level:
                continue
            record = self._analysis_record(card) or {}
            yaw = abs(float((record.get("metrics") or {}).get("pose_yaw_degrees", 0.0)))
            if self.project.timelapse_frontal_only and yaw > 12.0:
                continue
            year = str(record.get("capture_time") or "unbekannt")[:4]
            by_year[year] = by_year.get(year, 0) + 1
        limit = self.project.timelapse_max_images_per_year
        selected = sum(min(count, limit) for count in by_year.values()) if limit else sum(by_year.values())
        seconds = selected * (
            self.project.timelapse_frames_per_image + self.project.timelapse_transition_frames
        ) / self.project.fps
        self.timelapse_summary_label.configure(
            text=self.t.format("timelapse_summary", selected=selected, enabled=len(enabled), seconds=seconds)
        )

    def _build_general_settings(self) -> None:
        """Collect output values that affect quality assessment before card selection."""
        box = ttk.LabelFrame(self.general_tab, text=self.t("output_basics"), padding=(12, 10))
        box.pack(fill="x")
        self._setting_heading(box, self.t("output_preset"), "help_resolution")
        resolution = tk.StringVar(value=self._resolution_label())
        resolution_box = ttk.Combobox(
            box, state="readonly", textvariable=resolution,
            values=self._resolution_options(),
        )
        resolution_box.pack(fill="x")
        resolution_box.bind("<<ComboboxSelected>>", lambda _event: self._set_resolution(resolution.get()))
        self._settings_vars["resolution"] = resolution

        ttk.Label(box, text=self.t("frame_rate")).pack(anchor="w", pady=(14, 0))
        fps = tk.StringVar(value=f"{self.project.fps:.0f} FPS")
        fps_box = ttk.Combobox(box, state="readonly", textvariable=fps, values=("24 FPS", "25 FPS", "30 FPS", "60 FPS"))
        fps_box.pack(fill="x")
        fps_box.bind("<<ComboboxSelected>>", lambda _event: self._set_fps(fps.get()))
        self._settings_vars["fps"] = fps

        self.advanced_output_frame = ttk.LabelFrame(
            self.general_tab, text=self.t("advanced_output_options"), padding=(12, 10),
        )
        ttk.Label(self.advanced_output_frame, text=self.t("video_quality")).pack(anchor="w")
        quality = tk.StringVar(value=self._quality_label())
        quality_box = ttk.Combobox(
            self.advanced_output_frame, state="readonly", textvariable=quality,
            values=(self.t("quality_standard"), self.t("quality_high"), self.t("quality_smaller")),
        )
        quality_box.pack(fill="x", pady=(2, 0))
        quality_box.bind("<<ComboboxSelected>>", lambda _event: self._set_output_quality(quality.get()))
        self._settings_vars["output_quality"] = quality
        ttk.Label(
            self.advanced_output_frame, text=self.t("quality_hint"), foreground="#666", wraplength=420,
        ).pack(anchor="w", pady=(8, 0))
        self._refresh_advanced_output_visibility()

    def _build_audio_settings(self) -> None:
        """Keep audio and simple full-frame slides together for the early layout."""
        box = ttk.LabelFrame(self.audio_panel, text=self.t("background_music"), padding=8)
        box.pack(fill="x")
        self.background_music_list = tk.Listbox(box, height=5, activestyle="none", exportselection=False)
        self.background_music_list.pack(fill="x", pady=(3, 0))
        self.background_music_list.bind("<ButtonPress-1>", self._start_music_drag)
        self.background_music_list.bind("<ButtonRelease-1>", self._finish_music_drag)
        controls = ttk.Frame(box)
        controls.pack(fill="x", pady=(4, 0))
        ttk.Button(controls, text=self.t("choose_background_music"), command=self.choose_background_music).pack(side="left")
        ttk.Button(controls, text=self.t("remove_background_music"), command=self.remove_background_music).pack(side="right")
        self.background_music_status_label = ttk.Label(
            box, wraplength=420, foreground="#666", justify="left",
        )
        self.background_music_status_label.pack(anchor="w", pady=(7, 0))
        self._music_drag_index: int | None = None
        self._refresh_background_music_label()

        slides = ttk.LabelFrame(self.audio_panel, text=self.t("start_end_slides"), padding=8)
        slides.pack(fill="x", pady=(12, 0))
        self._slide_row(slides, "opening", self.t("opening_slide"))
        self._slide_row(slides, "closing", self.t("closing_slide"))
        self._setting_heading(slides, self.t("slide_hold_time"), "help_slide_hold_time", pady=(8, 0))
        self._setting_scale(
            slides, "slide_seconds", 1.0, 8.0, 0.1,
            lambda value: f"{value:.1f} {'seconds' if self.t.language == 'en' else 'Sekunden'}",
        )
        ttk.Label(slides, text=self.t("slides_hold_hint"), foreground="#666", wraplength=420).pack(anchor="w", pady=(7, 0))

    def _slide_row(self, parent: tk.Widget, kind: str, label: str) -> None:
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=(2, 5))
        ttk.Label(row, text=label).pack(anchor="w")
        details = ttk.Frame(row)
        details.pack(fill="x", pady=(1, 0))
        value_label = ttk.Label(details, foreground="#666", wraplength=255)
        value_label.pack(side="left", fill="x", expand=True)

        def refresh() -> None:
            raw_path = getattr(self.project, f"{kind}_slide_path")
            path = Path(raw_path) if raw_path else None
            if path is None:
                value_label.configure(text=self.t("no_slide_selected"), foreground="#666")
            elif path.is_file():
                value_label.configure(text=path.name, foreground="#356b8f")
            else:
                value_label.configure(text=self.t("slide_missing"), foreground="#a65e00")
            self._update_duration_label()

        def choose() -> None:
            raw_path = getattr(self.project, f"{kind}_slide_path")
            selected = filedialog.askopenfilename(
                parent=self.root, title=self.t("choose_slide"),
                initialdir=str(Path(raw_path).parent) if raw_path else str(self.project_path.parent),
                filetypes=[(self.t("images_filetype"), "*.jpg *.jpeg *.png"), (self.t("all_files"), "*.*")],
            )
            if selected:
                setattr(self.project, f"{kind}_slide_path", str(Path(selected).resolve()))
                refresh()

        def remove() -> None:
            setattr(self.project, f"{kind}_slide_path", "")
            refresh()

        ttk.Button(details, text=self.t("choose_slide"), command=choose).pack(side="right", padx=(5, 0))
        ttk.Button(row, text=self.t("remove_slide"), command=remove).pack(anchor="e", pady=(2, 0))
        refresh()

    def _build_export_settings(self) -> None:
        """Place final delivery controls in their own short, obvious tab."""
        box = ttk.LabelFrame(self.export_tab, text=self.t("tab_export"), padding=8)
        box.pack(fill="x")
        final_export = ttk.LabelFrame(box, text=self.t("final_export"), padding=(10, 7))
        final_export.pack(fill="x", pady=(0, 12))
        self.final_export_summary_label = ttk.Label(final_export, foreground="#356b8f", wraplength=400)
        self.final_export_summary_label.pack(anchor="w")
        self.final_export_details_label = ttk.Label(final_export, foreground="#555", justify="left", wraplength=400)
        self.final_export_details_label.pack(anchor="w", pady=(5, 0))
        self._refresh_final_export_summary()
        play_after_export = tk.BooleanVar(value=self.project.play_after_export)
        ttk.Checkbutton(
            box,
            text=self.t("start_after_export"),
            variable=play_after_export,
            command=lambda: setattr(self.project, "play_after_export", play_after_export.get()),
        ).pack(anchor="w", pady=(0, 7))
        self._settings_vars["play_after_export"] = play_after_export
        self._sync_preview_aspect_ratio()
        preview_resolution = tk.StringVar(value=self._preview_resolution_label())
        preview_box = ttk.LabelFrame(box, text=self.t("preview_options"), padding=(10, 8))
        preview_box.pack(fill="x", pady=(16, 0))
        ttk.Label(preview_box, text=self.t("preview_resolution")).pack(anchor="w")
        preview_picker = ttk.Combobox(
            preview_box, state="readonly", textvariable=preview_resolution,
            values=self._preview_resolution_options(),
        )
        preview_picker.pack(fill="x", pady=(2, 8))
        self.preview_resolution_picker = preview_picker
        preview_picker.bind("<<ComboboxSelected>>", lambda _event: self._set_preview_resolution(preview_resolution.get()))
        self._settings_vars["preview_resolution"] = preview_resolution
        ttk.Button(
            preview_box,
            text=self.t("preview_export"),
            command=lambda: self.export_video(preview=True),
        ).pack(anchor="w", ipadx=6, ipady=2)
        tk.Button(
            box,
            text=self.t("export_video"),
            command=self.export_video,
            background="#1479b8",
            activebackground="#0b659c",
            foreground="#ffffff",
            activeforeground="#ffffff",
            font=("Segoe UI Semibold", 11),
            relief="flat",
            padx=18,
            pady=8,
        ).pack(anchor="w", pady=(16, 2))

    def _refresh_background_music_label(self) -> None:
        """Show an ordered, compact playlist with local availability information."""
        if not hasattr(self, "background_music_list"):
            return
        paths = self._background_music_paths()
        self.background_music_list.delete(0, "end")
        if not paths:
            self.background_music_list.insert("end", self.t("no_background_music"))
            self.background_music_list.configure(foreground="#666")
            self.background_music_status_label.configure(text="")
            self._refresh_final_export_summary()
            return
        durations: list[float] = []
        missing = False
        unknown = False
        for index, path in enumerate(paths, start=1):
            self.background_music_list.insert("end", f"{index}. {path.name}")
            if not path.is_file():
                missing = True
                self.background_music_list.itemconfigure(index - 1, foreground="#a65e00")
                continue
            duration = audio_duration_seconds(path, bundled_asset_root())
            if duration is None:
                unknown = True
                self.background_music_list.itemconfigure(index - 1, foreground="#a65e00")
            else:
                durations.append(duration)
                self.background_music_list.itemconfigure(index - 1, foreground="#356b8f")
        if missing:
            self.background_music_status_label.configure(
                text=self.t("background_music_missing"), foreground="#a65e00",
            )
            self._refresh_final_export_summary()
            return
        if unknown:
            self.background_music_status_label.configure(
                text=self.t("background_music_duration_unknown"), foreground="#a65e00",
            )
            self._refresh_final_export_summary()
            return
        self.background_music_status_label.configure(
            text=(
                self.t.format("background_playlist_duration", count=len(paths), duration=format_audio_duration(sum(durations)))
                + "\n"
                + self.t("background_music_adapts")
            ),
            foreground="#356b8f",
        )
        self._refresh_final_export_summary()

    def _background_music_paths(self) -> list[Path]:
        paths = [Path(path) for path in self.project.background_audio_paths]
        if not paths and self.project.background_audio_path:
            paths = [Path(self.project.background_audio_path)]
            self.project.background_audio_paths = [str(paths[0])]
        self.project.background_audio_path = str(paths[0]) if paths else ""
        return paths

    def choose_background_music(self) -> None:
        """Append up to ten local audio files without copying user media into YiF."""
        paths = self._background_music_paths()
        remaining = 10 - len(paths)
        if remaining <= 0:
            messagebox.showinfo(self.t("background_music"), self.t("background_music_limit"), parent=self.root)
            return
        selected = filedialog.askopenfilenames(
            parent=self.root,
            title=self.t("choose_background_music"),
            initialdir=(
                str(paths[-1].parent) if paths else str(self.project_path.parent)
            ),
            filetypes=[
                (self.t("audio_filetype"), "*.mp3 *.wav *.m4a *.aac *.flac *.ogg"),
                (self.t("all_files"), "*.*"),
            ],
        )
        if selected:
            additions = [str(Path(path).resolve()) for path in selected]
            paths.extend(Path(path) for path in additions[:remaining])
            self.project.background_audio_paths = [str(path) for path in paths]
            self.project.background_audio_path = self.project.background_audio_paths[0]
            if len(additions) > remaining:
                messagebox.showinfo(self.t("background_music"), self.t("background_music_limit"), parent=self.root)
            self._refresh_background_music_label()

    def remove_background_music(self) -> None:
        selection = self.background_music_list.curselection() if hasattr(self, "background_music_list") else ()
        if selection and self._background_music_paths():
            del self.project.background_audio_paths[selection[0]]
        else:
            self.project.background_audio_paths = []
        self.project.background_audio_path = self.project.background_audio_paths[0] if self.project.background_audio_paths else ""
        self._refresh_background_music_label()

    def _start_music_drag(self, event: tk.Event) -> None:
        index = self.background_music_list.nearest(event.y)
        self._music_drag_index = index if self._background_music_paths() and index >= 0 else None

    def _finish_music_drag(self, event: tk.Event) -> None:
        if self._music_drag_index is None:
            return
        paths = self._background_music_paths()
        destination = min(max(0, self.background_music_list.nearest(event.y)), len(paths) - 1)
        source = self._music_drag_index
        self._music_drag_index = None
        if source != destination:
            moved = self.project.background_audio_paths.pop(source)
            self.project.background_audio_paths.insert(destination, moved)
            self.project.background_audio_path = self.project.background_audio_paths[0]
            self._refresh_background_music_label()
            self.background_music_list.selection_set(destination)

    def _setting_heading(
        self,
        parent: tk.Widget,
        text: str,
        help_key: str,
        *,
        pady: tuple[int, int] = (0, 0),
    ) -> None:
        """A compact label with a hover-only explanation for global settings."""
        row = ttk.Frame(parent)
        row.pack(anchor="w", pady=pady)
        ttk.Label(row, text=text).pack(side="left")
        help_icon = tk.Label(
            row,
            text="?",
            foreground="#246fa8",
            cursor="question_arrow",
            font=("Segoe UI", 9, "bold"),
        )
        help_icon.pack(side="left", padx=(5, 0))
        help_icon.bind("<Enter>", lambda event: self._show_quality_tooltip(event, self.t(help_key)))
        help_icon.bind("<Leave>", self._hide_quality_tooltip)

    def _setting_scale(
        self, parent: tk.Widget, field: str, start: float, end: float, resolution: float, formatter,
        on_change: Callable[[float], None] | None = None,
    ) -> None:
        variable = tk.DoubleVar(value=float(getattr(self.project, field)))
        value_label = ttk.Label(parent, anchor="e")
        value_label.pack(fill="x")

        def apply(value: str) -> None:
            rounded = round(float(value) / resolution) * resolution
            setattr(self.project, field, rounded)
            value_label.configure(text=formatter(rounded))
            if on_change is not None:
                on_change(rounded)
            if field in {"hold_seconds", "transition_seconds", "slide_seconds"} and hasattr(self, "duration_label"):
                self._update_duration_label()

        scale = tk.Scale(
            parent, from_=start, to=end, resolution=resolution, orient="horizontal",
            variable=variable, showvalue=False, command=apply, highlightthickness=0,
        )
        scale.pack(fill="x")
        apply(str(variable.get()))
        self._settings_vars[field] = variable

    def _integer_setting_scale(
        self, parent: tk.Widget, field: str, start: int, end: int, formatter,
        on_change: Callable[[int], None] | None = None,
    ) -> None:
        variable = tk.IntVar(value=int(getattr(self.project, field)))
        value_label = ttk.Label(parent, anchor="e")
        value_label.pack(fill="x")
        initializing = True

        def apply(value: str, *, initial: bool = False) -> None:
            setting = int(round(float(value)))
            setattr(self.project, field, setting)
            # Tk invokes the scale callback while the surrounding tab is still
            # being built.  At that point later widgets (and even later tabs)
            # do not exist yet, so only update the value display here.  The
            # regular callback path is reserved for an actual user change.
            if on_change is not None and not initial and not initializing:
                on_change(setting)
            value_label.configure(text=formatter(setting))
            if not initial and not initializing and field.startswith("timelapse_") and hasattr(self, "header_duration_label"):
                self._update_duration_label()

        scale = tk.Scale(
            parent, from_=start, to=end, resolution=1, orient="horizontal",
            variable=variable, showvalue=False, command=apply, highlightthickness=0,
        )
        scale.pack(fill="x")
        apply(str(variable.get()), initial=True)
        initializing = False
        self._settings_vars[field] = variable

    def _eligible_cards_for_target(self) -> list[tuple[StoryboardCard, dict]]:
        if not self.project.analysis_path:
            return []
        try:
            records = json.loads(Path(self.project.analysis_path).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        by_path = {str(Path(record["path"]).resolve()): record for record in records if record.get("path")}
        eligible: list[tuple[StoryboardCard, dict]] = []
        for card in self.project.cards:
            record = by_path.get(str(Path(card.source_path).resolve()))
            # Deferred cards are technically suitable; they were merely held back
            # by an earlier burst-photo reduction.  Once the user disables that
            # reduction, they must become available to the desired-count picker.
            usable_statuses = {"accepted"}
            if self.project.series_minimum_gap_minutes <= 0:
                usable_statuses.add("deferred")
            # The internal ``review`` status is intentionally broader than a
            # yellow card: it can also occur for genuinely unusable geometry.
            # The user-facing selection must instead follow the same traffic
            # light classification shown on each card.
            if not record or record.get("status") not in usable_statuses | {"review"}:
                continue
            if not self._pose_is_accepted(record):
                continue
            traffic_light, _colour, _text = self._card_quality(card)
            quality_level = {"green": 0, "yellow": 1, "red": 2}[traffic_light]
            if quality_level <= self.project.selection_quality_level:
                eligible.append((card, record))
        return eligible

    def _pose_is_accepted(self, record: dict) -> bool:
        yaw = abs(float((record.get("metrics") or {}).get("pose_yaw_degrees", 0.0)))
        return yaw <= self.project.maximum_side_view_degrees

    @staticmethod
    def _target_quality(record: dict) -> tuple[float, float, float, float]:
        metrics = record.get("metrics") or {}
        # Accepted images have already passed the initial check. YuNet score and
        # visible face size decide only between nearby chronological alternatives.
        return (
            1.0 if record.get("status") == "accepted" else 0.0,
            float(metrics.get("yunet_score", 0.0)),
            float(metrics.get("face_height_ratio", 0.0)),
            -abs(float(metrics.get("pose_yaw_degrees", 0.0))),
        )

    def apply_desired_image_count(self) -> None:
        try:
            desired = max(1, int(self.desired_count_var.get()))
        except tk.TclError:
            messagebox.showerror(self.t("desired_count"), self.t("whole_number_required"), parent=self.root)
            return
        eligible = self._eligible_cards_for_target()
        if not eligible:
            messagebox.showinfo(self.t("desired_count"), self.t("no_suitable_for_auto"), parent=self.root)
            return
        target = min(desired, len(eligible))
        chosen: set[int] = set()
        # Divide the chronological sequence into equally sized portions. This
        # prevents a large event from consuming the complete requested selection.
        for index in range(target):
            start = index * len(eligible) // target
            end = (index + 1) * len(eligible) // target
            segment = eligible[start:max(start + 1, end)]
            best_card, _ = max(segment, key=lambda item: self._target_quality(item[1]))
            chosen.add(id(best_card))
        # This is an explicit automatic re-selection.  Every non-eligible card,
        # especially a red one, is disabled even if it happened to be active
        # before the user requested a new distribution.
        for card in self.project.cards:
            card.enabled = id(card) in chosen
        self.project.desired_image_count = desired
        self._build_card_grid()
        self.refresh_inspector()
        self._update_selection_summary()
        self._update_duration_label()

    def _update_selection_summary(self) -> None:
        self._refresh_selection_controls()

    def _update_duration_label(self) -> None:
        count = sum(card.enabled for card in self.project.cards)
        slide_count = int(bool(self.project.opening_slide_path)) + int(bool(self.project.closing_slide_path))
        if self.project.movie_mode == "timelapse":
            seconds = count * (
                self.project.timelapse_frames_per_image + self.project.timelapse_transition_frames
            ) / self.project.fps
        else:
            seconds = count * (self.project.hold_seconds + self.project.transition_seconds)
        seconds += slide_count * self.project.slide_seconds
        # The normal initial card fade is replaced by the opening-slide fade.
        # A closing slide adds one additional soft transition after the stack.
        if self.project.closing_slide_path:
            seconds += self.project.transition_seconds
        minutes, remainder = divmod(round(seconds), 60)
        duration = (
            self.t.format("duration_value", minutes=minutes, seconds=remainder)
            if minutes else self.t.format("duration_seconds", seconds=remainder)
        )
        key = "duration_summary_with_slides" if slide_count else "duration_summary"
        if hasattr(self, "duration_label") and self.duration_label.winfo_exists():
            self.duration_label.configure(text=self.t.format(key, count=count, duration=duration, slides=slide_count))
        if hasattr(self, "header_duration_label") and self.header_duration_label.winfo_exists():
            self.header_duration_label.configure(text=self.t.format("header_duration", duration=duration))
        self._refresh_final_export_summary()

    def _resolution_label(self) -> str:
        labels = {
            (854, 480): "480p (854 x 480)",
            (1280, 720): "720p (1280 x 720)",
            (1920, 1080): "1080p (1920 x 1080)",
            (3840, 2160): "4K (3840 x 2160)",
            (1080, 1920): f"{self.t('phone_portrait')} (1080 x 1920)",
            (1080, 1080): f"{self.t('square')} (1080 x 1080)",
        }
        return labels.get((self.project.output_width, self.project.output_height), "1080p (1920 x 1080)")

    def _resolution_options(self) -> tuple[str, ...]:
        return (
            "480p (854 x 480)", "720p (1280 x 720)", "1080p (1920 x 1080)", "4K (3840 x 2160)",
            f"{self.t('phone_portrait')} (1080 x 1920)", f"{self.t('square')} (1080 x 1080)",
        )

    def _quality_label(self) -> str:
        return {
            "high": self.t("quality_high"),
            "smaller": self.t("quality_smaller"),
        }.get(self.project.output_quality, self.t("quality_standard"))

    def _preview_resolution_label(self) -> str:
        width, height = self.project.preview_width, self.project.preview_height
        label = {854: "480p", 1280: "720p", 1920: "1080p"}.get(max(width, height), "720p")
        return f"{label} ({width} x {height})"

    def _preview_resolution_options(self) -> tuple[str, ...]:
        """Offer preview size tiers while retaining the final movie's aspect ratio."""
        return tuple(
            f"{label} ({width} x {height})"
            for label, (width, height) in (
                ("480p", self._preview_dimensions(854)),
                ("720p", self._preview_dimensions(1280)),
                ("1080p", self._preview_dimensions(1920)),
            )
        )

    def _preview_dimensions(self, long_edge: int) -> tuple[int, int]:
        """Scale a chosen preview tier to the current final-output proportions."""
        output_long_edge = max(self.project.output_width, self.project.output_height)
        scale = long_edge / output_long_edge
        width = max(2, round(self.project.output_width * scale / 2) * 2)
        height = max(2, round(self.project.output_height * scale / 2) * 2)
        return width, height

    def _preview_long_edge(self) -> int:
        current = max(self.project.preview_width, self.project.preview_height)
        return min((854, 1280, 1920), key=lambda candidate: abs(candidate - current))

    def _sync_preview_aspect_ratio(self) -> None:
        self.project.preview_width, self.project.preview_height = self._preview_dimensions(self._preview_long_edge())

    def _eye_line_label(self, value: float) -> str:
        if self.t.language == "en":
            if abs(value - (1 / 3)) < 0.003:
                return f"{value * 100:.1f}% from top (upper third)"
            if abs(value - 0.382) < 0.003:
                return f"{value * 100:.1f}% from top (golden ratio)"
            return f"{value * 100:.1f}% from top"
        if abs(value - (1 / 3)) < 0.003:
            return f"{value * 100:.1f}% von oben (obere Drittellinie)"
        if abs(value - 0.382) < 0.003:
            return f"{value * 100:.1f}% von oben (goldener Schnitt)"
        return f"{value * 100:.1f}% von oben"

    def _set_resolution(self, label: str) -> None:
        self.project.output_width, self.project.output_height = {
            "480p (854 x 480)": (854, 480),
            "720p (1280 x 720)": (1280, 720),
            "1080p (1920 x 1080)": (1920, 1080),
            "4K (3840 x 2160)": (3840, 2160),
            f"{self.t('phone_portrait')} (1080 x 1920)": (1080, 1920),
            f"{self.t('square')} (1080 x 1080)": (1080, 1080),
        }[label]
        self._sync_preview_aspect_ratio()
        preview_var = self._settings_vars.get("preview_resolution")
        if hasattr(self, "preview_resolution_picker"):
            self.preview_resolution_picker.configure(values=self._preview_resolution_options())
        if preview_var is not None:
            preview_var.set(self._preview_resolution_label())
        # The traffic-light status depends on the target resolution. Reapply an
        # active quality filter so the visible cards always match its label.
        if self._active_filter_label() != self.t("all_cards"):
            self._apply_card_filter()
        else:
            self.update_card_styles()
        self._refresh_final_export_summary()

    def _set_preview_resolution(self, label: str) -> None:
        tier = {"480p": 854, "720p": 1280, "1080p": 1920}[label.split(" ", 1)[0]]
        self.project.preview_width, self.project.preview_height = self._preview_dimensions(tier)

    def _set_fps(self, label: str) -> None:
        self.project.fps = float(label.split()[0])
        self._refresh_final_export_summary()

    def _set_output_quality(self, label: str) -> None:
        self.project.output_quality = {
            self.t("quality_high"): "high",
            self.t("quality_smaller"): "smaller",
        }.get(label, "standard")
        self._refresh_final_export_summary()

    def _refresh_final_export_summary(self) -> None:
        """Keep the final target explicit next to the export button."""
        # Audio and slides are built before the Export tab.  They can request a
        # refresh safely, but its widgets do not exist until that later step.
        if (
            not hasattr(self, "final_export_summary_label")
            or not hasattr(self, "final_export_details_label")
            or not self.final_export_summary_label.winfo_exists()
            or not self.final_export_details_label.winfo_exists()
        ):
            return
        self.final_export_summary_label.configure(
            text=self.t.format(
                "final_export_summary",
                resolution=self._resolution_label(), fps=self.project.fps,
                quality=self._quality_label(),
            )
        )
        count = sum(card.enabled for card in self.project.cards)
        slide_count = int(bool(self.project.opening_slide_path)) + int(bool(self.project.closing_slide_path))
        seconds = count * (self.project.hold_seconds + self.project.transition_seconds)
        seconds += slide_count * self.project.slide_seconds
        if self.project.closing_slide_path:
            seconds += self.project.transition_seconds
        minutes, remainder = divmod(round(seconds), 60)
        duration = (
            self.t.format("duration_value", minutes=minutes, seconds=remainder)
            if minutes else self.t.format("duration_seconds", seconds=remainder)
        )
        music_count = len(self._background_music_paths())
        music_text = self.t("none") if not music_count else (
            f"{music_count} {'track' if music_count == 1 and self.t.language == 'en' else ('tracks' if self.t.language == 'en' else 'Titel')}"
        )
        quality_counts = {"green": 0, "yellow": 0, "red": 0}
        for card in self.project.cards:
            if card.enabled:
                quality, _colour, _text = self._card_quality(card)
                quality_counts[quality] += 1
        self.final_export_details_label.configure(text="\n".join((
            self.t.format("export_cards", count=count),
            self.t.format("export_quality_counts", **quality_counts),
            self.t.format("export_slides", value=self.t("yes") if slide_count else self.t("no")),
            self.t.format("export_music", value=music_text),
            self.t.format("export_duration", duration=duration),
        )))

    def _toggle_advanced_output_options(self) -> None:
        self.project.advanced_output_options = self.advanced_output_var.get()
        self._refresh_advanced_output_visibility()

    def _refresh_advanced_output_visibility(self) -> None:
        if not hasattr(self, "advanced_output_frame"):
            return
        if self.project.advanced_output_options:
            self.advanced_output_frame.pack(fill="x", pady=(16, 0))
        else:
            self.advanced_output_frame.pack_forget()

    def _set_card_size(self, label: str) -> None:
        self._card_zoom = {"Klein": 0.75, "Mittel": 1.0, "Gross": 1.25}[label]
        self._thumb_cache.clear()
        if hasattr(self, "grid"):
            previous_columns = self._column_count
            self._update_responsive_grid()
            if self._column_count == previous_columns:
                self._build_card_grid()

    def _card_dimensions(self) -> tuple[int, int]:
        return round(210 * self._card_zoom), round(150 * self._card_zoom)

    def _schedule_responsive_grid(self, _event: tk.Event) -> None:
        if self._resize_after_id:
            self.root.after_cancel(self._resize_after_id)
        self._resize_after_id = self.root.after(80, self._update_responsive_grid)

    def _update_responsive_grid(self) -> None:
        self._resize_after_id = None
        thumbnail_width, _ = self._card_dimensions()
        available = max(1, self.canvas.winfo_width())
        # The compact inspector has a fixed width; use the reclaimed workspace for
        # up to six cards before asking the user to scroll vertically.
        columns = min(6, max(1, (available - 12) // (thumbnail_width + 22)))
        needs_initial_build = bool(self.project.cards) and not self._card_widgets and not self._building_card_grid
        if columns != self._column_count or needs_initial_build:
            self._column_count = columns
            if self._building_card_grid:
                self._grid_rebuild_pending = True
            else:
                self._build_card_grid()

    def _ensure_initial_card_grid(self) -> None:
        """Recover from a first layout pass that left the visible grid empty."""
        if self.project.cards and not self._card_widgets and not self._building_card_grid:
            self._update_responsive_grid()
            if not self._card_widgets:
                self._build_card_grid(chunked=len(self.project.cards) > 500)

    def _resize_inspector(self, event: tk.Event) -> None:
        self.inspector_canvas.itemconfigure(self._inspector_window, width=event.width)
        self.root.after_idle(self._update_settings_scrollregion)

    def _resize_selection(self, event: tk.Event) -> None:
        self.selection_canvas.itemconfigure(self._selection_window, width=event.width)
        self.root.after_idle(self._update_selection_scrollregion)

    def _resize_audio(self, event: tk.Event) -> None:
        self.audio_canvas.itemconfigure(self._audio_window, width=event.width)
        self.root.after_idle(self._update_audio_scrollregion)

    def _update_audio_scrollregion(self) -> None:
        """Show the Audio & Slides scrollbar only when its controls no longer fit."""
        bbox = self.audio_canvas.bbox("all")
        if bbox is None:
            return
        self.audio_canvas.configure(scrollregion=bbox)
        needs_scroll = bbox[3] - bbox[1] > self.audio_canvas.winfo_height() + 2
        mapped = bool(self.audio_scroll.winfo_manager())
        if needs_scroll and not mapped:
            self.audio_scroll.pack(side="right", fill="y")
        elif not needs_scroll:
            self.audio_canvas.yview_moveto(0)
            if mapped:
                self.audio_scroll.pack_forget()

    def _update_selection_scrollregion(self) -> None:
        """Show the Storyboard scrollbar only when its controls no longer fit."""
        if not hasattr(self, "selection_scroll"):
            return
        bbox = self.selection_canvas.bbox("all")
        if bbox is None:
            return
        self.selection_canvas.configure(scrollregion=bbox)
        content_height = bbox[3] - bbox[1]
        viewport_height = self.selection_canvas.winfo_height()
        needs_scroll = content_height > viewport_height + 2
        mapped = bool(self.selection_scroll.winfo_manager())
        if needs_scroll and not mapped:
            self.selection_scroll.pack(side="right", fill="y")
        elif not needs_scroll:
            self.selection_canvas.yview_moveto(0)
            if mapped:
                self.selection_scroll.pack_forget()

    def _update_settings_scrollregion(self) -> None:
        """Hide the settings scrollbar and reset its view when every control fits."""
        if not hasattr(self, "inspector_scroll"):
            return
        bbox = self.inspector_canvas.bbox("all")
        if bbox is None:
            return
        self.inspector_canvas.configure(scrollregion=bbox)
        content_height = bbox[3] - bbox[1]
        viewport_height = self.inspector_canvas.winfo_height()
        needs_scroll = content_height > viewport_height + 2
        mapped = bool(self.inspector_scroll.winfo_manager())
        if needs_scroll and not mapped:
            self.inspector_scroll.pack(side="right", fill="y")
        elif not needs_scroll:
            self.inspector_canvas.yview_moveto(0)
            if mapped:
                self.inspector_scroll.pack_forget()

    def _center_dialog(self, dialog: tk.Toplevel) -> None:
        """Centre custom dialogs over the current Years in Focus window."""
        dialog.update_idletasks()
        width, height = dialog.winfo_reqwidth(), dialog.winfo_reqheight()
        x = self.root.winfo_rootx() + max(0, (self.root.winfo_width() - width) // 2)
        y = self.root.winfo_rooty() + max(0, (self.root.winfo_height() - height) // 2)
        dialog.geometry(f"+{x}+{y}")

    def _style_progress_dialog(self, dialog: tk.Toplevel) -> None:
        """Match short-running modal dialogs to the shared suite palette."""
        dialog.configure(background="#f4f6f8")

    @staticmethod
    def _read_output(process: subprocess.Popen[str], target: queue.Queue[str]) -> None:
        if process.stdout is not None:
            for line in process.stdout:
                target.put(line.rstrip())

    def _start_output_reader(self, process: subprocess.Popen[str], kind: str) -> None:
        lines = self._import_lines if kind == "import" else self._export_lines
        log = self._import_log if kind == "import" else self._export_log
        while not lines.empty():
            lines.get_nowait()
        log.clear()
        threading.Thread(target=self._read_output, args=(process, lines), daemon=True).start()

    def _drain_progress(self, kind: str, progress: ttk.Progressbar, status: ttk.Label) -> None:
        lines = self._import_lines if kind == "import" else self._export_lines
        log = self._import_log if kind == "import" else self._export_log
        while not lines.empty():
            line = lines.get_nowait()
            log.append(line)
            if not line.startswith("FM_PROGRESS\t"):
                continue
            _, phase, current, total = line.split("\t")
            current_value, total_value = int(current), int(total)
            phase_key = {
                "Analyse": "progress_analysis",
                "Reihenaufnahmen prüfen": "progress_burst_check",
                "Projektdaten schreiben": "progress_project_data",
                "Kontaktbogen erstellen": "progress_contact_sheet",
                "Gesichtsgeometrie": "progress_face_geometry",
                "Karten vorbereiten": "progress_prepare_cards",
                "Video schreiben": "progress_write_video",
                "Tonspur hinzufügen": "progress_add_audio",
                "add_audio": "progress_add_audio",
                "encode_quality": "progress_encode_quality",
            }.get(phase)
            translated_phase = self.t(phase_key) if phase_key else phase
            # Contact-sheet creation has only a start and an end event. Keep an
            # indeterminate bar moving during that interval so it never looks stuck.
            if phase == "Kontaktbogen erstellen" and current_value == 0 and total_value == 1:
                progress.configure(mode="indeterminate")
                progress.start(12)
            else:
                progress.stop()
                progress.configure(mode="determinate", maximum=max(1, total_value), value=current_value)
            status.configure(text=self.t.format("progress_of", phase=translated_phase, current=current_value, total=total_value))

    def _on_cards_yview(self, first: str, last: str) -> None:
        """Sync the card scrollbar and update the chronological context label."""
        self.cards_scroll.set(first, last)
        self._update_sticky_year_separator()

    def _update_sticky_year_separator(self) -> None:
        """Keep the current year visible once its regular divider has scrolled away."""
        if (
            not self.project.show_year_separators
            or self._sort_var.get() != self.t("date")
            or not self._year_separator_widgets
        ):
            self.sticky_year_label.place_forget()
            return
        top = self.canvas.canvasy(0)
        current: tuple[str, tk.Widget] | None = None
        for marker, widget in self._year_separator_widgets:
            if not widget.winfo_exists():
                continue
            if widget.winfo_y() <= top:
                current = (marker, widget)
            else:
                break
        if current is None:
            self.sticky_year_label.place_forget()
            return
        marker, widget = current
        if top <= widget.winfo_y() + widget.winfo_height():
            self.sticky_year_label.place_forget()
            return
        self.sticky_year_label.configure(text=marker)
        self.sticky_year_label.place(x=8, y=5)
        self.sticky_year_label.lift()

    def _mousewheel(self, event: tk.Event) -> str | None:
        """Scroll only a YiF canvas, never controls in a modal dialog."""
        try:
            if str(event.widget.winfo_toplevel()) != str(self.root):
                return None
        except tk.TclError:
            return None
        target = self.root.winfo_containing(event.x_root, event.y_root)
        if self._is_descendant(target, self.selection_canvas):
            self.selection_canvas.yview_scroll(-int(event.delta / 120), "units")
            return "break"
        if self._is_descendant(target, self.audio_canvas):
            self.audio_canvas.yview_scroll(-int(event.delta / 120), "units")
            return "break"
        if self._is_descendant(target, self.inspector_canvas):
            self.inspector_canvas.yview_scroll(-int(event.delta / 120), "units")
            return "break"
        if self._is_descendant(target, self.canvas):
            self.canvas.yview_scroll(-int(event.delta / 120), "units")
            return "break"
        return None

    def _digikam_connection_error_text(self, error: Exception) -> str:
        """Turn common database-driver noise into a clear action for normal users."""
        details = str(error)
        lowered = details.casefold()
        if "unknown database" in lowered:
            hint = self.t("digikam_database_hint")
        elif "can't connect" in lowered or "connection refused" in lowered or "10061" in lowered:
            hint = self.t("digikam_service_hint")
        else:
            hint = self.t("digikam_settings_hint")
        return self.t.format("digikam_connection_failed", hint=hint, error=details)

    @staticmethod
    def _is_descendant(widget: tk.Misc | None, ancestor: tk.Misc) -> bool:
        while widget is not None:
            if widget is ancestor:
                return True
            parent_name = widget.winfo_parent()
            if not parent_name:
                return False
            widget = widget.nametowidget(parent_name)
        return False

    def reduce_series(self) -> None:
        minimum_gap = self.project.series_minimum_gap_minutes
        if minimum_gap <= 0:
            messagebox.showinfo(self.t("series_title"), self.t("series_off"), parent=self.root)
            return
        try:
            records = json.loads(Path(self.project.analysis_path).read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            messagebox.showerror(self.t("series_title"), self.t.format("analysis_read_failed", error=error), parent=self.root)
            return
        by_path = {str(Path(record["path"]).resolve()): record for record in records if record.get("path")}
        candidates: list[tuple[StoryboardCard, dict]] = []
        for card in self.project.cards:
            record = by_path.get(str(Path(card.source_path).resolve()))
            if card.enabled and record and record.get("capture_time"):
                candidates.append((card, record))
        candidates.sort(key=lambda entry: entry[1]["capture_time"])
        groups: list[list[tuple[StoryboardCard, dict]]] = []
        limit_seconds = minimum_gap * 60
        for candidate in candidates:
            if not groups:
                groups.append([candidate])
                continue
            previous = datetime.fromisoformat(groups[-1][-1][1]["capture_time"])
            current = datetime.fromisoformat(candidate[1]["capture_time"])
            if (current - previous).total_seconds() <= limit_seconds:
                groups[-1].append(candidate)
            else:
                groups.append([candidate])

        to_disable: list[StoryboardCard] = []
        for group in groups:
            if len(group) < 2:
                continue
            def quality(entry: tuple[StoryboardCard, dict]) -> tuple[float, float, str]:
                metrics = entry[1].get("metrics") or {}
                return (
                    float(metrics.get("yunet_score", 0.0)),
                    float(metrics.get("face_height_ratio", 0.0)),
                    entry[0].source_path,
                )
            best_card, _ = max(group, key=quality)
            to_disable.extend(card for card, _ in group if card is not best_card)
        if not to_disable:
            messagebox.showinfo(self.t("series_title"), self.t("series_none"), parent=self.root)
            return
        if not messagebox.askyesno(
            self.t("reduce_series"),
            self.t.format("series_reduce_confirm", count=len(to_disable)),
            parent=self.root,
        ):
            return
        for card in to_disable:
            card.enabled = False
        self.refresh_inspector()
        self._update_duration_label()

    @staticmethod
    def _workspace_root() -> Path:
        return application_root()

    def new_project(self) -> None:
        if not self._confirm_project_replacement():
            return
        project = StoryboardProject(analysis_path="", title=PRODUCT_NAME)
        project_path = self._workspace_root() / "Years in Focus.yif.json"
        self._replace_project(project, project_path)

    def open_project(self) -> None:
        selected = filedialog.askopenfilename(
            title=self.t("open_project_title"),
            filetypes=[
                (self.t("project_file"), "*.yif.json"),
                (self.t("legacy_project_file"), "*.facemovie.json"),
                (self.t("json_file"), "*.json"),
            ],
        )
        if not selected:
            return
        try:
            project_path = Path(selected)
            if not self._confirm_project_replacement():
                return
            self._replace_project(StoryboardProject.load(project_path), project_path)
        except (OSError, ValueError, json.JSONDecodeError) as error:
            messagebox.showerror(self.t("open_project_title"), self.t.format("open_project_failed", error=error), parent=self.root)

    def _open_recent_project(self, project_path: Path) -> None:
        if not project_path.is_file():
            self._recent_projects = [value for value in self._recent_projects if Path(value) != project_path]
            return
        try:
            if not self._confirm_project_replacement():
                return
            self._replace_project(StoryboardProject.load(project_path), project_path)
        except (OSError, ValueError, json.JSONDecodeError) as error:
            messagebox.showerror(self.t("open_project_title"), self.t.format("open_project_failed", error=error), parent=self.root)

    def _missing_card_paths(self) -> list[str]:
        return [card.source_path for card in self.project.cards if not Path(card.source_path).is_file()]

    def _missing_enabled_card_paths(self) -> list[str]:
        """Return unavailable sources that the current export would need."""
        return [
            card.source_path
            for card in self.project.cards
            if card.enabled and not Path(card.source_path).is_file()
        ]

    def _offer_missing_original_relink(self) -> None:
        """Offer recovery once after opening; a red card alone is not enough guidance."""
        missing = self._missing_card_paths()
        if not missing:
            return
        if messagebox.askyesno(
            self.t("missing_originals_title"),
            self.t.format("missing_originals_body", count=len(missing)),
            parent=self.root,
        ):
            self.relink_missing_images()

    def _expected_source_sizes(self) -> dict[str, tuple[int, int]]:
        """Read the stored dimensions used to reject unsafe same-name matches."""
        try:
            records = json.loads(Path(self.project.analysis_path).read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            return {}
        expected: dict[str, tuple[int, int]] = {}
        for record in records:
            path, size = record.get("path"), record.get("source_size")
            if not path or not isinstance(size, (list, tuple)) or len(size) != 2:
                continue
            try:
                width, height = int(size[0]), int(size[1])
            except (TypeError, ValueError):
                continue
            if width > 0 and height > 0:
                expected[normalised_path(str(path))] = (width, height)
        return expected

    def relink_missing_images(self) -> None:
        """Search a user-picked root in the background and offer only safe matches."""
        missing = self._missing_card_paths()
        if not missing:
            messagebox.showinfo(self.t("relink_missing_images"), self.t("relink_none"), parent=self.root)
            return
        selected = filedialog.askdirectory(parent=self.root, title=self.t("relink_choose_root"))
        if not selected:
            return
        root = Path(selected)
        dialog = tk.Toplevel(self.root)
        dialog.title(self.t("relink_scanning"))
        dialog.transient(self.root)
        dialog.resizable(False, False)
        ttk.Label(dialog, text=self.t("relink_scanning"), padding=(18, 16, 18, 4)).pack()
        ttk.Label(dialog, text=self.t("relink_scanning_body"), foreground="#666", padding=(18, 0, 18, 12), wraplength=360).pack()
        progress = ttk.Progressbar(dialog, mode="indeterminate", length=320)
        progress.pack(padx=18, pady=(0, 18))
        progress.start(12)
        self._center_dialog(dialog)
        expected = self._expected_source_sizes()

        def scan() -> None:
            try:
                self._relink_messages.put(find_unique_matches(missing, root, expected))
            except Exception as error:  # keep a filesystem failure inside the GUI flow
                self._relink_messages.put(error)

        threading.Thread(target=scan, daemon=True).start()

        def finish() -> None:
            try:
                result = self._relink_messages.get_nowait()
            except queue.Empty:
                self.root.after(120, finish)
                return
            progress.stop()
            dialog.destroy()
            if isinstance(result, Exception):
                messagebox.showerror(self.t("relink_missing_images"), str(result), parent=self.root)
                return
            self._review_bulk_relink(result)

        self.root.after(120, finish)

    def _review_bulk_relink(self, result: RelinkSearch) -> None:
        if not result.matches:
            messagebox.showinfo(self.t("relink_result_title"), self.t("relink_none"), parent=self.root)
            return
        if messagebox.askyesno(
            self.t("relink_result_title"),
            self.t.format(
                "relink_result", found=len(result.matches), ambiguous=len(result.ambiguous), unresolved=len(result.unresolved),
            ),
            parent=self.root,
        ):
            self._apply_relinks(result.matches)

    def relink_card(self, index: int) -> None:
        """Let the user repair one missing card with an explicit file choice."""
        if not 0 <= index < len(self.project.cards):
            return
        old_path = self.project.cards[index].source_path
        old_file = Path(old_path)
        initial_directory = old_file.parent if old_file.parent.is_dir() else self.project_path.parent
        selected = filedialog.askopenfilename(
            parent=self.root,
            title=self.t.format("relink_choose_original", filename=old_file.name),
            initialdir=str(initial_directory),
            initialfile=old_file.name,
            filetypes=[(self.t("images_filetype"), "*.jpg *.jpeg"), (self.t("all_files"), "*.*")],
        )
        new_path = Path(selected) if selected else None
        if new_path is None:
            return
        if not new_path.is_file() or new_path.suffix.casefold() not in {".jpg", ".jpeg"}:
            messagebox.showerror(self.t("relink_original"), self.t("relink_invalid_file"), parent=self.root)
            return
        # A same-named file is the normal result after a folder move. The card
        # already identifies the missing filename, so asking whether A should
        # replace A only adds uncertainty.
        if old_file.name.casefold() == new_path.name.casefold():
            self._apply_relinks({old_path: new_path.resolve()})
            return
        if messagebox.askyesno(
            self.t("relink_original"),
            self.t.format("relink_confirm_one", old=old_file.name, new=new_path.name),
            parent=self.root,
        ):
            self._apply_relinks({old_path: new_path.resolve()})

    @staticmethod
    def _write_json_atomically(path: Path, payload: object) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, suffix=".json", delete=False) as file:
            temporary = Path(file.name)
            json.dump(payload, file, ensure_ascii=False, indent=2)
        temporary.replace(path)

    def _apply_relinks(self, matches: dict[str, Path]) -> None:
        """Persist all matching project sidecars together, after backing up the project."""
        if not matches:
            return
        replacements = {normalised_path(old): str(new.resolve()) for old, new in matches.items()}
        backup = self.project_path.with_suffix(self.project_path.suffix + ".before-relink.bak")
        try:
            if self.project_path.is_file():
                shutil.copy2(self.project_path, backup)
            for card in self.project.cards:
                replacement = replacements.get(normalised_path(card.source_path))
                if replacement:
                    card.source_path = replacement
            analysis_path = Path(self.project.analysis_path)
            if analysis_path.is_file():
                records = json.loads(analysis_path.read_text(encoding="utf-8"))
                for record in records:
                    replacement = replacements.get(normalised_path(str(record.get("path") or "")))
                    if replacement:
                        record["path"] = replacement
                self._write_json_atomically(analysis_path, records)
            for sidecar in (
                self.project_path.parent / f"{self.project_path.stem}-bilder.json",
                self.project_path.parent / f"{self.project_path.stem}-regionen.json",
                self.project_path.parent / f"{self.project_path.stem}-digiKam-regionen.json",
            ):
                if not sidecar.is_file():
                    continue
                payload = json.loads(sidecar.read_text(encoding="utf-8"))
                if not isinstance(payload, dict):
                    continue
                if isinstance(payload.get("images"), list):
                    payload["images"] = [replacements.get(normalised_path(str(value)), value) for value in payload["images"]]
                if isinstance(payload.get("regions"), dict):
                    payload["regions"] = {
                        replacements.get(normalised_path(str(key)), key): value for key, value in payload["regions"].items()
                    }
                self._write_json_atomically(sidecar, payload)
            self._analysis_by_path = None
            self._thumb_cache.clear()
            self._selected_preview_source = None
            self._mark_project_saved()
        except (OSError, ValueError, json.JSONDecodeError) as error:
            messagebox.showerror(self.t("relink_missing_images"), str(error), parent=self.root)
            return
        self._build_card_grid(chunked=len(self.project.cards) > 500)
        self.refresh_inspector()
        self._refresh_selection_controls()
        messagebox.showinfo(self.t("relink_result_title"), self.t.format("relink_done", count=len(matches)), parent=self.root)

    def _replace_project(self, project: StoryboardProject, project_path: Path) -> None:
        self._preview_alive = False
        for child in self.root.winfo_children():
            child.destroy()
        self.__init__(self.root, project, project_path)

    def import_images(self) -> None:
        if self._import_process and self._import_process.poll() is None:
            messagebox.showinfo(self.t("images_import_title"), self.t("analysis_running"), parent=self.root)
            return
        selected = filedialog.askopenfilenames(
            title=self.t("choose_images"),
            filetypes=[(self.t("images_filetype"), "*.jpg *.jpeg *.JPG *.JPEG"), (self.t("all_files"), "*.*")],
        )
        if not selected:
            return
        try:
            scan = self._scan_selected_images_with_feedback(tuple(Path(path) for path in selected))
        except (OSError, ValueError) as error:
            messagebox.showerror(self.t("images_import_title"), self.t.format("selection_unreadable", error=error), parent=self.root)
            return
        if not scan.image_files:
            messagebox.showerror(self.t("no_supported_images_title"), self.t("no_supported_images"), parent=self.root)
            return
        if self.project.cards and self.project.analysis_path and self.project.person_name:
            mode = self._choose_project_import_mode(scan)
            if mode is None:
                return
            if mode == "add":
                self._add_images_to_current_project(scan)
                return
        if not scan.person_counts:
            if not messagebox.askyesno(
                self.t("target_missing_title"),
                self.t.format("target_missing_body", count=len(scan.image_files)),
                parent=self.root,
            ):
                return
            manual = self._choose_manual_regions(scan)
            if manual is None:
                return
            person, regions = manual
            self._start_import(scan, person, regions=regions, title=scan.folder.name)
            return
        person = self._choose_import_person(scan)
        if not person:
            return
        missing_paths = tuple(path for path in scan.image_files if find_region(path, person) is None)
        # Count actual usable rectangles, rather than mere person-name tags.  Some
        # applications write a person keyword without a face-region geometry.
        tagged_for_person = len(scan.image_files) - len(missing_paths)
        if missing_paths:
            action = self._choose_incomplete_xmp_action(
                person, tagged_for_person, len(scan.image_files), len(missing_paths),
            )
            if action is None:
                return
            if action == "mark":
                missing_scan = ImportScan(scan.folder, missing_paths, {}, missing_paths)
                manual = self._choose_manual_regions(missing_scan, person_name=person)
                if manual is None:
                    return
                _manual_person, regions = manual
                self._start_import(scan, person, regions=regions, title=scan.folder.name)
                return
        self._start_import(scan, person)

    def _choose_project_import_mode(self, scan: ImportScan) -> str | None:
        """Make appending to an open project explicit and safe."""
        known = {str(Path(card.source_path).resolve()) for card in self.project.cards}
        new_count = sum(str(path.resolve()) not in known for path in scan.image_files)
        duplicate_count = len(scan.image_files) - new_count
        dialog = tk.Toplevel(self.root)
        dialog.title(self.t("project_import_title"))
        dialog.transient(self.root)
        dialog.grab_set()
        ttk.Label(dialog, text=self.t("project_import_heading"), font=("Segoe UI", 11, "bold"), padding=(18, 16, 18, 4)).pack(anchor="w")
        ttk.Label(
            dialog,
            text=self.t.format(
                "project_import_body", total=len(scan.image_files), new=new_count,
                duplicates=duplicate_count, person=self.project.person_name,
            ),
            justify="left", wraplength=520, padding=(18, 0, 18, 8),
        ).pack(anchor="w")
        result: dict[str, str | None] = {"mode": None}

        def choose(mode: str) -> None:
            result["mode"] = mode
            dialog.destroy()

        buttons = ttk.Frame(dialog, padding=(18, 4, 18, 18))
        buttons.pack(fill="x")
        ttk.Button(buttons, text=self.t("cancel"), command=dialog.destroy).pack(side="right")
        ttk.Button(buttons, text=self.t("project_import_new"), command=lambda: choose("new")).pack(side="right", padx=(0, 6))
        ttk.Button(buttons, text=self.t("project_import_add"), command=lambda: choose("add")).pack(side="right", padx=(0, 6))
        self._center_dialog(dialog)
        self.root.wait_window(dialog)
        return result["mode"]

    def _add_images_to_current_project(self, scan: ImportScan) -> None:
        """Analyse only new paths and append disabled cards without touching choices."""
        known = {str(Path(card.source_path).resolve()) for card in self.project.cards}
        new_paths = tuple(path for path in scan.image_files if str(path.resolve()) not in known)
        if not new_paths:
            messagebox.showinfo(self.t("project_import_title"), self.t("project_import_no_new"), parent=self.root)
            return
        # Re-scan the small delta so person coverage and manual gaps are accurate;
        # the original selection may have contained hundreds of already-known files.
        # Use the same visible XMP-reading feedback as a fresh import.  Even a
        # small delta can sit on a slow network drive, and silent work makes it
        # look as though the project has stopped responding.
        delta = self._scan_selected_images_with_feedback(new_paths)
        person = self.project.person_name
        missing_paths = tuple(path for path in delta.image_files if find_region(path, person) is None)
        regions: dict[str, object] | None = None
        if missing_paths:
            action = self._choose_incomplete_xmp_action(
                person, len(delta.image_files) - len(missing_paths), len(delta.image_files), len(missing_paths),
            )
            if action is None:
                return
            if action == "mark":
                manual_scan = ImportScan(delta.folder, missing_paths, {}, missing_paths)
                manual = self._choose_manual_regions(manual_scan, person_name=person)
                if manual is None:
                    return
                _manual_person, regions = manual
        self._start_project_image_update(delta, person, regions)

    def _scan_selected_images_with_feedback(self, paths: tuple[Path, ...]) -> ImportScan:
        """Read XMP person tags in a worker so file selection never looks stuck."""
        dialog = tk.Toplevel(self.root)
        dialog.title(self.t("reading_images_title"))
        dialog.transient(self.root)
        dialog.resizable(False, False)
        dialog.protocol("WM_DELETE_WINDOW", lambda: None)
        ttk.Label(dialog, text=self.t("reading_images"), padding=(18, 16, 18, 4)).pack()
        status = ttk.Label(dialog, text=self.t.format("reading_images_progress", current=0, total=len(paths)), foreground="#666")
        status.pack(padx=18, pady=(0, 10))
        progress = ttk.Progressbar(dialog, mode="determinate", maximum=max(1, len(paths)), length=360)
        progress.pack(padx=18, pady=(0, 18))
        self._center_dialog(dialog)
        messages: queue.Queue[tuple[str, object]] = queue.Queue()

        def worker() -> None:
            try:
                scan = scan_import_paths(paths, progress=lambda current, total: messages.put(("progress", (current, total))))
            except (OSError, ValueError) as error:
                messages.put(("error", error))
            else:
                messages.put(("done", scan))

        threading.Thread(target=worker, daemon=True, name="yif-xmp-scan").start()
        result: dict[str, ImportScan | Exception | None] = {"value": None}

        def watch() -> None:
            try:
                while True:
                    kind, value = messages.get_nowait()
                    if kind == "progress":
                        current, total = value  # type: ignore[misc]
                        progress.configure(maximum=max(1, total), value=current)
                        status.configure(text=self.t.format("reading_images_progress", current=current, total=total))
                    else:
                        result["value"] = value  # type: ignore[assignment]
                        dialog.destroy()
                        return
            except queue.Empty:
                pass
            self.root.after(60, watch)

        self.root.after(20, watch)
        self.root.wait_window(dialog)
        value = result["value"]
        if isinstance(value, Exception):
            raise value
        if isinstance(value, ImportScan):
            return value
        raise OSError(self.t("selection_unreadable"))

    def import_digikam(self) -> None:
        """Import from a saved or locally auto-discovered digiKam source."""
        settings = self._saved_digikam_connection()
        people: list[DigiKamPerson] | None = None
        if settings is not None:
            try:
                people = list_people(settings)
            except Exception as error:
                messagebox.showwarning(
                    self.t("digikam_auto_unavailable_title"),
                    self.t.format("digikam_auto_unavailable", details=self._digikam_connection_error_text(error)),
                    parent=self.root,
                )
                return
        if settings is None:
            discovery = discover_digikam_connection()
            if discovery is not None:
                settings = discovery.connection
                try:
                    people = list_people(settings)
                except Exception as error:
                    messagebox.showwarning(
                        self.t("digikam_auto_unavailable_title"),
                        self.t.format("digikam_auto_unavailable", details=self._digikam_connection_error_text(error)),
                        parent=self.root,
                    )
                    return
                self._remember_discovered_digikam(discovery.internal_server, settings)
        if people is None:
            configured = self.configure_digikam_source()
            if configured is None:
                return
            settings, people = configured
        self._import_digikam_person(settings, people)

    def _remember_discovered_digikam(self, internal_server: bool, settings: DigiKamConnection) -> None:
        """Persist non-sensitive auto-discovery results for later project updates."""
        kind = "Interne MariaDB (digiKam)" if internal_server else (
            "SQLite-Datenbank" if settings.database_type == "sqlite" else "Externe MariaDB"
        )
        previous_roots = self._digikam_profile.get("collection_roots", {})
        self._digikam_profile = {
            "kind": kind,
            "database": settings.database,
            "host": settings.host,
            "port": settings.port,
            "user": settings.user,
            "collection_roots": previous_roots if isinstance(previous_roots, dict) else {},
        }
        save_digikam_profile(self._digikam_profile)

    def configure_digikam_source(self) -> tuple[DigiKamConnection, list[DigiKamPerson]] | None:
        """Store a reusable read-only source profile; never persist passwords."""
        dialog = tk.Toplevel(self.root)
        dialog.title(self.t("digikam_connect"))
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.resizable(False, False)
        frame = ttk.Frame(dialog, padding=16)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="digiKam-Bibliothek verbinden", font=("Segoe UI", 11, "bold")).grid(
            row=0, column=0, columnspan=3, sticky="w"
        )
        ttk.Label(
            frame,
            text="Years in Focus liest nur bestätigte Personen, Bildpfade und Gesichtsrechtecke. Die Datenbank wird nicht verändert.",
            wraplength=470, foreground="#666",
        ).grid(row=1, column=0, columnspan=3, sticky="w", pady=(6, 14))
        ttk.Label(frame, text="Datenbanktyp").grid(row=2, column=0, sticky="w", pady=3)
        profile = self._digikam_profile
        stored_kind = str(profile.get("kind") or "Interne MariaDB (digiKam)")
        legacy_kind_labels = {
            "internal": "Interne MariaDB (digiKam)",
            "external": "Externe MariaDB",
            "sqlite": "SQLite-Datenbank",
        }
        kind_keys = {
            "internal": "digikam_internal_mariadb",
            "external": "digikam_external_mariadb",
            "sqlite": "digikam_sqlite",
        }
        kind_id = next((key for key, label in legacy_kind_labels.items() if label == stored_kind), "internal")
        display_to_kind = {self.t(key): identifier for identifier, key in kind_keys.items()}
        kind = tk.StringVar(value=self.t(kind_keys[kind_id]))
        kind_box = ttk.Combobox(
            frame, textvariable=kind, state="readonly", width=28,
            values=tuple(display_to_kind),
        )
        kind_box.grid(row=2, column=1, columnspan=2, sticky="ew", pady=3)
        host = tk.StringVar(value=str(profile.get("host") or "127.0.0.1"))
        port = tk.StringVar(value=str(profile.get("port") or "3307"))
        user = tk.StringVar(value=str(profile.get("user") or "root"))
        password = tk.StringVar(value=self._digikam_password)
        database = tk.StringVar(value=str(profile.get("database") or "digikam"))
        labels: list[ttk.Label] = []
        entries: list[tk.Widget] = []

        def field(row: int, label: str, variable: tk.StringVar, show: str | None = None) -> None:
            name = ttk.Label(frame, text=label)
            name.grid(row=row, column=0, sticky="w", pady=3)
            entry = ttk.Entry(frame, textvariable=variable, width=38, show=show or "")
            entry.grid(row=row, column=1, columnspan=2, sticky="ew", pady=3)
            labels.append(name)
            entries.append(entry)

        field(3, "Host", host)
        field(4, "Port", port)
        field(5, "Benutzer", user)
        field(6, "Passwort (optional)", password, "•")
        field(7, "Datenbank", database)
        database_entry = entries[-1]

        def selected_kind_id() -> str:
            return display_to_kind.get(kind.get(), "internal")

        def choose_sqlite() -> None:
            selected = filedialog.askopenfilename(
                parent=dialog, title=self.t("choose_sqlite_database"),
                filetypes=[(self.t("sqlite_database_file"), "*.db *.sqlite *.sqlite3"), (self.t("all_files"), "*.*")],
            )
            if selected:
                database.set(selected)

        browse = ttk.Button(frame, text=self.t("choose_file"), command=choose_sqlite)

        def apply_kind(*_args: object) -> None:
            is_sqlite = selected_kind_id() == "sqlite"
            for label, entry in zip(labels[:4], entries[:4]):
                label.configure(state="disabled" if is_sqlite else "normal")
                entry.configure(state="disabled" if is_sqlite else "normal")
            browse.grid_forget()
            if is_sqlite:
                browse.grid(row=7, column=2, sticky="e", pady=3)
                database_entry.configure(width=27)
            else:
                database_entry.configure(width=38)
                if selected_kind_id() == "external" and port.get() == "3307":
                    port.set("3306")
                elif selected_kind_id() == "internal" and port.get() == "3306":
                    port.set("3307")

        kind_box.bind("<<ComboboxSelected>>", apply_kind)
        apply_kind()
        status = ttk.Label(frame, foreground="#a65e00", wraplength=470)
        status.grid(row=8, column=0, columnspan=3, sticky="w", pady=(8, 4))
        result: dict[str, list[DigiKamPerson] | None] = {"people": None}

        def connect() -> None:
            try:
                settings = DigiKamConnection(
                    "sqlite" if selected_kind_id() == "sqlite" else "mariadb",
                    database.get().strip(), host.get().strip(), int(port.get() or "0"),
                    user.get().strip(), password.get(),
                )
                status.configure(text=self.t("digikam_connecting"), foreground="#666")
                dialog.update_idletasks()
                people = list_people(settings)
            except Exception as error:
                # Database drivers use different exception classes. None is allowed
                # to leave this dialog; credentials and paths are not echoed.
                status.configure(text=self._digikam_connection_error_text(error), foreground="#a00000")
                return
            if not people:
                status.configure(text="Verbunden, aber keine bestätigten Personen mit JPG/JPEG-Gesichtsregionen gefunden.")
                return
            result["people"] = people
            dialog.destroy()

        buttons = ttk.Frame(frame)
        buttons.grid(row=9, column=0, columnspan=3, sticky="e", pady=(10, 0))
        ttk.Button(buttons, text="Abbrechen", command=dialog.destroy).pack(side="right")
        ttk.Button(buttons, text="Verbinden und Personen laden", command=connect).pack(side="right", padx=(0, 6))
        localize_widget_tree(dialog, self.t)
        self._center_dialog(dialog)
        self.root.wait_window(dialog)
        if not result["people"]:
            return None
        # The password exists only for the active application session.
        settings = DigiKamConnection(
            "sqlite" if selected_kind_id() == "sqlite" else "mariadb",
            database.get().strip(), host.get().strip(), int(port.get() or "0"), user.get().strip(), password.get(),
        )
        self._digikam_password = password.get()
        previous_roots = self._digikam_profile.get("collection_roots", {})
        same_source = (
            self._digikam_profile.get("kind") == legacy_kind_labels[selected_kind_id()]
            and str(self._digikam_profile.get("database") or "") == settings.database
            and str(self._digikam_profile.get("host") or "") == settings.host
            and str(self._digikam_profile.get("port") or "") == str(settings.port)
            and str(self._digikam_profile.get("user") or "") == settings.user
        )
        self._digikam_profile = {
            "kind": legacy_kind_labels[selected_kind_id()],
            "database": settings.database,
            "host": settings.host,
            "port": settings.port,
            "user": settings.user,
            "collection_roots": previous_roots if same_source and isinstance(previous_roots, dict) else {},
        }
        save_digikam_profile(self._digikam_profile)
        return settings, result["people"]

    def _saved_digikam_connection(self) -> DigiKamConnection | None:
        profile = self._digikam_profile
        kind = str(profile.get("kind") or "")
        database = str(profile.get("database") or "").strip()
        if kind not in {"Interne MariaDB (digiKam)", "Externe MariaDB", "SQLite-Datenbank"} or not database:
            return None
        try:
            port = int(profile.get("port") or (3307 if kind.startswith("Interne") else 3306))
        except (TypeError, ValueError):
            return None
        return DigiKamConnection(
            "sqlite" if kind == "SQLite-Datenbank" else "mariadb",
            database,
            str(profile.get("host") or "127.0.0.1"),
            port,
            str(profile.get("user") or "root"),
            self._digikam_password,
        )

    def _import_digikam_person(self, settings: DigiKamConnection, people: list[DigiKamPerson]) -> None:
        person = self._choose_digikam_person(people)
        if not person:
            return
        try:
            subpaths = person_collection_subpaths(settings, person)
        except Exception as error:
            messagebox.showerror("digiKam-Import", f"Albumwurzel konnte nicht gelesen werden:\n{error}")
            return
        collection_roots = self._resolve_digikam_collection_roots(subpaths)
        if collection_roots is None:
            return
        try:
            images = person_images(settings, person, collection_roots)
        except Exception as error:
            messagebox.showerror("digiKam-Import", f"Bilder konnten nicht aus digiKam gelesen werden:\n{error}")
            return
        existing = [image for image in images if image.path.is_file()]
        if not existing:
            messagebox.showerror(
                "Keine erreichbaren JPG/JPEG-Bilder",
                "Für diese Person wurden Regionen gefunden, aber keine zugehörigen JPG/JPEG-Originale am gespeicherten Pfad. "
                "Bitte Albumwurzel und Laufwerke in digiKam prüfen.",
            )
            return
        missing = len(images) - len(existing)
        if missing:
            messagebox.showinfo(
                "Nicht erreichbare Bilder",
                f"{missing} von {len(images)} JPG/JPEG-Bildern sind am gespeicherten Ort nicht erreichbar und werden ausgelassen.",
            )
        scan = ImportScan(existing[0].path.parent, tuple(image.path for image in existing), {person.name: len(existing)}, ())
        regions = {str(image.path.resolve()): image.region for image in existing}
        digikam_source = {
            "person_tag_id": person.tag_id,
            "person_name": person.name,
            "database_type": settings.database_type,
            "database": settings.database,
            "host": settings.host,
            "port": settings.port,
            "user": settings.user,
            "collection_roots": {key: str(value) for key, value in collection_roots.items()},
            "imported_at": datetime.now().isoformat(timespec="seconds"),
        }
        self._start_import(
            scan, person.name, regions=regions, title=f"digiKam – {person.name}",
            digikam_source=digikam_source,
        )

    def update_digikam_project(self) -> None:
        """Incrementally add newly confirmed digiKam photos to this project."""
        if self._import_process and self._import_process.poll() is None:
            messagebox.showinfo("digiKam-Projekt aktualisieren", "Eine Bildanalyse läuft bereits.")
            return
        source = self.project.digikam_source or {}
        person_name = str(source.get("person_name") or "").strip()
        if not person_name:
            legacy_manifest = self.project_path.parent / f"{self.project_path.stem}-digiKam-regionen.json"
            try:
                person_name = str(json.loads(legacy_manifest.read_text(encoding="utf-8")).get("person") or "").strip()
            except (OSError, ValueError, json.JSONDecodeError):
                pass
        if not person_name:
            messagebox.showinfo(
                self.t("digikam_no_link_title"), self.t("digikam_no_link_body"), parent=self.root,
            )
            return
        settings = self._saved_digikam_connection()
        people: list[DigiKamPerson] | None = None
        if settings is not None:
            try:
                people = list_people(settings)
            except Exception:
                people = None
        if people is None:
            configured = self.configure_digikam_source()
            if configured is None:
                return
            settings, people = configured
        tag_id = source.get("person_tag_id")
        person = next((item for item in people if item.tag_id == tag_id), None)
        if person is None:
            matches = [item for item in people if item.name.casefold() == person_name.casefold()]
            if len(matches) == 1:
                person = matches[0]
            else:
                messagebox.showerror(
                    "digiKam-Person nicht gefunden",
                    f"Die gespeicherte Zielperson {person_name!r} konnte nicht eindeutig in digiKam gefunden werden.",
                )
                return
        try:
            roots = self._resolve_digikam_collection_roots(person_collection_subpaths(settings, person))
            if roots is None:
                return
            images = [image for image in person_images(settings, person, roots) if image.path.is_file()]
        except Exception as error:
            messagebox.showerror("digiKam-Projekt aktualisieren", f"digiKam konnte nicht gelesen werden:\n{error}")
            return
        known = {str(Path(card.source_path).resolve()) for card in self.project.cards}
        new_images = [image for image in images if str(image.path.resolve()) not in known]
        current_paths = {str(image.path.resolve()) for image in images}
        no_longer_confirmed = sum(1 for path in known if path not in current_paths)
        if not new_images:
            messagebox.showinfo(
                "digiKam-Projekt aktualisieren",
                f"Keine neuen bestätigten Bilder für {person.name}.\n"
                f"{no_longer_confirmed} bestehende Karten sind nicht mehr in der aktuellen digiKam-Auswahl; sie bleiben unverändert.",
            )
            return
        if not messagebox.askyesno(
            "digiKam-Projekt aktualisieren",
            f"Neue bestätigte Bilder: {len(new_images)}\n"
            f"Bereits im Projekt: {len(known)}\n"
            f"Nicht mehr in digiKam bestätigt: {no_longer_confirmed} (bleiben unverändert)\n\n"
            "Neue Bilder analysieren und als deaktivierte Karten ergänzen?",
        ):
            return
        self._start_digikam_update(settings, person, roots, new_images)

    def _start_digikam_update(
        self, settings: DigiKamConnection, person: DigiKamPerson, roots: dict[str, Path], images
    ) -> None:
        model = self._yunet_model_path()
        if model is None:
            messagebox.showerror("Gesichtsmodell fehlt", "Das für die Analyse benötigte YuNet-Modell wurde nicht gefunden.")
            return
        data_dir = Path(self.project.analysis_path).parent
        work_dir = Path(tempfile.mkdtemp(prefix="yif-update-", dir=data_dir))
        regions_path = work_dir / "regions.json"
        images_path = work_dir / "images.json"
        regions_path.write_text(
            json.dumps({"person": person.name, "regions": {str(image.path.resolve()): asdict(image.region) for image in images}}, ensure_ascii=False),
            encoding="utf-8",
        )
        images_path.write_text(json.dumps({"images": [str(image.path.resolve()) for image in images]}, ensure_ascii=False), encoding="utf-8")
        command = ([str(bundled_cli_path()), "align"] if getattr(sys, "frozen", False) else [sys.executable, "-m", "facemovie.cli", "align"]) + [
            "--output", str(work_dir), "--person", person.name, "--yunet-model", str(model),
            "--width", str(self.project.output_width), "--height", str(self.project.output_height),
            "--eye-y", str(self.project.eye_y), "--eye-distance", str(self.project.eye_distance),
            "--rotation-strength", "0", "--framing", "face-normalized", "--series-minutes",
            str(self.project.series_minimum_gap_minutes), "--series-keep", "1", "--reference-originals",
            "--regions-json", str(regions_path), "--input-list", str(images_path), "--progress",
        ]
        environment = os.environ.copy()
        if not getattr(sys, "frozen", False):
            environment["PYTHONPATH"] = str(self._workspace_root() / "src") + os.pathsep + environment.get("PYTHONPATH", "")
        try:
            self._import_cancelled = False
            self._import_process = subprocess.Popen(
                command, cwd=self._workspace_root(), env=environment, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", bufsize=1,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except OSError as error:
            shutil.rmtree(work_dir, ignore_errors=True)
            messagebox.showerror("Aktualisierung konnte nicht starten", str(error))
            return
        self._start_output_reader(self._import_process, "import")
        self._show_digikam_update_progress(work_dir, settings, person, roots)

    def _show_digikam_update_progress(
        self, work_dir: Path, settings: DigiKamConnection, person: DigiKamPerson, roots: dict[str, Path]
    ) -> None:
        dialog = tk.Toplevel(self.root)
        dialog.title("digiKam-Projekt aktualisieren")
        dialog.transient(self.root)
        dialog.resizable(False, False)
        dialog.protocol("WM_DELETE_WINDOW", lambda: None)
        ttk.Label(dialog, text="Neue Bilder werden analysiert …", padding=(18, 16, 18, 4)).pack()
        status = ttk.Label(dialog, text=person.name, foreground="#666", padding=(18, 0, 18, 12))
        status.pack()
        progress = ttk.Progressbar(dialog, mode="indeterminate", length=360)
        progress.pack(padx=18, pady=(0, 18))
        progress.start(12)
        ttk.Button(dialog, text="Abbrechen", command=self._cancel_import).pack(pady=(0, 14))
        self._center_dialog(dialog)
        self._import_dialog, self._import_status, self._import_progress = dialog, status, progress
        self.root.after(250, lambda: self._watch_digikam_update(work_dir, settings, person, roots))

    def _watch_digikam_update(
        self, work_dir: Path, settings: DigiKamConnection, person: DigiKamPerson, roots: dict[str, Path]
    ) -> None:
        process = self._import_process
        if process is None:
            return
        self._drain_progress("import", self._import_progress, self._import_status)
        if process.poll() is None:
            self.root.after(250, lambda: self._watch_digikam_update(work_dir, settings, person, roots))
            return
        process.wait()
        self._import_process = None
        self._import_progress.stop()
        self._import_dialog.destroy()
        if process.returncode:
            shutil.rmtree(work_dir, ignore_errors=True)
            if self._import_cancelled:
                messagebox.showinfo("Aktualisierung abgebrochen", "Das bestehende Projekt wurde nicht verändert.")
                return
            messagebox.showerror("Aktualisierung fehlgeschlagen", "\n".join(self._import_log) or "Unbekannter Fehler")
            return
        try:
            new_records = json.loads((work_dir / "analysis.json").read_text(encoding="utf-8"))
            analysis_path = Path(self.project.analysis_path)
            records = json.loads(analysis_path.read_text(encoding="utf-8"))
            known = {str(Path(record["path"]).resolve()) for record in records if record.get("path")}
            accepted = 0
            for record in new_records:
                if not record.get("path") or str(Path(record["path"]).resolve()) in known:
                    continue
                records.append(record)
                self.project.cards.append(StoryboardCard(record["path"], False))
                accepted += 1
            analysis_path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
            self.project.digikam_source = {
                "person_tag_id": person.tag_id, "person_name": person.name,
                "database_type": settings.database_type, "database": settings.database,
                "host": settings.host, "port": settings.port, "user": settings.user,
                "collection_roots": {key: str(value) for key, value in roots.items()},
                "imported_at": datetime.now().isoformat(timespec="seconds"),
            }
            self._mark_project_saved()
        except (OSError, ValueError, json.JSONDecodeError) as error:
            messagebox.showerror("Aktualisierung fehlgeschlagen", f"Projektdaten konnten nicht aktualisiert werden:\n{error}")
            return
        finally:
            shutil.rmtree(work_dir, ignore_errors=True)
        self._analysis_by_path = None
        self._build_card_grid()
        self.refresh_inspector()
        self._refresh_selection_controls()
        messagebox.showinfo(
            "digiKam-Projekt aktualisiert",
            f"{accepted} neue Karten wurden deaktiviert am Ende ergänzt.\n\n"
            "Bei Bedarf kannst du sie über „Datum“ chronologisch einsortieren.",
        )

    def _resolve_digikam_collection_roots(self, subpaths: list[str]) -> dict[str, Path] | None:
        """Resolve every digiKam album root once and remember accessible mappings."""
        stored = self._digikam_profile.get("collection_roots", {})
        mappings = dict(stored) if isinstance(stored, dict) else {}
        resolved: dict[str, Path] = {}
        changed = False
        for subpath in subpaths:
            stored_path = str(mappings.get(subpath) or "").strip()
            candidate = Path(stored_path).expanduser() if stored_path else None
            if candidate is not None and candidate.is_dir():
                resolved[subpath] = candidate
                continue
            configured_root = self._root_from_digikam_config(subpath)
            if configured_root is not None:
                resolved[subpath] = configured_root
                mappings[subpath] = str(configured_root)
                changed = True
                continue
            # Some digiKam setups already use an absolute specificPath. In that
            # case no user interaction is necessary at all.
            direct = Path(subpath).expanduser()
            if direct.is_dir():
                resolved[subpath] = direct
                mappings[subpath] = str(direct)
                changed = True
                continue
            selected = self._choose_digikam_collection_root([subpath])
            if not selected:
                return None
            resolved[subpath] = Path(selected)
            mappings[subpath] = selected
            changed = True
        if changed:
            self._digikam_profile["collection_roots"] = mappings
            save_digikam_profile(self._digikam_profile)
        return resolved

    @staticmethod
    def _root_from_digikam_config(specific_path: str) -> Path | None:
        """Use digiKam's own last configured collection base when it is valid."""
        local_app_data = os.environ.get("LOCALAPPDATA")
        if not local_app_data:
            return None
        config_path = Path(local_app_data) / "digikamrc"
        parser = ConfigParser(interpolation=None)
        try:
            parser.read(config_path, encoding="utf-8")
            raw_base = parser.get("Collection Settings", "LastAddedCollectionPath", fallback="").strip()
        except (OSError, ConfigParserError):
            return None
        if re.fullmatch(r"[A-Za-z]:", raw_base):
            raw_base += "\\"
        if not raw_base:
            return None
        base = Path(raw_base).expanduser()
        parts = [part for part in specific_path.replace("\\", "/").split("/") if part]
        if base.is_dir() and base.joinpath(*parts).is_dir():
            return base
        if base.is_dir() and len(base.parts) >= len(parts):
            tail = base.parts[-len(parts):] if parts else ()
            if all(left.casefold() == right.casefold() for left, right in zip(tail, parts)):
                return base
        return None

    def _choose_digikam_collection_root(self, subpaths: list[str]) -> str | None:
        dialog = tk.Toplevel(self.root)
        dialog.title("digiKam-Sammlungsordner")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.resizable(False, False)
        frame = ttk.Frame(dialog, padding=16)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Wo liegt diese digiKam-Sammlung?", font=("Segoe UI", 11, "bold")).pack(anchor="w")
        expected = ", ".join(path or "/" for path in subpaths[:3]) or "(keine Angabe)"
        ttk.Label(
            frame,
            text=(
                "digiKam speichert diesen Teil des Pfads relativ zur Sammlungswurzel:\n"
                f"{expected}\n\n"
                "Wähle entweder den Ordner direkt oberhalb dieses Eintrags oder den Eintrag selbst. "
                "Beispiel: Erwartet digiKam „Bilder und Videos“, funktionieren sowohl dessen Elternordner "
                "als auch der Ordner „Bilder und Videos“ selbst. Years in Focus speichert diese Zuordnung "
                "für spätere digiKam-Importe."
            ),
            wraplength=520, justify="left", foreground="#555",
        ).pack(anchor="w", pady=(6, 12))
        path_var = tk.StringVar()
        line = ttk.Frame(frame)
        line.pack(fill="x")
        ttk.Entry(line, textvariable=path_var, width=55).pack(side="left", fill="x", expand=True)

        def browse() -> None:
            selected = filedialog.askdirectory(parent=dialog, title="Sammlungsordner auswählen", mustexist=True)
            if selected:
                path_var.set(selected)

        ttk.Button(line, text="Durchsuchen…", command=browse).pack(side="left", padx=(6, 0))
        result: dict[str, str | None] = {"path": None}

        def confirm() -> None:
            candidate = Path(path_var.get().strip()).expanduser()
            if not candidate.is_dir():
                messagebox.showerror("Sammlungsordner", "Bitte einen vorhandenen Ordner auswählen.", parent=dialog)
                return
            result["path"] = str(candidate)
            dialog.destroy()

        buttons = ttk.Frame(frame)
        buttons.pack(fill="x", pady=(14, 0))
        ttk.Button(buttons, text="Abbrechen", command=dialog.destroy).pack(side="right")
        ttk.Button(buttons, text="Bilder an diesem Ort prüfen", command=confirm).pack(side="right", padx=(0, 6))
        self._center_dialog(dialog)
        self.root.wait_window(dialog)
        return result["path"]

    def _choose_digikam_person(self, people: list[DigiKamPerson]) -> DigiKamPerson | None:
        dialog = tk.Toplevel(self.root)
        dialog.title(self.t("select_person"))
        dialog.transient(self.root)
        dialog.grab_set()
        ttk.Label(dialog, text=self.t("select_person"), font=("Segoe UI", 11, "bold"), padding=(16, 14, 16, 4)).pack()
        ttk.Label(dialog, text=self.t.format("confirmed_people_found", count=len(people)), padding=(16, 0, 16, 10)).pack(anchor="w")
        controls = ttk.Frame(dialog, padding=(16, 0, 16, 8))
        controls.pack(fill="x")
        ttk.Label(controls, text="Suchen").pack(side="left")
        search = tk.StringVar()
        search_entry = ttk.Entry(controls, textvariable=search, width=24)
        search_entry.pack(side="left", padx=(6, 16), fill="x", expand=True)
        ttk.Label(controls, text=self.t("sort_by")).pack(side="left")
        order = tk.StringVar(value=self.t("most_images"))
        order_box = ttk.Combobox(
            controls, textvariable=order, state="readonly", width=14,
            values=(self.t("most_images"), self.t("alphabetical")),
        )
        order_box.pack(side="left", padx=(6, 0))
        list_shell = ttk.Frame(dialog, padding=(16, 0, 16, 0))
        list_shell.pack(fill="both", expand=True)
        listbox = tk.Listbox(list_shell, height=14, width=62, activestyle="none", exportselection=False)
        scrollbar = ttk.Scrollbar(list_shell, orient="vertical", command=listbox.yview)
        listbox.configure(yscrollcommand=scrollbar.set)
        listbox.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        visible: list[DigiKamPerson] = []

        def refresh_list(*_args: object) -> None:
            selected_id = visible[listbox.curselection()[0]].tag_id if listbox.curselection() else None
            needle = search.get().casefold().strip()
            visible[:] = [person for person in people if needle in person.name.casefold()]
            if order.get() == self.t("alphabetical"):
                visible.sort(key=lambda person: person.name.casefold())
            else:
                visible.sort(key=lambda person: (-person.image_count, person.name.casefold()))
            listbox.delete(0, "end")
            for person in visible:
                listbox.insert("end", f"{person.name}   ({self.t.format('image_count', count=person.image_count)})")
            if visible:
                index = next((i for i, person in enumerate(visible) if person.tag_id == selected_id), 0)
                listbox.selection_set(index)
                listbox.activate(index)
                listbox.see(index)

        search.trace_add("write", refresh_list)
        order_box.bind("<<ComboboxSelected>>", refresh_list)
        refresh_list()
        result: dict[str, DigiKamPerson | None] = {"person": None}

        def confirm() -> None:
            selected = listbox.curselection()
            if not selected:
                return
            result["person"] = visible[selected[0]]
            dialog.destroy()

        listbox.bind("<Double-Button-1>", lambda _event: confirm())

        buttons = ttk.Frame(dialog, padding=(16, 12, 16, 16))
        buttons.pack(fill="x")
        ttk.Button(buttons, text=self.t("cancel"), command=dialog.destroy).pack(side="right")
        ttk.Button(buttons, text=self.t("import_person"), command=confirm).pack(side="right", padx=(0, 6))
        localize_widget_tree(dialog, self.t)
        self._center_dialog(dialog)
        search_entry.focus_set()
        self.root.wait_window(dialog)
        return result["person"]

    def _choose_import_person(self, scan: ImportScan) -> str | None:
        names = sorted(scan.person_counts, key=lambda name: (-scan.person_counts[name], name.casefold()))
        summary = self.t.format(
            "import_scan_summary",
            total=len(scan.image_files), tagged=scan.tagged_count, untagged=len(scan.untagged_files),
        )
        if len(names) == 1:
            person = names[0]
            if messagebox.askyesno(
                self.t("confirm_target_title"),
                self.t.format("import_confirm", summary=summary, person=person, count=scan.person_counts[person]),
                parent=self.root,
            ):
                return person
            return None

        dialog = tk.Toplevel(self.root)
        dialog.title(self.t("select_person"))
        dialog.transient(self.root)
        dialog.grab_set()
        ttk.Label(dialog, text=self.t("multiple_people_found"), font=("Segoe UI", 11, "bold"), padding=(16, 14, 16, 4)).pack()
        ttk.Label(dialog, text=summary, padding=(16, 0, 16, 10), justify="left").pack(anchor="w")
        choices = [f"{name} ({self.t.format('image_count', count=scan.person_counts[name])})" for name in names]
        box = ttk.Combobox(dialog, state="readonly", values=choices, width=42)
        box.current(0)
        box.pack(padx=16, fill="x")
        result: dict[str, str | None] = {"person": None}

        def confirm() -> None:
            result["person"] = names[box.current()]
            dialog.destroy()

        buttons = ttk.Frame(dialog, padding=(16, 12, 16, 16))
        buttons.pack(fill="x")
        ttk.Button(buttons, text=self.t("cancel"), command=dialog.destroy).pack(side="right")
        ttk.Button(buttons, text=self.t("import_person"), command=confirm).pack(side="right", padx=(0, 6))
        self._center_dialog(dialog)
        self.root.wait_window(dialog)
        return result["person"]

    def _choose_incomplete_xmp_action(
        self, person: str, tagged: int, total: int, missing: int,
    ) -> str | None:
        """Let mixed metadata imports start immediately or review their gaps."""
        dialog = tk.Toplevel(self.root)
        dialog.title(self.t("xmp_coverage_title"))
        dialog.transient(self.root)
        dialog.grab_set()
        ttk.Label(
            dialog, text=self.t("xmp_coverage_heading"), font=("Segoe UI", 11, "bold"),
            padding=(18, 16, 18, 4),
        ).pack(anchor="w")
        ttk.Label(
            dialog,
            text=self.t.format("xmp_coverage_choice", person=person, tagged=tagged, total=total, missing=missing),
            justify="left", wraplength=510, padding=(18, 0, 18, 8),
        ).pack(anchor="w")
        result: dict[str, str | None] = {"action": None}

        def choose(action: str) -> None:
            result["action"] = action
            dialog.destroy()

        buttons = ttk.Frame(dialog, padding=(18, 4, 18, 18))
        buttons.pack(fill="x")
        ttk.Button(buttons, text=self.t("cancel"), command=dialog.destroy).pack(side="right")
        ttk.Button(buttons, text=self.t("xmp_coverage_start"), command=lambda: choose("start")).pack(side="right", padx=(0, 6))
        ttk.Button(buttons, text=self.t("xmp_coverage_mark"), command=lambda: choose("mark")).pack(side="right", padx=(0, 6))
        self._center_dialog(dialog)
        self.root.wait_window(dialog)
        return result["action"]

    def _choose_manual_regions(
        self, scan: ImportScan, person_name: str | None = None,
    ) -> tuple[str, dict[str, object]] | None:
        """Collect explicitly confirmed target rectangles for an untagged import."""
        model = self._yunet_model_path()
        if model is None:
            messagebox.showerror(self.t("manual_faces_title"), self.t("manual_faces_model_missing"), parent=self.root)
            return None
        result = ManualRegionDialog(
            self.root, scan.image_files, model, self.t, person_name=person_name,
            allow_person_name_edit=person_name is None,
        ).show()
        if result is None:
            return None
        person, regions = result
        return person, regions

    @staticmethod
    def _face_region_from_mapping(data: object) -> FaceRegion | None:
        if not isinstance(data, dict):
            return None
        try:
            return FaceRegion(
                str(data["name"]), float(data["x"]), float(data["y"]),
                float(data["width"]), float(data["height"]),
                str(data["coordinate_system"]), str(data["source"]),
            )
        except (KeyError, TypeError, ValueError):
            return None

    @staticmethod
    def _eye_alignment_preview_size(output_size: tuple[int, int]) -> tuple[int, int]:
        """Keep the inspection responsive while preserving the movie's aspect ratio."""
        width, height = output_size
        longest_edge = max(width, height)
        scale = min(1.0, 1200 / longest_edge)
        return max(2, round(width * scale)), max(2, round(height * scale))

    @staticmethod
    def _draw_eye_alignment_markers(
        image: Image.Image,
        points: tuple[tuple[float, float], tuple[float, float]],
        *,
        offset: tuple[int, int] = (0, 0),
        subtle: bool = False,
    ) -> Image.Image:
        """Show the two iris centers used as the export anchor without altering input."""
        result = image.copy()
        draw = ImageDraw.Draw(result)
        shifted = [(x + offset[0], y + offset[1]) for x, y in points]
        eye_distance = max(
            1.0,
            math.hypot(shifted[1][0] - shifted[0][0], shifted[1][1] - shifted[0][1]),
        )
        if subtle:
            radius = max(2, min(4, round(eye_distance * 0.06)))
            for x, y in shifted:
                draw.ellipse((x - radius, y - radius, x + radius, y + radius), outline="#22d3ee", width=1)
                draw.ellipse((x - 1, y - 1, x + 1, y + 1), fill="#ffffff")
            return result
        # Small source images otherwise receive oversized, goggle-like handles.
        # Keep normal-size photos just as easy to grab while scaling down gracefully.
        radius = max(3, min(9, round(eye_distance * 0.13)))
        line_width = max(1, round(radius * 0.44))
        outer_width = max(1, round(radius * 0.55))
        inner_radius = max(1, radius - outer_width)
        inner_width = max(1, round(radius * 0.34))
        center_radius = max(1, round(radius * 0.22))
        draw.line(shifted, fill="#22d3ee", width=line_width)
        for x, y in shifted:
            draw.ellipse(
                (x - radius, y - radius, x + radius, y + radius),
                outline="#062a36",
                width=outer_width,
            )
            draw.ellipse(
                (x - inner_radius, y - inner_radius, x + inner_radius, y + inner_radius),
                outline="#22d3ee",
                width=inner_width,
            )
            draw.ellipse(
                (x - center_radius, y - center_radius, x + center_radius, y + center_radius),
                fill="#ffffff",
            )
        return result

    def inspect_selected_eye_alignment(self) -> None:
        """Open a read-only before/after view of the iris geometry used for export."""
        if not self.project.cards:
            return
        card = self.project.cards[self.selected_index]
        source = Path(card.source_path)
        record = self._analysis_record(card)
        region = self._face_region_from_mapping((record or {}).get("region"))
        model_path = bundled_asset_root() / "models" / "mediapipe" / "face_landmarker.task"
        if not source.is_file():
            messagebox.showinfo(self.t("eye_alignment_title"), self.t("preview_missing"), parent=self.root)
            return
        if region is None:
            messagebox.showinfo(
                self.t("eye_alignment_title"), self.t("eye_alignment_no_region"), parent=self.root,
            )
            return
        if not model_path.is_file():
            messagebox.showerror(
                self.t("eye_alignment_title"), self.t("eye_alignment_model_missing"), parent=self.root,
            )
            return

        dialog = tk.Toplevel(self.root)
        dialog.title(self.t("eye_alignment_title"))
        dialog.transient(self.root)
        dialog.geometry("1180x720")
        dialog.minsize(800, 520)
        body = ttk.Frame(dialog, padding=18)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text=self.t("eye_alignment_title"), font=("Segoe UI", 13, "bold")).pack(anchor="w")
        ttk.Label(body, text=self.t("eye_alignment_loading")).pack(anchor="w", pady=(6, 0))
        status = ttk.Label(body, text=self.t("eye_alignment_loading"))
        status.pack(anchor="w", pady=(14, 0))
        ttk.Button(body, text=self.t("close"), command=dialog.destroy).pack(anchor="e", pady=(12, 0))
        self._center_dialog(dialog)

        def work() -> None:
            try:
                with Image.open(source) as original:
                    source_image = ImageOps.exif_transpose(original).convert("RGB")
                image_bgr = cv2.cvtColor(np.asarray(source_image), cv2.COLOR_RGB2BGR)
                with MediaPipeFaceLandmarker(model_path) as landmarker:
                    dense = landmarker.detect(image_bgr, region)
                if dense is None:
                    raise ValueError(self.t("eye_alignment_not_found"))
                landmarks = dense.as_sparse_landmarks("iris")
                automatic_points = (tuple(landmarks.left_eye), tuple(landmarks.right_eye))
                override = card.eye_override
                if (
                    isinstance(override, list) and len(override) == 2
                    and all(isinstance(point, list) and len(point) == 2 for point in override)
                ):
                    try:
                        iris_points = tuple(tuple(float(value) for value in point) for point in override)
                    except (TypeError, ValueError):
                        iris_points = automatic_points
                else:
                    iris_points = automatic_points
                landmarks = Landmarks(
                    left_eye=iris_points[0], right_eye=iris_points[1], nose=landmarks.nose,
                    left_mouth=landmarks.left_mouth, right_mouth=landmarks.right_mouth,
                    score=landmarks.score, face_box=landmarks.face_box,
                )
                preview_size = self._eye_alignment_preview_size(
                    (self.project.output_width, self.project.output_height)
                )
                target_y = preview_size[1] * self.project.eye_y
                target_distance = preview_size[0] * self.project.eye_distance
                after_points = (
                    (preview_size[0] / 2 - target_distance / 2, target_y),
                    (preview_size[0] / 2 + target_distance / 2, target_y),
                )

                def render_alignment(points: tuple[tuple[float, float], tuple[float, float]]) -> Image.Image:
                    adjusted = Landmarks(
                        left_eye=points[0], right_eye=points[1], nose=landmarks.nose,
                        left_mouth=landmarks.left_mouth, right_mouth=landmarks.right_mouth,
                        score=landmarks.score, face_box=landmarks.face_box,
                    )
                    matrix = similarity_matrix(
                        adjusted, preview_size, self.project.eye_y, self.project.eye_distance,
                        rotation_strength=1.0,
                    )
                    aligned_bgr = cv2.warpAffine(
                        image_bgr, matrix, preview_size, flags=cv2.INTER_CUBIC,
                        borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0),
                    )
                    aligned = Image.fromarray(cv2.cvtColor(aligned_bgr, cv2.COLOR_BGR2RGB))
                    return self._draw_eye_alignment_markers(aligned, after_points, subtle=True)

                aligned = render_alignment(iris_points)

                x1 = max(0, int(region.x - region.width * 0.8))
                y1 = max(0, int(region.y - region.height * 0.8))
                x2 = min(source_image.width, int(region.x + region.width * 1.8))
                y2 = min(source_image.height, int(region.y + region.height * 1.8))
                if region.coordinate_system != "pixel_left_top":
                    x1 = max(0, int((region.x - region.width * 0.8) * source_image.width))
                    y1 = max(0, int((region.y - region.height * 0.8) * source_image.height))
                    x2 = min(source_image.width, int((region.x + region.width * 1.8) * source_image.width))
                    y2 = min(source_image.height, int((region.y + region.height * 1.8) * source_image.height))
                before_base = source_image.crop((x1, y1, x2, y2))
                pose = dense.head_pose_degrees() or {}
                before_points = tuple((x - x1, y - y1) for x, y in iris_points)
                automatic_before_points = tuple((x - x1, y - y1) for x, y in automatic_points)
                self.root.after(0, lambda: show_result(
                    before_base, aligned, pose, before_points, automatic_before_points,
                    after_points, (x1, y1), render_alignment,
                ))
            except Exception as error:  # noqa: BLE001 - native model errors remain inside the read-only dialog
                error_text = str(error)
                self.root.after(0, lambda: show_error(error_text))

        def show_result(
            before_base: Image.Image,
            aligned: Image.Image,
            pose: dict[str, float],
            before_points: tuple[tuple[float, float], tuple[float, float]],
            automatic_before_points: tuple[tuple[float, float], tuple[float, float]],
            after_points: tuple[tuple[float, float], tuple[float, float]],
            source_offset: tuple[int, int],
            render_alignment: Callable[[tuple[tuple[float, float], tuple[float, float]]], Image.Image],
        ) -> None:
            if not dialog.winfo_exists():
                return
            for child in body.winfo_children():
                child.destroy()
            ttk.Label(body, text=self.t("eye_alignment_title"), font=("Segoe UI", 13, "bold")).pack(anchor="w")
            ttk.Label(body, text=self.t("eye_alignment_explanation"), wraplength=1080).pack(anchor="w", pady=(6, 14))
            controls = ttk.Frame(body)
            controls.pack(fill="x", pady=(0, 8))
            ttk.Label(controls, text=self.t("eye_alignment_zoom_hint")).pack(side="left")
            zoom = {"value": 1.0}
            points = [list(point) for point in before_points]
            selected_eye = {"index": None}
            automatic_points_active = {"value": card.eye_override is None}
            saved_override = (
                None
                if card.eye_override is None
                else tuple(
                    (round(point[0] + source_offset[0], 3), round(point[1] + source_offset[1], 3))
                    for point in before_points
                )
            )

            before = self._draw_eye_alignment_markers(before_base, tuple(tuple(point) for point in points))
            normal_images = [before]
            panels = ttk.Frame(body)
            panels.pack(fill="both", expand=True)
            panels.columnconfigure(0, weight=1)
            panels.rowconfigure(0, weight=1)
            views: list[tk.Canvas] = []
            pan = {"x": 0.0, "y": 0.0, "last": None}
            for column, title in ((0, self.t("eye_alignment_before")),):
                panel = ttk.Frame(panels)
                panel.grid(row=0, column=column, sticky="nsew", padx=(0, 10) if column == 0 else (10, 0))
                panel.columnconfigure(0, weight=1)
                panel.rowconfigure(1, weight=1)
                ttk.Label(panel, text=title, font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(0, 6))
                viewport = ttk.Frame(panel)
                viewport.pack(fill="both", expand=True)
                viewport.columnconfigure(0, weight=1)
                viewport.rowconfigure(0, weight=1)
                canvas = tk.Canvas(viewport, highlightthickness=1, highlightbackground="#b9c1c8")
                canvas.grid(row=0, column=0, sticky="nsew")
                views.append(canvas)

            def image_scale(canvas: tk.Canvas, image: Image.Image) -> float:
                available_width = max(1, canvas.winfo_width() - 4)
                available_height = max(1, canvas.winfo_height() - 4)
                fit = min(available_width / image.width, available_height / image.height)
                return min(12.0, max(0.05, fit * zoom["value"]))

            def redraw() -> None:
                images = normal_images
                for canvas, image in zip(views, images, strict=True):
                    scale = image_scale(canvas, image)
                    size = (max(1, round(image.width * scale)), max(1, round(image.height * scale)))
                    photo = ImageTk.PhotoImage(image.resize(size, Image.Resampling.LANCZOS))
                    canvas.delete("preview")
                    center_x = canvas.winfo_width() / 2 + pan["x"]
                    center_y = canvas.winfo_height() / 2 + pan["y"]
                    canvas.create_image(center_x, center_y, anchor="center", image=photo, tags="preview")
                    canvas.image = photo
                    canvas.image_origin = (center_x - size[0] / 2, center_y - size[1] / 2)

            def refresh_adjustment_preview(update_after: bool = False) -> None:
                current_points = tuple(tuple(point) for point in points)
                normal_images[0] = self._draw_eye_alignment_markers(before_base, current_points)
                redraw()

            def begin_eye_drag(event: tk.Event) -> str | None:
                scale = image_scale(views[0], normal_images[0])
                origin_x, origin_y = getattr(views[0], "image_origin", (0.0, 0.0))
                x = (event.x - origin_x) / scale
                y = (event.y - origin_y) / scale
                distances = [float(np.hypot(x - point[0], y - point[1])) for point in points]
                selected_eye["index"] = int(np.argmin(distances)) if min(distances) < 40 else None
                return "break"

            def drag_eye(event: tk.Event) -> str | None:
                index = selected_eye["index"]
                if index is None:
                    return None
                scale = image_scale(views[0], normal_images[0])
                origin_x, origin_y = getattr(views[0], "image_origin", (0.0, 0.0))
                x = (event.x - origin_x) / scale
                y = (event.y - origin_y) / scale
                points[index] = [min(max(0.0, x), before_base.width), min(max(0.0, y), before_base.height)]
                automatic_points_active["value"] = False
                refresh_adjustment_preview()
                return "break"

            def finish_eye_drag(_event: tk.Event) -> str | None:
                if selected_eye["index"] is None:
                    return None
                selected_eye["index"] = None
                refresh_adjustment_preview(update_after=True)
                return "break"

            def adjust_zoom(event: tk.Event) -> str:
                canvas = event.widget
                if not isinstance(canvas, tk.Canvas):
                    return "break"
                factor = 1.2 if event.delta > 0 else 1 / 1.2
                zoom["value"] = min(8.0, max(0.5, zoom["value"] * factor))
                pan["x"] = 0.0
                pan["y"] = 0.0
                redraw()
                return "break"

            def reset_zoom() -> None:
                zoom["value"] = 1.0
                pan["x"] = 0.0
                pan["y"] = 0.0
                redraw()

            def begin_pan(event: tk.Event) -> str:
                pan["last"] = (event.x, event.y)
                return "break"

            def drag_pan(event: tk.Event) -> str:
                last = pan["last"]
                if last is None:
                    return "break"
                pan["x"] += event.x - last[0]
                pan["y"] += event.y - last[1]
                pan["last"] = (event.x, event.y)
                redraw()
                return "break"

            def apply_eye_adjustment() -> None:
                card.eye_override = current_override()
                try:
                    self._mark_project_saved()
                except OSError as error:
                    messagebox.showerror(self.t("eye_alignment_title"), self.t.format("save_failed", error=error), parent=dialog)
                    return
                dialog.destroy()

            def reset_eye_adjustment() -> None:
                points[:] = [list(point) for point in automatic_before_points]
                automatic_points_active["value"] = True
                refresh_adjustment_preview(update_after=True)

            def current_override() -> list[list[float]] | None:
                if automatic_points_active["value"]:
                    return None
                return [
                    [round(x + source_offset[0], 3), round(y + source_offset[1], 3)]
                    for x, y in points
                ]

            def has_unapplied_adjustment() -> bool:
                pending_override = current_override()
                if pending_override is None:
                    return saved_override is not None
                return tuple(tuple(point) for point in pending_override) != saved_override

            def request_dialog_close() -> None:
                if not has_unapplied_adjustment():
                    dialog.destroy()
                    return
                decision = messagebox.askyesnocancel(
                    self.t("eye_alignment_unsaved_title"),
                    self.t("eye_alignment_unsaved_body"),
                    parent=dialog,
                )
                if decision is None:
                    return
                if decision:
                    apply_eye_adjustment()
                else:
                    dialog.destroy()

            ttk.Button(controls, text=self.t("reset_zoom"), command=reset_zoom).pack(side="right")
            ttk.Button(controls, text=self.t("eye_alignment_reset_points"), command=reset_eye_adjustment).pack(side="right", padx=(0, 8))
            ttk.Button(controls, text=self.t("eye_alignment_apply"), command=apply_eye_adjustment).pack(side="right", padx=(0, 8))
            for canvas in views:
                canvas.bind("<Control-MouseWheel>", adjust_zoom)
                canvas.bind("<ButtonPress-2>", begin_pan)
                canvas.bind("<B2-Motion>", drag_pan)
                canvas.bind("<Configure>", lambda _event: dialog.after_idle(redraw))
            views[0].bind("<ButtonPress-1>", begin_eye_drag)
            views[0].bind("<B1-Motion>", drag_eye)
            views[0].bind("<ButtonRelease-1>", finish_eye_drag)
            dialog.after_idle(redraw)
            dialog.protocol("WM_DELETE_WINDOW", request_dialog_close)
            yaw = abs(float(pose.get("pose_yaw_degrees", 0.0)))
            ttk.Label(body, text=self.t.format("eye_alignment_pose", yaw=yaw)).pack(anchor="w", pady=(12, 0))
            ttk.Button(body, text=self.t("close"), command=request_dialog_close).pack(anchor="e", pady=(10, 0))

        def show_error(error: str) -> None:
            if dialog.winfo_exists():
                status.configure(text=self.t.format("eye_alignment_failed", error=error))

        threading.Thread(target=work, daemon=True).start()

    def edit_selected_face_region(self) -> None:
        """Explicitly replace the selected card's region without touching source XMP."""
        if not self.project.cards:
            return
        model = self._yunet_model_path()
        if model is None:
            messagebox.showerror(self.t("manual_faces_title"), self.t("manual_faces_model_missing"), parent=self.root)
            return
        card = self.project.cards[self.selected_index]
        source = Path(card.source_path).resolve()
        record = self._analysis_record(card)
        if record is None:
            messagebox.showerror(self.t("edit_face_region"), self.t("edit_face_region_no_analysis"), parent=self.root)
            return
        existing = self._face_region_from_mapping(record.get("region"))
        initial = {str(source): existing} if existing is not None else None
        result = ManualRegionDialog(
            self.root, (source,), model, self.t, person_name=self.project.person_name,
            initial_regions=initial, allow_person_name_edit=False, confirm_on_last_image=False,
        ).show()
        if result is None:
            return
        _person, regions = result
        chosen = regions.get(str(source))
        if chosen is None:
            return
        # A correction belongs to the existing project target even when a legacy
        # analysis record has an inconsistent or empty region name.
        chosen = FaceRegion(
            self.project.person_name or chosen.name, chosen.x, chosen.y, chosen.width,
            chosen.height, "pixel_left_top", "yif_manual_confirmed",
        )
        try:
            self._apply_face_region_override(source, chosen)
        except (OSError, ValueError, cv2.error) as error:
            messagebox.showerror(
                self.t("edit_face_region"),
                self.t.format("edit_face_region_failed", error=error), parent=self.root,
            )
            return
        # The preview loader intentionally ignores an unchanged source path to
        # avoid needless disk reads during normal card selection.  A region edit
        # changes the overlay, not the path, therefore explicitly invalidate it.
        self._selected_preview_source = None
        self.refresh_inspector()

    def _apply_face_region_override(self, source: Path, region: FaceRegion) -> None:
        """Persist one manual override and refresh its local quality analysis."""
        analysis_path = Path(self.project.analysis_path)
        records = json.loads(analysis_path.read_text(encoding="utf-8"))
        key = str(source.resolve())
        record = next((item for item in records if item.get("path") and str(Path(item["path"]).resolve()) == key), None)
        if record is None:
            raise ValueError(self.t("edit_face_region_no_analysis"))

        with Image.open(source) as original:
            image = ImageOps.exif_transpose(original).convert("RGB")
        width, height = image.size
        bgr = cv2.cvtColor(np.asarray(image), cv2.COLOR_RGB2BGR)
        model = self._yunet_model_path()
        if model is None:
            raise FileNotFoundError(self.t("manual_faces_model_missing"))
        landmarks = YuNetLandmarker(model).detect(bgr, region)
        record["source_size"] = [width, height]
        record["region"] = asdict(region)
        record["landmarks"] = asdict(landmarks) if landmarks is not None else None
        warnings, metrics = assess((width, height), landmarks, self.project.output_height)
        if landmarks is not None:
            midpoint, distance, angle = eye_geometry(landmarks)
            metrics.update({
                "eye_midpoint_x": midpoint[0], "eye_midpoint_y": midpoint[1],
                "eye_distance_px": distance, "eye_angle_degrees": angle,
            })
        record["metrics"] = metrics
        record["warnings"] = warnings
        record["status"] = "accepted" if landmarks is not None and not warnings else ("review" if landmarks is not None else "rejected")
        analysis_path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
        self._analysis_by_path = {
            str(Path(item["path"]).resolve()): item for item in records if item.get("path")
        }

        # Keep manual edits separately from imported digiKam/XMP region manifests.
        # The analysis JSON uses this override immediately; this readable file is
        # the durable project-local audit trail for later project maintenance.
        override_path = self.project_path.parent / f"{self.project_path.stem}-regionen.json"
        try:
            payload = json.loads(override_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            payload = {"person": self.project.person_name, "regions": {}}
        if not isinstance(payload.get("regions"), dict):
            payload["regions"] = {}
        payload["person"] = self.project.person_name
        payload["regions"][key] = asdict(region)
        override_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        self._mark_project_saved()

    def _start_project_image_update(
        self, scan: ImportScan, person: str, regions: dict[str, object] | None = None,
    ) -> None:
        """Analyse a delta import in isolation, then append it to this project."""
        model = self._yunet_model_path()
        analysis_path = Path(self.project.analysis_path)
        if model is None or not analysis_path.is_file():
            messagebox.showerror(self.t("project_import_title"), self.t("project_import_update_unavailable"), parent=self.root)
            return
        work_dir = Path(tempfile.mkdtemp(prefix="yif-image-update-", dir=analysis_path.parent))
        input_path = work_dir / "images.json"
        regions_path = work_dir / "regions.json"
        input_path.write_text(
            json.dumps({"images": [str(path.resolve()) for path in scan.image_files]}, ensure_ascii=False),
            encoding="utf-8",
        )
        command = ([str(bundled_cli_path()), "align"] if getattr(sys, "frozen", False) else [sys.executable, "-m", "facemovie.cli", "align"]) + [
            "--output", str(work_dir), "--person", person, "--yunet-model", str(model),
            "--width", str(self.project.output_width), "--height", str(self.project.output_height),
            "--eye-y", str(self.project.eye_y), "--eye-distance", str(self.project.eye_distance),
            "--rotation-strength", "0", "--framing", "face-normalized", "--series-minutes",
            str(self.project.series_minimum_gap_minutes), "--series-keep", "1", "--reference-originals",
            "--input-list", str(input_path), "--progress",
        ]
        if regions:
            regions_path.write_text(
                json.dumps({"person": person, "regions": {path: asdict(region) for path, region in regions.items()}}, ensure_ascii=False),
                encoding="utf-8",
            )
            command.extend(("--regions-json", str(regions_path)))
        environment = os.environ.copy()
        if not getattr(sys, "frozen", False):
            environment["PYTHONPATH"] = str(self._workspace_root() / "src") + os.pathsep + environment.get("PYTHONPATH", "")
        try:
            self._import_cancelled = False
            self._import_process = subprocess.Popen(
                command, cwd=self._workspace_root(), env=environment, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", bufsize=1,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except OSError as error:
            shutil.rmtree(work_dir, ignore_errors=True)
            messagebox.showerror(self.t("project_import_title"), str(error), parent=self.root)
            return
        self._start_output_reader(self._import_process, "import")
        self._show_project_update_progress(work_dir, regions)

    def _show_project_update_progress(self, work_dir: Path, regions: dict[str, object] | None) -> None:
        dialog = tk.Toplevel(self.root)
        dialog.title(self.t("project_import_title"))
        dialog.transient(self.root)
        dialog.resizable(False, False)
        dialog.protocol("WM_DELETE_WINDOW", lambda: None)
        ttk.Label(dialog, text=self.t("project_import_running"), padding=(18, 16, 18, 4)).pack()
        status = ttk.Label(dialog, text=self.project.person_name, foreground="#666", padding=(18, 0, 18, 12))
        status.pack()
        progress = ttk.Progressbar(dialog, mode="indeterminate", length=360)
        progress.pack(padx=18, pady=(0, 18))
        progress.start(12)
        ttk.Button(dialog, text=self.t("cancel"), command=self._cancel_import).pack(pady=(0, 14))
        self._center_dialog(dialog)
        self._import_dialog, self._import_status, self._import_progress = dialog, status, progress
        self.root.after(250, lambda: self._watch_project_image_update(work_dir, regions))

    def _watch_project_image_update(self, work_dir: Path, regions: dict[str, object] | None) -> None:
        process = self._import_process
        if process is None:
            return
        self._drain_progress("import", self._import_progress, self._import_status)
        if process.poll() is None:
            self.root.after(250, lambda: self._watch_project_image_update(work_dir, regions))
            return
        process.wait()
        self._import_process = None
        self._import_progress.stop()
        if self._import_dialog.winfo_exists():
            self._import_dialog.destroy()
        if process.returncode:
            shutil.rmtree(work_dir, ignore_errors=True)
            if self._import_cancelled:
                messagebox.showinfo(self.t("import_cancelled"), self.t("project_import_unchanged"), parent=self.root)
                return
            messagebox.showerror(self.t("project_import_title"), "\n".join(self._import_log) or self.t("unknown_error"), parent=self.root)
            return
        try:
            new_records = json.loads((work_dir / "analysis.json").read_text(encoding="utf-8"))
            analysis_path = Path(self.project.analysis_path)
            records = json.loads(analysis_path.read_text(encoding="utf-8"))
            known = {str(Path(record["path"]).resolve()) for record in records if record.get("path")}
            added = 0
            for record in new_records:
                if not record.get("path") or str(Path(record["path"]).resolve()) in known:
                    continue
                records.append(record)
                # Never alter the user's current film selection when new material
                # arrives.  New cards deliberately start disabled for review.
                self.project.cards.append(StoryboardCard(record["path"], False))
                added += 1
            analysis_path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
            if regions:
                override_path = self.project_path.parent / f"{self.project_path.stem}-regionen.json"
                try:
                    payload = json.loads(override_path.read_text(encoding="utf-8"))
                except (OSError, ValueError, json.JSONDecodeError):
                    payload = {"person": self.project.person_name, "regions": {}}
                if not isinstance(payload.get("regions"), dict):
                    payload["regions"] = {}
                payload["person"] = self.project.person_name
                payload["regions"].update({path: asdict(region) for path, region in regions.items()})
                override_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            self._mark_project_saved()
        except (OSError, ValueError, json.JSONDecodeError) as error:
            messagebox.showerror(self.t("project_import_title"), self.t.format("project_import_failed", error=error), parent=self.root)
            return
        finally:
            shutil.rmtree(work_dir, ignore_errors=True)
        self._analysis_by_path = None
        self._build_card_grid()
        self.refresh_inspector()
        self._refresh_selection_controls()
        messagebox.showinfo(
            self.t("project_import_title"), self.t.format("project_import_finished", count=added), parent=self.root,
        )

    def _start_import(
        self, scan: ImportScan, person: str, regions: dict[str, object] | None = None,
        title: str | None = None, digikam_source: dict[str, object] | None = None,
    ) -> None:
        count = len(scan.image_files)
        if count >= LARGE_IMPORT_THRESHOLD and not messagebox.askyesno(
            self.t("large_import_title"), self.t.format("large_import_confirm", count=count), parent=self.root,
        ):
            return
        default_stem = self._safe_project_stem(person) if regions else scan.folder.name
        while True:
            target = filedialog.asksaveasfilename(
                title=self.t("save_new_project"),
                initialdir=str(self.project_path.parent),
                initialfile=f"{default_stem}.yif.json",
                defaultextension=".yif.json",
                filetypes=[(self.t("project_file"), "*.yif.json")],
            )
            if not target:
                return
            project_path = Path(target)
            data_dir = project_path.parent / f"{project_path.stem}-Daten"
            region_manifest = project_path.parent / (
                f"{project_path.stem}-digiKam-regionen.json" if digikam_source else f"{project_path.stem}-regionen.json"
            )
            input_manifest = project_path.parent / f"{project_path.stem}-bilder.json"
            if not (project_path.exists() or data_dir.exists() or input_manifest.exists() or (regions and region_manifest.exists())):
                break
            # The manual review can have taken a long time.  Keep its result in
            # memory and return to the save dialog instead of discarding it.
            messagebox.showerror(self.t("project_exists"), self.t("project_exists_body"), parent=self.root)
        yunet_model = self._yunet_model_path()
        if yunet_model is None:
            messagebox.showerror(
                "Gesichtsmodell fehlt",
                "Das für die Analyse benötigte YuNet-Modell wurde nicht gefunden. Die Standalone-Version wird dieses Modell mitliefern.",
            )
            return
        command = ([str(bundled_cli_path()), "align"] if getattr(sys, "frozen", False) else [
            sys.executable, "-m", "facemovie.cli", "align"
        ]) + [
            "--output", str(data_dir), "--person", person,
            "--yunet-model", str(yunet_model), "--width", "1920", "--height", "1080",
            "--mediapipe-model", str(bundled_asset_root() / "models" / "mediapipe" / "face_landmarker.task"),
            "--eye-y", "0.38", "--eye-distance", "0.11", "--rotation-strength", "0",
            "--framing", "face-normalized", "--series-minutes", "5", "--series-keep", "1",
            "--reference-originals", "--progress",
        ]
        if regions:
            region_manifest.write_text(
                json.dumps(
                    {"person": person, "regions": {source: asdict(region) for source, region in regions.items()}},
                    ensure_ascii=False, indent=2,
                ),
                encoding="utf-8",
            )
            command.extend(("--regions-json", str(region_manifest)))
        input_manifest.write_text(
            json.dumps({"images": [str(path.resolve()) for path in scan.image_files]}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        command.extend(("--input-list", str(input_manifest)))
        environment = os.environ.copy()
        if not getattr(sys, "frozen", False):
            environment["PYTHONPATH"] = str(self._workspace_root() / "src") + os.pathsep + environment.get("PYTHONPATH", "")
        try:
            self._import_cancelled = False
            self._import_process = subprocess.Popen(
                command, cwd=self._workspace_root(), env=environment,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", bufsize=1,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except OSError as error:
            input_manifest.unlink(missing_ok=True)
            if regions:
                region_manifest.unlink(missing_ok=True)
            messagebox.showerror("Import konnte nicht starten", str(error))
            return
        self._start_output_reader(self._import_process, "import")
        self._show_import_progress(
            project_path, data_dir, scan, person, title or scan.folder.name, digikam_source,
            manual_regions=bool(regions) and digikam_source is None, manual_marked_count=len(regions or {}),
        )

    @staticmethod
    def _safe_project_stem(name: str) -> str:
        """Keep the readable person name while making it safe for Windows filenames."""
        cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", name).strip(" .")
        return cleaned[:120] or "Mein Years in Focus"

    def _yunet_model_path(self) -> Path | None:
        workspace = bundled_asset_root()
        local_app_data = os.environ.get("LOCALAPPDATA")
        candidates = [workspace / "models" / "yunet" / "face_detection_yunet_2023mar.onnx"]
        if local_app_data:
            candidates.append(Path(local_app_data) / "digikam" / "facesengine" / "face_detection_yunet_2023mar.onnx")
        return next((path for path in candidates if path.is_file()), None)

    def _show_import_progress(
        self, project_path: Path, data_dir: Path, scan: ImportScan, person: str, title: str,
        digikam_source: dict[str, object] | None = None, manual_regions: bool = False, manual_marked_count: int = 0,
    ) -> None:
        dialog = tk.Toplevel(self.root)
        dialog.title(self.t("importing_images"))
        dialog.transient(self.root)
        dialog.resizable(False, False)
        dialog.protocol("WM_DELETE_WINDOW", lambda: None)
        self._style_progress_dialog(dialog)
        ttk.Label(
            dialog, text=self.t("analysing_images"), style="DialogTitle.TLabel", padding=(18, 16, 18, 4),
        ).pack()
        status_text = (
            self.t.format(
                "import_status_manual", person=person, marked=manual_marked_count,
                total=len(scan.image_files),
            ) if manual_regions else self.t.format(
                "import_status", person=person, tagged=scan.person_counts.get(person, 0), untagged=len(scan.untagged_files)
            )
        )
        self._import_status = ttk.Label(
            dialog,
            text=status_text,
            style="DialogBody.TLabel", padding=(18, 0, 18, 12), justify="left",
        )
        self._import_status.pack()
        progress = ttk.Progressbar(dialog, style="Accent.Horizontal.TProgressbar", mode="indeterminate", length=360)
        progress.pack(padx=18, pady=(0, 18))
        progress.start(12)
        self._import_cancel_button = ttk.Button(dialog, text=self.t("cancel"), command=self._cancel_import)
        self._import_cancel_button.pack(pady=(0, 14))
        self._center_dialog(dialog)
        self._import_dialog = dialog
        self._import_progress = progress
        self.root.after(250, lambda: self._watch_import(project_path, data_dir, title, digikam_source))

    def _watch_import(
        self, project_path: Path, data_dir: Path, title: str, digikam_source: dict[str, object] | None = None,
    ) -> None:
        process = self._import_process
        if process is None:
            return
        self._drain_progress("import", self._import_progress, self._import_status)
        if process.poll() is None:
            self.root.after(250, lambda: self._watch_import(project_path, data_dir, title, digikam_source))
            return
        process.wait()
        self._import_process = None
        self._import_progress.stop()
        if process.returncode:
            self._import_dialog.destroy()
            if self._import_cancelled:
                messagebox.showinfo(self.t("import_cancelled"), self.t("import_cancelled_body"), parent=self.root)
                return
            messagebox.showerror(self.t("import_failed"), "\n".join(self._import_log) or self.t("unknown_error"), parent=self.root)
            return
        project = StoryboardProject.from_analysis(data_dir / "analysis.json")
        project.title = title
        project.digikam_source = digikam_source
        project.save(project_path)
        self._prepare_imported_project(project, project_path)

    def _prepare_imported_project(self, project: StoryboardProject, project_path: Path) -> None:
        """Prewarm card thumbnails while the import dialog stays visible."""
        total = len(project.cards)
        dialog = self._import_dialog
        self._import_status.configure(
            text=self.t.format("analysis_complete_preparing", total=total)
        )
        self._import_progress.configure(mode="determinate", maximum=max(1, total), value=0)
        self._import_cancel_button.configure(state="disabled", text=self.t("preparing_cards"))
        self._thumbnail_prepare_active = True
        self._thumbnail_prepare_current = 0
        self._thumbnail_prepare_total = total
        self._thumbnail_prepare_last_ui_update = 0.0
        width, height = self._card_dimensions()

        def prepare() -> None:
            cache = ThumbnailCache(project_path)
            for current, card in enumerate(project.cards, start=1):
                cache.load_or_create(card.source_path, width, height)
                self._thumbnail_prepare_messages.put(("progress", current, total))
            self._thumbnail_prepare_messages.put(("done", total, total))

        threading.Thread(target=prepare, daemon=True, name="yif-thumbnail-prepare").start()
        self.root.after(60, lambda: self._watch_thumbnail_preparation(project, project_path, dialog))

    def _watch_thumbnail_preparation(
        self, project: StoryboardProject, project_path: Path, dialog: tk.Toplevel
    ) -> None:
        done = False
        current = self._thumbnail_prepare_current
        total = self._thumbnail_prepare_total
        try:
            while True:
                kind, current, total = self._thumbnail_prepare_messages.get_nowait()
                self._thumbnail_prepare_current = current
                self._thumbnail_prepare_total = total
                if kind == "done":
                    done = True
        except queue.Empty:
            pass
        now = time.monotonic()
        # Rendering a Tk label and progressbar for every background-cache update
        # creates visible flicker on projects with thousands of cards. Keep the
        # operation responsive but redraw at a calm, human-readable cadence.
        should_refresh_ui = done or (
            current > 0 and now - self._thumbnail_prepare_last_ui_update >= 0.25
        )
        if should_refresh_ui:
            self._import_progress.configure(value=current)
            self._import_status.configure(
                text=self.t.format("cards_preparing_progress", current=current, total=total)
            )
            self._thumbnail_prepare_last_ui_update = now
        if not done:
            self.root.after(60, lambda: self._watch_thumbnail_preparation(project, project_path, dialog))
            return
        self._thumbnail_prepare_active = False
        if dialog.winfo_exists():
            dialog.destroy()
        self._replace_project(project, project_path)
        messagebox.showinfo(
            self.t("import_finished"), self.t.format("import_finished_body", count=len(project.cards)),
            parent=self.root,
        )

    def export_video(self, preview: bool = False) -> None:
        if self._export_process and self._export_process.poll() is None:
            messagebox.showinfo(PRODUCT_NAME, self.t("export_running"), parent=self.root)
            return
        missing_sources = self._missing_enabled_card_paths()
        if missing_sources:
            if messagebox.askyesno(
                self.t("missing_originals_title"),
                self.t.format("export_missing_originals_body", count=len(missing_sources)),
                parent=self.root,
            ):
                self.relink_missing_images()
            return
        music_paths = self._background_music_paths()
        missing_music = [path for path in music_paths if not path.is_file()]
        if missing_music:
            if messagebox.askyesno(
                self.t("background_music_missing_title"),
                self.t("background_music_missing_export"),
                parent=self.root,
            ):
                self.choose_background_music()
            return
        missing_slides = [
            Path(path) for path in (self.project.opening_slide_path, self.project.closing_slide_path)
            if path and not Path(path).is_file()
        ]
        if missing_slides:
            messagebox.showerror(
                self.t("slide_missing_title"),
                self.t.format("slide_missing_export", names=", ".join(path.name for path in missing_slides)),
                parent=self.root,
            )
            return
        if not self.project.person_name:
            messagebox.showerror(
                "Zielperson fehlt",
                "Im Projekt ist keine Zielperson hinterlegt. Bitte zunächst eine Analyse mit vorhandenen Gesichtstags öffnen.",
            )
            return

        suffix = "-Preview" if preview else ""
        default_name = f"{self.project.title or 'years-in-focus'}{suffix}.mp4"
        target = filedialog.asksaveasfilename(
            title=self.t("export_preview_title") if preview else self.t("export_title"),
            initialdir=str(self.project_path.parent),
            initialfile=default_name,
            defaultextension=".mp4",
            filetypes=[("MP4-Video", "*.mp4")],
        )
        if not target:
            return
        output_path = Path(target)
        # Windows already asks whether an existing filename should be replaced in
        # the Save As dialog.  Reaching this point therefore means that choice was
        # accepted; the worker still keeps the old file until the new export succeeds.
        overwrite = output_path.exists()

        workspace_root = self._workspace_root()
        asset_root = bundled_asset_root()
        model_path = asset_root / "models" / "mediapipe" / "face_landmarker.task"
        if not model_path.is_file():
            messagebox.showerror("MediaPipe-Modell fehlt", f"Nicht gefunden:\n{model_path}")
            return

        # Export settings and the inferred target person are persisted before rendering.
        self._mark_project_saved()
        command = build_export_command(
            sys.executable,
            asset_root,
            self.project_path,
            self.project,
            output_path,
            width=self.project.preview_width if preview else None,
            height=self.project.preview_height if preview else None,
            overwrite=overwrite,
        )
        environment = os.environ.copy()
        if not getattr(sys, "frozen", False):
            source_root = workspace_root / "src"
            environment["PYTHONPATH"] = str(source_root) + os.pathsep + environment.get("PYTHONPATH", "")
        try:
            self._export_cancelled = False
            self._export_process = subprocess.Popen(
                command,
                cwd=workspace_root,
                env=environment,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except OSError as error:
            messagebox.showerror("Export konnte nicht starten", str(error))
            return
        self._start_output_reader(self._export_process, "export")
        self._show_export_progress(output_path, preview)

    def _show_export_progress(self, output_path: Path, preview: bool) -> None:
        dialog = tk.Toplevel(self.root)
        dialog.title(self.t("export_finished"))
        dialog.transient(self.root)
        dialog.resizable(False, False)
        dialog.protocol("WM_DELETE_WINDOW", lambda: None)
        self._style_progress_dialog(dialog)
        label = self.t("preview_creating") if preview else self.t("video_creating")
        ttk.Label(dialog, text=label, style="DialogTitle.TLabel", padding=(18, 16, 18, 4)).pack()
        self._export_status = ttk.Label(
            dialog,
            text=self.t.format("alignment_status", filename=output_path.name),
            style="DialogBody.TLabel",
            padding=(18, 0, 18, 12),
        )
        self._export_status.pack()
        progress = ttk.Progressbar(dialog, style="Accent.Horizontal.TProgressbar", mode="indeterminate", length=300)
        progress.pack(padx=18, pady=(0, 18))
        progress.start(12)
        ttk.Button(dialog, text=self.t("cancel"), command=self._cancel_export).pack(pady=(0, 14))
        self._center_dialog(dialog)
        self._export_dialog = dialog
        self._export_progress = progress
        self.root.after(250, lambda: self._watch_export(output_path, preview))

    def _watch_export(self, output_path: Path, preview: bool) -> None:
        process = self._export_process
        if process is None:
            return
        self._drain_progress("export", self._export_progress, self._export_status)
        if process.poll() is None:
            self.root.after(250, lambda: self._watch_export(output_path, preview))
            return
        process.wait()
        self._export_process = None
        self._export_progress.stop()
        self._export_dialog.destroy()
        if process.returncode:
            if self._export_cancelled:
                messagebox.showinfo(self.t("export_cancelled"), self.t("export_cancelled_body"), parent=self.root)
                return
            details = "\n".join(self._export_log).strip() or self.t("unknown_error")
            messagebox.showerror(self.t("export_failed"), details, parent=self.root)
            return
        if self.project.play_after_export:
            os.startfile(output_path)
        self._show_export_finished(output_path, preview)

    def _cancel_import(self) -> None:
        if self._import_process and self._import_process.poll() is None:
            self._import_cancelled = True
            self._import_status.configure(text=self.t("cancelling_import"))
            self._import_process.terminate()

    def _cancel_export(self) -> None:
        if self._export_process and self._export_process.poll() is None:
            self._export_cancelled = True
            self._export_status.configure(text=self.t("cancelling_export"))
            self._export_process.terminate()

    def _show_export_finished(self, output_path: Path, preview: bool) -> None:
        dialog = tk.Toplevel(self.root)
        dialog.title(self.t("export_finished"))
        dialog.transient(self.root)
        dialog.resizable(False, False)
        title = self.t("preview_finished") if preview else self.t("video_finished")
        ttk.Label(dialog, text=title, font=("Segoe UI", 11, "bold"), padding=(18, 16, 18, 4)).pack()
        ttk.Label(dialog, text=str(output_path), wraplength=520, foreground="#555", padding=(18, 0, 18, 12)).pack()
        actions = ttk.Frame(dialog, padding=(18, 0, 18, 18))
        actions.pack(fill="x")
        ttk.Button(actions, text=self.t("open_folder"), command=lambda: os.startfile(output_path.parent)).pack(side="left")
        ttk.Button(actions, text=self.t("play_movie"), command=lambda: os.startfile(output_path)).pack(side="left", padx=6)
        ttk.Button(actions, text=self.t("close"), command=dialog.destroy).pack(side="right")
        self._center_dialog(dialog)

    def _thumbnail(self, card: StoryboardCard, width: int, height: int) -> ImageTk.PhotoImage:
        key = (card.source_path, width, height)
        cached = self._thumb_cache.get(key)
        if cached is not None:
            return cached
        board = self._thumbnail_disk_cache.load_or_create(card.source_path, width, height)
        thumbnail = ImageTk.PhotoImage(board)
        self._thumb_cache[key] = thumbnail
        return thumbnail

    def _analysis_record(self, card: StoryboardCard) -> dict | None:
        """Read quality data once; drawing many cards must not touch image files."""
        if self._analysis_by_path is None:
            try:
                records = json.loads(Path(self.project.analysis_path).read_text(encoding="utf-8"))
            except (OSError, ValueError, TypeError):
                records = []
            self._analysis_by_path = {
                str(Path(record["path"]).resolve()): record
                for record in records if record.get("path")
            }
        return self._analysis_by_path.get(str(Path(card.source_path).resolve()))

    def _card_quality(self, card: StoryboardCard) -> tuple[str, str, str]:
        """Return compact traffic-light state from existing analysis metrics only."""
        record = self._analysis_record(card)
        metrics = (record or {}).get("metrics") or {}
        face_height = float(metrics.get("face_height_px", 0.0))
        score = float(metrics.get("yunet_score", 0.0))
        yaw = abs(float(metrics.get("pose_yaw_degrees", 0.0)))
        required = self.project.output_height * 0.22
        if face_height <= 0 or score <= 0:
            return "red", "#ff6b63", ("Red: eye position cannot be determined reliably." if self.t.language == "en" else "Rot: Augenposition nicht ausreichend bestimmbar.")
        if face_height < required * 0.65 or score < 0.42:
            return "red", "#ff6b63", (
                f"Red: technically unsuitable for {self.project.output_height}p (face {face_height:.0f}px, detection score {score * 100:.0f} %)."
                if self.t.language == "en" else f"Rot: technisch ungeeignet für {self.project.output_height}p (Gesicht {face_height:.0f}px, Erkennungswert {score * 100:.0f} %)."
            )
        pose_only_review = (
            (record or {}).get("status") == "review"
            and bool((record or {}).get("warnings"))
            and all("Seitenansicht" in str(warning) for warning in (record or {}).get("warnings", ()))
        )
        if yaw > self.project.maximum_side_view_degrees:
            return "yellow", "#ffd54f", (
                f"Yellow: side view {yaw:.0f}° exceeds the selected limit of {self.project.maximum_side_view_degrees:.0f}°."
                if self.t.language == "en" else f"Gelb: Seitenansicht {yaw:.0f}° überschreitet den gewählten Grenzwert von {self.project.maximum_side_view_degrees:.0f}°."
            )
        if face_height < required or score < 0.65 or ((record or {}).get("status") == "review" and not pose_only_review):
            return "yellow", "#ffd54f", (
                f"Yellow: borderline for {self.project.output_height}p (face {face_height:.0f}px, detection score {score * 100:.0f} %)."
                if self.t.language == "en" else f"Gelb: Grenzfall für {self.project.output_height}p (Gesicht {face_height:.0f}px, Erkennungswert {score * 100:.0f} %)."
            )
        return "green", "#ffffff", (
            f"Green: technically suitable for {self.project.output_height}p (face {face_height:.0f}px, detection score {score * 100:.0f} %)."
            if self.t.language == "en" else f"Grün: technisch geeignet für {self.project.output_height}p (Gesicht {face_height:.0f}px, Erkennungswert {score * 100:.0f} %)."
        )

    def _show_quality_tooltip(self, event: tk.Event, text: str) -> None:
        self._hide_quality_tooltip()
        tooltip = tk.Toplevel(self.root)
        tooltip.overrideredirect(True)
        tooltip.attributes("-topmost", True)
        tk.Label(tooltip, text=text, background="#ffffe1", relief="solid", borderwidth=1, padx=6, pady=4).pack()
        tooltip.geometry(f"+{event.x_root + 14}+{event.y_root + 16}")
        self._quality_tooltip = tooltip

    def _hide_quality_tooltip(self, _event: tk.Event | None = None) -> None:
        if self._quality_tooltip is not None:
            self._quality_tooltip.destroy()
        self._quality_tooltip = None

    def _build_card_grid(self, *, chunked: bool = False) -> None:
        if self._building_card_grid:
            self._grid_rebuild_pending = True
            return
        self._building_card_grid = True
        self._hide_quality_tooltip()
        columns = self._column_count
        try:
            for child in self.grid.winfo_children():
                child.destroy()
            self._card_widgets.clear()
            self._year_separator_widgets.clear()
            self.sticky_year_label.place_forget()
            self._filtered_card_indices = [
                index
                for index, card in enumerate(self.project.cards)
                if self._card_matches_filter(card)
            ]
            page_count = max(1, (len(self._filtered_card_indices) + CARD_PAGE_SIZE - 1) // CARD_PAGE_SIZE)
            self._card_page = max(0, min(self._card_page, page_count - 1))
            page_start = self._card_page * CARD_PAGE_SIZE
            self._visible_card_indices = self._filtered_card_indices[page_start:page_start + CARD_PAGE_SIZE]
            self._update_card_page_controls()
            width, height = self._card_dimensions()
            if chunked and len(self._visible_card_indices) > 500:
                self._grid_build_state = (self._visible_card_indices, 0, columns, width, height)
                self._show_grid_loading(0, len(self._visible_card_indices))
                self.root.after_idle(self._build_card_grid_chunk)
                return
            self._append_card_widgets(self._visible_card_indices, 0, columns, width, height)
            self._complete_card_grid_build()
        finally:
            if self._grid_build_state is None:
                self._building_card_grid = False
                self.root.after_idle(self._finish_card_grid_build)

    def _year_separator_for_card(self, card: StoryboardCard) -> str | None:
        """Return the visible year marker for a date-sorted card, if available."""
        if not self.project.show_year_separators or self._sort_var.get() != self.t("date"):
            return None
        record = self._analysis_record(card) or {}
        capture_time = str(record.get("capture_time") or "")
        match = re.match(r"^(\d{4})-\d{2}-\d{2}", capture_time)
        return match.group(1) if match else self.t("year_separator_undated")

    def _append_year_separator(self, marker: str, row: int, columns: int) -> None:
        """Add a quiet full-width chronology divider without creating a card slot."""
        separator = tk.Frame(self.grid, background="#d7e2ec", height=24)
        separator.grid(row=row, column=0, columnspan=columns, padx=6, pady=(10, 2), sticky="ew")
        tk.Label(
            separator, text=marker, background="#d7e2ec", foreground="#38556e",
            font=("Segoe UI", 9, "bold"), padx=8,
        ).pack(side="left")
        tk.Frame(separator, background="#89a5ba", height=1).pack(side="left", fill="x", expand=True, padx=(2, 8), pady=12)
        self._year_separator_widgets.append((marker, separator))

    def _append_card_widgets(
        self, indices: list[int], start: int, columns: int, width: int, height: int
    ) -> None:
        row = 0
        column = 0
        last_year_marker: str | None = None
        for visible_index in range(start, len(indices)):
            index = indices[visible_index]
            item = self.project.cards[index]
            year_marker = self._year_separator_for_card(item)
            if year_marker is not None and year_marker != last_year_marker:
                if column:
                    row += 1
                    column = 0
                self._append_year_separator(year_marker, row, columns)
                row += 1
                last_year_marker = year_marker
            frame = tk.Frame(self.grid, padx=3, pady=3)
            frame.grid(row=row, column=column, padx=6, pady=6, sticky="nsew")
            button = tk.Button(frame, image=self._thumbnail(item, width, height), command=lambda i=index: self.select(i))
            button.pack()
            label_row = tk.Frame(frame)
            label_row.pack(fill="x")
            label = tk.Label(label_row, width=max(16, width // 8), anchor="w")
            label.pack(side="left", fill="x", expand=True)
            badge = tk.Label(label_row, width=2, anchor="e", cursor="question_arrow")
            badge.pack(side="right")
            for widget in (frame, button, label, badge):
                widget.bind("<Double-Button-1>", lambda _event, i=index: self.toggle(i))
                widget.bind("<ButtonPress-1>", lambda event, i=index: self._drag_begin(event, i))
                widget.bind("<B1-Motion>", self._drag_motion)
                widget.bind("<ButtonRelease-1>", self._drag_end)
                widget.bind("<Button-3>", lambda event, i=index: self._post_card_context_menu(event, i))
            label.bind(
                "<Enter>",
                lambda event, path=item.source_path: self._show_quality_tooltip(
                    event, f"{'File' if self.t.language == 'en' else 'Datei'}: {Path(path).name}"
                ),
            )
            label.bind("<Leave>", self._hide_quality_tooltip)
            self._card_widgets.append((frame, button, label, badge))
            column += 1
            if column >= columns:
                row += 1
                column = 0

    def _build_card_grid_chunk(self) -> None:
        state = self._grid_build_state
        if state is None:
            return
        indices, start, columns, width, height = state
        end = min(start + 30, len(indices))
        self._append_card_widgets(indices[start:end], 0, columns, width, height)
        # _append_card_widgets receives a local list, so correct its grid rows to
        # the global visible-card sequence after it has created this small batch.
        for offset, widget_tuple in enumerate(self._card_widgets[start:end], start=start):
            widget_tuple[0].grid_configure(row=offset // columns, column=offset % columns)
        self._show_grid_loading(end, len(indices))
        if end < len(indices):
            self._grid_build_state = (indices, end, columns, width, height)
            self.root.after(1, self._build_card_grid_chunk)
            return
        self._grid_build_state = None
        self._complete_card_grid_build()
        self._building_card_grid = False
        self.root.after_idle(self._finish_card_grid_build)

    def _show_grid_loading(self, current: int, total: int) -> None:
        self.grid_loading_progress.configure(maximum=max(1, total), value=current)
        self.grid_loading_status.configure(text=self.t.format("building_storyboard_progress", current=current, total=total))
        self.grid_loading_overlay.place(relx=0.5, rely=0.45, anchor="center")

    def _complete_card_grid_build(self) -> None:
        self.grid_loading_overlay.place_forget()
        self.update_card_styles()

    def _finish_card_grid_build(self) -> None:
        """Refresh the canvas only after Tk has completed the entire grid layout."""
        self.root.update_idletasks()
        self.canvas.configure(scrollregion=self.canvas.bbox("all") or (0, 0, 0, 0))
        self._update_sticky_year_separator()
        if self._grid_rebuild_pending:
            self._grid_rebuild_pending = False
            self._build_card_grid()

    def _drag_begin(self, event: tk.Event, index: int) -> None:
        self._drag_source = index
        self._drag_start = (event.x_root, event.y_root)

    def _drag_motion(self, event: tk.Event) -> None:
        if self._drag_source is None or self._drag_start is None:
            return
        if self._drag_preview is None:
            if abs(event.x_root - self._drag_start[0]) < 8 and abs(event.y_root - self._drag_start[1]) < 8:
                return
            width, height = self._card_dimensions()
            self._drag_preview_image = self._thumbnail(self.project.cards[self._drag_source], width, height)
            preview = tk.Toplevel(self.root)
            preview.overrideredirect(True)
            preview.attributes("-topmost", True)
            preview.attributes("-alpha", 0.68)
            tk.Label(preview, image=self._drag_preview_image, borderwidth=2, relief="solid", background="#ff9800").pack()
            self._drag_preview = preview
            visible_slot = self._visible_card_indices.index(self._drag_source)
            self._card_widgets[visible_slot][0].configure(background="#ff9800")
        self._drag_preview.geometry(f"+{event.x_root + 18}+{event.y_root + 18}")

    def _destroy_drag_preview(self) -> None:
        if self._drag_preview is not None:
            self._drag_preview.destroy()
        self._drag_preview = None
        self._drag_preview_image = None

    def _drag_end(self, event: tk.Event) -> str | None:
        source = self._drag_source
        start = self._drag_start
        self._drag_source = None
        self._drag_start = None
        self._destroy_drag_preview()
        self.root.update_idletasks()
        if source is None or start is None:
            return None
        if abs(event.x_root - start[0]) < 8 and abs(event.y_root - start[1]) < 8:
            self.select(source)
            return "break"
        target_widget = self.root.winfo_containing(event.x_root, event.y_root)
        target = self._card_index_for_widget(target_widget)
        if target is None or target == source:
            return "break"
        card = self.project.cards.pop(source)
        if source < target:
            target -= 1
        self.project.cards.insert(target, card)
        self.selected_index = target
        self._build_card_grid()
        self.refresh_inspector()
        return "break"

    def _card_index_for_widget(self, widget: tk.Misc | None) -> int | None:
        while widget is not None:
            for index, (frame, _button, _label, _badge) in zip(self._visible_card_indices, self._card_widgets):
                if widget is frame:
                    return index
            parent_name = widget.winfo_parent()
            if not parent_name:
                return None
            widget = widget.nametowidget(parent_name)
        return None

    @staticmethod
    def _card_caption(index: int, source_path: str, limit: int = 24) -> str:
        """Shorten only the stem so file extensions remain recognisable."""
        path = Path(source_path)
        prefix = f"{index + 1}. "
        available = max(8, limit - len(prefix))
        filename = path.name
        if len(filename) <= available:
            return prefix + filename
        extension = path.suffix
        if extension and len(extension) + 1 < available:
            stem_length = available - len(extension) - 1
            return prefix + path.stem[:stem_length] + "…" + extension
        return prefix + filename[: max(1, available - 1)] + "…"

    def update_card_styles(self, indices: set[int] | None = None) -> None:
        """Update all cards only when their data changes, not on plain selection."""
        for index, (frame, button, label, badge) in zip(self._visible_card_indices, self._card_widgets):
            if indices is not None and index not in indices:
                continue
            item = self.project.cards[index]
            color = "#2e7d32" if item.enabled else "#757575"
            frame.configure(background=color)
            label.master.configure(background=color)
            button.configure(relief="solid" if index == self.selected_index else "flat", highlightbackground=color)
            label.configure(
                text=self._card_caption(index, item.source_path, limit=max(16, self._card_dimensions()[0] // 8)),
                background=color,
                foreground="white",
            )
            _quality, marker_color, quality_text = self._card_quality(item)
            badge.configure(text="●", background=color, foreground=marker_color)
            # Green cards use a white checkmark: a green dot would disappear against
            # their active-card background. Yellow and red retain traffic-light dots.
            badge.configure(text="✓" if _quality == "green" else "●", foreground=marker_color)
            badge.bind("<Enter>", lambda event, text=quality_text: self._show_quality_tooltip(event, text))
            badge.bind("<Leave>", self._hide_quality_tooltip)
        self._last_styled_selected_index = self.selected_index

    def refresh_inspector(self) -> None:
        if not self.project.cards:
            self.project_count_label.configure(text=self.t("no_images"))
            if hasattr(self, "header_duration_label") and self.header_duration_label.winfo_exists():
                self.header_duration_label.configure(text=self.t.format("header_duration", duration=self.t.format("duration_seconds", seconds=0)))
            self._refresh_digikam_link_label()
            self._show_empty_preview(self.t("preview_empty"))
            return
        self.selected_index = max(0, min(self.selected_index, len(self.project.cards) - 1))
        card = self.project.cards[self.selected_index]
        self.name_label.configure(text=f"{self.t('selected_image')}: {Path(card.source_path).name}")
        enabled_count = sum(item.enabled for item in self.project.cards)
        self.project_count_label.configure(
            text=self.t.format("cards_summary", total=len(self.project.cards), enabled=enabled_count)
        )
        self._refresh_digikam_link_label()
        warning = self._card_warning(card)
        self.warning_label.configure(text=warning)
        self._request_selected_preview(card.source_path)
        changed_selection = {self.selected_index}
        if self._last_styled_selected_index is not None:
            changed_selection.add(self._last_styled_selected_index)
        self.update_card_styles(changed_selection)

    def _refresh_digikam_link_label(self) -> None:
        source = self.project.digikam_source or {}
        person = str(source.get("person_name") or "").strip()
        if not person:
            # Projects created before the provenance field existed still carry the
            # readable region manifest. Recognise them as linked without claiming
            # that their older files already contain a stable tag ID.
            legacy_manifest = self.project_path.parent / f"{self.project_path.stem}-digiKam-regionen.json"
            try:
                person = str(json.loads(legacy_manifest.read_text(encoding="utf-8")).get("person") or "").strip()
            except (OSError, ValueError, json.JSONDecodeError):
                pass
        self.digikam_link_label.configure(
            text=self.t.format("digikam_linked", person=person) if person else self.t("not_digikam_linked")
        )

    def _show_empty_preview(self, text: str) -> None:
        self._selected_preview_source = None
        self._selected_preview_image = None
        if self.preview_label is not None and self.preview_label.winfo_exists():
            self.preview_label.configure(image="", text=text)

    def _toggle_preview(self) -> None:
        self.project.preview_enabled = self.preview_enabled_var.get()
        if self.project.preview_enabled:
            self._open_preview_window()
            return
        self._close_preview_window()

    def _toggle_year_separators(self) -> None:
        """Refresh the card view; separators are visual context only."""
        self.project.show_year_separators = self.year_separators_var.get()
        self._build_card_grid()

    def _toggle_preview_face_region(self) -> None:
        self.project.preview_show_face_region = self.preview_face_region_var.get()
        self._selected_preview_source = None
        if self.project.cards:
            self._request_selected_preview(self.project.cards[self.selected_index].source_path)

    def _open_preview_window(self) -> None:
        if not self.project.preview_enabled:
            return
        if self._preview_window is not None and self._preview_window.winfo_exists():
            self._preview_window.deiconify()
            self._preview_window.lift()
        else:
            window = tk.Toplevel(self.root)
            window.title(f"{PRODUCT_NAME} – {self.t('image_preview')}")
            window.geometry("760x600")
            window.minsize(420, 340)
            # A regular application window supports Windows 11 snap layouts and
            # does not have to remain above the storyboard while editing.
            window.protocol("WM_DELETE_WINDOW", self._close_preview_from_window)
            preview_header = ttk.Frame(window, padding=(12, 10, 12, 4))
            preview_header.pack(fill="x")
            preview_header.columnconfigure(0, weight=1)
            ttk.Label(preview_header, text=self.t("image_preview"), font=("Segoe UI", 11, "bold")).grid(row=0, column=0, sticky="w")
            ttk.Button(
                preview_header, text=self.t("edit_face_region"), command=self.edit_selected_face_region,
            ).grid(row=0, column=1, sticky="e", padx=(8, 8))
            ttk.Checkbutton(
                preview_header,
                text=self.t("show_face_region"),
                variable=self.preview_face_region_var,
                command=self._toggle_preview_face_region,
            ).grid(row=0, column=2, sticky="e")
            self.preview_label = tk.Label(
                window,
                text=self.t("preview_empty"),
                foreground="#d8d8d8",
                background="#252525",
                anchor="center",
            )
            self.preview_label.bind("<Double-Button-1>", self._open_selected_original)
            self.preview_label.bind("<Button-3>", self._post_preview_context_menu)
            self.preview_label.bind("<Configure>", self._schedule_preview_resize)
            self.preview_label.pack(fill="both", expand=True, padx=12, pady=(0, 12))
            self._preview_window = window
        if self.project.cards:
            self._selected_preview_source = None
            self._request_selected_preview(self.project.cards[self.selected_index].source_path)

    def _close_preview_from_window(self) -> None:
        self.preview_enabled_var.set(False)
        self.project.preview_enabled = False
        self._close_preview_window()

    def _close_preview_window(self) -> None:
        if self._preview_resize_after_id is not None:
            self.root.after_cancel(self._preview_resize_after_id)
            self._preview_resize_after_id = None
        if self._preview_window is not None and self._preview_window.winfo_exists():
            self._preview_window.destroy()
        self._preview_window = None
        self.preview_label = None
        self._preview_context_menu = None
        self._selected_preview_size = None
        self._selected_preview_image = None

    def _selected_original_path(self) -> Path | None:
        """Return the selected source image only when it is still reachable."""
        if not self.project.cards:
            return None
        path = Path(self.project.cards[self.selected_index].source_path)
        return path if path.is_file() else None

    def _open_selected_original(self, _event: tk.Event | None = None) -> str | None:
        """Open the selected source file in the Windows default image application."""
        path = self._selected_original_path()
        if path is None:
            messagebox.showinfo(self.t("image_preview"), self.t("preview_missing"), parent=self._preview_window or self.root)
            return "break" if _event is not None else None
        os.startfile(path)
        return "break" if _event is not None else None

    def _open_selected_original_folder(self) -> None:
        """Open the selected source image's containing folder in Explorer."""
        path = self._selected_original_path()
        if path is None:
            messagebox.showinfo(self.t("image_preview"), self.t("preview_missing"), parent=self._preview_window or self.root)
            return
        os.startfile(path.parent)

    def _post_preview_context_menu(self, event: tk.Event) -> str:
        """Keep the same image-specific review actions available from the preview."""
        menu = tk.Menu(self._preview_window or self.root, tearoff=False)
        menu.add_command(label=self.t("inspect_eye_alignment"), command=self.inspect_selected_eye_alignment)
        menu.add_separator()
        menu.add_command(label=self.t("open_original"), command=self._open_selected_original)
        menu.add_command(label=self.t("open_folder"), command=self._open_selected_original_folder)
        self._preview_context_menu = menu
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()
        return "break"

    def _preview_region(self, source_path: str) -> dict[str, object] | None:
        if not self.project.preview_show_face_region or not self.project.cards:
            return None
        card = next((item for item in self.project.cards if item.source_path == source_path), None)
        record = self._analysis_record(card) if card is not None else None
        region = (record or {}).get("region")
        return region if isinstance(region, dict) else None

    def _preview_target_size(self) -> tuple[int, int]:
        """Fit the preview into its live viewport, with a sensible memory ceiling."""
        if self.preview_label is None or not self.preview_label.winfo_exists():
            return (720, 520)
        width, height = self.preview_label.winfo_width(), self.preview_label.winfo_height()
        if width < 200 or height < 160:
            return (720, 520)
        return (min(1920, max(200, width - 16)), min(1200, max(160, height - 16)))

    def _schedule_preview_resize(self, _event: tk.Event | None = None) -> None:
        """Debounce resizing so dragging a window never queues dozens of image reads."""
        if not self.project.preview_enabled or not self.project.cards:
            return
        if self._preview_resize_after_id is not None:
            self.root.after_cancel(self._preview_resize_after_id)
        self._preview_resize_after_id = self.root.after(180, self._resize_selected_preview)

    def _resize_selected_preview(self) -> None:
        self._preview_resize_after_id = None
        if not self.project.cards:
            return
        source_path = self.project.cards[self.selected_index].source_path
        if self._preview_target_size() != self._selected_preview_size:
            self._request_selected_preview(source_path)

    @staticmethod
    def _draw_preview_region(image: Image.Image, region: dict[str, object] | None) -> None:
        if region is None:
            return
        try:
            x, y = float(region["x"]), float(region["y"])
            width, height = float(region["width"]), float(region["height"])
            coordinate_system = str(region.get("coordinate_system", ""))
        except (KeyError, TypeError, ValueError):
            return
        if coordinate_system.startswith("normalized"):
            x, width = x * image.width, width * image.width
            y, height = y * image.height, height * image.height
        if coordinate_system == "normalized_center":
            x -= width / 2
            y -= height / 2
        line_width = max(3, round(min(image.width, image.height) / 180))
        draw = ImageDraw.Draw(image)
        draw.rectangle((x, y, x + width, y + height), outline="#00e676", width=line_width)

    def _request_selected_preview(self, source_path: str) -> None:
        """Read and scale just the selected original image outside the Tk thread."""
        if not self.project.preview_enabled:
            return
        target_size = self._preview_target_size()
        if source_path == self._selected_preview_source and target_size == self._selected_preview_size:
            return
        self._selected_preview_source = source_path
        self._selected_preview_size = target_size
        self._selected_preview_token += 1
        token = self._selected_preview_token
        region = self._preview_region(source_path)
        self._selected_preview_loading = True
        self._selected_preview_image = None
        if self.preview_label is None or not self.preview_label.winfo_exists():
            return
        self.preview_label.configure(image="", text=self.t("preview_loading"))

        def load_preview() -> None:
            try:
                with Image.open(source_path) as original:
                    preview = ImageOps.exif_transpose(original).convert("RGB")
                    self._draw_preview_region(preview, region)
                    preview.thumbnail(target_size, Image.Resampling.LANCZOS)
                    preview = preview.copy()
            except (OSError, ValueError) as error:
                self._selected_preview_messages.put((token, None, str(error)))
                return
            self._selected_preview_messages.put((token, preview, None))

        threading.Thread(target=load_preview, daemon=True, name="yif-selected-preview").start()
        self.root.after(35, self._drain_selected_preview)

    def _drain_selected_preview(self) -> None:
        if not self._preview_alive:
            return
        try:
            while True:
                token, preview, error = self._selected_preview_messages.get_nowait()
                if token != self._selected_preview_token:
                    continue
                self._selected_preview_loading = False
                if self.preview_label is None or not self.preview_label.winfo_exists():
                    continue
                if preview is None:
                    self.preview_label.configure(image="", text=self.t("preview_missing"))
                    continue
                photo = ImageTk.PhotoImage(preview)
                self._selected_preview_image = photo
                self.preview_label.configure(image=photo, text="")
        except queue.Empty:
            pass
        if self._selected_preview_loading and self._preview_alive:
            self.root.after(35, self._drain_selected_preview)

    def _card_warning(self, card: StoryboardCard) -> str:
        if not self.project.analysis_path:
            return ""
        try:
            records = json.loads(Path(self.project.analysis_path).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return "Analyseinformationen nicht verfügbar."
        wanted = str(Path(card.source_path).resolve())
        record = next((item for item in records if item.get("path") and str(Path(item["path"]).resolve()) == wanted), None)
        if not record:
            return "Kein Analyseergebnis für dieses Bild."
        warnings = record.get("warnings") or []
        if warnings:
            if self.t.language == "en":
                return "Note: " + " ".join(self._friendly_warning(str(item)) for item in warnings[:2])
            return "Hinweis: " + " ".join(self._friendly_warning(str(item)) for item in warnings[:2])
        if record.get("status") == "deferred":
            return self.t("burst_note")
        return ""

    def _friendly_warning(self, value: str) -> str:
        """Translate technical warning texts from existing analyses for the GUI."""
        # Older analysis files can contain UTF-8 that was decoded as a Windows
        # code page (for example ``fÃ¼r``). Normalize that legacy spelling first.
        normalized = value
        if "\u00c3" in value or "\u00e2" in value:
            try:
                normalized = value.encode("latin-1").decode("utf-8")
            except UnicodeError:
                pass
        if self.t.language == "en":
            if normalized.startswith("Zeitlich nahe Serienaufnahme:"):
                match = re.search(
                    r"Auswahl auf\s+(\d+)\s+Bild\(er\)\s+pro\s+([0-9]+(?:[.,][0-9]+)?)-Minuten-Cluster begrenzt\.?",
                    normalized,
                )
                if match:
                    count, minutes = match.groups()
                    return (
                        "Closely timed burst photo: selection limited to "
                        f"{count} image(s) per {minutes.replace(',', '.')} minute(s) cluster."
                    )
                return "Closely timed burst photo: selection was limited within its time cluster."
            if normalized.startswith("Gesicht zu klein f\u00fcr die Zielh\u00f6he:"):
                return "Face too small for target height:" + normalized.split(":", 1)[1]
            if normalized.startswith("Gesicht zu klein f\u00fcr Zielh\u00f6he:"):
                return "Face too small for target height:" + normalized.split(":", 1)[1]
            if normalized.startswith("Keine Gesichtsregion f\u00fcr "):
                name = normalized.removeprefix("Keine Gesichtsregion f\u00fcr ").removesuffix(" gefunden.")
                return "No face region found for " + name + "."
            if normalized.startswith("YuNet fand innerhalb der markierten Region"):
                return "The eye position for automatic alignment could not be determined reliably."
            if normalized.startswith("Die Augenposition f\u00fcr die automatische Ausrichtung konnte nicht sicher bestimmt werden."):
                return "The eye position for automatic alignment could not be determined reliably."
            if normalized.startswith("Augenposition f\u00fcr die automatische Ausrichtung unsicher"):
                score = normalized.partition("Erkennungswert:")[2].strip().rstrip(").")
                return (
                    f"Eye position for automatic alignment is uncertain (detection score: {score})."
                    if score else "Eye position for automatic alignment is uncertain."
                )
            if normalized.startswith("Erkannte Augen liegen au\u00dferhalb des Bildbereichs."):
                return "Detected eyes lie outside the image bounds."
        prefix = "Niedrige YuNet-Konfidenz: "
        if normalized.startswith(prefix):
            try:
                score = float(normalized.removeprefix(prefix).rstrip("."))
                if self.t.language == "en":
                    return f"Eye position for automatic alignment is uncertain (detection score: {score * 100:.0f} %)."
                return f"Augenposition f\u00fcr die automatische Ausrichtung unsicher (Erkennungswert: {score * 100:.0f} %)."
            except ValueError:
                return "Augenposition f\u00fcr die automatische Ausrichtung unsicher."
        if normalized.startswith("YuNet fand innerhalb der markierten Region"):
            return "Die Augenposition f\u00fcr die automatische Ausrichtung konnte nicht sicher bestimmt werden."
        return normalized

    def select(self, index: int) -> None:
        self.selected_index = index
        self.refresh_inspector()

    def _post_card_context_menu(self, event: tk.Event, index: int) -> str:
        """Offer project-only deletion without putting a destructive button in every card."""
        self.selected_index = index
        self.refresh_inspector()
        menu = tk.Menu(self.root, tearoff=False)
        if not Path(self.project.cards[index].source_path).is_file():
            menu.add_command(label=self.t("relink_original"), command=lambda: self.relink_card(index))
            menu.add_separator()
        else:
            menu.add_command(
                label=self.t("inspect_eye_alignment"), command=self.inspect_selected_eye_alignment,
            )
            menu.add_separator()
        menu.add_command(label=self.t("remove_card"), command=lambda: self.remove_card(index))
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()
        return "break"

    def remove_card(self, index: int) -> None:
        """Remove one card and its project-local analysis; never touch the original file."""
        if not 0 <= index < len(self.project.cards):
            return
        card = self.project.cards[index]
        if not messagebox.askyesno(
            self.t("remove_card_title"),
            self.t.format("remove_card_confirm", filename=Path(card.source_path).name),
            icon="warning", parent=self.root,
        ):
            return
        self.project.cards.pop(index)
        # Deliberately leave analysis and thumbnail sidecars alone.  The removal
        # becomes durable only when the project itself is saved; choosing
        # "Don't save" while closing must restore the old project intact.
        self.selected_index = min(index, max(0, len(self.project.cards) - 1))
        self._build_card_grid()
        self.refresh_inspector()
        self._refresh_selection_controls()

    def _card_matches_filter(self, card: StoryboardCard) -> bool:
        used_only = self._card_filter_states["used_only"].get()
        selected_qualities = {
            quality
            for quality, key in (("green", "suitable"), ("yellow", "borderline"), ("red", "unsuitable"))
            if self._card_filter_states[key].get()
        }
        # "Used" is a category rather than a restrictive mode: it can be
        # combined with quality categories to compare active cards and new
        # candidates in one view.
        if used_only and card.enabled:
            return True
        if used_only and not selected_qualities:
            return False
        # Without "Used", quality categories deliberately show only unused
        # candidates. With it, active cards are already included above.
        if selected_qualities and card.enabled:
            return False
        if not selected_qualities:
            return True
        quality, _color, _text = self._card_quality(card)
        return quality in selected_qualities

    def _active_filter_label(self) -> str:
        active = [
            key for key in ("used_only", "suitable", "borderline", "unsuitable")
            if self._card_filter_states[key].get()
        ]
        return self.t("all_cards") if not active else ", ".join(self.t(key) for key in active)

    def _apply_card_filter(self) -> None:
        """Filter the view only; it never changes project selection or order."""
        filter_name = self._active_filter_label()
        self._card_filter_label.set(filter_name)
        if filter_name != self.t("all_cards") and self.project.cards:
            if not self._card_matches_filter(self.project.cards[self.selected_index]):
                self.selected_index = next(
                    (index for index, card in enumerate(self.project.cards) if self._card_matches_filter(card)),
                    self.selected_index,
                )
        self._card_page = 0
        self._build_card_grid()
        self.refresh_inspector()

    def toggle(self, index: int) -> str:
        self.selected_index = index
        self.project.cards[index].enabled = not self.project.cards[index].enabled
        if self._active_filter_label() != self.t("all_cards"):
            self._build_card_grid()
        else:
            self.update_card_styles({index})
        self.refresh_inspector()
        self._update_duration_label()
        return "break"

    def sort_cards(self, order: str) -> None:
        """Apply an explicit ordering without changing enabled states or adjustments."""
        if not self.project.analysis_path:
            return
        try:
            records = json.loads(Path(self.project.analysis_path).read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            messagebox.showerror("Sortieren", f"Analyse kann nicht gelesen werden:\n{error}")
            return
        by_path = {str(Path(record["path"]).resolve()): record for record in records if record.get("path")}
        selected_path = self.project.cards[self.selected_index].source_path if self.project.cards else ""
        if order == "name":
            self.project.cards.sort(key=lambda card: Path(card.source_path).name.casefold())
        else:
            self.project.cards.sort(
                key=lambda card: (
                    not bool((by_path.get(str(Path(card.source_path).resolve())) or {}).get("capture_time")),
                    str((by_path.get(str(Path(card.source_path).resolve())) or {}).get("capture_time") or ""),
                    Path(card.source_path).name.casefold(),
                )
            )
        self.selected_index = next(
            (index for index, card in enumerate(self.project.cards) if card.source_path == selected_path), 0
        )
        self._card_page = 0
        self._build_card_grid()
        self.refresh_inspector()

    def _project_signature(self) -> str:
        """Return the project state relevant to an explicit Save decision."""
        return json.dumps(asdict(self.project), ensure_ascii=False, sort_keys=True)

    def _mark_project_saved(self) -> None:
        self.project.save(self.project_path)
        self._saved_project_signature = self._project_signature()

    def _confirm_project_replacement(self) -> bool:
        """Save, discard or cancel before replacing the current project."""
        if self._project_signature() == self._saved_project_signature:
            return True
        decision = messagebox.askyesnocancel(
            self.t("unsaved_changes_title"), self.t("unsaved_changes_body"), parent=self.root,
        )
        if decision is None:
            return False
        if decision:
            try:
                self._mark_project_saved()
            except OSError as error:
                messagebox.showerror(
                    self.t("unsaved_changes_title"), self.t.format("save_failed", error=error), parent=self.root,
                )
                return False
        return True

    def _request_close(self) -> None:
        """Never discard card selection, ordering or settings without a choice."""
        if not self._confirm_project_replacement():
            return
        self.root.destroy()

    def save(self) -> None:
        try:
            self._mark_project_saved()
        except OSError as error:
            messagebox.showerror(self.t("save_project"), self.t.format("save_failed", error=error), parent=self.root)
            return
        save_recent_project(self.project_path)
        self._recent_projects = load_recent_projects()
        messagebox.showinfo(PRODUCT_NAME, f"Projekt gespeichert:\n{self.project_path}")

    def save_as(self) -> None:
        target = filedialog.asksaveasfilename(
            defaultextension=".yif.json",
            filetypes=[(self.t("project_file"), "*.yif.json")],
        )
        if target:
            self.project_path = Path(target)
            self._thumbnail_disk_cache = ThumbnailCache(self.project_path)
            self.save()


def launch(analysis_path: Path | None, project_path: Path | None) -> None:
    if project_path and project_path.exists():
        project = StoryboardProject.load(project_path)
    elif analysis_path:
        project = StoryboardProject.from_analysis(analysis_path)
        project_path = project_path or analysis_path.with_suffix(".yif.json")
    else:
        project = StoryboardProject(analysis_path="", title=PRODUCT_NAME)
        project_path = Path.cwd() / "Years in Focus.yif.json"
    if sys.platform == "win32":
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("YearsInFocus.0.1")
        except (AttributeError, OSError):
            pass
    root = tk.Tk()
    StoryboardApp(root, project, project_path)
    root.mainloop()
