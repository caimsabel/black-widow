#!/usr/bin/env python
"""
Windows mouse data collector for Mic-E-Mouse (Brazilian hardware edition).

Replaces src/mouse_logger/logger.cc (Windows port). Strategy:

  Primary:  Win32 Raw Input (WM_INPUT) with RIDEV_INPUTSINK + own window.
            Raw Input deltas are the true sensor counts (unaffected by
            pointer acceleration and "enhance pointer precision").

  Fallback: Some Windows builds refuse RIDEV_INPUTSINK registration
            (ERROR_INVALID_PARAMETER) even with a valid target window.
            In that case the collector switches to a global low-level
            hook (WH_MOUSE_LL) AND normalizes the OS pointer so that
            hook-reported pixel deltas == raw sensor counts:
              - "Enhance pointer precision" is turned OFF
              - pointer speed is set to 10/11 (1.0x gain)
              - the thread uses PerMonitorV2 DPI awareness so hook points
                are in PHYSICAL pixels
            The original pointer settings are restored on exit. Manual
            setting instructions are printed as a warning banner.

CSV format is identical to the C++ logger:
    header:  "offset, x, y"
    rows:    inter-event delta (us), count-x, count-y
All events are logged (including zero-delta reports) unless
--motion-only is passed, so `offset` tracks the real polling clock.

Usage:
    python src/mouse_logger/mouse_logger_win.py                    # auto-named CSV
    python src/mouse_logger/mouse_logger_win.py --out data/rec.csv
    python src/mouse_logger/mouse_logger_win.py --list-mice        # list devices
    python src/mouse_logger/mouse_logger_win.py --seconds 120      # capture for 2 min
    python src/mouse_logger/mouse_logger_win.py --motion-only      # drop zero-delta rows

Requires: only the stdlib (ctypes).
"""

import argparse
import ctypes
import ctypes.wintypes as wt
import os
import statistics
import struct
import sys
import time

# --------------------------------------------------------------------------
# Win32 constants
# --------------------------------------------------------------------------
user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

WM_INPUT = 0x00FF
RIDEV_INPUTSINK = 0x00000001
RID_INPUT = 0x10000003
RIDI_DEVICENAME = 0x20000007
MOUSE_MOVE_ABSOLUTE = 0x0001
RAWINPUTHEADER_SIZE = 24          # x64: dwType, dwSize, hDevice, wParam
RAWMOUSE_SIZE = 24

WH_MOUSE_LL = 14
WM_MOUSEMOVE = 0x0200
WH_HOOK_DESTROYING = 0

SPI_GETMOUSE = 0x000F
SPI_SETMOUSE = 0x000F
SPI_GETMOUSESPEED = 0x00E8
SPI_SETMOUSESPEED = 0x00E9
SPI_GETMOUSEVERTICALWHEEL = 0x0158

DPI_AWARE_PER_MONITOR_V2 = -4  # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2

RAWINPUTDEVICE_ARGTYPES_DEFINED = True

WNDPROC = ctypes.WINFUNCTYPE(
    ctypes.c_longlong, wt.HWND, ctypes.c_uint, ctypes.c_longlong, ctypes.c_longlong
)
LLMOUSEPROC = ctypes.WINFUNCTYPE(
    ctypes.c_longlong, ctypes.c_int, ctypes.c_longlong, ctypes.c_longlong
)


class RAWINPUTDEVICE(ctypes.Structure):
    _fields_ = [
        ("usUsagePage", ctypes.c_ushort),
        ("usUsage", ctypes.c_ushort),
        ("dwFlags", wt.DWORD),
        ("hwndTarget", wt.HWND),
    ]


class RAWINPUTDEVICELIST(ctypes.Structure):
    # {HANDLE hDevice; DWORD dwType;} -> 8 + 4 + padding = 16 on x64
    _fields_ = [
        ("hDevice", wt.HANDLE),
        ("dwType", wt.DWORD),
    ]


