# -*- coding: utf-8 -*-
#
# KeyPresser - 重复按键小工具（Windows / 仅用 Python 标准库）
#
# 功能:
#   1. 按键序列：可以放一个键，也可以放多个键按顺序循环执行；
#      每一步都能单独设间隔，按键是全局的，不挑窗口。
#   2. 全局热键开启 / 停止（默认 F8 / F9，可自己改），开启和停止都有声音提示。
#   3. 声音来源三选一：
#        内置提示音   —— 程序自带的三套提示音（清脆/柔和/低沉，代码合成，CC0）
#        自定义语音   —— 导入自己的 wav，或直接用麦克风录制
#        系统语音     —— 调用 Windows 自带的中文语音朗读"开始按键/停止按键"
#   4. 作用范围可选：全局，或只在指定程序最前面时生效。
#
# 许可证: MIT
# 版本:   见下面的 __version__（发布新版时改这一处即可）

# 程序版本号：窗口标题、界面横幅、--version 输出都用它。
__version__ = "1.0.1"

import ctypes
import ctypes.wintypes as wintypes
import hashlib
import json
import math
import os
import queue
import shutil
import subprocess
import sys
import tempfile
import threading

# 打包成 exe 之后，Tcl/Tk 的脚本目录需要自己找一下（放在程序旁边的 tcl 目录里）。
# 这段必须放在 import tkinter 之前。
if getattr(sys, "frozen", False):
    os.environ.pop("TCL_LIBRARY", None)
    os.environ.pop("TK_LIBRARY", None)

import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

import winsound

# --------------------------------------------------------------------------
# Win32
# --------------------------------------------------------------------------

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
winmm = ctypes.WinDLL("winmm", use_last_error=True)

ULONG_PTR = ctypes.c_ulonglong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_ulong

INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002

WM_HOTKEY = 0x0312
WM_APP_QUIT = 0x8001

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
CREATE_NO_WINDOW = 0x08000000


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUTUNION)]


user32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
user32.SendInput.restype = wintypes.UINT
user32.MapVirtualKeyW.argtypes = (wintypes.UINT, wintypes.UINT)
user32.MapVirtualKeyW.restype = wintypes.UINT

user32.RegisterHotKey.argtypes = (wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT)
user32.RegisterHotKey.restype = wintypes.BOOL
user32.UnregisterHotKey.argtypes = (wintypes.HWND, ctypes.c_int)
user32.UnregisterHotKey.restype = wintypes.BOOL
user32.GetMessageW.argtypes = (ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT)
user32.GetMessageW.restype = ctypes.c_int
user32.PostThreadMessageW.argtypes = (wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
user32.PostThreadMessageW.restype = wintypes.BOOL

user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetWindowThreadProcessId.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
user32.IsWindowVisible.argtypes = (wintypes.HWND,)
user32.IsWindowVisible.restype = wintypes.BOOL
user32.GetWindowTextLengthW.argtypes = (wintypes.HWND,)
user32.GetWindowTextLengthW.restype = ctypes.c_int
user32.GetWindowTextW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
user32.GetWindowTextW.restype = ctypes.c_int
user32.SetForegroundWindow.argtypes = (wintypes.HWND,)
user32.SetForegroundWindow.restype = wintypes.BOOL
kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
kernel32.QueryFullProcessImageNameW.argtypes = (
    wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)
)
kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
kernel32.GetCurrentThreadId.restype = wintypes.DWORD

winmm.mciSendStringW.argtypes = (wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.UINT, wintypes.HWND)
winmm.mciSendStringW.restype = wintypes.DWORD


def send_key_event(vk, down=True):
    scan = user32.MapVirtualKeyW(vk, 0)
    flags = 0 if down else KEYEVENTF_KEYUP
    inp = INPUT(type=INPUT_KEYBOARD,
                u=_INPUTUNION(ki=KEYBDINPUT(vk, scan, flags, 0, 0)))
    user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))


def foreground_pid():
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return 0
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value


def process_exe(pid):
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return ""
    try:
        size = wintypes.DWORD(1024)
        buf = ctypes.create_unicode_buffer(size.value)
        if kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            return os.path.basename(buf.value)
        return ""
    finally:
        kernel32.CloseHandle(handle)


def list_windows():
    """返回 [(hwnd, pid, 标题, 进程名)]，只列出可见且有标题的窗口。"""
    result = []
    seen = set()

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def _callback(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        title = buf.value.strip()
        if not title:
            return True
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        key = (pid.value, title)
        if key in seen:
            return True
        seen.add(key)
        result.append((hwnd, pid.value, title, process_exe(pid.value)))
        return True

    user32.EnumWindows(_callback, 0)
    return result


# --------------------------------------------------------------------------
# 路径
# --------------------------------------------------------------------------

if getattr(sys, "frozen", False):
    APP_DIR = os.path.dirname(os.path.abspath(sys.executable))
    RES_DIR = getattr(sys, "_MEIPASS", APP_DIR)                  # 只读：自带资源
else:
    APP_DIR = os.path.dirname(os.path.abspath(__file__))
    RES_DIR = APP_DIR

# 用户的设置和录音统一放到 %APPDATA%\KeyPresser，
# 程序所在目录永远保持干净（只有程序本身）。
DATA_DIR = os.path.join(os.environ.get("APPDATA") or APP_DIR, "KeyPresser")

TTS_PS1 = os.path.join(RES_DIR, "tts_synth.ps1")
ICON_ICO = os.path.join(RES_DIR, "assets", "icon.ico")
SOUNDS_DIR = os.path.join(RES_DIR, "sounds")
CUSTOM_DIR = os.path.join(DATA_DIR, "custom_voice")
SETTINGS_FILE = os.path.join(DATA_DIR, "settings.json")
SPEECH_CACHE_DIR = os.path.join(tempfile.gettempdir(), "keypresser_tts")

PHRASE_START = "开始按键"
PHRASE_STOP = "停止按键"

VOICE_CUSTOM = "自定义语音（我导入/录制的）"

# 内置提示音（代码合成，CC0）
SOUND_STYLES = [
    ("内置提示音 · 清脆", "chime"),
    ("内置提示音 · 柔和", "soft"),
    ("内置提示音 · 低沉", "deep"),
]
DEFAULT_VOICE = SOUND_STYLES[0][0]

FALLBACK_VOICES = ["Microsoft Huihui", "Microsoft Yaoyao", "Microsoft Kangkang"]


def custom_voice_files():
    return (os.path.join(CUSTOM_DIR, "start.wav"), os.path.join(CUSTOM_DIR, "stop.wav"))


def custom_voice_ready():
    start_wav, stop_wav = custom_voice_files()
    return wav_exists(start_wav) and wav_exists(stop_wav)


def _run_hidden(args, timeout):
    return subprocess.run(args, creationflags=CREATE_NO_WINDOW, timeout=timeout,
                          stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)


def list_system_voices():
    """列出 Windows 上可用的语音；失败时给一份后备清单。"""
    fallback = [(v, "zh-CN") for v in FALLBACK_VOICES]
    if not os.path.exists(TTS_PS1):
        return fallback
    try:
        result = _run_hidden(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                              "-File", TTS_PS1, "-List"], 30)
        text = result.stdout.decode("utf-8", "replace")
    except Exception:
        return fallback
    voices = []
    for line in text.splitlines():
        line = line.strip()
        if "|" in line:
            name, lang = line.split("|", 1)
            name, lang = name.strip(), lang.strip()
            if name:
                voices.append((name, lang))
    return voices or fallback


def wav_cache_path(text, voice):
    digest = hashlib.md5(("%s|%s" % (text, voice)).encode("utf-8")).hexdigest()[:12]
    return os.path.join(SPEECH_CACHE_DIR, digest + ".wav")


def wav_exists(path):
    try:
        return os.path.exists(path) and os.path.getsize(path) > 2000
    except Exception:
        return False


def synth_to_wav(text, voice, out_path):
    if not os.path.exists(TTS_PS1):
        return False
    try:
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
    except Exception:
        return False
    args = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", TTS_PS1,
            "-Text", text, "-Out", out_path]
    if voice:
        args += ["-Voice", voice]
    try:
        result = _run_hidden(args, 60)
    except Exception:
        return False
    return result.returncode == 0 and wav_exists(out_path)


def play_wav(path):
    winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC)


def mci(command):
    buf = ctypes.create_unicode_buffer(512)
    code = winmm.mciSendStringW(command, buf, 512, None)
    return code, buf.value


# --------------------------------------------------------------------------
# 按键表
# --------------------------------------------------------------------------

KEY_CHOICES = [("F%d" % i, 0x70 + i - 1) for i in range(1, 13)]
KEY_CHOICES += [
    ("空格 Space", 0x20),
    ("回车 Enter", 0x0D),
    ("Tab", 0x09),
    ("Esc", 0x1B),
    ("退格 Backspace", 0x08),
    ("Delete", 0x2E),
    ("Insert", 0x2D),
    ("Home", 0x24),
    ("End", 0x23),
    ("PageUp", 0x21),
    ("PageDown", 0x22),
    ("↑ 上", 0x26),
    ("↓ 下", 0x28),
    ("← 左", 0x25),
    ("→ 右", 0x27),
]
for _ch in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
    KEY_CHOICES.append((_ch, ord(_ch)))
for _digit in "0123456789":
    KEY_CHOICES.append((_digit, ord(_digit)))

KEY_VK = dict(KEY_CHOICES)
KEY_LABELS = [label for label, _vk in KEY_CHOICES]
DEFAULT_KEY_LABEL = "F"

