import os
import threading
import time
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import cv2
import numpy as np
import qrcode
from PIL import Image, ImageTk

# -------------------------
# Utility helpers
# -------------------------
def ensure_dirs():
    os.makedirs("output", exist_ok=True)
    os.makedirs("samples", exist_ok=True)

def pil_image_to_tk(img: Image.Image, max_size=(400, 400)):
    """Resize (keeping aspect) and convert a PIL Image to ImageTk.PhotoImage."""
    img.thumbnail(max_size, Image.LANCZOS)
    return ImageTk.PhotoImage(img.copy())

# -------------------------
# Main Application
# -------------------------
class QRProApp(tk.Tk):
    def __init__(self):
        super().__init__()
        ensure_dirs()
        self.title("QR Pro — Generator & Scanner")
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.geometry("880x560")
        self.resizable(False, False)

        self._camera_thread = None
        self._camera_running = False
        self._camera_lock = threading.Lock()
        self._video_capture = None

        self._build_ui()

    def _build_ui(self):
        style = ttk.Style(self)
        style.theme_use("clam")

        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True, padx=10, pady=10)

        # Generator tab
        gen_frame = ttk.Frame(notebook)
        self._build_generator_tab(gen_frame)
        notebook.add(gen_frame, text="Generate QR")

        # Scanner tab
        scan_frame = ttk.Frame(notebook)
        self._build_scanner_tab(scan_frame)
        notebook.add(scan_frame, text="Scan QR")

    # -------------------------
    # Generator Tab
    # -------------------------
    def _build_generator_tab(self, parent):
        left = ttk.Frame(parent, width=440)
        right = ttk.Frame(parent, width=440)
        left.pack(side="left", fill="both", expand=False, padx=(10,5), pady=10)
        right.pack(side="right", fill="both", expand=False, padx=(5,10), pady=10)

        # Left: Controls
        ttk.Label(left, text="Enter text or URL to encode:", font=("Segoe UI", 10)).pack(anchor="w", pady=(8,4))
        self.gen_text = tk.Text(left, height=6, wrap="word", font=("Segoe UI", 10))
        self.gen_text.pack(fill="x", padx=6)

        ttk.Label(left, text="Filename (without extension):", font=("Segoe UI", 10)).pack(anchor="w", pady=(10,4), padx=6)
        self.gen_filename = ttk.Entry(left)
        self.gen_filename.pack(fill="x", padx=6)

        # Options frame
        opts = ttk.Frame(left)
        opts.pack(fill="x", padx=6, pady=8)
        ttk.Label(opts, text="Box size:").grid(row=0, column=0, sticky="w")
        self.box_size_var = tk.IntVar(value=10)
        ttk.Spinbox(opts, from_=3, to=20, textvariable=self.box_size_var, width=6).grid(row=0, column=1, sticky="w", padx=6)

        ttk.Label(opts, text="Border:").grid(row=0, column=2, sticky="w", padx=(12,0))
        self.border_var = tk.IntVar(value=4)
        ttk.Spinbox(opts, from_=1, to=10, textvariable=self.border_var, width=6).grid(row=0, column=3, sticky="w", padx=6)

        ttk.Label(opts, text="Image scale preview:").grid(row=1, column=0, columnspan=2, sticky="w", pady=(8,0))
        self.preview_scale_var = tk.IntVar(value=300)
        ttk.Scale(opts, from_=100, to=600, variable=self.preview_scale_var, orient="horizontal").grid(row=1, column=2, columnspan=2, sticky="we", padx=6)

        # Buttons
        btn_frame = ttk.Frame(left)
        btn_frame.pack(fill="x", padx=6, pady=(6,0))
        ttk.Button(btn_frame, text="Generate & Preview", command=self.generate_preview).pack(side="left", padx=(0,6))
        ttk.Button(btn_frame, text="Save QR (to output/)", command=self.save_qr).pack(side="left")
        ttk.Button(btn_frame, text="Clear", command=self.clear_gen_fields).pack(side="right")

        # Right: Preview area
        ttk.Label(right, text="Preview:", font=("Segoe UI", 10)).pack(anchor="w", pady=(8,4))
        preview_box = ttk.LabelFrame(right, text="QR Preview", padding=(8,8))
        preview_box.pack(fill="both", expand=True, padx=6, pady=6)

        self.preview_label = ttk.Label(preview_box)
        self.preview_label.pack(expand=True)

        # status
        self.gen_status = ttk.Label(right, text="Ready", anchor="w")
        self.gen_status.pack(fill="x", padx=6, pady=6)

        # store latest generated PIL image
        self._last_qr_image = None

    def clear_gen_fields(self):
        self.gen_text.delete("1.0", tk.END)
        self.gen_filename.delete(0, tk.END)
        self.preview_label.config(image="")
        self._last_qr_image = None
        self.gen_status.config(text="Cleared")

    def generate_preview(self):
        data = self.gen_text.get("1.0", "end").strip()
        if not data:
            messagebox.showwarning("Input required", "Please enter text or URL to generate a QR code.")
            return

        try:
            img = self._make_qr_image(data,
                                      box_size=self.box_size_var.get(),
                                      border=self.border_var.get())
            self._last_qr_image = img
            tk_img = pil_image_to_tk(img, max_size=(self.preview_scale_var.get(), self.preview_scale_var.get()))
            self.preview_label.image = tk_img
            self.preview_label.config(image=tk_img)
            self.gen_status.config(text="Preview ready")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to generate QR: {e}")

    def save_qr(self):
        if self._last_qr_image is None:
            # try auto-generate from text if preview was not created
            data = self.gen_text.get("1.0", "end").strip()
            if not data:
                messagebox.showwarning("Nothing to save", "Generate a QR or enter text first.")
                return
            self._last_qr_image = self._make_qr_image(data,
                                                     box_size=self.box_size_var.get(),
                                                     border=self.border_var.get())

        filename = self.gen_filename.get().strip() or f"qr_{int(time.time())}"
        safe_name = "".join(c for c in filename if c.isalnum() or c in ("_", "-")).rstrip()
        filepath = os.path.join("output", f"{safe_name}.png")
        try:
            self._last_qr_image.save(filepath)
            messagebox.showinfo("Saved", f"QR saved to:\n{filepath}")
            self.gen_status.config(text=f"Saved: {filepath}")
        except Exception as e:
            messagebox.showerror("Save failed", f"Could not save image: {e}")

    def _make_qr_image(self, data, box_size=10, border=4):
        qr = qrcode.QRCode(
            version=None,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=box_size,
            border=border
        )
        qr.add_data(data)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
        return img

    # -------------------------
    # Scanner Tab
    # -------------------------
    def _build_scanner_tab(self, parent):
        left = ttk.Frame(parent, width=440)
        right = ttk.Frame(parent, width=440)
        left.pack(side="left", fill="both", expand=False, padx=(10,5), pady=10)
        right.pack(side="right", fill="both", expand=False, padx=(5,10), pady=10)

        # Left: File scanner UI
        ttk.Label(left, text="Scan from Image File", font=("Segoe UI", 10)).pack(anchor="w", pady=(8,4), padx=6)
        ttk.Button(left, text="Choose Image and Scan", command=self.scan_file_dialog).pack(fill="x", padx=6)

        ttk.Separator(left, orient="horizontal").pack(fill="x", pady=10, padx=6)

        ttk.Label(left, text="Live Camera Scanner", font=("Segoe UI", 10)).pack(anchor="w", pady=(4,6), padx=6)
        cam_btns = ttk.Frame(left)
        cam_btns.pack(fill="x", padx=6)
        self.cam_toggle_btn = ttk.Button(cam_btns, text="Start Camera", command=self.toggle_camera)
        self.cam_toggle_btn.pack(side="left")
        ttk.Button(cam_btns, text="Select Camera Device...", command=self.select_camera_device).pack(side="left", padx=(6,0))

        ttk.Label(left, text="Decoded text:", font=("Segoe UI", 10)).pack(anchor="w", pady=(12,4), padx=6)
        self.decoded_text = tk.Text(left, height=6, wrap="word", font=("Segoe UI", 10))
        self.decoded_text.pack(fill="x", padx=6, pady=(0,6))

        ttk.Button(left, text="Copy decoded text", command=self.copy_decoded_to_clipboard).pack(fill="x", padx=6, pady=(0,6))

        # Right: Camera / image preview area
        ttk.Label(right, text="Preview:", font=("Segoe UI", 10)).pack(anchor="w", pady=(8,4))
        preview_box = ttk.LabelFrame(right, text="Camera / Image", padding=(8,8))
        preview_box.pack(fill="both", expand=True, padx=6, pady=6)

        self.scan_preview_label = ttk.Label(preview_box)
        self.scan_preview_label.pack(expand=True)

        # scanner status
        self.scan_status = ttk.Label(right, text="Idle", anchor="w")
        self.scan_status.pack(fill="x", padx=6, pady=6)

        # default device index
        self._camera_index = 0

    def copy_decoded_to_clipboard(self):
        text = self.decoded_text.get("1.0", "end").strip()
        if not text:
            return
        self.clipboard_clear()
        self.clipboard_append(text)
        messagebox.showinfo("Copied", "Decoded text copied to clipboard.")

    def scan_file_dialog(self):
        filetypes = [("Image files", "*.png;*.jpg;*.jpeg;*.bmp"), ("All files", "*.*")]
        path = filedialog.askopenfilename(title="Select QR image", initialdir=os.path.abspath("."), filetypes=filetypes)
        if not path:
            return
        self.scan_image_file(path)

    def scan_image_file(self, path):
        if not os.path.exists(path):
            messagebox.showerror("File not found", "Selected file does not exist.")
            return
        try:
            img = cv2.imread(path)
            if img is None:
                raise ValueError("Failed to read image (unsupported format?)")
            data, points = self._detect_qr_in_image(img)
            self._update_scan_preview(img, points)
            if data:
                self._show_decoded(data)
                self.scan_status.config(text="Decoded from file")
            else:
                self._show_decoded("[No QR detected or unreadable]")
                self.scan_status.config(text="No QR found")
        except Exception as e:
            messagebox.showerror("Scan failed", f"Error scanning file:\n{e}")

    def _detect_qr_in_image(self, img_bgr):
        detector = cv2.QRCodeDetector()
        data, points, straight_qrcode = detector.detectAndDecode(img_bgr)
        return data, points

    def _show_decoded(self, text):
        self.decoded_text.delete("1.0", tk.END)
        self.decoded_text.insert("1.0", text)

    def _update_scan_preview(self, img_bgr, points=None):
        # draw bbox if points available
        disp = img_bgr.copy()
        if points is not None and hasattr(points, "shape") and points.shape[0] >= 1:
            pts = points.astype(int).reshape(-1, 2)
            if pts.shape[0] >= 4:
                for i in range(len(pts)):
                    pt1 = tuple(pts[i])
                    pt2 = tuple(pts[(i + 1) % len(pts)])
                    cv2.line(disp, pt1, pt2, (0, 200, 0), 2)

        # convert to PIL then to tk
        b,g,r = cv2.split(disp)
        disp_rgb = cv2.merge((r,g,b))
        pil_img = Image.fromarray(disp_rgb)
        tk_img = pil_image_to_tk(pil_img, max_size=(420,420))
        self.scan_preview_label.image = tk_img
        self.scan_preview_label.config(image=tk_img)

    # -------------------------
    # Camera handling
    # -------------------------
    def select_camera_device(self):
        # simple input box for camera device index
        idx = tk.simpledialog.askinteger("Camera device", "Enter camera device index (0 is default):", initialvalue=self._camera_index, minvalue=0, maxvalue=10)
        if idx is not None:
            self._camera_index = idx
            self.scan_status.config(text=f"Camera device set to {self._camera_index}")

    def toggle_camera(self):
        if self._camera_running:
            self.stop_camera()
        else:
            started = self.start_camera(self._camera_index)
            if started:
                self.cam_toggle_btn.config(text="Stop Camera")

    def start_camera(self, device_index=0):
        with self._camera_lock:
            if self._camera_running:
                return False
            try:
                cap = cv2.VideoCapture(device_index, cv2.CAP_DSHOW) if os.name == 'nt' else cv2.VideoCapture(device_index)
                if not cap.isOpened():
                    # fallback without DSHOW
                    cap.open(device_index)
                if not cap.isOpened():
                    raise RuntimeError("Could not open camera. Check device index or camera permissions.")
                self._video_capture = cap
                self._camera_running = True
                self._camera_thread = threading.Thread(target=self._camera_loop, daemon=True)
                self._camera_thread.start()
                self.scan_status.config(text="Camera started")
                return True
            except Exception as e:
                messagebox.showerror("Camera error", f"Failed to start camera:\n{e}")
                self._camera_running = False
                if self._video_capture:
                    self._video_capture.release()
                    self._video_capture = None
                return False

    def stop_camera(self):
        with self._camera_lock:
            if not self._camera_running:
                return
            self._camera_running = False
        # wait for thread to finish
        if self._camera_thread:
            self._camera_thread.join(timeout=1.0)
        if self._video_capture:
            try:
                self._video_capture.release()
            except Exception:
                pass
            self._video_capture = None
        self.cam_toggle_btn.config(text="Start Camera")
        self.scan_status.config(text="Camera stopped")
        # clear preview
        self.scan_preview_label.config(image="")
        self.scan_preview_label.image = None

    def _camera_loop(self):
        detector = cv2.QRCodeDetector()
        while True:
            with self._camera_lock:
                if not self._camera_running:
                    break
                cap = self._video_capture
            if cap is None:
                break
            ret, frame = cap.read()
            if not ret or frame is None:
                # small sleep to avoid busy loop on errors
                time.sleep(0.05)
                continue

            # detect & decode
            data, points, _ = detector.detectAndDecode(frame)
            if data:
                # update decoded text (only when changed)
                current = self.decoded_text.get("1.0", "end").strip()
                if current != data:
                    self._show_decoded(data)
                    self.scan_status.config(text="Decoded from camera")
            # draw preview and bbox
            try:
                self._update_scan_preview(frame, points)
            except Exception:
                pass

            # sleep a bit so UI remains responsive
            time.sleep(0.03)

    # -------------------------
    # Closing / cleanup
    # -------------------------
    def on_close(self):
        if self._camera_running:
            if messagebox.askyesno("Quit", "Camera is running. Stop camera and exit?"):
                self.stop_camera()
            else:
                return
        # cleanup and exit
        self.destroy()

# -------------------------
# Run app
# -------------------------
if __name__ == "__main__":
    app = QRProApp()
    app.mainloop()