user32.DefWindowProcW.argtypes = [wt.HWND, ctypes.c_uint, ctypes.c_longlong, ctypes.c_longlong]
user32.DefWindowProcW.restype = ctypes.c_longlong
user32.CreateWindowExW.argtypes = [
    wt.DWORD, wt.LPCWSTR, wt.LPCWSTR, wt.DWORD,
    ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    wt.HWND, wt.HWND, wt.HINSTANCE, wt.LPVOID,
]
user32.CreateWindowExW.restype = wt.HWND
user32.RegisterRawInputDevices.argtypes = [ctypes.POINTER(RAWINPUTDEVICE), ctypes.c_uint, ctypes.c_uint]
user32.RegisterRawInputDevices.restype = ctypes.c_int
user32.GetRawInputData.argtypes = [wt.HANDLE, ctypes.c_uint, ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint), ctypes.c_uint]
user32.GetRawInputData.restype = ctypes.c_uint
user32.GetRawInputDeviceList.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint), ctypes.c_uint]
user32.GetRawInputDeviceList.restype = ctypes.c_uint
user32.GetRawInputDeviceInfoA.argtypes = [wt.HANDLE, ctypes.c_uint, ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint)]
user32.GetRawInputDeviceInfoA.restype = ctypes.c_uint
user32.SetWindowsHookExW.argtypes = [ctypes.c_int, LLMOUSEPROC, wt.HINSTANCE, wt.DWORD]
user32.SetWindowsHookExW.restype = ctypes.c_void_p
user32.UnhookWindowsHookEx.argtypes = [ctypes.c_void_p]
user32.UnhookWindowsHookEx.restype = ctypes.c_int
user32.CallNextHookEx.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_longlong, ctypes.c_longlong]
user32.CallNextHookEx.restype = ctypes.c_longlong
user32.SetThreadDpiAwarenessContext.argtypes = [ctypes.c_void_p]
user32.SetThreadDpiAwarenessContext.restype = ctypes.c_void_p
user32.SystemParametersInfoW.argtypes = [ctypes.c_uint, ctypes.c_uint, ctypes.c_void_p, ctypes.c_uint]
user32.SystemParametersInfoW.restype = ctypes.c_int


def list_mice() -> None:
    """Enumerate attached raw-input mice with their device names."""
    count = ctypes.c_uint(0)
    if user32.GetRawInputDeviceList(
        None, ctypes.byref(count), ctypes.sizeof(RAWINPUTDEVICELIST)
    ) != 0:
        print("error: raw input device probe failed", file=sys.stderr)
        return
    devices = (RAWINPUTDEVICELIST * count.value)()
    user32.GetRawInputDeviceList(devices, ctypes.byref(count), ctypes.sizeof(RAWINPUTDEVICELIST))
    n = 0
    for dev in devices:
        if dev.dwType != 1:  # RIM_TYPEMOUSE
            continue
        n += 1
        size = ctypes.c_uint(0)
        user32.GetRawInputDeviceInfoA(dev.hDevice, RIDI_DEVICENAME, None, ctypes.byref(size))
        name_buf = ctypes.create_string_buffer(size.value + 1)
        user32.GetRawInputDeviceInfoA(dev.hDevice, RIDI_DEVICENAME, name_buf, ctypes.byref(size))
        print(f"  {name_buf.value.decode(errors='replace')}")
    if n == 0:
        print("  (nenhum mouse detectado)")


# --------------------------------------------------------------------------
# Buffered CSV writer, shared by both capture paths
# --------------------------------------------------------------------------
class _CsvWriter:
    def __init__(self, out_path: str, motion_only: bool) -> None:
        self.out_path = out_path
        self.motion_only = motion_only
        self.rows = []  # [dt_us, dx, dy]
        self.total = 0
        self._identify_mode = "rawinput"

    def add(self, dt_us: int, dx: int, dy: int) -> None:
        self.rows.append([dt_us, dx, dy])
        self.total += 1
        if len(self.rows) >= 50_000:
            self.flush()

    def flush(self) -> None:
        if not self.rows:
            return
        os.makedirs(os.path.dirname(os.path.abspath(self.out_path)), exist_ok=True)
        header_needed = (not os.path.isfile(self.out_path)) or os.path.getsize(self.out_path) == 0
        with open(self.out_path, "a", encoding="ascii") as f:
            if header_needed:
                f.write("offset, x, y\n")
            f.writelines(f"{dt}, {dx}, {dy}\n" for dt, dx, dy in self.rows)
        self.rows = []

    def estimated_polling(self, window: int = 20_000) -> float:
        if len(self.rows) < 100:
            return 0.0
        dts = [r[0] for r in self.rows[-window:]]
        return 1e6 / statistics.median(dts)