VK_NAMES = {
    "return": 0x0D, "enter": 0x0D, "kp_enter": 0x0D,
    "space": 0x20, "tab": 0x09, "escape": 0x1B, "backspace": 0x08,
    "delete": 0x2E, "insert": 0x2D, "home": 0x24, "end": 0x23,
    "prior": 0x21, "next": 0x22, "up": 0x26, "down": 0x28,
    "left": 0x25, "right": 0x27, "caps_lock": 0x14, "num_lock": 0x90,
    "scroll_lock": 0x91, "print": 0x2C, "pause": 0x13,
    "minus": 0xBD, "equal": 0xBB, "bracketleft": 0xDB, "bracketright": 0xDD,
    "backslash": 0xDC, "semicolon": 0xBA, "apostrophe": 0xDE,
    "comma": 0xBC, "period": 0xBE, "slash": 0xBF, "grave": 0xC0,
    "kp_0": 0x60, "kp_1": 0x61, "kp_2": 0x62, "kp_3": 0x63, "kp_4": 0x64,
    "kp_5": 0x65, "kp_6": 0x66, "kp_7": 0x67, "kp_8": 0x68, "kp_9": 0x69,
    "kp_decimal": 0x6E, "kp_add": 0x6B, "kp_subtract": 0x6D,
    "kp_multiply": 0x6A, "kp_divide": 0x6F,
}

MODIFIER_KEYSYMS = {
    "control_l": MOD_CONTROL, "control_r": MOD_CONTROL,
    "shift_l": MOD_SHIFT, "shift_r": MOD_SHIFT,
    "alt_l": MOD_ALT, "alt_r": MOD_ALT,
    "super_l": MOD_WIN, "super_r": MOD_WIN,
}


def keysym_to_vk(keysym):
    k = keysym.lower()
    if k in VK_NAMES:
        return VK_NAMES[k]
    if len(keysym) == 1:
        ch = keysym.upper()
        if ("A" <= ch <= "Z") or ("0" <= ch <= "9"):
            return ord(ch)
    if k.startswith("f") and k[1:].isdigit():
        n = int(k[1:])
        if 1 <= n <= 24:
            return 0x70 + n - 1
    return None


def key_display(keysym):
    k = keysym.lower()
    pretty = {
        "return": "Enter", "space": "空格", "tab": "Tab", "escape": "Esc",
        "backspace": "退格", "up": "↑", "down": "↓", "left": "←", "right": "→",
        "prior": "PgUp", "next": "PgDn", "delete": "Delete", "insert": "Insert",
    }
    if k in pretty:
        return pretty[k]
    return keysym.upper() if len(keysym) == 1 else keysym


def key_label_to_vk(label):
    if label in KEY_VK:
        return KEY_VK[label]
    return keysym_to_vk(label)


# --------------------------------------------------------------------------
# 全局热键线程
# --------------------------------------------------------------------------

class HotkeyThread(threading.Thread):
    def __init__(self, bindings, out_queue):
        super().__init__(daemon=True)
        self.bindings = bindings
        self.out_queue = out_queue
        self.thread_id = None

    def run(self):
        self.thread_id = kernel32.GetCurrentThreadId()
        for hk_id, (mods, vk) in self.bindings.items():
            if not user32.RegisterHotKey(None, hk_id, mods | MOD_NOREPEAT, vk):
                self.out_queue.put(("hotkey_fail", hk_id))

        msg = wintypes.MSG()
        while True:
            ret = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if ret == 0 or ret == -1:
                break
            if msg.message == WM_APP_QUIT:
                for hk_id in self.bindings:
                    user32.UnregisterHotKey(None, hk_id)
                break
            if msg.message == WM_HOTKEY:
                self.out_queue.put(("hotkey", int(msg.wParam)))

    def stop(self):
        if self.thread_id:
            user32.PostThreadMessageW(self.thread_id, WM_APP_QUIT, 0, 0)


# --------------------------------------------------------------------------
# 自定义语音窗口
# --------------------------------------------------------------------------

class CustomVoiceDialog(tk.Toplevel):
    """导入 / 录制自己的开始音和停止音。"""

    def __init__(self, master, on_saved):
        super().__init__(master)
        self.title("自定义语音")
        self.configure(bg=CARD_BG)
        self.resizable(False, False)
        self.transient(master)
        self.grab_set()
        self.on_saved = on_saved
        self.recording = None            # None / "start" / "stop"
        self.buttons = {}

        pad = {"padx": 8, "pady": 6}
        ttk.Label(self, text="导入自己的 wav 文件，或直接用麦克风录一段。",
                  foreground=HINT_FG).grid(row=0, column=0, columnspan=4, sticky="w", **pad)

        for row, (kind, label) in enumerate((("start", "开始音"), ("stop", "停止音")), start=1):
            ttk.Label(self, text=label + "：").grid(row=row, column=0, sticky="e", **pad)
            ttk.Button(self, text="导入 WAV…", width=11,
                       command=lambda k=kind: self.import_wav(k)).grid(row=row, column=1, **pad)
            btn = ttk.Button(self, text="录制", width=11,
                             command=lambda k=kind: self.toggle_record(k))
            btn.grid(row=row, column=2, **pad)
            self.buttons[kind] = btn
            ttk.Button(self, text="试听", width=7,
                       command=lambda k=kind: self.audition(k)).grid(row=row, column=3, **pad)

        ttk.Label(self, text="说明：导入只支持 .wav；录制使用的是系统默认麦克风。",
                  foreground=HINT_FG).grid(row=3, column=0, columnspan=4, sticky="w", **pad)
        ttk.Button(self, text="关闭", width=10, command=self.close).grid(
            row=4, column=3, sticky="e", **pad)

    # ------------------------------------------------------------------
    def import_wav(self, kind):
        path = filedialog.askopenfilename(
            parent=self, title="选择 WAV 文件",
            filetypes=[("WAV 音频", "*.wav"), ("所有文件", "*.*")])
        if not path:
            return
        if not path.lower().endswith(".wav"):
            messagebox.showinfo("提示", "目前只支持 .wav 文件。\n"
                                        "（可以用系统「录音机」录完再转成 wav，"
                                        "或者直接用本窗口的「录制」功能。）", parent=self)
            return
        try:
            os.makedirs(CUSTOM_DIR, exist_ok=True)
            dst = custom_voice_files()[0 if kind == "start" else 1]
            shutil.copyfile(path, dst)
        except Exception as exc:
            messagebox.showerror("导入失败", str(exc), parent=self)
            return
        self.on_saved()

    def toggle_record(self, kind):
        if self.recording == kind:
            self.stop_record()
            return
        if self.recording is not None:
            messagebox.showinfo("提示", "正在录制另一个声音，请先把它停下。", parent=self)
            return

        code, _ = mci("open new type waveaudio alias kzrec")
        if code:
            messagebox.showerror("录制失败",
                                 "打不开录音设备（错误码 %d）。\n"
                                 "请确认电脑有麦克风，并且系统允许程序使用麦克风。" % code,
                                 parent=self)
            return
        code, _ = mci("record kzrec")
        if code:
            mci("close kzrec")
            messagebox.showerror("录制失败", "开始录音失败（错误码 %d）。" % code, parent=self)
            return

        self.recording = kind
        self.buttons[kind].config(text="停止并保存")

    def stop_record(self):
        kind = self.recording
        self.recording = None
        if kind:
            self.buttons[kind].config(text="录制")

        mci("stop kzrec")
        tmp_wav = os.path.join(tempfile.gettempdir(), "keypresser_rec.wav")
        try:
            os.path.exists(tmp_wav) and os.remove(tmp_wav)
        except Exception:
            pass
        code, _ = mci('save kzrec "%s"' % tmp_wav)
        mci("close kzrec")

        if code or not os.path.exists(tmp_wav):
            messagebox.showerror("录制失败", "保存录音失败。", parent=self)
            return
        try:
            os.makedirs(CUSTOM_DIR, exist_ok=True)
            dst = custom_voice_files()[0 if kind == "start" else 1]
            shutil.copyfile(tmp_wav, dst)
        except Exception as exc:
            messagebox.showerror("保存失败", str(exc), parent=self)
            return
        self.on_saved()

    def audition(self, kind):
        path = custom_voice_files()[0 if kind == "start" else 1]
        if wav_exists(path):
            play_wav(path)
        else:
            messagebox.showinfo("提示", "还没有这个声音，先导入或录一段吧。", parent=self)

    def close(self):
        if self.recording:
            self.stop_record()
        self.destroy()


# --------------------------------------------------------------------------
# 主界面
# --------------------------------------------------------------------------

APP_TITLE = "KeyPresser 按键精灵"

# --------------------------------------------------------------------------
# 主题（配色）系统
#
# 【主题数据的原始来源】
#   1. 程序目录 / 打包资源里的  themes.json  —— 这是主题的原始数据文件，
#      每个主题就是一组颜色 + 名字，想加主题或改配色直接改这个文件即可。
#   2. 如果找不到 themes.json（比如被删了），就用下面 BUILTIN_THEMES 里
#      内置的同一份数据兜底，保证程序一定能起来。
#   3. 运行时：load_themes() 读取原始数据 -> apply_theme() 把选中的主题
#      写进下面这些全局配色变量 -> _apply_theme() 刷新控件样式 +
#      _build_ui() 重建界面，于是整个界面换肤。
# --------------------------------------------------------------------------

# 主题里必须提供的颜色键（也就是 themes.json 中每个主题的 colors 字段）
THEME_KEYS = (
    "APP_BG", "CARD_BG", "CARD_BORDER",
    "TITLE_FG", "TEXT_FG", "HINT_FG",
    "ACCENT", "ACCENT_LIGHT", "ACCENT_DARK",
    "BUBBLE", "BUBBLE_LIGHT", "BUBBLE_DARK",
    "FIELD_BG", "FIELD_BORDER",
    "BTN_BG", "BTN_HOVER", "BTN_PRESS", "BTN_FG", "BTN_DISABLED_FG",
    "TREE_BG", "TREE_HEAD_BG", "TREE_HEAD_ACTIVE", "TREE_SEL_BG",
    "HEAD_TOP", "HEAD_BOTTOM",
)

