# TEST NAME: RED.Y-LIGHT RGBW Controller + B10 Speed + Breathing
# Startup default: solid red（01 01 00 00 00 FF 00 00 00 00）
# All RGBW sliders use the same fixed width.
# Layout keeps the Color and PACKET cards aligned without artificial empty space.
# Run this complete file; do not copy isolated UI fragments.
# Python 3.12 + Bleak
# pip install bleak
#
# Packet:
# 01 01 00 00 00 R G B W B10
#
# B6=R, B7=G, B8=B, B9=W, B10=speed
# B10=00 = solid
#
# Key features:
# 1. Visual RGB color picker with hue bar and saturation/value square.
# 2. R/G/B/W can also be adjusted with sliders.
# 3. BLE scanning is performed only when needed.
# 4. If disconnected before sending, reconnect once.
# 5. No automatic write retries, avoiding duplicate state commands.
# 6. Scan both name and local_name for better Windows BLE discovery.

import asyncio
import colorsys
import threading
import time
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk
from bleak import BleakScanner, BleakClient

DEVICE_NAME = "RED.Y-LIGHT"
WRITE_UUID = "00010203-0405-0607-0809-0a0b0c0d2b19"


class App:
    def __init__(self, root):
        self.root = root
        self.root.title("RED.Y-LIGHT  •  RGBW CONTROL")

        # The color picker uses a fixed size and pre-rendered Pillow images.
        # This avoids creating tens of thousands of Canvas rectangles during dragging.
        self.PALETTE_W = 380
        self.PALETTE_H = 330
        self.HUE_W = 24
        self.HUE_H = 330
        # The fixed window size keeps all four channel sliders exactly equal.
        self.CHANNEL_SLIDER_W = 390
        self.palette_photo = None
        self.palette_image_id = None
        self.hue_photo = None
        self.hue_image_id = None
        self.root.geometry("1180x800")
        self.root.resizable(False, False)
        self.root.minsize(1050, 760)
        self.root.configure(bg="#0e1014")

        self.bg = "#0e1014"
        self.panel = "#171a20"
        self.panel2 = "#22262e"
        self.text = "#f4f5f7"
        self.muted = "#9ca3af"
        self.accent = "#a78bfa"
        self.green = "#34d399"
        self.red = "#fb7185"
        self.status_idle_bg = "#171a20"
        self.status_search_bg = "#33250d"
        self.status_ok_bg = "#0d2a20"
        self.status_error_bg = "#35171f"

        self.client = None
        self.device = None
        self.connect_lock = None
        self.busy = False
        self.closing = False
        self.auto_send_after = None
        self.auto_send_seq = 0
        self.suppress_live_send = True
        self.startup_red_sent = False

        # Breathing mode continuously sends RGB packets from the PC for a smooth color-cycle and breathing effect.
        # Breathing mode keeps B10=00 to avoid interference with the device's hardware effect.
        self.breathing_active = False
        self.breathing_task = None
        self.breathing_phase = 0.0

        self.loop = asyncio.new_event_loop()
        self.loop_thread = threading.Thread(
            target=self.loop.run_forever, daemon=True
        )
        self.loop_thread.start()

        self.vars = {
            "R": tk.IntVar(value=255),
            "G": tk.IntVar(value=0),
            "B": tk.IntVar(value=0),
            "W": tk.IntVar(value=0),
            "SPEED": tk.IntVar(value=0),
        }

        self.hue = 0.0
        self.sat = 1.0
        self.val_rgb = 1.0

        self.build_style()
        self.build_ui()
        self.refresh_all_no_send()
        self.suppress_live_send = False

        self.root.protocol("WM_DELETE_WINDOW", self.close)

        self.log_line("TEST NAME: RGB Status + RGBW + B10")
        self.log_line("B10=00 → Solid")
        self.log_line("Startup default: solid red（R=FF G=00 B=00 W=00 B10=00）")
        self.log_line("StatusSearch RED.Y-LIGHT...")
        self.set_status(False, "Auto-connectMedium...")

        # Start BLE scanning after the Tk main loop is running.
        # This lets the window appear before the first automatic connection.
        self.root.after(150, self.auto_connect_on_start)
        # Periodically synchronize the UI with the actual Bleak GATT connection state.
        # Internal implementation detail.
        self.root.after(300, self.poll_connection_status)

    # =========================================================
    # UI
    # =========================================================

    def build_style(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure(
            "Action.TButton",
            font=("Segoe UI", 10, "bold"),
            padding=(14, 9),
            foreground="#f5f3ff",
            background="#6d5dfc",
            borderwidth=0,
        )
        style.map(
            "Action.TButton",
            background=[("active", "#806dff"), ("pressed", "#5948e8")],
        )
        style.configure(
            "Small.TButton",
            font=("Segoe UI", 9, "bold"),
            padding=(10, 7),
            foreground="#d7d9e0",
            background="#252933",
            borderwidth=0,
        )
        style.map(
            "Small.TButton",
            background=[("active", "#303541"), ("pressed", "#1f2229")],
        )

    def label(self, parent, text, size=10, bold=False, fg=None):
        return tk.Label(
            parent,
            text=text,
            bg=parent.cget("bg"),
            fg=fg or self.text,
            font=("Segoe UI", size, "bold" if bold else "normal"),
        )

    def card(self, parent, bg=None, padx=20, pady=18):
        frame = tk.Frame(
            parent,
            bg=bg or self.panel,
            highlightthickness=1,
            highlightbackground="#272b35",
            bd=0,
        )
        frame.pack(fill="x", padx=0, pady=0)
        return frame

    def build_ui(self):
        # ---------- Top navigation ----------
        header = tk.Frame(self.root, bg=self.bg, height=72)
        header.pack(fill="x", padx=30, pady=(20, 12))
        header.pack_propagate(False)

        brand = tk.Frame(header, bg=self.bg)
        brand.pack(side="left", fill="y")

        tk.Label(
            brand,
            text="RED.Y",
            bg=self.bg,
            fg="#ffffff",
            font=("Segoe UI", 24, "bold"),
        ).pack(side="left")

        tk.Label(
            brand,
            text="  LIGHT",
            bg=self.bg,
            fg="#9b8cff",
            font=("Segoe UI", 24, "normal"),
        ).pack(side="left")

        tk.Label(
            brand,
            text="  /  RGBW CONTROL",
            bg=self.bg,
            fg="#707683",
            font=("Segoe UI", 9, "bold"),
        ).pack(side="left", pady=(12, 0))

        # Connection area intentionally lives in the top-right.
        conn = tk.Frame(
            header,
            bg=self.status_idle_bg,
            highlightthickness=1,
            highlightbackground="#292e39",
            padx=12,
            pady=8,
        )
        conn.pack(side="right")
        self.status_frame = conn

        self.status_dot = tk.Label(
            conn,
            text="●",
            bg=self.status_idle_bg,
            fg=self.red,
            font=("Segoe UI", 11, "bold"),
        )
        self.status_dot.pack(side="left")

        self.status_label = tk.Label(
            conn,
            text="Disconnected",
            bg=self.status_idle_bg,
            fg="#e5e7eb",
            font=("Segoe UI", 9, "bold"),
        )
        self.status_label.pack(side="left", padx=(6, 12))

        self.reconnect_btn = ttk.Button(
            conn,
            text="↻  Status",
            style="Small.TButton",
            command=self.connect_button,
        )
        self.reconnect_btn.pack(side="left")
        self.reconnect_btn.pack_forget()

        # ---------- Main content ----------
        main = tk.Frame(self.root, bg=self.bg)
        # Internal implementation detail.
        # Internal implementation detail.
        main.pack(fill="x", expand=False, padx=30, pady=(0, 9))

        main.grid_columnconfigure(0, weight=13, minsize=470)
        main.grid_columnconfigure(1, weight=9, minsize=340)
        main.grid_rowconfigure(0, weight=0)

        left = tk.Frame(main, bg=self.bg)
        left.grid(row=0, column=0, sticky="new", padx=(0, 8))
        left.grid_rowconfigure(0, weight=0)
        left.grid_columnconfigure(0, weight=1)

        right = tk.Frame(main, bg=self.bg)
        right.grid(row=0, column=1, sticky="new", padx=(8, 0))

        # ===== Color picker card =====
        picker_card = tk.Frame(
            left,
            bg=self.panel,
            highlightthickness=1,
            highlightbackground="#292e39",
        )
        picker_card.pack(fill="x", expand=False)

        top = tk.Frame(picker_card, bg=self.panel)
        top.pack(fill="x", padx=24, pady=(20, 8))

        tk.Label(
            top,
            text="COLOR",
            bg=self.panel,
            fg="#a8b0bd",
            font=("Segoe UI", 9, "bold"),
        ).pack(side="left")

        tk.Label(
            top,
            text="Status",
            bg=self.panel,
            fg="#ffffff",
            font=("Segoe UI", 16, "bold"),
        ).pack(side="left", padx=(9, 0))

        tk.Label(
            top,
            text="LIVE",
            bg="#18251f",
            fg="#4ade80",
            font=("Segoe UI", 8, "bold"),
            padx=8,
            pady=3,
        ).pack(side="right")

        self.label(
            picker_card,
            "Status；Status Hue",
            9,
            False,
            "#858b98",
        ).pack(anchor="w", padx=24, pady=(0, 14))

        # Internal implementation detail.
        # Internal implementation detail.
        palette_row = tk.Frame(
            picker_card,
            bg=self.panel,
            width=418,
            height=330,
        )
        palette_row.pack(padx=24, pady=(0, 0), anchor="center")
        palette_row.pack_propagate(False)

        self.palette = tk.Canvas(
            palette_row,
            width=self.PALETTE_W,
            height=self.PALETTE_H,
            bg=self.panel,
            highlightthickness=0,
            bd=0,
            cursor="crosshair",
        )
        self.palette.pack(side="left", fill="none", expand=False)

        self.huebar = tk.Canvas(
            palette_row,
            width=self.HUE_W,
            height=self.HUE_H,
            bg=self.panel2,
            highlightthickness=0,
            bd=0,
            cursor="hand2",
        )
        self.huebar.pack(side="left", fill="none", expand=False, padx=(14, 0))

        self.palette.bind("<Button-1>", self.palette_click)
        self.palette.bind("<B1-Motion>", self.palette_click)
        self.huebar.bind("<Button-1>", self.hue_click)
        self.huebar.bind("<B1-Motion>", self.hue_click)

        # Internal implementation detail.
        self.draw_palette()
        self.draw_huebar()

        # Color preview / values
        # Internal implementation detail.
        # Internal implementation detail.
        self.color_preview = tk.Frame(
            picker_card,
            bg="#101217",
            height=70,
            highlightthickness=1,
            highlightbackground="#2d333e",
        )
        self.color_preview.pack(fill="x", padx=24, pady=(18, 8))
        self.color_preview.pack_propagate(False)

        preview_inner = tk.Frame(self.color_preview, bg="#101217")
        preview_inner.pack(fill="both", expand=True, padx=12, pady=10)

        preview_inner.grid_columnconfigure(0, weight=0)
        preview_inner.grid_columnconfigure(1, weight=1)
        preview_inner.grid_columnconfigure(2, weight=0)

        self.color_swatch = tk.Frame(
            preview_inner,
            bg="#ff0000",
            width=46,
            height=46,
        )
        self.color_swatch.grid(row=0, column=0, sticky="nsw", padx=(0, 12))
        self.color_swatch.grid_propagate(False)

        self.color_text = tk.Label(
            preview_inner,
            text="#FF000000",
            bg="#101217",
            fg="#f3f5f8",
            font=("Consolas", 16, "bold"),
            anchor="w",
        )
        self.color_text.grid(row=0, column=1, sticky="w")

        self.rgb_value_label = tk.Label(
            preview_inner,
            text="R FF    G 00    B 00    W 00",
            bg="#101217",
            fg="#cbd2dd",
            font=("Consolas", 10, "bold"),
            anchor="e",
        )
        self.rgb_value_label.grid(row=0, column=2, sticky="e", padx=(12, 0))

        # ===== Right controls =====
        control_card = tk.Frame(
            right,
            bg=self.panel,
            highlightthickness=1,
            highlightbackground="#292e39",
        )
        control_card.pack(fill="x", pady=(0, 6))

        tk.Label(
            control_card,
            text="CHANNELS",
            bg=self.panel,
            fg="#a8b0bd",
            font=("Segoe UI", 9, "bold"),
        ).pack(anchor="w", padx=22, pady=(11, 1))

        tk.Label(
            control_card,
            text="RGBW Brightness",
            bg=self.panel,
            fg="#ffffff",
            font=("Segoe UI", 16, "bold"),
        ).pack(anchor="w", padx=22, pady=(0, 2))

        tk.Label(
            control_card,
            text="Fine-tune the four LED channels",
            bg=self.panel,
            fg="#b1b8c4",
            font=("Segoe UI", 9),
        ).pack(anchor="w", padx=22, pady=(0, 8))

        self.make_slider(control_card, "R", "R", "#fb7185")
        self.make_slider(control_card, "G", "G", "#4ade80")
        self.make_slider(control_card, "B", "B", "#60a5fa")
        self.make_slider(control_card, "W", "W", "#f8fafc")

        # ===== Effect / speed card =====
        effect_card = tk.Frame(
            right,
            bg=self.panel,
            highlightthickness=1,
            highlightbackground="#292e39",
        )
        effect_card.pack(fill="x", pady=(6, 0))

        tk.Label(
            effect_card,
            text="EFFECT",
            bg=self.panel,
            fg="#a8b0bd",
            font=("Segoe UI", 9, "bold"),
        ).pack(anchor="w", padx=22, pady=(12, 1))

        title_row = tk.Frame(effect_card, bg=self.panel)
        title_row.pack(fill="x", padx=22)

        tk.Label(
            title_row,
            text="Effect Speed",
            bg=self.panel,
            fg="#ffffff",
            font=("Segoe UI", 16, "bold"),
        ).pack(side="left")

        self.speed_label = tk.Label(
            title_row,
            text="Solid",
            bg="#211d31",
            fg="#c4b5fd",
            font=("Consolas", 10, "bold"),
            padx=10,
            pady=5,
        )
        self.speed_label.pack(side="right")

        tk.Label(
            effect_card,
            text="B10 = 00 means solid output",
            bg=self.panel,
            fg="#b1b8c4",
            font=("Segoe UI", 9),
        ).pack(anchor="w", padx=22, pady=(1, 5))

        speed_row = tk.Frame(effect_card, bg=self.panel, height=36)
        speed_row.pack(fill="x", padx=22)
        speed_row.pack_propagate(False)
        speed_row.grid_columnconfigure(0, minsize=self.CHANNEL_SLIDER_W, weight=0)

        self.SPEED_slider = tk.Canvas(
            speed_row,
            width=self.CHANNEL_SLIDER_W,
            height=28,
            bg=self.panel,
            highlightthickness=0,
            bd=0,
            cursor="hand2",
        )
        self.SPEED_slider.grid(row=0, column=0, sticky="w")
        self.SPEED_slider.bind("<Button-1>", lambda e: self.speed_slider_click(e))
        self.SPEED_slider.bind("<B1-Motion>", lambda e: self.speed_slider_click(e))
        self.root.after_idle(lambda: self.draw_channel_slider("SPEED"))

        preset = tk.Frame(effect_card, bg=self.panel)
        preset.pack(fill="x", padx=22, pady=(6, 10))
        for col in range(4):
            preset.grid_columnconfigure(col, weight=1, uniform="speed_preset")

        for col, (txt, value) in enumerate([
            ("Solid", 0),
            ("Slow", 32),
            ("Medium", 128),
            ("Fast", 255),
        ]):
            ttk.Button(
                preset,
                text=txt,
                style="Small.TButton",
                command=lambda v=value: self.set_speed(v),
            ).grid(row=0, column=col, sticky="ew", padx=(0 if col == 0 else 4, 0 if col == 3 else 4))

        # PC software breathing mode: smooth continuous color changes without B10 hardware blinking.
        breath_row = tk.Frame(effect_card, bg=self.panel)
        breath_row.pack(fill="x", padx=22, pady=(0, 12))
        self.breath_btn = ttk.Button(
            breath_row,
            text="🌈  Breathing: OFF",
            style="Small.TButton",
            command=self.toggle_breathing,
        )
        self.breath_btn.pack(fill="x")

        # ===== Technical status strip =====
        # Keep PACKET directly below EFFECT with consistent spacing.
        # Internal implementation detail.
        tech = tk.Frame(
            right,
            bg="#101217",
            highlightthickness=1,
            highlightbackground="#252a33",
        )
        tech.pack(fill="x", pady=(6, 0))

        tk.Label(
            tech,
            text="PACKET",
            bg="#101217",
            fg="#6f7581",
            font=("Segoe UI", 8, "bold"),
        ).pack(anchor="w", padx=16, pady=(7, 1))

        self.packet_label = tk.Label(
            tech,
            text="",
            bg="#101217",
            fg="#d4c8ff",
            font=("Consolas", 10, "bold"),
            anchor="w",
        )
        self.packet_label.pack(fill="x", padx=16, pady=(0, 7))

        # Bottom log uses the exact same horizontal gutter as the main cards.
        # Text itself has no extra left padding, so the first character aligns
        # with the card edge instead of starting several pixels inward.
        log_frame = tk.Frame(self.root, bg=self.bg)
        log_frame.pack(fill="x", padx=30, pady=(0, 12))

        self.log = tk.Text(
            log_frame,
            height=4,
            bg="#090b0f",
            fg="#aeb6c3",
            insertbackground="#ffffff",
            relief="flat",
            font=("Consolas", 8),
            padx=0,
            pady=7,
            borderwidth=0,
            highlightthickness=0,
        )
        self.log.pack(fill="x")

    def make_slider(self, parent, key, icon, fg):
        # ===== Fixed-size sliders =====
        # Do not let grid/geometry determine Canvas width.
        # Create every RGBW slider with the same fixed width.
        slider_w = self.CHANNEL_SLIDER_W
        row_w = 30 + 10 + slider_w + 12 + 58

        row = tk.Frame(parent, bg=self.panel, width=row_w, height=36)
        row.pack(fill="none", padx=22, pady=2, anchor="w")
        row.pack_propagate(False)

        # Three fixed columns: name / slider / HEX
        row.grid_columnconfigure(0, minsize=40, weight=0)
        row.grid_columnconfigure(1, minsize=slider_w, weight=0)
        row.grid_columnconfigure(2, minsize=70, weight=0)

        tk.Label(
            row, text=key, bg=self.panel, fg=fg,
            font=("Segoe UI", 11, "bold"), width=2, anchor="w",
        ).grid(row=0, column=0, sticky="w")

        # The Canvas itself also uses CHANNEL_SLIDER_W.
        # Do not use sticky="ew" so Tkinter cannot change the width during layout.
        canvas = tk.Canvas(
            row, width=slider_w, height=28,
            bg=self.panel, highlightthickness=0, bd=0, cursor="hand2",
        )
        canvas.grid(row=0, column=1, sticky="w")

        canvas.bind("<Button-1>", lambda e, k=key: self.slider_click(e, k))
        canvas.bind("<B1-Motion>", lambda e, k=key: self.slider_click(e, k))

        lab = tk.Label(
            row, text="00", bg=self.panel2, fg=self.text,
            font=("Consolas", 11, "bold"), width=5, pady=6,
        )
        lab.grid(row=0, column=2, sticky="e", padx=(12, 0))

        setattr(self, key + "_label", lab)
        setattr(self, key + "_slider", canvas)

        self.draw_channel_slider(key)

    def slider_click(self, event, key):
        canvas = getattr(self, key + "_slider")
        w = max(1, canvas.winfo_width())
        # Keep room for the thumb radius so the circular handle stays inside the track.
        margin = 10
        x = max(margin, min(w - margin, event.x))
        value = round((x - margin) / max(1, w - 2 * margin) * 255)
        self.vars[key].set(value)

        if key in ("R", "G", "B"):
            self.sync_picker_from_rgb()

        # Redraw only the slider currently being dragged.
        self.draw_channel_slider(key)
        self.refresh_rgb_text(update_sliders=False)

    def draw_channel_slider(self, key):
        canvas = getattr(self, key + "_slider", None)
        if canvas is None or not canvas.winfo_exists():
            return

        # Always use the configured fixed width instead of winfo_width().
        # winfo_width() can temporarily report only the requested width during Tk initialization/layout,
        # which previously caused the first slider to be longer than the other three.
        w = self.CHANNEL_SLIDER_W
        h = 28
        canvas.configure(width=w, height=h)
        value = self.val(key)

        canvas.delete("all")

        left = 10
        right = w - 10
        cy = h // 2

        # Track
        canvas.create_line(
            left, cy, right, cy,
            fill="#3b414d",
            width=10,
            capstyle="round",
        )

        # Selected portion
        fill_color = {
            "R": "#fb7185",
            "G": "#4ade80",
            "B": "#60a5fa",
            "W": "#f8fafc",
            "SPEED": "#c4b5fd",
        }.get(key, "#a78bfa")

        x = left + (right - left) * value / 255
        if value > 0:
            canvas.create_line(
                left, cy, x, cy,
                fill=fill_color,
                width=12,
                capstyle="round",
            )

        # Large circular thumb with outline
        canvas.create_oval(
            x - 10, cy - 10, x + 10, cy + 10,
            fill=fill_color,
            outline="#ffffff",
            width=2,
        )

        # Inner dot for clearer position feedback
        canvas.create_oval(
            x - 3, cy - 3, x + 3, cy + 3,
            fill="#0f1115",
            outline="",
        )

    def speed_slider_click(self, event):
        canvas = self.SPEED_slider
        w = max(1, canvas.winfo_width())
        margin = 10
        x = max(margin, min(w - margin, event.x))
        value = round((x - margin) / max(1, w - 2 * margin) * 255)
        self.vars["SPEED"].set(value)
        self.refresh_all()

    # =========================================================
    # Palette
    # =========================================================

   # =========================================================

    def draw_huebar(self):
        # Rebuild the hue gradient only when Hue changes.
        w, h = self.HUE_W, self.HUE_H
        img = Image.new("RGB", (w, h))
        px = img.load()

        for y in range(h):
            hue = 1.0 - y / max(1, h - 1)
            rgb = tuple(int(c * 255) for c in colorsys.hsv_to_rgb(hue, 1, 1))
            for x in range(w):
                px[x, y] = rgb

        self.hue_photo = ImageTk.PhotoImage(img)
        self.huebar.delete("all")
        self.hue_image_id = self.huebar.create_image(
            0, 0, anchor="nw", image=self.hue_photo
        )

        y = int((1.0 - self.hue) * (h - 1))
        self.huebar.create_rectangle(
            1, y - 2, w - 2, y + 2, outline="white", width=2
        )

    def draw_palette(self):
        # Use a fixed 380x330 size without relying on incomplete Tk geometry.
        w, h = self.PALETTE_W, self.PALETTE_H
        img = Image.new("RGB", (w, h))
        px = img.load()

        # Generate the HSV saturation/value plane for the current Hue.
        for y in range(h):
            v = 1.0 - y / max(1, h - 1)
            for x in range(w):
                s = x / max(1, w - 1)
                px[x, y] = tuple(
                    int(c * 255)
                    for c in colorsys.hsv_to_rgb(self.hue, s, v)
                )

        self.palette_photo = ImageTk.PhotoImage(img)
        self.palette.delete("all")
        self.palette_image_id = self.palette.create_image(
            0, 0, anchor="nw", image=self.palette_photo
        )
        self.palette_cursor_id = None
        self.draw_palette_cursor()

    def draw_palette_cursor(self):
        # Create the picker cursor once and only update its coordinates while dragging.
        # This prevents black or dashed cursor trails during continuous dragging.
        w, h = self.PALETTE_W, self.PALETTE_H
        x = int(self.sat * (w - 1))
        y = int((1.0 - self.val_rgb) * (h - 1))
        coords = (x - 8, y - 8, x + 8, y + 8)

        if getattr(self, "palette_cursor_id", None) is None:
            self.palette_cursor_id = self.palette.create_oval(
                *coords,
                outline="black",
                width=4,
                tags="cursor",
            )
            self.palette.tag_raise(self.palette_cursor_id)
        else:
            self.palette.coords(self.palette_cursor_id, *coords)

    def palette_click(self, event):
        w, h = self.PALETTE_W, self.PALETTE_H
        self.sat = max(0.0, min(1.0, event.x / max(1, w - 1)))
        self.val_rgb = max(0.0, min(1.0, 1.0 - event.y / max(1, h - 1)))

        # Dragging only moves the cursor; gradients are not rebuilt, keeping mouse response immediate.
        self.draw_palette_cursor()

        r, g, b = colorsys.hsv_to_rgb(self.hue, self.sat, self.val_rgb)
        self.vars["R"].set(round(r * 255))
        self.vars["G"].set(round(g * 255))
        self.vars["B"].set(round(b * 255))
        self.refresh_all()

    def hue_click(self, event):
        h = self.HUE_H
        self.hue = max(0.0, min(1.0, 1.0 - event.y / max(1, h - 1)))

        # Redraw immediately after a Hue change while keeping the current saturation/value coordinates.
        # Internal implementation detail.
        # Only a Hue change requires rebuilding both gradient images.
        self.draw_huebar()
        self.draw_palette()

        r, g, b = colorsys.hsv_to_rgb(self.hue, self.sat, self.val_rgb)
        self.vars["R"].set(round(r * 255))
        self.vars["G"].set(round(g * 255))
        self.vars["B"].set(round(b * 255))
        self.refresh_all()

    # =========================================================
    # Values / packet
    # =========================================================

    def sync_picker_from_rgb(self):
        """Sync the color-picker cursor to the current RGB when R/G/B are changed directly."""
        r = self.val("R") / 255.0
        g = self.val("G") / 255.0
        b = self.val("B") / 255.0

        h, s, v = colorsys.rgb_to_hsv(r, g, b)

        # Hue has no useful meaning for black or grayscale; keep the current Hue
        # so restoring brightness does not unexpectedly change the selected color.
        if s > 0.001:
            self.hue = h

        self.sat = s
        self.val_rgb = v

        self.draw_huebar()
        self.draw_palette()

    def val(self, key):
        return max(0, min(255, int(round(self.vars[key].get()))))

    def set_speed(self, value):
        self.vars["SPEED"].set(value)
        self.draw_channel_slider("SPEED")
        self.refresh_all()

    def packet(self):
        return [
            0x01, 0x01, 0x00, 0x00, 0x00,
            self.val("R"),
            self.val("G"),
            self.val("B"),
            self.val("W"),
            self.val("SPEED"),
        ]

    def refresh_rgb_text(self, update_sliders=True):
        vals = {k: self.val(k) for k in ("R", "G", "B", "W")}
        for k in vals:
            getattr(self, k + "_label").config(text=f"{vals[k]:02X}")

        r, g, b = vals["R"], vals["G"], vals["B"]
        w = vals["W"]
        self.rgb_value_label.config(
            text=f"R {r:02X}    G {g:02X}    B {b:02X}    W {w:02X}"
        )

        # RGB preview; W is shown as an additional mixed channel
        rr, gg, bb = min(255, r + w), min(255, g + w), min(255, b + w)
        color = f"#{rr:02X}{gg:02X}{bb:02X}"
        brightness = 0.299 * rr + 0.587 * gg + 0.114 * bb
        fg = "#111111" if brightness > 155 else "#FFFFFF"

        # Keep the information card dark and update only the color swatch.
        self.color_swatch.config(bg=color)
        self.color_text.config(
            text=f"#{r:02X}{g:02X}{b:02X}{w:02X}",
            fg="#f3f5f8",
        )

        if update_sliders:
            for k in ("R", "G", "B", "W", "SPEED"):
                self.draw_channel_slider(k)

        self.schedule_live_send()

    def schedule_live_send(self):
        """Automatically send the latest packet after parameter changes with a 20 ms debounce."""
        if self.closing or self.suppress_live_send:
            return

        if self.auto_send_after is not None:
            try:
                self.root.after_cancel(self.auto_send_after)
            except Exception:
                pass

        self.auto_send_seq += 1
        seq = self.auto_send_seq
        self.auto_send_after = self.root.after(
            30, lambda: self.live_send(seq)
        )

    def live_send(self, seq):
        if self.closing or seq != self.auto_send_seq:
            return
        self.auto_send_after = None
        p = self.packet()
        self.run(self.tx_live(p, seq))

    async def tx_live(self, p, seq):
        if self.closing or seq != self.auto_send_seq:
            return

        if not await self.ensure_connected():
            self.log_line("Live control: BLE disconnected; the next change will try to reconnect")
            return

        if self.closing or seq != self.auto_send_seq:
            return

        try:
            await self.client.write_gatt_char(
                WRITE_UUID, bytes(p), response=False
            )
            self.set_status(True)
            self.log_line("LIVE TX  " + " ".join(f"{x:02X}" for x in p))
        except Exception as e:
            self.log_line(f"Live send failed：{type(e).__name__}: {e}")
            self.set_status(False, "Disconnected")
            # Internal implementation detail.

    def refresh_all_no_send(self):
        self.refresh_rgb_text()
        p = self.packet()
        self.packet_label.config(text=" ".join(f"{x:02X}" for x in p))
        speed = p[9]
        self.speed_label.config(
            text=f"B10 = {speed:02X}  •  {'Solid' if speed == 0 else 'Status'}"
        )

    def refresh_all(self):
        # Manual color or speed changes stop breathing mode to prevent competing BLE writes.
        if self.breathing_active and not self.closing:
            self.stop_breathing(restore_ui=False)
        self.refresh_rgb_text()
        p = self.packet()
        self.packet_label.config(text=" ".join(f"{x:02X}" for x in p))

        speed = p[9]
        self.speed_label.config(
            text=f"B10 = {speed:02X}  •  {'Solid' if speed == 0 else 'Status'}"
        )
        self.schedule_live_send()

    # =========================================================
    # Logging / status
    # =========================================================

    def log_line(self, text):
        if hasattr(self, "log"):
            self.root.after(0, self._append_log, text)

    def _append_log(self, text):
        self.log.insert("end", text + "\n")
        self.log.see("end")

    def set_status(self, connected, message=None):
        def update():
            # The actual GATT client state has highest UI priority.
            # Avoid showing an error when the device is still connected but temporarily absent from scanning.
            actually_connected = bool(
                self.client is not None and self.client.is_connected
            )
            status_connected = bool(connected) or actually_connected

            msg = message or ""
            searching = any(
                key in msg
                for key in ("Search", "SearchMedium", "Auto-connect", "StatusSearch", "StatusMedium")
            )

            if status_connected:
                self.status_frame.config(bg=self.status_ok_bg)
                self.status_dot.config(bg=self.status_ok_bg, fg=self.green)
                self.status_label.config(
                    bg=self.status_ok_bg,
                    text="Connected",
                    fg=self.green,
                )
                self.reconnect_btn.pack_forget()

            elif searching:
                self.status_frame.config(bg=self.status_search_bg)
                self.status_dot.config(bg=self.status_search_bg, fg="#f59e0b")
                self.status_label.config(
                    bg=self.status_search_bg,
                    text=message or "StatusMedium",
                    fg="#f59e0b",
                )
                self.reconnect_btn.pack_forget()

            else:
                self.status_frame.config(bg=self.status_error_bg)
                self.status_dot.config(bg=self.status_error_bg, fg=self.red)
                self.status_label.config(
                    bg=self.status_error_bg,
                    text=message or "Unable to connect",
                    fg=self.red,
                )
                if not self.reconnect_btn.winfo_ismapped():
                    self.reconnect_btn.pack(side="left")

        self.root.after(0, update)

    def poll_connection_status(self):
        """Sync the top-right UI with the actual Bleak GATT state.

        Scan results do not indicate connection state; when the client exists and is_connected=True,
        UI Status「Connected」。Status client Status，Status。
        StatusSearch、Status client StatusSearchMediumStatus。
        """
        if self.closing:
            return

        client = self.client
        if client is not None:
            try:
                if client.is_connected:
                    self.set_status(True)
                elif not self.busy:
                    self.set_status(False, "Disconnected")
            except Exception:
                if not self.busy:
                    self.set_status(False, "Disconnected")

        self.root.after(500, self.poll_connection_status)

    # =========================================================
    # BLE connection
    # =========================================================

    def run(self, coro):
        return asyncio.run_coroutine_threadsafe(coro, self.loop)

    def auto_connect_on_start(self):
        """StatusSearchStatus，Status。"""
        if self.closing or self.busy:
            return

        self.busy = True
        self.set_status(False, "StatusSearchMedium...")
        self.log_line("StatusAuto-connect：Search RED.Y-LIGHT")
        self.run(self.connect_once(startup=True))

    def connect_button(self):
        # Internal implementation detail.
        if self.busy:
            self.log_line("StatusMedium，Status")
            return
        self.busy = True
        self.set_status(False, "SearchMedium...")
        self.run(self.connect_once(force=True))

    async def send_startup_red(self):
        """Status，Status。"""
        if self.closing or self.startup_red_sent:
            return

        # Internal implementation detail.
        startup_packet = [0x01, 0x01, 0x00, 0x00, 0x00,
                          0xFF, 0x00, 0x00, 0x00, 0x00]
        try:
            if self.client is None or not self.client.is_connected:
                return
            await self.client.write_gatt_char(
                WRITE_UUID, bytes(startup_packet), response=False
            )
            self.startup_red_sent = True
            self.log_line("STARTUP TX  " + " ".join(f"{x:02X}" for x in startup_packet))
            self.set_status(True)
        except Exception as e:
            self.log_line(f"StatusSend failed：{type(e).__name__}: {e}")

    async def connect_once(self, startup=False, force=False):
        try:
            # Internal implementation detail.
            # Internal implementation detail.
            # Internal implementation detail.
            if force and self.client is not None:
                old_client = self.client
                self.log_line("Status：StatusMediumStatus BLE Status...")
                try:
                    if old_client.is_connected:
                        await old_client.disconnect()
                except Exception as e:
                    self.log_line(f"MediumStatusConnection failed（StatusSearch）：{type(e).__name__}: {e}")
                finally:
                    if self.client is old_client:
                        self.client = None
                    self.device = None

            # Internal implementation detail.
            # do not rebuild the connection just because Windows temporarily misses the advertisement.
            if not force and self.client is not None and self.client.is_connected:
                self.log_line("Status BLE Connected，Status")
                self.set_status(True)
                if startup:
                    await self.send_startup_red()
                return True

            self.log_line("Starting one-time BLE scan...")

            # Read advertisement data and use local_name when name is unavailable.
            found = await BleakScanner.discover(
                timeout=6.0,
                return_adv=True,
            )

            device = None
            for d, adv in found.values():
                name1 = (d.name or "").strip()
                name2 = (getattr(adv, "local_name", "") or "").strip()

                if name1 == DEVICE_NAME or name2 == DEVICE_NAME:
                    device = d
                    self.log_line(
                        f"Found {DEVICE_NAME} | address={d.address}"
                    )
                    break

            if device is None:
                # Internal implementation detail.
                # Internal implementation detail.
                if self.client is not None and self.client.is_connected:
                    self.log_line("StatusFoundStatus，Status BLE Status")
                    self.set_status(True)
                    if startup:
                        await self.send_startup_red()
                    return True

                # List named devices to help diagnose Windows scanning.
                names = []
                for d, adv in found.values():
                    n = (getattr(adv, "local_name", "") or d.name or "").strip()
                    if n and n not in names:
                        names.append(n)

                self.log_line("RED.Y-LIGHT not found")
                if names:
                    self.log_line("Devices found in this scan: " + " / ".join(names[:15]))
                self.set_status(False, "Status")
                return False

            # If an existing connection is still healthy during scanning, keep it.
            # With force=True, the old connection was explicitly closed, so create a new GATT session.
            if not force and self.client is not None and self.client.is_connected:
                self.log_line("Status BLE Connected，Status")
                self.device = device
                self.set_status(True)
                if startup:
                    await self.send_startup_red()
                return True

            self.log_line("Establishing BLE connection...")
            client = BleakClient(device)
            await client.connect()

            self.client = client
            self.device = device
            try:
                self.client.set_disconnected_callback(self.on_ble_disconnected)
            except Exception as e:
                self.log_line(f"Failed to set disconnect callback：{type(e).__name__}: {e}")

            if self.client.is_connected:
                self.set_status(True)
                self.log_line("BLE Connected")
                if startup:
                    await self.send_startup_red()
                return True

            self.set_status(False, "Connection failed")
            return False

        except Exception as e:
            self.set_status(False, "Connection failed")
            self.log_line(f"Connection error：{type(e).__name__}: {e}")
            return False
        finally:
            self.busy = False

    def on_ble_disconnected(self, client):
        """Update the UI when Bleak detects a real GATT disconnect; this is not a scan failure."""
        self.set_status(False, "Disconnected")
        self.log_line("BLE GATT Disconnected")

    async def ensure_connected(self):
        if self.client is not None and self.client.is_connected:
            return True

        # Internal implementation detail.
        return await self.connect_once()

    # =========================================================
    # BLE TX
    # =========================================================

    def send_once(self):
        if self.busy:
            self.log_line("A connection operation is in progress; please wait.")
            return

        p = self.packet()
        self.log_line(
            f"Send once | RGBW="
            f"{p[5]:02X} {p[6]:02X} {p[7]:02X} {p[8]:02X}"
            f" | B10={p[9]:02X}"
        )
        self.run(self.tx_once(p))

    async def tx_once(self, p):
        if not await self.ensure_connected():
            self.log_line("Status：BLE Disconnected")
            return

        try:
            await self.client.write_gatt_char(
                WRITE_UUID,
                bytes(p),
                response=False,
            )
            self.set_status(True)
            self.log_line("TX  " + " ".join(f"{x:02X}" for x in p))
        except Exception as e:
            self.log_line(f"Send failed：{type(e).__name__}: {e}")
            self.set_status(False, "Disconnected")
            # No automatic retry, avoiding duplicate state commands.

    # =========================================================
    # Breathing / continuous color cycle
    # =========================================================

    def toggle_breathing(self):
        """Toggle the PC software breathing mode.

        Breathing mode continuously sends new RGB values instead of sending only one packet.
        Colors move smoothly around the HSV wheel while brightness follows a sine curve.
        B10 stays at 00 to avoid stacking hardware effects with the software animation.
        """
        if self.closing:
            return

        if self.breathing_active:
            self.stop_breathing()
            return

        self.breathing_active = True
        self.breathing_phase = 0.0
        self.breath_btn.config(text="🌈  Breathing: ON")
        self.speed_label.config(text="Breathing  •  PC Animation")
        self.log_line("Breathing: continuous color cycle started (B10 fixed at 00)")
        self.run(self.breathing_loop())

    def stop_breathing(self, restore_ui=True):
        self.breathing_active = False
        if self.breathing_task is not None:
            try:
                self.breathing_task.cancel()
            except Exception:
                pass
            self.breathing_task = None

        if hasattr(self, "breath_btn") and self.breath_btn.winfo_exists():
            self.breath_btn.config(text="🌈  Breathing: OFF")

        if restore_ui and not self.closing:
            self.refresh_all_no_send()
            self.log_line("Breathing: stopped; returning to the current manual color")

    async def breathing_loop(self):
        """Continuously send a smooth rainbow breathing effect.

        Update every 80 ms; one full Hue cycle takes about 12 seconds.
        Brightness pulses from about 15% to 100% without fully turning off.
        """
        task = asyncio.current_task()
        self.breathing_task = task

        try:
            while self.breathing_active and not self.closing:
                # Advance Hue continuously and wrap from 1 back to 0.
                hue = (self.breathing_phase / 360.0) % 1.0

                # Breathing brightness: 15% to 100% with smooth peaks and valleys.
                pulse = 0.15 + 0.85 * ((1.0 - __import__('math').cos(self.breathing_phase * __import__('math').pi / 180.0)) / 2.0)

                r, g, b = colorsys.hsv_to_rgb(hue, 1.0, pulse)
                vals = (round(r * 255), round(g * 255), round(b * 255))

                # Update the UI only on the Tk main thread; keep BLE writes in the asyncio thread.
                self.root.after(0, self.apply_breathing_frame, vals)

                if self.client is not None and self.client.is_connected:
                    packet = [0x01, 0x01, 0x00, 0x00, 0x00,
                              vals[0], vals[1], vals[2], 0x00, 0x00]
                    try:
                        await self.client.write_gatt_char(
                            WRITE_UUID, bytes(packet), response=False
                        )
                    except Exception as e:
                        self.root.after(0, lambda e=e: self.log_line(
                            f"StatusSend failed：{type(e).__name__}: {e}"
                        ))
                        self.root.after(0, lambda: self.set_status(False, "Disconnected"))
                        # Do not retry; a later animation frame can continue after reconnection.

                self.breathing_phase = (self.breathing_phase + 3.0) % 360.0
                await asyncio.sleep(0.08)

        except asyncio.CancelledError:
            pass
        finally:
            if self.breathing_task is task:
                self.breathing_task = None

    def apply_breathing_frame(self, vals):
        if self.closing or not self.breathing_active:
            return

        self.vars["R"].set(vals[0])
        self.vars["G"].set(vals[1])
        self.vars["B"].set(vals[2])
        self.vars["W"].set(0)

        # Update the color preview and four sliders without calling the normal live_send path.
        # Otherwise each frame would enter a second BLE send path.
        old_suppress = self.suppress_live_send
        self.suppress_live_send = True
        try:
            self.refresh_rgb_text(update_sliders=True)
        finally:
            self.suppress_live_send = old_suppress
        self.packet_label.config(
            text="01 01 00 00 00 " +
                 " ".join(f"{x:02X}" for x in (*vals, 0, 0))
        )
        self.speed_label.config(text="Breathing  •  PC Animation")

    # =========================================================
    # Close
    # =========================================================

    def close(self):
        self.stop_breathing(restore_ui=False)
        self.closing = True
        if self.auto_send_after is not None:
            try:
                self.root.after_cancel(self.auto_send_after)
            except Exception:
                pass

        async def shutdown():
            try:
                if self.client is not None and self.client.is_connected:
                    await self.client.disconnect()
            except Exception:
                pass
            self.loop.call_soon_threadsafe(self.loop.stop)

        self.run(shutdown())
        self.root.after(350, self.root.destroy)


if __name__ == "__main__":
    root = tk.Tk()
    app = App(root)
    root.mainloop()