# --------------------------------------------------------------------------
# Path A: WM_INPUT raw input capture
# --------------------------------------------------------------------------
class _RawInputCollector:
    """Raw-input sink: buffers (dt_us, dx, dy) via WM_INPUT."""

    def __init__(self, out_path: str, motion_only: bool) -> None:
        self.out_path = out_path
        self.writer = _CsvWriter(out_path, motion_only)
        self.last_t = None
        self.hwnd = None
        self.proc = None  # keepalive
        self.mode = "raw input"

    # ---- window / wndproc ----
    def _wndproc(self, hwnd, msg, wparam, lparam):
        if msg != WM_INPUT:
            return user32.DefWindowProcW(hwnd, msg, wparam, lparam)
        try:
            size = ctypes.c_uint(0)
            h_raw = ctypes.c_void_p(lparam)
            user32.GetRawInputData(h_raw, RID_INPUT, None, ctypes.byref(size), RAWINPUTHEADER_SIZE)
            if size.value < RAWINPUTHEADER_SIZE + RAWMOUSE_SIZE:
                return 0
            buf = ctypes.create_string_buffer(size.value)
            if not user32.GetRawInputData(h_raw, RID_INPUT, buf, ctypes.byref(size), RAWINPUTHEADER_SIZE):
                return 0
            us_flags = struct.unpack_from("H", buf, RAWINPUTHEADER_SIZE)[0]
            dx, dy = struct.unpack_from("ii", buf, RAWINPUTHEADER_SIZE + 12)
            if us_flags & MOUSE_MOVE_ABSOLUTE:
                return 0  # absolute devices (VMs/touch) are not the sensor channel
            t = time.perf_counter_ns() // 1000
            if self.last_t is None:
                self.last_t = t
                return 0
            dt = t - self.last_t
            self.last_t = t
            if self.writer.motion_only and dx == 0 and dy == 0:
                return 0
            self.writer.add(dt, max(-32767, min(32767, dx)), max(-32767, min(32767, dy)))
            return 0
        except Exception:
            return 0

    def register(self) -> bool:
        hinstance = kernel32.GetModuleHandleW(None)
        classname = ctypes.c_wchar_p("MicEMouseWinCollector")

        class POINT(ctypes.Structure):
            _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

        class MSG(ctypes.Structure):
            _fields_ = [
                ("hwnd", wt.HWND), ("message", ctypes.c_uint),
                ("wParam", ctypes.c_longlong), ("lParam", ctypes.c_longlong),
                ("time", wt.DWORD), ("pt", POINT),
            ]

        class WNDCLASSW(ctypes.Structure):
            _fields_ = [
                ("style", ctypes.c_uint), ("lpfnWndProc", WNDPROC),
                ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int),
                ("hInstance", wt.HINSTANCE), ("hIcon", wt.HWND), ("hCursor", wt.HWND),
                ("hbrBackground", wt.HWND), ("lpszMenuName", wt.LPCWSTR),
                ("lpszClassName", wt.LPCWSTR), ("hIconSm", wt.HWND),
            ]

        self.proc = WNDPROC(self._wndproc)  # keepalive: must out-live the window
        wc = WNDCLASSW()
        wc.lpfnWndProc = self.proc
        wc.hInstance = hinstance
        wc.lpszClassName = classname
        if not user32.RegisterClassW(ctypes.byref(wc)):
            return False
        # Real hidden window (message-only windows don't reliably get raw input)
        self.hwnd = user32.CreateWindowExW(
            0, classname, "Mic-E-Mouse collector", 0, 0, 0, 0, 0, None, None, hinstance, None,
        )
        if not self.hwnd:
            return False
        rid = RAWINPUTDEVICE(0x01, 0x02, RIDEV_INPUTSINK, self.hwnd)
        return bool(user32.RegisterRawInputDevices(ctypes.byref(rid), 1, ctypes.sizeof(RAWINPUTDEVICE)))

    def pump(self, run_seconds: "float | None") -> None:
        class POINT(ctypes.Structure):
            _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

        class MSG(ctypes.Structure):
            _fields_ = [
                ("hwnd", wt.HWND), ("message", ctypes.c_uint),
                ("wParam", ctypes.c_longlong), ("lParam", ctypes.c_longlong),
                ("time", wt.DWORD), ("pt", POINT),
            ]

        msg = MSG()
        start = time.perf_counter()
        last_report = time.perf_counter()
        auto_stop = run_seconds is not None
        try:
            while True:
                if auto_stop and time.perf_counter() - start >= run_seconds:
                    break
                while user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
                    user32.TranslateMessage(ctypes.byref(msg))
                    user32.DispatchMessageW(ctypes.byref(msg))
                now = time.perf_counter()
                if now - last_report >= 3.0:
                    self.writer.flush()
                    est = self.writer.estimated_polling()
                    if est:
                        print(f"  eventos={self.writer.total}  polling estimado ~{est:.0f} Hz")
                    last_report = now
                time.sleep(0.002)
        except KeyboardInterrupt:
            pass
        finally:
            self.writer.flush()
            print(f"concluido ({self.mode}): {self.writer.total} eventos gravados")