BUILTIN_THEMES = [
    {
        "id": "sakura_light",
        "name": "樱粉 · 亮",
        "colors": {
            "APP_BG": "#FDF1F7", "CARD_BG": "#FFFFFF", "CARD_BORDER": "#F3C6DC",
            "TITLE_FG": "#C22A66", "TEXT_FG": "#3A3145", "HINT_FG": "#6C5C79",
            "ACCENT": "#D93A82", "ACCENT_LIGHT": "#F58BB9", "ACCENT_DARK": "#A81F5C",
            "BUBBLE": "#3D74D8", "BUBBLE_LIGHT": "#84ACF0", "BUBBLE_DARK": "#2A55A8",
            "FIELD_BG": "#FFFFFF", "FIELD_BORDER": "#E9B9D2",
            "BTN_BG": "#FBDCEA", "BTN_HOVER": "#F7C9DD", "BTN_PRESS": "#F2B5D0",
            "BTN_FG": "#B02360", "BTN_DISABLED_FG": "#9C8FA6",
            "TREE_BG": "#FFFFFF", "TREE_HEAD_BG": "#F8DCEA",
            "TREE_HEAD_ACTIVE": "#F2CBE0", "TREE_SEL_BG": "#F5BBD8",
            "HEAD_TOP": "#FBE3EF", "HEAD_BOTTOM": "#E3ECFA",
        },
    },
    {
        "id": "sakura_dark",
        "name": "樱粉 · 暗",
        "colors": {
            "APP_BG": "#1E1826", "CARD_BG": "#292132", "CARD_BORDER": "#463A55",
            "TITLE_FG": "#FF8FC4", "TEXT_FG": "#F1E9F6", "HINT_FG": "#BCAACB",
            "ACCENT": "#FF6FB2", "ACCENT_LIGHT": "#C9518A", "ACCENT_DARK": "#FF9ECB",
            "BUBBLE": "#5A8DF0", "BUBBLE_LIGHT": "#3F69B8", "BUBBLE_DARK": "#8FB4FF",
            "FIELD_BG": "#332A3F", "FIELD_BORDER": "#544469",
            "BTN_BG": "#3B2F49", "BTN_HOVER": "#4A3B5C", "BTN_PRESS": "#584670",
            "BTN_FG": "#FFA6D2", "BTN_DISABLED_FG": "#8A7C97",
            "TREE_BG": "#292132", "TREE_HEAD_BG": "#3A2E47",
            "TREE_HEAD_ACTIVE": "#493A5A", "TREE_SEL_BG": "#5B3E68",
            "HEAD_TOP": "#2A2033", "HEAD_BOTTOM": "#1F2A3D",
        },
    },
    {
        "id": "mint_light",
        "name": "薄荷 · 亮",
        "colors": {
            "APP_BG": "#EFF8F5", "CARD_BG": "#FFFFFF", "CARD_BORDER": "#BFE3D8",
            "TITLE_FG": "#16705C", "TEXT_FG": "#2F3B39", "HINT_FG": "#5E7370",
            "ACCENT": "#1E9E83", "ACCENT_LIGHT": "#7FD3BF", "ACCENT_DARK": "#0F6E5A",
            "BUBBLE": "#3F7FD1", "BUBBLE_LIGHT": "#8FB6E8", "BUBBLE_DARK": "#2A5C9E",
            "FIELD_BG": "#FFFFFF", "FIELD_BORDER": "#BFE0D8",
            "BTN_BG": "#DCEFE9", "BTN_HOVER": "#C9E7DE", "BTN_PRESS": "#B5DED3",
            "BTN_FG": "#11614F", "BTN_DISABLED_FG": "#8C9C99",
            "TREE_BG": "#FFFFFF", "TREE_HEAD_BG": "#DCEFE9",
            "TREE_HEAD_ACTIVE": "#CBE7DF", "TREE_SEL_BG": "#B9E3D6",
            "HEAD_TOP": "#E3F5EF", "HEAD_BOTTOM": "#E4EEFB",
        },
    },
    {
        "id": "night_blue",
        "name": "星夜 · 暗",
        "colors": {
            "APP_BG": "#141A26", "CARD_BG": "#1D2534", "CARD_BORDER": "#33415A",
            "TITLE_FG": "#7FD8FF", "TEXT_FG": "#E8EFF8", "HINT_FG": "#A9BACC",
            "ACCENT": "#43C7F4", "ACCENT_LIGHT": "#2C7FA8", "ACCENT_DARK": "#8FE3FF",
            "BUBBLE": "#8C7BF0", "BUBBLE_LIGHT": "#5B4EB0", "BUBBLE_DARK": "#B7ACFF",
            "FIELD_BG": "#26303F", "FIELD_BORDER": "#3C4C66",
            "BTN_BG": "#25303F", "BTN_HOVER": "#2F3C4E", "BTN_PRESS": "#3A4A5F",
            "BTN_FG": "#8FD8F5", "BTN_DISABLED_FG": "#7D8A9B",
            "TREE_BG": "#1D2534", "TREE_HEAD_BG": "#28334A",
            "TREE_HEAD_ACTIVE": "#33425C", "TREE_SEL_BG": "#2F5273",
            "HEAD_TOP": "#1B2433", "HEAD_BOTTOM": "#17263A",
        },
    },
]

DEFAULT_THEME_ID = BUILTIN_THEMES[0]["id"]

# 下面这些就是"当前生效"的配色变量，由 apply_theme() 从主题数据里写入
APP_BG = "#FDF1F7"
CARD_BG = "#FFFFFF"
CARD_BORDER = "#F3C6DC"
TITLE_FG = "#C22A66"
TEXT_FG = "#3A3145"
HINT_FG = "#6C5C79"
ACCENT = "#D93A82"
ACCENT_LIGHT = "#F58BB9"
ACCENT_DARK = "#A81F5C"
BUBBLE = "#3D74D8"
BUBBLE_LIGHT = "#84ACF0"
BUBBLE_DARK = "#2A55A8"
FIELD_BG = "#FFFFFF"
FIELD_BORDER = "#E9B9D2"
BTN_BG = "#FBDCEA"
BTN_HOVER = "#F7C9DD"
BTN_PRESS = "#F2B5D0"
BTN_FG = "#B02360"
BTN_DISABLED_FG = "#9C8FA6"
TREE_BG = "#FFFFFF"
TREE_HEAD_BG = "#F8DCEA"
TREE_HEAD_ACTIVE = "#F2CBE0"
TREE_SEL_BG = "#F5BBD8"
HEAD_TOP = "#FBE3EF"
HEAD_BOTTOM = "#E3ECFA"

F_TITLE = ("幼圆", 18)
F_SECTION = ("幼圆", 12)
F_BODY = ("幼圆", 10)
F_SMALL = ("幼圆", 9)


def themes_path():
    """主题原始数据文件的查找顺序：程序(exe/脚本)旁边 -> 打包资源里。"""
    for base in (APP_DIR, RES_DIR):
        path = os.path.join(base, "themes.json")
        if os.path.exists(path):
            return path
    return os.path.join(RES_DIR, "themes.json")


def load_themes():
    """读取主题原始数据，返回 (主题列表, 数据来源说明)。"""
    path = themes_path()
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        themes = []
        for item in data.get("themes", []):
            colors = item.get("colors") or {}
            if item.get("id") and all(k in colors for k in THEME_KEYS):
                themes.append({"id": item["id"],
                               "name": item.get("name", item["id"]),
                               "colors": colors})
        if themes:
            return themes, path
    except Exception:
        pass
    return BUILTIN_THEMES, "内置主题数据(BUILTIN_THEMES)"


def apply_palette(colors):
    """把一份配色写进下面的全局变量；界面各处都读这些变量。"""
    g = globals()
    for key in THEME_KEYS:
        if key in colors:
            g[key] = colors[key]


def _rr_fill(canvas, x1, y1, x2, y2, r, color):
    """在 Canvas 上画一个纯色圆角矩形（两个矩形 + 四个扇形）。"""
    if x2 - x1 < 2 or y2 - y1 < 2:
        return
    r = max(0, min(r, (x2 - x1) / 2, (y2 - y1) / 2))
    d = 2 * r
    canvas.create_rectangle(x1 + r, y1, x2 - r, y2, fill=color, outline=color)
    canvas.create_rectangle(x1, y1 + r, x2, y2 - r, fill=color, outline=color)
    for ax, ay, start in ((x1, y1, 90), (x2 - d, y1, 0),
                          (x1, y2 - d, 180), (x2 - d, y2 - d, 270)):
        canvas.create_arc(ax, ay, ax + d, ay + d, start=start, extent=90,
                          fill=color, outline=color, style="pieslice")


def _round_rect(canvas, x1, y1, x2, y2, r, fill, border):
    _rr_fill(canvas, x1, y1, x2, y2, r, border)
    _rr_fill(canvas, x1 + 1, y1 + 1, x2 - 1, y2 - 1, r - 1, fill)


def _rgb(color):
    return tuple(int(color[i:i + 2], 16) for i in (1, 3, 5))


def _hex(rgb):
    return "#%02X%02X%02X" % tuple(max(0, min(255, int(v))) for v in rgb)


def _corner_inset(i, h, r):
    """圆角矩形第 i 行左右各要内缩多少像素。"""
    if r <= 0:
        return 0
    if i < r:
        dy = r - i - 0.5
    elif i >= h - r:
        dy = i - (h - r) + 0.5
    else:
        return 0
    return int(r - math.sqrt(max(0.0, r * r - dy * dy)))


