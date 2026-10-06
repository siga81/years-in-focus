"""Interactive, read-only cards-only movie preview with bounded render caches."""
from copy import deepcopy
import queue
import threading
import time
import tkinter as tk
from tkinter import ttk

import cv2
from PIL import Image, ImageTk
from facemovie.rendering.project_sequence import prepare_project_sequence
from facemovie.rendering.probe import CardProbeRenderer, CardTimeline


def blend_pair(first, second, opacity):
    return cv2.addWeighted(first, 1 - opacity, second, opacity, 0)


def open_film_probe(root, project, records, model_path, language):
    project, records = deepcopy(project), deepcopy(records)
    en = language == "en"
    def text(de, english):
        return english if en else de
    width = min(800, max(300, root.winfo_screenwidth() - 100))
    height = max(2, round(width * project.output_height / project.output_width))
    max_height = min(600, max(150, root.winfo_screenheight() - 340))
    if height > max_height:
        width = max(2, round(width * max_height / height))
        height = max_height
    size = width, height
    window = tk.Toplevel(root)
    window.title(text("Karten-Filmprobe", "Card movie preview"))
    ttk.Label(window, text=text(
        "Kartenfilm mit Exportauswahl und Stapel. Ohne Musik und Start-/Endfolien. Momentaufnahme des Projekts.",
        "Card movie with export selection and stack. No music or opening/closing slides. Snapshot of this project."),
        wraplength=max(width, 450)).pack(padx=12, pady=8)
    image_label = ttk.Label(window, anchor="center")
    image_label.pack(padx=12, pady=4)
    status = ttk.Label(window, text=text("Gesichtsgeometrie vorbereiten…", "Preparing face geometry…"), wraplength=max(width, 450))
    status.pack(padx=12, pady=4)
    progressbar = ttk.Progressbar(window)
    progressbar.pack(fill="x", padx=12, pady=4)
    details = ttk.Label(window, wraplength=max(width, 450))
    details.pack(padx=12)
    requests = queue.Queue(maxsize=1)
    results = queue.Queue()
    stop = threading.Event()
    state = {"generation": 0, "photo": None, "timeline": None, "entries": [], "frame": 0,
             "prepared": None, "slider_after": None, "slider_value": None,
             "index": 0, "playing": False, "busy": True, "last_tick": time.monotonic(), "sync": False}

    def worker():
        last_progress = [0.0]
        def progress(phase, current, total):
            now = time.monotonic()
            if current == total or now - last_progress[0] > .1:
                results.put(("progress", (current, total)))
                last_progress[0] = now
        try:
            entries, skipped = prepare_project_sequence(project, records, model_path, project.person_name,
                progress=progress, cancelled=stop.is_set)
            if stop.is_set():
                return
            hold, transition = project.hold_seconds, project.transition_seconds
            if project.movie_mode == "timelapse":
                hold = project.timelapse_frames_per_image / project.fps
                transition = project.timelapse_transition_frames / project.fps
            timeline = CardTimeline(len(entries), project.fps, hold, transition, project.edge_fades_enabled)
            renderer = CardProbeRenderer(entries, project, size)
            results.put(("ready", (entries, skipped, timeline)))
            while not stop.is_set():
                try:
                    generation, index, opacity = requests.get(timeout=.1)
                except queue.Empty:
                    continue
                renderer.cancelled = lambda: stop.is_set() or generation != state["generation"]
                renderer.progress = lambda current, total: progress("stack", current, total)
                try:
                    frame = renderer.frame(index, opacity)
                    if not renderer.cancelled():
                        results.put(("frame", (generation, frame, index, renderer.dissolve)))
                except InterruptedError:
                    continue
                except Exception as error:
                    results.put(("error", (generation, str(error))))
        except InterruptedError:
            return
        except Exception as error:
            results.put(("error", (None, str(error))))

    controls = ttk.Frame(window)
    controls.pack(fill="x", padx=12, pady=4)
    def pause():
        state["playing"] = False
        play.configure(text=text("Abspielen", "Play"))
    def render(index, opacity):
        state["generation"] += 1
        state["index"] = index
        state["busy"] = True
        state["sync"] = True
        fraction.set((opacity if opacity is not None else 1.0) * 100)
        state["sync"] = False
        status.configure(text=f"{index+1}/{len(state['entries'])}: {state['entries'][index][0].name}")
        try:
            requests.get_nowait()
        except queue.Empty:
            pass
        requests.put_nowait((state["generation"], index, opacity))
    def seek(value, manual=True):
        if state["sync"] or state["timeline"] is None:
            return
        if state["slider_after"] is not None:
            window.after_cancel(state["slider_after"])
            state["slider_after"] = None
        if manual:
            pause()
        state["frame"] = max(0, min(state["timeline"].length - 1, int(float(value))))
        index, opacity = state["timeline"].position(state["frame"])
        render(index, opacity)
        timer.configure(text=f"{state['frame']/project.fps:.1f} / {state['timeline'].length/project.fps:.1f} s")
    def move(step):
        if state["timeline"] is None:
            return
        index = max(0, min(len(state["entries"])-1, state["index"] + step))
        frame = state["timeline"].hold_position(index)
        set_timeline(frame)
        seek(frame)
    def toggle_play():
        if state["timeline"] is None:
            return
        if state["playing"]:
            pause()
        else:
            if state["frame"] >= state["timeline"].length - 1:
                set_timeline(0)
                seek(0)
            state["playing"] = True
            state["last_tick"] = time.monotonic()
            play.configure(text=text("Pause", "Pause"))
    previous = ttk.Button(controls, text=text("← Zurück", "← Previous"), command=lambda: move(-1), state="disabled")
    previous.pack(side="left")
    play = ttk.Button(controls, text=text("Abspielen", "Play"), command=toggle_play, state="disabled")
    play.pack(side="left", padx=8)
    following = ttk.Button(controls, text=text("Weiter →", "Next →"), command=lambda: move(1), state="disabled")
    following.pack(side="left")
    timer = ttk.Label(controls, text="")
    timer.pack(side="right")
    sequence = tk.Scale(window, from_=0, to=1, orient="horizontal", showvalue=False, command=seek, state="disabled")
    sequence.pack(fill="x", padx=12)
    def set_timeline(frame):
        state["sync"] = True
        # Tk Scale callbacks are deferred; temporarily detach them for programmatic updates.
        sequence.configure(command="")
        sequence.set(frame)
        sequence.configure(command=seek)
        state["sync"] = False
    ttk.Label(window, text=text("Übergang der gewählten Karte: 0–100 %", "Selected card transition: 0–100%")).pack(pady=(8, 0))
    fraction = tk.DoubleVar(value=0)
    def display(frame):
        state["photo"] = ImageTk.PhotoImage(Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)), master=window)
        image_label.configure(image=state["photo"])

    def flush_slider():
        state["slider_after"] = None
        if stop.is_set():
            return
        opacity = state["slider_value"]
        prepared = state["prepared"]
        if prepared is not None and prepared[0] == state["index"]:
            # Supersede any playback request without round-tripping through the worker.
            state["generation"] += 1
            state["busy"] = False
            display(prepared[1].frame(opacity))
        else:
            render(state["index"], opacity)

    def dissolve(value):
        if state["sync"] or state["timeline"] is None:
            return
        pause()
        state["slider_value"] = float(value) / 100
        if state["slider_after"] is None:
            state["slider_after"] = window.after(16, flush_slider)
    dissolve_scale = ttk.Scale(window, from_=0, to=100, variable=fraction, command=dissolve, state="disabled")
    dissolve_scale.pack(fill="x", padx=12, pady=(2, 12))
    window.bind("<Left>", lambda _: move(-1))
    window.bind("<Right>", lambda _: move(1))
    window.bind("<space>", lambda _: toggle_play())
    def poll():
        if stop.is_set():
            return
        while True:
            try:
                kind, payload = results.get_nowait()
            except queue.Empty:
                break
            if kind == "progress":
                current, total = payload
                progressbar.configure(maximum=max(1, total), value=current)
            elif kind == "ready":
                entries, skipped, timeline = payload
                state["entries"], state["timeline"] = entries, timeline
                sequence.configure(to=timeline.length-1, state="normal")
                for widget in (previous, play, following, dissolve_scale):
                    widget.configure(state="normal")
                details.configure(text=(text("Karten im Film: ", "Cards in movie: ") + str(len(entries))
                    + (text(" · Ohne Geometrie übersprungen: ", " · Skipped without geometry: ") + str(len(skipped)) if skipped else "")
                    + ("\n" + "; ".join(item["filename"] for item in skipped[:3])
                       + (" …" if len(skipped) > 3 else "") if skipped else "")))
                seek(0)
            elif kind == "frame":
                generation, frame, index, prepared = payload
                if generation != state["generation"]:
                    continue
                state["busy"] = False
                state["prepared"] = (index, prepared)
                display(frame)
                progressbar.configure(value=0)
                previous.configure(state="normal" if state["index"] else "disabled")
                following.configure(state="normal" if state["index"] < len(state["entries"])-1 else "disabled")
            elif kind == "error":
                generation, error = payload
                if generation is None or generation == state["generation"]:
                    pause()
                    state["busy"] = False
                    status.configure(text=error)
        now = time.monotonic()
        if state["playing"] and not state["busy"]:
            elapsed = now - state["last_tick"]
            if elapsed >= 1 / project.fps:
                frame = min(state["timeline"].length - 1, state["frame"] + max(1, int(elapsed * project.fps)))
                state["last_tick"] = now
                set_timeline(frame)
                seek(frame, manual=False)
                if frame == state["timeline"].length - 1:
                    pause()
        window.after(16, poll)
    def close():
        stop.set()
        window.destroy()
    window.protocol("WM_DELETE_WINDOW", close)
    window.bind("<Destroy>", lambda event: stop.set() if event.widget is window else None)
    threading.Thread(target=worker, daemon=True).start()
    poll()