# --------------------------------------------------------------------------
# Path B: low-level mouse hook with OS-pointer normalization
# --------------------------------------------------------------------------
class _PointerNormalizer:
    """
    Keep the OS pointer pipeline out of the sensor counts.

    Strategy:
      * 'Enhance pointer precision' must be OFF: with EPP on the deltas
        are scaled non-linearly. Turned off via SPI_SETMOUSE (works even
        where SPI_SETMOUSESPEED is restricted), restored on exit.
      * Pointer speed (MouseSensitivity 1-20) contributes a linear gain
        factor = (v-10)/10 + 1. We READ it (registry; SPI_GETMOUSESPEED
        is refused by some builds with ERROR_INVALID_PARAMETER) and
        software-correct the hook deltas: counts = px / factor. The
        user's setting is never touched.
    """

    SPEED_GAIN = 1.0  # linear gain applied by the OS speed setting

    def __init__(self) -> None:
        self.epp_state = (ctypes.c_int * 3)(0, 0, 0)
        self.old_epp = None
        self.gain = 1.0

    def apply(self) -> bool:
        # 1) EPP state
        if user32.SystemParametersInfoW(SPI_GETMOUSE, 0, self.epp_state, 0):
            self.old_epp = list(self.epp_state)
            if self.old_epp[2] != 0:
                off = (ctypes.c_int * 3)(self.old_epp[0], self.old_epp[1], 0)
                user32.SystemParametersInfoW(SPI_SETMOUSE, 0, off, 0)
        # 2) linear speed gain from the registry
        try:
            import winreg
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, r"Control Panel\Mouse"
            ) as k:
                sens = int(winreg.QueryValueEx(k, "MouseSensitivity")[0])
        except (OSError, ValueError):
            sens = 10
        self.gain = (sens - 10) / 10.0 + 1.0
        if self.gain != 1.0:
            print(f"  [normalizar] speed {sens}/20 -> ganho x{self.gain:.2f} em software")
        if self.old_epp and self.old_epp[2] != 0:
            print("  [normalizar] 'Enhance pointer precision' foi DESLIGADO no sistema (restaurado ao sair)")
        return True

    def counts(self, dx: float, dy: float) -> "tuple[int, int]":
        """Convert hook pixel deltas into raw sensor counts."""
        return int(round(dx / self.gain)), int(round(dy / self.gain))

    def restore(self) -> None:
        if self.old_epp and self.old_epp[2] != 0:
            orig = (ctypes.c_int * 3)(*self.old_epp)
            user32.SystemParametersInfoW(SPI_SETMOUSE, 0, orig, 0)