def _grad_rr(canvas, x1, y1, x2, y2, r, c_top, c_bottom):
    """逐行渐变 + 圆角裁切，画一个可爱的圆角块。"""
    h = int(round(y2 - y1))
    if h <= 0 or x2 <= x1:
        return
    top, bottom = _rgb(c_top), _rgb(c_bottom)
    r = max(0, min(r, (x2 - x1) / 2, h / 2))
    for i in range(h):
        t = i / max(1, h - 1)
        col = _hex([a + (b - a) * t for a, b in zip(top, bottom)])
        inset = _corner_inset(i, h, r)
        canvas.create_line(x1 + inset, y1 + i, x2 - inset, y1 + i, fill=col)


def _chevron(canvas, cx, cy, size, up, color):
    """小箭头（圆头折线），用两条线拼出来。"""
    d = size
    if up:
        canvas.create_line(cx - d, cy + d * 0.5, cx, cy - d * 0.5,
                           cx + d, cy + d * 0.5, fill=color,
                           width=max(2, size * 0.6), capstyle="round", joinstyle="round")
    else:
        canvas.create_line(cx - d, cy - d * 0.5, cx, cy + d * 0.5,
                           cx + d, cy - d * 0.5, fill=color,
                           width=max(2, size * 0.6), capstyle="round", joinstyle="round")


class RoundButton(tk.Canvas):
    """圆润的胶囊按钮（带悬停 / 按下效果）。"""

    def __init__(self, master, text, command=None, width=156, height=58,
                 color=(ACCENT_LIGHT, ACCENT), dark=None, text_color="#FFFFFF"):
        super().__init__(master, width=width, height=height,
                         bg=master["bg"], highlightthickness=0, bd=0)
        self.command = command
        self.text = text
        self.color = color
        self.dark = dark or ACCENT_DARK
        self.text_color = text_color
        self.enabled = True
        self.hover = False
        self.pressed = False
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<Button-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<Configure>", lambda e: self._draw())
        self._draw()

    # 兼容 tk 的 config(state=...) 写法
    def configure(self, **kwargs):
        if "state" in kwargs:
            self.enabled = str(kwargs.pop("state")) != "disabled"
        if "text" in kwargs:
            self.text = kwargs.pop("text")
        if kwargs:
            super().configure(**kwargs)
        self._draw()

    config = configure

    def _shade(self, c, factor):
        r = int(c[1:3], 16)
        g = int(c[3:5], 16)
        b = int(c[5:7], 16)
        return "#%02X%02X%02X" % (min(255, int(r * factor)),
                                  min(255, int(g * factor)),
                                  min(255, int(b * factor)))

    def _draw(self):
        self.delete("all")
        w = int(self["width"])
        h = int(self["height"])
        if not self.enabled:
            top, bottom = "#EFE7EE", "#DCD3DE"
        elif self.pressed:
            top, bottom = self._shade(self.dark, 0.90), self.dark
        elif self.hover:
            top, bottom = self._shade(self.color[0], 1.06), self._shade(self.color[1], 1.06)
        else:
            top, bottom = self.color

        _grad_rr(self, 0, 0, w, h, h / 2, top, bottom)
        self.create_text(w // 2, h // 2, text=self.text, fill=self.text_color,
                         font=("幼圆", 14))

    def _on_enter(self, _e):
        self.hover = True
        self.configure_cursor("hand2")
        self._draw()

    def _on_leave(self, _e):
        self.hover = False
        self.pressed = False
        self._draw()

    def _on_press(self, _e):
        if not self.enabled:
            return
        self.pressed = True
        self._draw()

    def _on_release(self, event):
        if not self.enabled or not self.pressed:
            return
        self.pressed = False
        self._draw()
        if 0 <= event.x <= int(self["width"]) and 0 <= event.y <= int(self["height"]):
            if self.command:
                self.command()

    def configure_cursor(self, name):
        try:
            self.configure(cursor=name)
        except Exception:
            pass


class CuteScrollbar(tk.Canvas):
    """可爱版纵向滚动条：圆角渐变小滑块 + 上下两个小箭头按钮。"""

    ARROW_H = 16
    PAD = 3

    def __init__(self, master, command=None, width=18):
        super().__init__(master, width=width, height=90, bg=master["bg"],
                         highlightthickness=0, bd=0)
        self.command = command
        self.first, self.last = 0.0, 1.0
        self.hover = None
        self.dragging = False
        self.drag_dy = 0
        self.bind("<Configure>", lambda e: self._draw())
        self.bind("<Button-1>", self._on_press)
        self.bind("<B1-Motion>", self._on_drag)
        self.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<Motion>", self._on_motion)
        self.bind("<Leave>", self._on_leave)
        self._draw()

    def set(self, first, last):
        self.first, self.last = float(first), float(last)
        self._draw()

    # ---------------------------------------------------------------- 绘制
    def _thumb_range(self):
        h = self.winfo_height()
        top_y = self.PAD + self.ARROW_H
        bot_y = h - self.PAD - self.ARROW_H
        track = max(10, bot_y - top_y)
        y1 = top_y + track * self.first
        y2 = top_y + track * self.last
        min_h = 26
        if y2 - y1 < min_h:
            y2 = y1 + min_h
            if y2 > bot_y:
                y2 = bot_y
                y1 = max(top_y, y2 - min_h)
        return int(y1), int(y2), top_y, bot_y

    def _draw(self):
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if w < 6 or h < 40:
            return
        _round_rect(self, 2, 2, w - 2, h - 2, (w - 4) / 2, CARD_BG, CARD_BORDER)
        for up, y0, zone in ((True, self.PAD, "up"),
                             (False, h - self.ARROW_H - self.PAD, "down")):
            top = BTN_HOVER if self.hover == zone else BTN_BG
            _grad_rr(self, 3, y0, w - 3, y0 + self.ARROW_H, 7, top, top)
            _chevron(self, w / 2, y0 + self.ARROW_H / 2, 3.2, up, BTN_FG)
        y1, y2, _t, _b = self._thumb_range()
        _grad_rr(self, 3.5, y1, w - 3.5, y2, (w - 7) / 2, ACCENT_LIGHT, ACCENT)
        self.create_line(w / 2, y1 + 6, w / 2, y2 - 6, fill="#FFFFFF", width=1)

    # ---------------------------------------------------------------- 交互
    def _zone(self, y):
        h = self.winfo_height()
        if y < self.PAD + self.ARROW_H:
            return "up"
        if y > h - self.PAD - self.ARROW_H:
            return "down"
        return "thumb"

    def _on_motion(self, event):
        zone = self._zone(event.y)
        if zone != self.hover:
            self.hover = zone
            self._draw()

    def _on_leave(self, _e):
        self.hover = None
        self._draw()

    def _on_press(self, event):
        if self.command is None:
            return
        zone = self._zone(event.y)
        y1, y2, _t, _b = self._thumb_range()
        if zone == "up":
            self.command("scroll", -1, "units")
        elif zone == "down":
            self.command("scroll", 1, "units")
        elif y1 <= event.y <= y2:
            self.dragging = True
            self.drag_dy = event.y - y1
        else:
            self.command("scroll", -1 if event.y < y1 else 1, "pages")

    def _on_drag(self, event):
        if not self.dragging or self.command is None:
            return
        y1, y2, top_y, bot_y = self._thumb_range()
        thumb_h = max(1, y2 - y1)
        track = max(1, bot_y - top_y - thumb_h)
        frac = (event.y - self.drag_dy - top_y) / track
        self.command("moveto", str(min(1.0, max(0.0, frac))))

    def _on_release(self, _e):
        self.dragging = False


class CuteSpin(tk.Frame):
    """可爱版数字调节框：白底输入框 + 右侧两个圆润的上下小按钮。"""

    def __init__(self, master, width=6, value=100, minimum=1, maximum=600000, step=1):
        super().__init__(master, bg=master["bg"])
        self.minimum, self.maximum, self.step = minimum, maximum, step
        self.var = tk.StringVar(value=str(value))
        self.entry = tk.Entry(self, textvariable=self.var, width=width, justify="center",
                              relief="flat", font=F_BODY, bg=FIELD_BG, fg=TEXT_FG,
                              insertbackground=TITLE_FG, highlightthickness=1,
                              highlightbackground=FIELD_BORDER, highlightcolor=ACCENT)
        self.entry.pack(side="left", ipady=4, padx=(0, 5))
        self.arrows = tk.Canvas(self, width=20, height=28, bg=master["bg"],
                                highlightthickness=0, bd=0)
        self.arrows.pack(side="left")
        self.arrows.bind("<Button-1>", self._on_click)
        self.arrows.bind("<Motion>", self._on_motion)
        self.arrows.bind("<Leave>", self._on_leave)
        self._hover = None
        self._draw()

    def get(self):
        return self.var.get()

    def set(self, value):
        self.var.set(str(value))

    def _draw(self):
        c = self.arrows
        c.delete("all")
        w, h = int(c["width"]), int(c["height"])
        half = h // 2
        for up, y0, zone in ((True, 0, "up"), (False, half, "down")):
            color = BTN_HOVER if self._hover == zone else BTN_BG
            _grad_rr(c, 0, y0 + 1, w, y0 + half - 1, 6, color, color)
            _chevron(c, w / 2, y0 + half / 2, 3.0, up, BTN_FG)

    def _on_motion(self, event):
        zone = "up" if event.y < int(self.arrows["height"]) // 2 else "down"
        if zone != self._hover:
            self._hover = zone
            self._draw()

    def _on_leave(self, _e):
        self._hover = None
        self._draw()

    def _on_click(self, event):
        half = int(self.arrows["height"]) // 2
        self._nudge(self.step if event.y < half else -self.step)

    def _nudge(self, delta):
        try:
            value = int(float(self.var.get()))
        except ValueError:
            value = self.minimum
        value = max(self.minimum, min(self.maximum, value + delta))
        self.var.set(str(value))