class _LLHookCollector:
    """WH_MOUSE_LL sink with pointer normalization (pixel == sensor count)."""

    def __init__(self, out_path: str, motion_only: bool) -> None:
        self.writer = _CsvWriter(out_path, motion_only)
        self.last_pt = None
        self.normalizer = _PointerNormalizer()
        self.old_ctx = None
        self._hook = None
        self.proc = None  # WNDPROC keepalive: must out-live the hook
        self.mode = "low-level hook (px->count software-corrected)"

    def _hook_proc(self, code, wparam, lparam):
        if code >= 0 and wparam == WM_MOUSEMOVE:
            # MSLLHOOKSTRUCT begins with POINT pt (LONG x, LONG y).
            x, y = struct.unpack_from("ll", ctypes.c_void_p(lparam))
            t = time.perf_counter_ns() // 1000
            if self.last_pt is None:
                self.last_pt = (x, y, t)
            else:
                dt = t - self.last_pt[2]
                dx = x - self.last_pt[0]
                dy = y - self.last_pt[1]
                self.last_pt = (x, y, t)
                if not (self.writer.motion_only and dx == 0 and dy == 0):
                    cx, cy = self.normalizer.counts(dx, dy)
                    self.writer.add(dt, cx, cy)
        return user32.CallNextHookEx(None, code, wparam, lparam)

    def open(self) -> bool:
        # PerMonitorV2: hook 'pt' comes in PHYSICAL pixels (100% scale == 1:1
        # sensor counts after EPP removal / software gain correction).
        old = user32.SetThreadDpiAwarenessContext(
            ctypes.c_void_p(DPI_AWARE_PER_MONITOR_V2)
        )
        self.old_ctx = old if old else None
        if not self.normalizer.apply():
            return False
        self.proc = LLMOUSEPROC(self._hook_proc)  # gc: must out-live the hook
        self._hook = user32.SetWindowsHookExW(WH_MOUSE_LL, self.proc, None, 0)
        if not self._hook:
            # Last resort: switch back to system sensitivity scale knowledge.
            user32.SystemParametersInfoW(SPI_SETMOUSE, 0, self.normalizer.epp_state, 0)
            if self.old_ctx:
                user32.SetThreadDpiAwarenessContext(self.old_ctx)
            return False
        return True

    def pump(self, run_seconds):
        start = time.perf_counter()
        last_report = time.perf_counter()
        try:
            while True:
                if run_seconds is not None and time.perf_counter() - start >= run_seconds:
                    break
                now = time.perf_counter()
                if now - last_report >= 3.0:
                    self.writer.flush()
                    est = self.writer.estimated_polling()
                    if est:
                        print(f"  eventos={self.writer.total}  polling estimado ~{est:.0f} Hz")
                    last_report = now
                # The low-level hook requires the installing thread to pump messages.
                class POINT(ctypes.Structure):
                    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

                class MSG(ctypes.Structure):
                    _fields_ = [
                        ("hwnd", wt.HWND), ("message", ctypes.c_uint),
                        ("wParam", ctypes.c_longlong), ("lParam", ctypes.c_longlong),
                        ("time", wt.DWORD), ("pt", POINT),
                    ]

                msg = MSG()
                while user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
                    user32.TranslateMessage(ctypes.byref(msg))
                    user32.DispatchMessageW(ctypes.byref(msg))
                time.sleep(0.002)
        except KeyboardInterrupt:
            pass
        finally:
            user32.UnhookWindowsHookEx(self._hook)
            self.normalizer.restore()
            if self.old_ctx:
                user32.SetThreadDpiAwarenessContext(self.old_ctx)
            self.writer.flush()
            print(f"concluido ({self.mode}): {self.writer.total} eventos gravados")


# --------------------------------------------------------------------------
# Entry point: try raw input, fall back to LL hook automatically
# --------------------------------------------------------------------------
def run_collector(out_path: str, motion_only: bool, run_seconds: float = None) -> None:
    print(f"output: {out_path}")

    ri = _RawInputCollector(out_path, motion_only)
    if ri.register():
        print("modo captura: Raw Input (WM_INPUT, contagens cruas do sensor)")
        ri.pump(run_seconds)
        return

    print("aviso: Raw Input + RIDEV_INPUTSINK nao registrado nesta build (err 87).")
    print("       migrando para Low-Level Hook + normalizacao de ponteiro:")
    print("       'Enhance pointer precision' sera DESLIGADO e a velocidade fixa em")
    print("       10/11 durante a coleta (restaurado no fim). Os deltas em pixels")
    print("       equivalem as contagens cruas do sensor.")

    ll = _LLHookCollector(out_path, motion_only)
    if not ll.open():
        print("error: fallback LL hook also failed (unlikely)")
        sys.exit(1)
    print("modo captura: Low-Level Hook (contagens por pixel normalizado)")
    ll.pump(run_seconds)
    print("concluida a coleta.")


def main() -> int:
    p = argparse.ArgumentParser(
        description="Raw mouse capture collector for Mic-E-Mouse on Windows "
                    "(Brazilian mice: 4,000 DPI / 1-2 kHz polling).",
    )
    p.add_argument("--out", default=None, help="output CSV path (default: data/data_win_<ts>.csv)")
    p.add_argument("--list-mice", action="store_true", help="list attached mice and exit")
    p.add_argument("--motion-only", action="store_true",
                   help="log only non-zero-delta events (smaller file, breaks polling estimate)")
    p.add_argument("--seconds", type=float, default=None,
                   help="auto-stop after N seconds (scriptable runs)")
    args = p.parse_args()

    if args.list_mice:
        list_mice()
        return 0

    out_path = args.out
    if not out_path:
        stamp = time.strftime("%Y-%m-%d_%H-%M-%S")
        out_path = os.path.join("data", f"data_win_{stamp}.csv")

    run_collector(out_path, args.motion_only, args.seconds)
    return 0


if __name__ == "__main__":
    sys.exit(main())