DEFAULTS = {
    "steps": [{"key": DEFAULT_KEY_LABEL, "interval_ms": 100}],
    "hold_ms": 20,
    "start_hotkey": "F8",
    "stop_hotkey": "F9",
    "voice": DEFAULT_VOICE,
    "theme": DEFAULT_THEME_ID,
    "scope": "global",
    "target_pid": 0,
    "target_name": "",
}


class App:
    def __init__(self, root):
        self.root = root
        self.root.title("%s v%s" % (APP_TITLE, __version__))
        self.root.resizable(False, False)
        self._set_icon()

        self.cfg = dict(DEFAULTS)
        self.load_settings()

        # 主题数据来源：themes.json（找不到就用内置 BUILTIN_THEMES）
        self.themes, self.themes_source = load_themes()
        self.theme_id = self.cfg.get("theme", DEFAULT_THEME_ID)
        apply_palette(self.current_theme()["colors"])

        self.running = False
        self.stop_event = threading.Event()
        self.sender_thread = None
        self.hotkey_thread = None
        self.events = queue.Queue()

        self.window_map = []
        self.voice_entries = []
        self.steps = []
        self.start_hotkey = (0, None)
        self.stop_hotkey = (0, None)

        self._build_ui()
        self._apply_settings_to_ui()
        self._load_voice_list()
        self.refresh_windows()
        self.register_hotkeys()
        self.prepare_system_voice()

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.after(50, self.pump_events)

    def _set_icon(self):
        if os.path.exists(ICON_ICO):
            try:
                self.root.iconbitmap(default=ICON_ICO)
            except Exception:
                pass

    # ------------------------------------------------------------------ 界面
    def current_theme(self):
        for theme in self.themes:
            if theme["id"] == self.theme_id:
                return theme
        return self.themes[0]

    def apply_theme(self, theme_id):
        """切换主题：写入配色 -> 刷新控件样式 -> 重建界面。"""
        self.theme_id = theme_id
        self.cfg["theme"] = theme_id
        self.save_settings()
        apply_palette(self.current_theme()["colors"])
        self._apply_theme()
        self._rebuild_ui()

    def _rebuild_ui(self):
        for child in self.root.winfo_children():
            child.destroy()
        self.root.configure(bg=APP_BG)
        self._build_ui()
        self._apply_settings_to_ui()
        self._load_voice_list()
        self.refresh_windows()
        self.set_hint("主题已切换为「%s」。主题数据来源：%s"
                      % (self.current_theme()["name"], self.themes_source))

    def _apply_theme(self):
        """二次元风格：淡粉底 + 圆角白卡片 + 幼圆字体。"""
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure(".", font=F_BODY, background=CARD_BG, foreground=TEXT_FG)
        style.configure("TLabel", font=F_BODY, background=CARD_BG, foreground=TEXT_FG)
        style.configure("Hint.TLabel", font=F_SMALL, background=CARD_BG, foreground=HINT_FG)
        style.configure("AppHint.TLabel", font=F_SMALL, background=APP_BG, foreground=HINT_FG)
        style.configure("TRadiobutton", font=F_BODY, background=CARD_BG, foreground=TEXT_FG)
        style.map("TRadiobutton", background=[("active", CARD_BG)])
        style.configure("TCheckbutton", font=F_BODY, background=CARD_BG, foreground=TEXT_FG)
        style.map("TCheckbutton", background=[("active", CARD_BG)])
        style.configure("TButton", font=F_BODY, padding=(10, 5),
                        background=BTN_BG, foreground=BTN_FG,
                        borderwidth=0, focusthickness=0)
        style.map("TButton",
                  background=[("active", BTN_HOVER), ("pressed", BTN_PRESS)],
                  foreground=[("disabled", BTN_DISABLED_FG)])
        style.configure("Theme.TMenubutton", font=F_BODY, padding=(12, 5),
                        background=BTN_BG, foreground=BTN_FG,
                        borderwidth=0, relief="flat", arrowcolor=TITLE_FG)
        style.map("Theme.TMenubutton",
                  background=[("active", BTN_HOVER), ("pressed", BTN_PRESS)],
                  foreground=[("disabled", BTN_DISABLED_FG)])
        style.configure("TEntry", padding=4, fieldbackground=FIELD_BG,
                        foreground=TEXT_FG, bordercolor=FIELD_BORDER,
                        lightcolor=FIELD_BORDER, darkcolor=FIELD_BORDER,
                        insertcolor=TITLE_FG)
        style.configure("TCombobox", padding=4, fieldbackground=FIELD_BG,
                        background=FIELD_BG, foreground=TEXT_FG,
                        bordercolor=FIELD_BORDER, arrowcolor=ACCENT)
        style.map("TCombobox",
                  fieldbackground=[("readonly", FIELD_BG)],
                  background=[("readonly", FIELD_BG), ("active", BTN_HOVER)],
                  foreground=[("readonly", TEXT_FG)],
                  arrowcolor=[("active", TITLE_FG)])
        style.configure("TSpinbox", padding=4, fieldbackground=FIELD_BG,
                        foreground=TEXT_FG, bordercolor=FIELD_BORDER,
                        arrowcolor=ACCENT)
        style.configure("Treeview", font=F_BODY, rowheight=28,
                        background=TREE_BG, fieldbackground=TREE_BG,
                        foreground=TEXT_FG, bordercolor=CARD_BORDER)
        style.map("Treeview", background=[("selected", TREE_SEL_BG)],
                  foreground=[("selected", TEXT_FG)])
        style.configure("Treeview.Heading", font=F_SECTION, background=TREE_HEAD_BG,
                        foreground=TITLE_FG, relief="flat", padding=(4, 4))
        style.map("Treeview.Heading", background=[("active", TREE_HEAD_ACTIVE)])
        style.configure("Vertical.TScrollbar", background=BTN_BG,
                        troughcolor=APP_BG, bordercolor=APP_BG, arrowcolor=ACCENT)

        # 下拉列表 / 右键菜单也要跟着主题走，否则暗色主题下会白底白字
        self.root.option_add("*Menu.background", CARD_BG)
        self.root.option_add("*Menu.foreground", TEXT_FG)
        self.root.option_add("*Menu.activeBackground", BTN_HOVER)
        self.root.option_add("*Menu.activeForeground", BTN_FG)
        self.root.option_add("*TCombobox*Listbox.background", FIELD_BG)
        self.root.option_add("*TCombobox*Listbox.foreground", TEXT_FG)
        self.root.option_add("*TCombobox*Listbox.selectBackground", ACCENT)
        self.root.option_add("*TCombobox*Listbox.selectForeground", "#FFFFFF")

    def _build_header(self):
        """顶部横幅：渐层背景 + 吉祥物 + 标题（整个用 Canvas 画，可随窗口缩放）。"""
        holder = tk.Frame(self.root, bg=APP_BG)
        holder.grid(row=0, column=0, columnspan=2, sticky="ew", padx=12, pady=(12, 6))
        canvas = tk.Canvas(holder, bg=APP_BG, highlightthickness=0, bd=0, height=104)
        canvas.pack(fill="x")

        mascot_png = os.path.join(RES_DIR, "assets", "mascot.png")
        self._mascot_img = None
        if os.path.exists(mascot_png):
            try:
                self._mascot_img = tk.PhotoImage(file=mascot_png).subsample(3)
            except Exception:
                self._mascot_img = None

        def draw(_event=None):
            canvas.delete("all")
            w = canvas.winfo_width()
            h = canvas.winfo_height()
            if w < 10:
                return
            top = tuple(int(HEAD_TOP[i:i + 2], 16) for i in (1, 3, 5))
            bottom = tuple(int(HEAD_BOTTOM[i:i + 2], 16) for i in (1, 3, 5))
            for y in range(h):
                t = y / max(1, h - 1)
                col = "#%02X%02X%02X" % tuple(int(a + (b - a) * t)
                                              for a, b in zip(top, bottom))
                canvas.create_line(0, y, w, y, fill=col)
            for (sx, sy, sr) in ((w - 60, 26, 9), (w - 130, 78, 6), (w - 22, 84, 5)):
                canvas.create_polygon(sx, sy - sr, sx + sr * 0.26, sy - sr * 0.26,
                                      sx + sr, sy, sx + sr * 0.26, sy + sr * 0.26,
                                      sx, sy + sr, sx - sr * 0.26, sy + sr * 0.26,
                                      sx - sr, sy, sx - sr * 0.26, sy - sr * 0.26,
                                      fill="#FFFFFF", outline="")
            if self._mascot_img is not None:
                canvas.create_image(16, h // 2, anchor="w", image=self._mascot_img)
            canvas.create_text(122, h // 2 - 14, anchor="w", text=APP_TITLE,
                               fill=TITLE_FG, font=F_TITLE)
            canvas.create_text(124, h // 2 + 16, anchor="w",
                               text="自动重复按键 · 多个按键顺序执行 · 全局热键控制"
                                    " · v%s" % __version__,
                               fill=HINT_FG, font=F_SMALL)

        canvas.bind("<Configure>", draw)

        # 右上角：主题切换按钮（主题数据来自 themes.json）
        self.theme_btn = ttk.Menubutton(
            holder, text="主题：%s" % self.current_theme()["name"],
            style="Theme.TMenubutton")
        menu = tk.Menu(self.theme_btn, tearoff=0)
        for theme in self.themes:
            menu.add_command(label=theme["name"],
                             command=lambda tid=theme["id"]: self.apply_theme(tid))
        menu.add_separator()
        menu.add_command(label="数据来源：themes.json", state="disabled")
        self.theme_btn["menu"] = menu
        self.theme_btn.place(relx=1.0, x=-16, y=18, anchor="ne")
        return 1

    def _make_card(self, title, row, column, rowspan=1, columnspan=1,
                   padx=0, pady=0, sticky="nsew"):
        """在圆角白卡片里放内容，返回内容容器。"""
        holder = tk.Frame(self.root, bg=APP_BG)
        holder.grid(row=row, column=column, rowspan=rowspan, columnspan=columnspan,
                    sticky=sticky, padx=padx, pady=pady)

        canvas = tk.Canvas(holder, bg=APP_BG, highlightthickness=0, bd=0)
        canvas.place(x=0, y=0, relwidth=1, relheight=1)

        body = tk.Frame(holder, bg=CARD_BG)
        body.grid(row=0, column=0, sticky="nsew", padx=14, pady=(36, 14))
        holder.grid_rowconfigure(0, weight=1)
        holder.grid_columnconfigure(0, weight=1)

        def redraw(_event=None):
            w, h = holder.winfo_width(), holder.winfo_height()
            if w < 10 or h < 10:
                return
            canvas.delete("all")
            _round_rect(canvas, 1, 1, w - 1, h - 1, 18, CARD_BG, CARD_BORDER)
            if title:
                canvas.create_text(20, 12, anchor="nw", text="❀ " + title,
                                   fill=TITLE_FG, font=F_SECTION)

        holder.bind("<Configure>", redraw)
        return body, holder

    def _build_ui(self):
        self._apply_theme()
        self.root.configure(bg=APP_BG)
        self.root.columnconfigure(0, weight=3, minsize=470)
        self.root.columnconfigure(1, weight=2, minsize=350)
        pad = {"padx": 8, "pady": 4}
        row = self._build_header()

        box_seq, _ = self._make_card("按键序列（按顺序循环执行）", row, 0, rowspan=3,
                                     padx=(12, 6), pady=6)

        ttk.Label(box_seq, text="按键：").grid(row=0, column=0, sticky="w", **pad)
        self.combo_key = ttk.Combobox(box_seq, width=12, state="readonly", values=KEY_LABELS)
        self.combo_key.grid(row=0, column=1, sticky="w", **pad)
        self.combo_key.set(DEFAULT_KEY_LABEL)

        ttk.Label(box_seq, text="该步间隔(毫秒)：").grid(row=0, column=2, sticky="e", **pad)
        self.spin_step_interval = CuteSpin(box_seq, width=6, value=100,
                                           minimum=1, maximum=600000)
        self.spin_step_interval.grid(row=0, column=3, sticky="w", **pad)

        ttk.Button(box_seq, text="添加到序列", width=12,
                   command=self.add_step).grid(row=0, column=4, **pad)
        ttk.Label(box_seq, text="（只放一个就是单键重复）",
                  foreground=HINT_FG).grid(row=0, column=5, sticky="w", **pad)

        tree_wrap = tk.Frame(box_seq, bg=CARD_BG)
        tree_wrap.grid(row=1, column=0, columnspan=6, sticky="ew", padx=8, pady=2)
        self.tree = ttk.Treeview(tree_wrap, columns=("no", "key", "interval"),
                                 show="headings", height=9, selectmode="browse")
        for col, text, width in (("no", "#", 40), ("key", "按键", 120),
                                 ("interval", "间隔(毫秒)", 96)):
            self.tree.heading(col, text=text)
            self.tree.column(col, width=width, anchor="center")
        self.tree.pack(side="left", fill="both", expand=True)
        scroller = CuteScrollbar(tree_wrap, command=self.tree.yview, width=18)
        scroller.pack(side="right", fill="y")
        self.tree.configure(yscrollcommand=scroller.set)
        self.tree.bind("<Double-1>", self.on_step_double_click)

        bar = tk.Frame(box_seq, bg=CARD_BG)
        bar.grid(row=2, column=0, columnspan=6, sticky="w", padx=8, pady=(0, 4))
        ttk.Button(bar, text="删除选中", width=10,
                   command=self.remove_step).grid(row=0, column=0, padx=(0, 6))
        ttk.Button(bar, text="上移", width=6,
                   command=lambda: self.move_step(-1)).grid(row=0, column=1, padx=(0, 6))
        ttk.Button(bar, text="下移", width=6,
                   command=lambda: self.move_step(1)).grid(row=0, column=2, padx=(0, 16))

        ttk.Label(bar, text="每次按住(毫秒)：").grid(row=0, column=3)
        self.spin_hold = CuteSpin(bar, width=5, value=20, minimum=1, maximum=5000)
        self.spin_hold.grid(row=0, column=4, padx=(4, 6))
        ttk.Label(bar, text="（双击某一行可改它的间隔）",
                  foreground=HINT_FG).grid(row=0, column=5)

        box_voice, _ = self._make_card("声音提示", row, 1, sticky="new",
                                       padx=(6, 12), pady=6)

        ttk.Label(box_voice, text="声音：").grid(row=0, column=0, sticky="w", **pad)
        self.combo_voice = ttk.Combobox(box_voice, width=22, state="readonly")
        self.combo_voice.grid(row=0, column=1, **pad)
        self.combo_voice.bind("<<ComboboxSelected>>", self.on_voice_change)

        ttk.Button(box_voice, text="试听", width=8,
                   command=self.audition_voice).grid(row=0, column=2, **pad)
        ttk.Button(box_voice, text="自定义语音…", width=13,
                   command=self.open_custom_dialog).grid(row=0, column=3, **pad)

        ttk.Button(box_voice, text="刷新语音列表", width=13,
                   command=self.refresh_voice_list).grid(row=1, column=2, **pad)
        ttk.Button(box_voice, text="获取更多系统语音…", width=18,
                   command=self.open_speech_settings).grid(row=1, column=3, **pad)
        ttk.Label(box_voice,
                  text="（开始/停止时各播一次声音：可选内置提示音、自己导入或录制的声音，"
                       "或用系统语音朗读「%s / %s」）" % (PHRASE_START, PHRASE_STOP),
                  foreground=HINT_FG, wraplength=320, justify="left").grid(
                      row=2, column=0, columnspan=4, sticky="w", **pad)

        box_scope, _ = self._make_card("作用范围", row + 1, 1, sticky="new",
                                       padx=(6, 12), pady=6)

        self.var_scope = tk.StringVar(value="global")
        ttk.Radiobutton(box_scope, text="全局 —— 任何窗口都一直按",
                        variable=self.var_scope, value="global",
                        command=self.on_scope_change).grid(row=0, column=0, columnspan=3,
                                                           sticky="w", **pad)
        ttk.Radiobutton(box_scope, text="只在指定程序里按",
                        variable=self.var_scope, value="app",
                        command=self.on_scope_change).grid(row=1, column=0, sticky="w", **pad)
        self.combo_target = ttk.Combobox(box_scope, width=26, state="readonly")
        self.combo_target.grid(row=1, column=1, **pad)
        self.combo_target.bind("<<ComboboxSelected>>", self.on_target_change)

        self.btn_refresh = ttk.Button(box_scope, text="刷新列表", width=10,
                                      command=self.refresh_windows)
        self.btn_refresh.grid(row=1, column=2, **pad)
        self.btn_front = ttk.Button(box_scope, text="把目标窗口调到最前", width=20,
                                    command=self.bring_target_front)
        self.btn_front.grid(row=2, column=1, sticky="w", **pad)
        ttk.Label(box_scope, text="（选了指定程序后，只有当它在最前面时才会按键）",
                  foreground=HINT_FG, wraplength=330, justify="left").grid(
                      row=3, column=0, columnspan=3, sticky="w", **pad)

        box_hotkey, _ = self._make_card("全局热键（任何窗口下都有效）", row + 2, 1,
                                        sticky="new", padx=(6, 12), pady=6)

        ttk.Label(box_hotkey, text="开始：").grid(row=0, column=0, sticky="e", **pad)
        self.entry_start_hk = ttk.Entry(box_hotkey, width=14, justify="center")
        self.entry_start_hk.grid(row=0, column=1, **pad)
        self.entry_start_hk.bind("<KeyPress>", lambda e: self.on_capture_hotkey(e, "start"))

        ttk.Label(box_hotkey, text="停止：").grid(row=0, column=2, sticky="e", **pad)
        self.entry_stop_hk = ttk.Entry(box_hotkey, width=14, justify="center")
        self.entry_stop_hk.grid(row=0, column=3, **pad)
        self.entry_stop_hk.bind("<KeyPress>", lambda e: self.on_capture_hotkey(e, "stop"))

        ttk.Button(box_hotkey, text="应用热键", width=12,
                   command=self.on_apply_hotkeys).grid(row=0, column=4, **pad)

        self.var_manual = tk.BooleanVar(value=False)
        ttk.Checkbutton(box_hotkey, text="手动输入热键文字",
                        variable=self.var_manual).grid(row=1, column=4, sticky="w", **pad)
        ttk.Label(box_hotkey,
                  text="（点框后按新键；要用 Alt 组合键就勾上「手动输入」再打字）",
                  foreground=HINT_FG, wraplength=330, justify="left").grid(
                      row=2, column=0, columnspan=5, sticky="w", **pad)

        box_run = tk.Frame(self.root, bg=APP_BG)
        box_run.grid(row=row + 3, column=0, columnspan=2, sticky="ew", padx=12, pady=(10, 4))
        # 左右各留一份弹性空间，让"开始 / 停止"正好居中；状态显示贴右边
        box_run.grid_columnconfigure(0, weight=1)
        box_run.grid_columnconfigure(1, weight=0)
        box_run.grid_columnconfigure(2, weight=1)

        btn_box = tk.Frame(box_run, bg=APP_BG)
        btn_box.grid(row=0, column=1)

        self.btn_start = RoundButton(btn_box, "开 始", self.start_pressing,
                                     width=160, height=56,
                                     color=(ACCENT_LIGHT, ACCENT), dark=ACCENT_DARK)
        self.btn_start.grid(row=0, column=0, padx=(0, 12))

        self.btn_stop = RoundButton(btn_box, "停 止", self.stop_pressing,
                                    width=160, height=56,
                                    color=(BUBBLE_LIGHT, BUBBLE), dark=BUBBLE_DARK)
        self.btn_stop.grid(row=0, column=1)

        self.lbl_status = tk.Label(box_run, text="已停止", fg=TITLE_FG, bg=APP_BG,
                                   font=("幼圆", 13))
        self.lbl_status.grid(row=0, column=2, sticky="e", padx=(16, 6))

        self.lbl_hint = ttk.Label(self.root, text="", style="AppHint.TLabel",
                                  wraplength=840, justify="left")
        self.lbl_hint.grid(row=row + 4, column=0, columnspan=2, sticky="w",
                           padx=14, pady=(0, 10))

        self.set_hint("提示：开始和停止都会播放提示音，可以在上面换成自己的声音。"
                      "关闭本窗口也会停止。")

    def set_hint(self, text):
        self.lbl_hint.config(text=text)

    # -------------------------------------------------------------- 设置读写
    def load_settings(self):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            for key in DEFAULTS:
                if key in data:
                    self.cfg[key] = data[key]
            # 兼容老版本的"单个按键"设置
            if "steps" not in data and "key_label" in data:
                self.cfg["steps"] = [{"key": data["key_label"],
                                      "interval_ms": int(data.get("interval_ms", 100))}]
        except Exception:
            pass

    def save_settings(self):
        if self.steps:
            self.cfg["steps"] = [dict(s) for s in self.steps]
        try:
            os.makedirs(DATA_DIR, exist_ok=True)
            with open(SETTINGS_FILE, "w", encoding="utf-8") as fh:
                json.dump(self.cfg, fh, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _apply_settings_to_ui(self):
        self.steps = []
        for step in self.cfg.get("steps") or DEFAULTS["steps"]:
            key = step.get("key", DEFAULT_KEY_LABEL)
            if key not in KEY_VK:
                key = DEFAULT_KEY_LABEL
            try:
                interval = max(1, int(step.get("interval_ms", 100)))
            except Exception:
                interval = 100
            self.steps.append({"key": key, "interval_ms": interval})
        if not self.steps:
            self.steps = [{"key": DEFAULT_KEY_LABEL, "interval_ms": 100}]
        self.refresh_steps()

        self.combo_key.set(self.steps[0]["key"])
        self.spin_step_interval.set(str(self.steps[0]["interval_ms"]))
        self.spin_hold.set(str(self.cfg.get("hold_ms", 20)))
        self.entry_start_hk.insert(0, self.cfg.get("start_hotkey", "F8"))
        self.entry_stop_hk.insert(0, self.cfg.get("stop_hotkey", "F9"))
        self.var_scope.set(self.cfg.get("scope", "global"))
        self.on_scope_change()

    # -------------------------------------------------------------- 按键序列
    def refresh_steps(self):
        self.tree.delete(*self.tree.get_children())
        for i, step in enumerate(self.steps, start=1):
            self.tree.insert("", "end", iid=str(i),
                             values=(i, step["key"], step["interval_ms"]))

    def selected_step_index(self):
        selection = self.tree.selection()
        if not selection:
            return None
        try:
            return int(selection[0]) - 1
        except ValueError:
            return None

    def add_step(self):
        label = self.combo_key.get()
        if label not in KEY_VK:
            self.set_hint("请先从下拉框里选一个键。")
            return
        try:
            interval = max(1, int(float(self.spin_step_interval.get())))
        except ValueError:
            interval = 100
        self.steps.append({"key": label, "interval_ms": interval})
        self.refresh_steps()
        self.tree.selection_set(str(len(self.steps)))
        self.tree.see(str(len(self.steps)))
        self.save_settings()
        self.set_hint("已添加第 %d 步：%s，间隔 %d 毫秒。" % (len(self.steps), label, interval))

    def remove_step(self):
        index = self.selected_step_index()
        if index is None:
            self.set_hint("请先在列表里选中一行。")
            return
        if len(self.steps) <= 1:
            self.set_hint("至少要保留一个按键。")
            return
        removed = self.steps.pop(index)
        self.refresh_steps()
        self.save_settings()
        self.set_hint("已删除：%s。" % removed["key"])

    def move_step(self, delta):
        index = self.selected_step_index()
        if index is None:
            self.set_hint("请先在列表里选中一行。")
            return
        target = index + delta
        if target < 0 or target >= len(self.steps):
            return
        self.steps[index], self.steps[target] = self.steps[target], self.steps[index]
        self.refresh_steps()
        self.save_settings()
        self.tree.selection_set(str(target + 1))

    def on_step_double_click(self, _event=None):
        index = self.selected_step_index()
        if index is None:
            return
        step = self.steps[index]
        value = simpledialog.askinteger(
            "修改间隔",
            "「%s」这一步按完之后等多少毫秒？" % step["key"],
            parent=self.root, initialvalue=step["interval_ms"],
            minvalue=1, maxvalue=600000)
        if value:
            step["interval_ms"] = int(value)
            self.refresh_steps()
            self.save_settings()

    # ---------------------------------------------------------- 热键输入捕获
    def on_capture_hotkey(self, event, which):
        if self.var_manual.get():
            return None
        keysym = event.keysym
        if keysym in MODIFIER_KEYSYMS:
            self.set_hint("热键不能只由 Ctrl/Shift/Alt 组成，请再加上一个普通键。")
            return "break"
        vk = keysym_to_vk(keysym)
        if vk is None:
            self.set_hint("这个键不能做热键，换一个。")
            return "break"

        mods = 0
        if event.state & 0x0004:
            mods |= MOD_CONTROL
        if event.state & 0x0001:
            mods |= MOD_SHIFT
        if event.state & 0x0008 or keysym in ("Alt_L", "Alt_R"):
            mods |= MOD_ALT

        name = self.hotkey_text(mods, keysym)
        widget = self.entry_start_hk if which == "start" else self.entry_stop_hk
        widget.delete(0, "end")
        widget.insert(0, name)
        self.set_hint("热键已改为 %s，记得点右边「应用热键」。" % name)
        return "break"

    @staticmethod
    def hotkey_text(mods, keysym):
        parts = []
        if mods & MOD_CONTROL:
            parts.append("Ctrl")
        if mods & MOD_SHIFT:
            parts.append("Shift")
        if mods & MOD_ALT:
            parts.append("Alt")
        parts.append(key_display(keysym))
        return "+".join(parts)

    @staticmethod
    def parse_hotkey(text):
        mods = 0
        vk = None
        for part in [p for p in text.split("+") if p.strip()]:
            low = part.strip().lower()
            if low in ("ctrl", "control"):
                mods |= MOD_CONTROL
            elif low == "shift":
                mods |= MOD_SHIFT
            elif low == "alt":
                mods |= MOD_ALT
            elif low == "win":
                mods |= MOD_WIN
            else:
                found = keysym_to_vk(low)
                if found is None and len(part.strip()) == 1:
                    found = keysym_to_vk(part.strip())
                if found is not None:
                    vk = found
        return (mods, vk)

    def register_hotkeys(self):
        self.unregister_hotkeys()
        ms, mv = self.parse_hotkey(self.entry_start_hk.get())
        ts, tv = self.parse_hotkey(self.entry_stop_hk.get())
        if mv is None or tv is None:
            self.set_hint("热键看不懂，请重新设置开始 / 停止热键。")
            return
        if (ms, mv) == (ts, tv):
            self.set_hint("开始和停止不能用同一个热键，请改一个。")
            return

        self.start_hotkey = (ms, mv)
        self.stop_hotkey = (ts, tv)
        self.cfg["start_hotkey"] = self.entry_start_hk.get().strip()
        self.cfg["stop_hotkey"] = self.entry_stop_hk.get().strip()
        self.save_settings()
        self.hotkey_thread = HotkeyThread({1: self.start_hotkey, 2: self.stop_hotkey}, self.events)
        self.hotkey_thread.start()

    def unregister_hotkeys(self):
        if self.hotkey_thread is not None:
            self.hotkey_thread.stop()
            self.hotkey_thread = None

    def on_apply_hotkeys(self):
        self.register_hotkeys()
        self.set_hint("热键已应用：开始 = %s，停止 = %s。"
                      % (self.cfg.get("start_hotkey"), self.cfg.get("stop_hotkey")))

    # ------------------------------------------------------------ 窗口 / 范围
    def refresh_windows(self):
        self.window_map = list_windows()
        items = []
        for i, (_hwnd, pid, title, exe) in enumerate(self.window_map):
            name = exe if exe else ("pid %d" % pid)
            short = title if len(title) <= 38 else title[:38] + "…"
            items.append("%02d  %s  |  %s" % (i + 1, name, short))
        self.combo_target["values"] = items
        want_pid = self.cfg.get("target_pid", 0)
        if want_pid:
            for i, (_hwnd, pid, _title, _exe) in enumerate(self.window_map):
                if pid == want_pid:
                    self.combo_target.current(i)
                    break

    def on_target_change(self, _event=None):
        idx = self.combo_target.current()
        if idx < 0 or idx >= len(self.window_map):
            return
        _hwnd, pid, title, exe = self.window_map[idx]
        self.cfg["target_pid"] = pid
        self.cfg["target_name"] = "%s | %s" % (exe, title)
        self.save_settings()
        self.set_hint("已选择目标程序：%s" % self.cfg["target_name"])

    def on_scope_change(self):
        scope = self.var_scope.get()
        self.cfg["scope"] = scope
        state = "readonly" if scope == "app" else "disabled"
        self.combo_target.config(state=state)
        self.btn_refresh.config(state=("normal" if scope == "app" else "disabled"))
        self.btn_front.config(state=("normal" if scope == "app" else "disabled"))
        self.save_settings()

    def bring_target_front(self):
        idx = self.combo_target.current()
        if idx < 0 or idx >= len(self.window_map):
            self.set_hint("请先在下拉框里选一个程序。")
            return
        user32.SetForegroundWindow(self.window_map[idx][0])

    # ------------------------------------------------------------- 声音提示
    def _load_voice_list(self):
        self.voice_entries = [(label, "builtin", style) for label, style in SOUND_STYLES]
        self.voice_entries.append((VOICE_CUSTOM, "custom", ""))
        for name, _lang in list_system_voices():
            self.voice_entries.append((name + "（系统语音）", "system", name))

        names = [entry[0] for entry in self.voice_entries]
        self.combo_voice["values"] = names
        want = self.cfg.get("voice", "")
        if want not in names:
            want = DEFAULT_VOICE
        self.combo_voice.set(want)
        self.cfg["voice"] = want
        self.save_settings()

    def resolve_current_voice(self):
        label = self.combo_voice.get() or DEFAULT_VOICE
        for entry_label, kind, value in self.voice_entries:
            if entry_label == label:
                return kind, value
        return "builtin", SOUND_STYLES[0][1]

    def voice_files(self, text):
        kind, value = self.resolve_current_voice()
        if kind == "builtin":
            name = "%s_start.wav" % value if text == PHRASE_START else "%s_stop.wav" % value
            return kind, os.path.join(SOUNDS_DIR, name)
        if kind == "custom":
            return kind, custom_voice_files()[0 if text == PHRASE_START else 1]
        if kind == "system":
            return kind, wav_cache_path(text, value)
        return kind, ""

    def on_voice_change(self, _event=None):
        self.cfg["voice"] = self.combo_voice.get()
        self.save_settings()
        self.prepare_system_voice()
        self.set_hint("声音已换成「%s」。可以点「试听」听听。" % self.cfg["voice"])

    def refresh_voice_list(self):
        self._load_voice_list()
        self.set_hint("语音列表已刷新，共 %d 个可选声音。" % len(self.voice_entries))

    def open_speech_settings(self):
        try:
            os.startfile("ms-settings:speech")
        except Exception:
            try:
                subprocess.Popen(["cmd", "/c", "start", "", "ms-settings:speech"],
                                 creationflags=CREATE_NO_WINDOW)
            except Exception:
                pass
        self.set_hint("已打开 Windows 的语音设置：在那里可以添加更多系统语音，"
                      "装好后回来点「刷新语音列表」。")

    def prepare_system_voice(self):
        """系统语音需要先合成；自定义语音需要先录好。"""
        kind, value = self.resolve_current_voice()
        if kind == "system":
            def _work():
                ok = True
                for text in (PHRASE_START, PHRASE_STOP):
                    path = wav_cache_path(text, value)
                    if not wav_exists(path) and not synth_to_wav(text, value, path):
                        ok = False
                self.events.put(("voice_ready" if ok else "voice_failed", value))
            threading.Thread(target=_work, daemon=True).start()
        elif kind == "custom" and not custom_voice_ready():
            self.set_hint("「自定义语音」还没准备好，点「自定义语音…」导入或录一段吧。")

    def open_custom_dialog(self):
        CustomVoiceDialog(self.root, on_saved=self._on_custom_saved)

    def _on_custom_saved(self):
        self.cfg["voice"] = VOICE_CUSTOM
        self.save_settings()
        if VOICE_CUSTOM in self.combo_voice["values"]:
            self.combo_voice.set(VOICE_CUSTOM)
        self.set_hint("自定义语音已保存。点「试听」听听效果。")

    def audition_voice(self):
        _kind, path = self.voice_files(PHRASE_START)
        if wav_exists(path):
            play_wav(path)
            return
        kind, value = self.resolve_current_voice()
        if kind == "custom":
            self.set_hint("还没有自定义语音，点「自定义语音…」导入或录一段吧。")
        elif kind == "system":
            self.set_hint("正在合成语音，请稍等一下再点「试听」。")
            def _work():
                if synth_to_wav(PHRASE_START, value, path):
                    play_wav(path)
                    self.events.put(("voice_ready", value))
                else:
                    self.events.put(("voice_failed", value))
            threading.Thread(target=_work, daemon=True).start()

    def announce(self, text):
        _kind, path = self.voice_files(text)
        if wav_exists(path):
            try:
                play_wav(path)
                return
            except Exception:
                pass

    # ----------------------------------------------------------- 开始 / 停止
    def start_pressing(self):
        if self.running:
            return

        if not self.steps:
            self.set_hint("按键序列是空的，请先添加至少一个按键。")
            return
        try:
            hold = max(1, int(float(self.spin_hold.get())))
        except ValueError:
            self.set_hint("「每次按住」要填数字（毫秒）。")
            return

        plan = []
        for step in self.steps:
            vk = key_label_to_vk(step["key"])
            if vk is None:
                self.set_hint("序列里的「%s」不认识，请重新添加。" % step["key"])
                return
            plan.append((vk, max(1, int(step["interval_ms"]))))

        target_pid = None
        if self.var_scope.get() == "app":
            idx = self.combo_target.current()
            if idx < 0 or idx >= len(self.window_map):
                self.set_hint("你选了「只在指定程序里按」，但还没选程序。")
                return
            target_pid = self.window_map[idx][1]
            self.cfg["target_pid"] = target_pid
            self.cfg["target_name"] = "%s | %s" % (self.window_map[idx][3], self.window_map[idx][2])

        self.cfg["hold_ms"] = hold
        self.save_settings()

        self.running = True
        self.stop_event.clear()
        self.sender_thread = threading.Thread(
            target=self._sender_loop, args=(plan, hold, target_pid), daemon=True)
        self.sender_thread.start()

        self.btn_start.config(state="disabled")
        self.lbl_status.config(text="运行中 ♪", fg=ACCENT)
        self.announce(PHRASE_START)
        summary = " → ".join(step["key"] for step in self.steps)
        self.set_hint("正在循环执行序列：%s（共 %d 步）。按停止热键 %s，或点「停 止」结束。"
                      % (summary, len(self.steps), self.cfg.get("stop_hotkey")))

    def stop_pressing(self, with_sound=True):
        if not self.running:
            return
        self.running = False
        self.stop_event.set()
        self.btn_start.config(state="normal")
        self.lbl_status.config(text="已停止", fg=BUBBLE)
        if with_sound:
            self.announce(PHRASE_STOP)
        self.set_hint("已停止。")

    def _wait_for_target(self, target_pid):
        """等到目标程序在最前面；被停止就一直返回 False。"""
        while not self.stop_event.is_set():
            if foreground_pid() == target_pid:
                return True
            if self.stop_event.wait(0.1):
                return False
        return False

    def _sender_loop(self, plan, hold, target_pid):
        """按顺序循环执行整个序列。"""
        count = 0
        while not self.stop_event.is_set():
            for vk, interval in plan:
                if self.stop_event.is_set():
                    return
                if target_pid is not None and not self._wait_for_target(target_pid):
                    return

                send_key_event(vk, True)
                if self.stop_event.wait(hold / 1000.0):
                    send_key_event(vk, False)
                    return
                send_key_event(vk, False)

                count += 1
                if count % 20 == 0:
                    self.events.put(("count", count))

                gap = (interval - hold) / 1000.0
                if gap > 0 and self.stop_event.wait(gap):
                    return

    # ------------------------------------------------------------------ 事件
    def pump_events(self):
        try:
            while True:
                kind, value = self.events.get_nowait()
                if kind == "hotkey":
                    if value == 1:
                        self.start_pressing()
                    elif value == 2:
                        self.stop_pressing()
                elif kind == "hotkey_fail":
                    self.set_hint("热键 %s 被别的程序占用了，换一个试试。"
                                  % ("开始" if value == 1 else "停止"))
                elif kind == "count":
                    if self.running:
                        self.lbl_status.config(text="运行中 (%d 次)" % value)
                elif kind == "voice_ready":
                    self.set_hint("系统语音「%s」已就绪。" % value)
                elif kind == "voice_failed":
                    self.set_hint("系统语音「%s」合成失败，可以换一个声音或用自定义语音。" % value)
        except queue.Empty:
            pass
        self.root.after(50, self.pump_events)

    def on_close(self):
        self.stop_pressing(with_sound=False)
        self.unregister_hotkeys()
        self.root.destroy()


def main():
    # 命令行：python main.py --version 只打印版本号（打包、CI 里会用到）
    if "--version" in sys.argv[1:] or "-V" in sys.argv[1:]:
        print("KeyPresser %s" % __version__)
        return

    try:
        root = tk.Tk()
        try:
            root.call("tk", "scaling", 1.2)
        except Exception:
            pass
        App(root)
        root.mainloop()
    except Exception as exc:
        try:
            messagebox.showerror(APP_TITLE,
                                 "程序出错（v%s）：\n%s" % (__version__, exc))
        except Exception:
            pass
        raise


if __name__ == "__main__":
    main()
