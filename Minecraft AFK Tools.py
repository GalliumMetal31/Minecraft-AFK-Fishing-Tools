import sys
import time
import threading
import queue
import json
import os
import numpy as np
import pyaudio
import pyautogui
import vgamepad as vg
from pynput import keyboard

import tkinter as tk
from tkinter import ttk, messagebox

# --- CONFIGURATION FILE NAME ---
CONFIG_FILE = "config.json"
ICON = "logo.ico"

# --- Color Palette (Modern Slate/Indigo Theme) ---
BG_MAIN = "#020617"       # slate-950 (Window Background)
BG_CARD = "#0f172a"       # slate-900 (Card/Panel Background)
BG_INPUT = "#1e293b"      # slate-800 (Inputs/Frames)
FG_MAIN = "#f8fafc"       # slate-50 (Main Text)
FG_MUTED = "#94a3b8"      # slate-400 (Labels/Subtext)
COLOR_PRIMARY = "#4f46e5" # indigo-600 (Accent)
COLOR_RUNNING = "#059669" # emerald-600 (Running State - Green)
COLOR_IDLE = "#475569"    # slate-600 (Stopped/Paused State - Gray)
COLOR_STOPPED = "#be123c" # rose-600 (Error/Stop color)
COLOR_BORDER = "#334155"  # slate-700

def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)

# --- UTILITY: HYBRID INPUT CONTROLLER ---
class InputController:
    def __init__(self):
        self.gamepad = None
        self.gamepad_available = False
        try:
            self.gamepad = vg.VX360Gamepad()
            self.gamepad_available = True
            print("Gamepad initialized.")
        except:
            pass

    def perform_action(self, action_name, state):
        if action_name.startswith("Key:"):
            key = action_name.split(": ")[1].lower()
            if state:
                pyautogui.keyDown(key)
            else:
                pyautogui.keyUp(key)
                
        elif action_name == "Mouse: Left Click":
            if state:
                pyautogui.mouseDown(button='left')
            else:
                pyautogui.mouseUp(button='left')

        elif action_name == "Mouse: Right Click":
            if state:
                pyautogui.mouseDown(button='right')
            else:
                pyautogui.mouseUp(button='right')

        elif action_name.startswith("Gamepad:") and self.gamepad:
            btn_name = action_name.split(": ")[1]
            if btn_name == "Left Trigger":
                self.gamepad.left_trigger(value=255 if state else 0)
            elif btn_name == "Right Trigger":
                self.gamepad.right_trigger(value=255 if state else 0)
            else:
                btn_map = {
                    "Button A": vg.XUSB_BUTTON.XUSB_GAMEPAD_A,
                    "Button B": vg.XUSB_BUTTON.XUSB_GAMEPAD_B,
                    "Button X": vg.XUSB_BUTTON.XUSB_GAMEPAD_X,
                    "Button Y": vg.XUSB_BUTTON.XUSB_GAMEPAD_Y,
                    "Right Shoulder": vg.XUSB_BUTTON.XUSB_GAMEPAD_RIGHT_SHOULDER
                }
                if btn_name in btn_map:
                    target_btn = btn_map[btn_name]
                    if state:
                        self.gamepad.press_button(button=target_btn)
                    else:
                        self.gamepad.release_button(button=target_btn)
            self.gamepad.update()

    def perform_switch(self, mode):
        if mode == "Mouse":
            pyautogui.scroll(-500)
        elif mode == "Gamepad":
            if self.gamepad:
                self.gamepad.press_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_RIGHT_SHOULDER)
                self.gamepad.update()
                time.sleep(0.1)
                self.gamepad.release_button(button=vg.XUSB_BUTTON.XUSB_GAMEPAD_RIGHT_SHOULDER)
                self.gamepad.update()

    def perform_scroll(self):
        pyautogui.scroll(-500)

input_ctrl = InputController()

# --- WORKER 1: AUTO CLICKER ---
class AutoClickWorker:
    def __init__(self, msg_queue):
        self.msg_queue = msg_queue
        self.mode = "Macro"
        self.macro_interval = 0.1
        self.hold_duration = 0.0
        self.auto_scroll_enabled = False
        self.auto_scroll_interval = 300.0
        self.target_action = "Mouse: Left Click"
        self._is_running = False
        self._is_paused = False

    def set_config(self, mode, action, macro_int, hold_dur, scroll_en, scroll_int):
        self.mode = mode
        self.target_action = action
        self.macro_interval = macro_int
        self.hold_duration = hold_dur
        self.auto_scroll_enabled = scroll_en
        self.auto_scroll_interval = scroll_int

    def set_paused(self, paused):
        self._is_paused = paused
        status = "PAUSED" if paused else "RUNNING"
        self.msg_queue.put(("status", status))

    def run(self):
        self._is_running = True
        self._is_paused = False
        self.msg_queue.put(("status", "RUNNING"))
        self.msg_queue.put(("sys_msg", f"Auto Clicker Started [{self.mode}]."))
        
        if self.mode == "Macro":
            self._run_macro()
        elif self.mode == "Hold":
            self._run_hold()
            
        self.msg_queue.put(("status", "STOPPED"))
        self.msg_queue.put(("sys_msg", "Auto Clicker Stopped."))

    def _run_macro(self):
        click_count = 0
        while self._is_running:
            if self._is_paused:
                time.sleep(0.1)
                continue

            try:
                input_ctrl.perform_action(self.target_action, True)
                time.sleep(0.02)
                input_ctrl.perform_action(self.target_action, False)
                click_count += 1
                self.msg_queue.put(("sys_msg", f"Click #{click_count} performed"))
                
                start_wait = time.time()
                while (time.time() - start_wait) < self.macro_interval:
                    if not self._is_running: break
                    time.sleep(0.01)
            except Exception as e:
                self.msg_queue.put(("sys_msg", f"Error: {e}"))
                break

    def _run_hold(self):
        try:
            input_ctrl.perform_action(self.target_action, True)
            self.msg_queue.put(("sys_msg", f"Holding button..."))
            start_time = time.time()
            last_scroll_time = time.time()

            while self._is_running:
                if self._is_paused:
                    input_ctrl.perform_action(self.target_action, False)
                    self.msg_queue.put(("sys_msg", "Hold paused..."))
                    while self._is_paused and self._is_running:
                        time.sleep(0.1)
                    if self._is_running:
                        input_ctrl.perform_action(self.target_action, True)
                        self.msg_queue.put(("sys_msg", "Resuming hold..."))
                    continue

                current_time = time.time()
                if self.hold_duration > 0 and (current_time - start_time) >= self.hold_duration:
                    self.msg_queue.put(("sys_msg", "Hold duration reached."))
                    self._is_running = False
                    break

                if self.auto_scroll_enabled and (current_time - last_scroll_time) >= self.auto_scroll_interval:
                    self.msg_queue.put(("sys_msg", f"Auto-scroll..."))
                    input_ctrl.perform_action(self.target_action, False)
                    time.sleep(0.1)
                    input_ctrl.perform_scroll()
                    time.sleep(0.1)
                    input_ctrl.perform_action(self.target_action, True)
                    last_scroll_time = current_time

                time.sleep(0.1)
        finally:
            input_ctrl.perform_action(self.target_action, False)

    def stop(self):
        self._is_running = False

# --- WORKER 2: AFK FISHING ---
class AFKFishingWorker:
    def __init__(self, msg_queue):
        self.msg_queue = msg_queue
        self.device_index = None
        self.target_action = "Mouse: Right Click"
        self.threshold = 6
        self.switch_delay = 120
        self.switch_mode = "Mouse"
        self._is_running = False
        self._is_paused = False

    def set_config(self, device_index, action_name, threshold, switch_delay, switch_mode):
        self.device_index = device_index
        self.target_action = action_name
        self.threshold = threshold
        self.switch_delay = switch_delay
        self.switch_mode = switch_mode

    def set_paused(self, paused):
        self._is_paused = paused
        status = "PAUSED" if paused else "RUNNING"
        self.msg_queue.put(("status", status))

    def run(self):
        self._is_running = True
        self._is_paused = False
        CHUNK = 1024
        FORMAT = pyaudio.paInt16
        CHANNELS = 1
        p = pyaudio.PyAudio()
        stream = None
        
        try:
            dev_info = p.get_device_info_by_index(self.device_index)
            native_rate = int(dev_info['defaultSampleRate'])
            
            stream = p.open(format=FORMAT, channels=CHANNELS, rate=native_rate, 
                            input=True, input_device_index=self.device_index, frames_per_buffer=CHUNK)
            
            self.msg_queue.put(("status", "RUNNING"))
            self.msg_queue.put(("sys_msg", "Listening for audio..."))
            
            catch_count = 0
            last_click_time, last_input_time = time.time(), time.time()
            no_input_count = 0

            while self._is_running:
                if self._is_paused:
                    time.sleep(0.1)
                    continue

                try:
                    data = np.frombuffer(stream.read(CHUNK, exception_on_overflow=False), dtype=np.int16)
                    volume = np.linalg.norm(data) / CHUNK
                    self.msg_queue.put(("volume", int(volume)))
                    has_input = volume > self.threshold
                except Exception:
                    has_input = False

                if has_input:
                    if time.time() - last_click_time > 3:
                        catch_count += 1
                        no_input_count = 0
                        self.msg_queue.put(("sys_msg", f"Catch #{catch_count} performed"))
                        
                        input_ctrl.perform_action(self.target_action, True)
                        time.sleep(0.1)
                        input_ctrl.perform_action(self.target_action, False)
                        time.sleep(0.5)
                        input_ctrl.perform_action(self.target_action, True)
                        time.sleep(0.1)
                        input_ctrl.perform_action(self.target_action, False)

                        last_click_time = time.time()
                        last_input_time = time.time()
                else:
                    if time.time() - last_input_time > self.switch_delay:
                        no_input_count += 1
                        if no_input_count >= 2:
                            self.msg_queue.put(("sys_msg", "Timeout. Stopping."))
                            pyautogui.press("esc")
                            self._is_running = False
                            break
                        
                        self.msg_queue.put(("sys_msg", "Switching rod (Anti-AFK)..."))
                        input_ctrl.perform_switch(self.switch_mode)
                        time.sleep(0.5)
                        input_ctrl.perform_action(self.target_action, True)
                        time.sleep(0.1)
                        input_ctrl.perform_action(self.target_action, False)
                        
                        last_input_time = time.time()
                        last_click_time = time.time()
                time.sleep(0.01)

        except Exception as e:
            self.msg_queue.put(("sys_msg", f"Audio Error: {e}"))
        finally:
            if stream and stream.is_active(): stream.stop_stream()
            if stream: stream.close()
            p.terminate()
            self.msg_queue.put(("volume", 0))
            self.msg_queue.put(("status", "STOPPED"))
            self.msg_queue.put(("sys_msg", "Fishing Worker Stopped."))

    def stop(self):
        self._is_running = False

# --- MAIN GUI (Tkinter) ---
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        
        self.title("Minecraft AFK Tools")
        self.geometry("520x720")
        self.resizable(False, False)
        self.configure(bg=BG_MAIN)
        
        try:
            icon_path = resource_path(ICON)
            self.iconbitmap(icon_path) 
        except: pass

        self.setup_styles()
        
        self.queue = queue.Queue()
        self.ac_worker = AutoClickWorker(self.queue)
        self.fish_worker = AFKFishingWorker(self.queue)
        self.ac_thread = None
        self.fish_thread = None

        self.output_options = [
            "Mouse: Left Click", "Mouse: Right Click",
            "Gamepad: Left Trigger", "Gamepad: Right Trigger", 
            "Gamepad: Button A", "Gamepad: Button B",
            "Key: SPACE", "Key: E", "Key: F", "Key: ENTER"
        ]

        # Init UI
        self.create_widgets()
        
        # Load configs
        self.load_settings()
        self.setup_traces()

        # Start Global Keyboard Listener
        self.listener = keyboard.Listener(on_press=self.on_key_press)
        self.listener.start()
        self.process_queue()

    def setup_styles(self):
        style = ttk.Style()
        style.theme_use('clam')

        # Frames & Notebook
        style.configure("TFrame", background=BG_MAIN)
        style.configure("Card.TFrame", background=BG_CARD)
        
        style.configure("TNotebook", background=BG_MAIN, borderwidth=0)
        style.configure("TNotebook.Tab", background=BG_INPUT, foreground=FG_MUTED, padding=[15, 10], font=("Segoe UI", 11, "bold"), borderwidth=0)
        style.map("TNotebook.Tab", background=[("selected", BG_CARD)], foreground=[("selected", COLOR_PRIMARY)])

        # Labels
        style.configure("TLabel", background=BG_CARD, foreground=FG_MAIN, font=("Segoe UI", 11))
        style.configure("Sub.TLabel", background=BG_CARD, foreground=FG_MUTED, font=("Segoe UI", 10, "bold"))
        style.configure("SysMsg.TLabel", background=BG_MAIN, foreground=FG_MUTED, font=("Consolas", 10))

        # Radio & Checkbuttons
        style.configure("TRadiobutton", background=BG_CARD, foreground=FG_MAIN, font=("Segoe UI", 12))
        style.map("TRadiobutton", background=[('active', BG_CARD)], indicatorcolor=[('selected', COLOR_PRIMARY)])
        
        style.configure("TCheckbutton", background=BG_CARD, foreground=FG_MAIN, font=("Segoe UI", 12))
        style.map("TCheckbutton", background=[('active', BG_CARD)])

        # Inputs 
        style.configure("TCombobox", fieldbackground=BG_INPUT, foreground=FG_MAIN, background=BG_INPUT, arrowcolor=FG_MAIN, borderwidth=0, font=("Segoe UI", 12))
        style.map("TCombobox", 
                  fieldbackground=[('readonly', BG_INPUT), ('active', BG_INPUT), ('focus', BG_INPUT)],
                  background=[('readonly', BG_INPUT), ('active', BG_INPUT)],
                  selectbackground=[('focus', COLOR_PRIMARY), ('!focus', BG_INPUT)], 
                  selectforeground=[('focus', FG_MAIN), ('!focus', FG_MAIN)])

        style.configure("TEntry", fieldbackground=BG_INPUT, foreground=FG_MAIN, borderwidth=0, insertcolor=FG_MAIN, font=("Segoe UI", 12))
        style.map("TEntry", 
                  fieldbackground=[('readonly', BG_INPUT), ('active', BG_INPUT), ('!disabled', BG_INPUT)],
                  selectbackground=[('focus', COLOR_PRIMARY)], 
                  selectforeground=[('focus', FG_MAIN)])
        
        # Scale & Progress
        style.configure("Horizontal.TScale", background=BG_CARD, troughcolor=BG_INPUT)
        style.configure("Horizontal.TProgressbar", background=COLOR_PRIMARY, troughcolor=BG_INPUT, borderwidth=0)

        # COMBOBOX DROPDOWN (LISTBOX) STYLE FIX
        self.option_add('*TCombobox*Listbox.background', BG_CARD)
        self.option_add('*TCombobox*Listbox.foreground', FG_MAIN)
        self.option_add('*TCombobox*Listbox.selectBackground', COLOR_PRIMARY)
        self.option_add('*TCombobox*Listbox.selectForeground', FG_MAIN)
        self.option_add('*TCombobox*Listbox.font', ("Segoe UI", 12))

    def create_widgets(self):
        # Header
        header = tk.Frame(self, bg=BG_CARD, height=65)
        header.pack(fill='x')
        tk.Label(header, text="Minecraft AFK Tools", font=("Segoe UI", 16, "bold"), bg=BG_CARD, fg=FG_MAIN).pack(side=tk.LEFT, padx=20, pady=15)
        
        # Reset Config Button
        btn_reset = tk.Button(header, text="Reset Config", font=("Segoe UI", 10), bg=BG_INPUT, fg=FG_MAIN, relief="flat", cursor="hand2", command=self.reset_settings)
        btn_reset.pack(side=tk.RIGHT, padx=20, pady=15)

        # Tabs
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(expand=True, fill='both', padx=15, pady=10)
        self.notebook.bind("<<NotebookTabChanged>>", self.on_tab_change)

        self.tab_ac = ttk.Frame(self.notebook, style="Card.TFrame")
        self.notebook.add(self.tab_ac, text='   Auto Clicker   ')
        self.setup_ac_tab()

        self.tab_fish = ttk.Frame(self.notebook, style="Card.TFrame")
        self.notebook.add(self.tab_fish, text='   AFK Fishing   ')
        self.setup_fish_tab()
        
        # Footer Action Bar
        footer = tk.Frame(self, bg=BG_MAIN)
        footer.pack(fill='x', side=tk.BOTTOM, padx=15, pady=15)

        self.sys_msg_var = tk.StringVar(value="System Ready.")
        ttk.Label(footer, textvariable=self.sys_msg_var, style="SysMsg.TLabel").pack(anchor='w', pady=(0, 10))

        # Action Buttons Wrapper
        btn_frame = tk.Frame(footer, bg=BG_MAIN)
        btn_frame.pack(fill='x', expand=True)

        # Dynamic Start/Pause Button (Left)
        self.btn_toggle = tk.Button(btn_frame, text="▶ START (F9)", font=("Segoe UI", 15, "bold"), bg=COLOR_IDLE, fg="white", relief="flat", cursor="hand2", command=self.handle_toggle)
        self.btn_toggle.pack(side=tk.LEFT, fill='x', expand=True, ipady=12, padx=(0, 5))

        # Restart Button (Right)
        self.btn_restart = tk.Button(btn_frame, text="↻ RESTART (F10)", font=("Segoe UI", 15, "bold"), bg=BG_INPUT, fg=COLOR_PRIMARY, relief="flat", cursor="hand2", command=self.handle_restart)
        self.btn_restart.pack(side=tk.RIGHT, fill='x', expand=True, ipady=12, padx=(5, 0))

    def setup_ac_tab(self):
        ttk.Label(self.tab_ac, text="GENERAL OUTPUT ACTION", style="Sub.TLabel").pack(anchor='w', padx=15, pady=(15, 2))
        self.ac_action_var = tk.StringVar(value="Mouse: Left Click")
        ttk.Combobox(self.tab_ac, textvariable=self.ac_action_var, values=self.output_options, state="readonly", font=("Segoe UI", 12)).pack(fill='x', padx=15, pady=5)

        ttk.Label(self.tab_ac, text="SELECT MODE", style="Sub.TLabel").pack(anchor='w', padx=15, pady=(15, 2))
        mode_frame = ttk.Frame(self.tab_ac, style="Card.TFrame")
        mode_frame.pack(fill='x', padx=15)
        self.ac_mode_var = tk.StringVar(value="Macro")
        ttk.Radiobutton(mode_frame, text="Macro", variable=self.ac_mode_var, value="Macro", command=self.toggle_ac_mode).pack(side=tk.LEFT, pady=5, padx=(0, 20))
        ttk.Radiobutton(mode_frame, text="Hold", variable=self.ac_mode_var, value="Hold", command=self.toggle_ac_mode).pack(side=tk.LEFT, pady=5)

        # Config Area
        self.config_frame = ttk.Frame(self.tab_ac, style="Card.TFrame")
        self.config_frame.pack(fill='x', padx=15, pady=15)
        
        self.ac_macro_interval_var = tk.StringVar(value="0.1")
        self.ac_hold_duration_var = tk.StringVar(value="0.0")
        self.ac_auto_scroll_var = tk.BooleanVar(value=False)
        self.ac_auto_scroll_interval_var = tk.StringVar(value="300.0")
        
        self.toggle_ac_mode()

    def toggle_ac_mode(self):
        for widget in self.config_frame.winfo_children():
            widget.destroy()
            
        if self.ac_mode_var.get() == "Macro":
            ttk.Label(self.config_frame, text="CLICK INTERVAL (SECONDS)", style="Sub.TLabel").pack(anchor='w', pady=(0, 2))
            ttk.Entry(self.config_frame, textvariable=self.ac_macro_interval_var, font=("Segoe UI", 12)).pack(fill='x', pady=5)
        else:
            ttk.Label(self.config_frame, text="HOLD DURATION (0 = INFINITE)", style="Sub.TLabel").pack(anchor='w', pady=(0, 2))
            ttk.Entry(self.config_frame, textvariable=self.ac_hold_duration_var, font=("Segoe UI", 12)).pack(fill='x', pady=5)
            
            ttk.Checkbutton(self.config_frame, text="Enable Anti-AFK Auto Scroll", variable=self.ac_auto_scroll_var).pack(anchor='w', pady=(10, 5))
            
            ttk.Label(self.config_frame, text="AUTO-SCROLL INTERVAL (SEC)", style="Sub.TLabel").pack(anchor='w', pady=(5, 2))
            ttk.Entry(self.config_frame, textvariable=self.ac_auto_scroll_interval_var, font=("Segoe UI", 12)).pack(fill='x', pady=5)

    def setup_fish_tab(self):
        ttk.Label(self.tab_fish, text="AUDIO INPUT SOURCE", style="Sub.TLabel").pack(anchor='w', padx=15, pady=(15, 2))
        
        self.audio_combo = ttk.Combobox(self.tab_fish, state="readonly", font=("Segoe UI", 12), postcommand=self.refresh_audio_devices)
        self.audio_combo.pack(fill='x', padx=15, pady=5)
        self.audio_map = {}

        # Audio Threshold Area
        thresh_frame = tk.Frame(self.tab_fish, bg=BG_INPUT)
        thresh_frame.pack(fill='x', padx=15, pady=15)
        
        header = tk.Frame(thresh_frame, bg=BG_INPUT)
        header.pack(fill='x', padx=10, pady=(10, 0))
        ttk.Label(header, text="DETECTION THRESHOLD", style="Sub.TLabel", background=BG_INPUT).pack(side=tk.LEFT)
        
        self.thresh_var = tk.StringVar(value="6")
        entry_thresh = ttk.Entry(header, textvariable=self.thresh_var, width=6, justify="center", font=("Segoe UI", 12))
        entry_thresh.pack(side=tk.RIGHT)
        
        self.thresh_scale = ttk.Scale(thresh_frame, from_=1, to=100, orient='horizontal', command=self.on_scale_drag)
        self.thresh_scale.set(6)
        self.thresh_scale.pack(fill='x', padx=10, pady=10)
        
        # Prevent slider error when typing manually, but keep it updated (bypassing auto_save trace)
        self.thresh_var.trace_add('write', self.on_thresh_entry_change)
        
        self.vol_var = tk.IntVar(value=0)
        ttk.Progressbar(thresh_frame, variable=self.vol_var, maximum=100, style="Horizontal.TProgressbar").pack(fill='x', padx=10, pady=(0, 10))

        # Bottom Configs
        grid = tk.Frame(self.tab_fish, bg=BG_CARD)
        grid.pack(fill='x', padx=15)
        
        left = tk.Frame(grid, bg=BG_CARD)
        left.pack(side=tk.LEFT, fill='x', expand=True, padx=(0, 5))
        ttk.Label(left, text="SWITCH DELAY (SEC)", style="Sub.TLabel").pack(anchor='w')
        self.switch_delay_var = tk.StringVar(value="120")
        ttk.Entry(left, textvariable=self.switch_delay_var, font=("Segoe UI", 12)).pack(fill='x', pady=5)

        right = tk.Frame(grid, bg=BG_CARD)
        right.pack(side=tk.RIGHT, fill='x', expand=True, padx=(5, 0))
        ttk.Label(right, text="SWITCH MODE", style="Sub.TLabel").pack(anchor='w')
        self.switch_mode_var = tk.StringVar(value="Mouse")
        ttk.Combobox(right, textvariable=self.switch_mode_var, values=["Mouse", "Gamepad"], state="readonly", font=("Segoe UI", 12)).pack(fill='x', pady=5)

        ttk.Label(self.tab_fish, text="CATCH ACTION", style="Sub.TLabel").pack(anchor='w', padx=15, pady=(15, 2))
        self.fish_action_var = tk.StringVar(value="Mouse: Right Click")
        self.fish_action_combo = ttk.Combobox(self.tab_fish, textvariable=self.fish_action_var, state="readonly", font=("Segoe UI", 12))
        self.fish_action_combo.pack(fill='x', padx=15, pady=5)

        # Trigger automatic filter when mode is changed
        self.switch_mode_var.trace_add('write', self.update_fish_action_options)
        self.update_fish_action_options() # Run once when UI is first created

    def update_fish_action_options(self, *args):
        mode = self.switch_mode_var.get()
        if mode == "Gamepad":
            # Filter only Gamepad options
            valid_opts = [opt for opt in self.output_options if opt.startswith("Gamepad:")]
            default = "Gamepad: Right Trigger"
        else:
            # Filter only Mouse & Keyboard options
            valid_opts = [opt for opt in self.output_options if not opt.startswith("Gamepad:")]
            default = "Mouse: Right Click"
            
        # Update dropdown contents
        self.fish_action_combo['values'] = valid_opts
        
        # If the previously selected option is not in the new list, revert to default
        if self.fish_action_var.get() not in valid_opts:
            self.fish_action_var.set(default)

    def on_scale_drag(self, val):
        int_val = int(float(val))
        if self.thresh_var.get() != str(int_val):
            self.thresh_var.set(str(int_val))

    def on_thresh_entry_change(self, *args):
        try:
            val = int(self.thresh_var.get())
            self.thresh_scale.set(val)
        except ValueError:
            pass # Ignore error if user deletes string or input is incomplete

    def refresh_audio_devices(self, target=None):
        current_val = self.audio_combo.get()
        if target is None and current_val:
            target = current_val

        self.audio_combo.set('')
        self.audio_map.clear()
        values = []
        p = pyaudio.PyAudio()
        for i in range(p.get_device_count()):
            try:
                dev = p.get_device_info_by_index(i)
                if dev.get('maxInputChannels') > 0:
                    if "MME" in p.get_host_api_info_by_index(dev.get('hostApi'))['name']:
                        name = dev.get('name')
                        values.append(name)
                        self.audio_map[name] = i
            except: pass
        p.terminate()
        
        self.audio_combo['values'] = values
        if target and target in values: 
            self.audio_combo.set(target)
        elif values: 
            self.audio_combo.current(0)

    # --- AUTO SAVE FUNCTIONALITY ---
    def setup_traces(self):
        """Attaches a listener to auto-save when any variable changes"""
        variables = [
            self.ac_mode_var, self.ac_macro_interval_var, self.ac_hold_duration_var,
            self.ac_auto_scroll_var, self.ac_auto_scroll_interval_var, self.ac_action_var,
            self.fish_action_var, self.thresh_var, self.switch_delay_var, self.switch_mode_var
        ]
        for var in variables:
            var.trace_add('write', self.auto_save)
            
        self.audio_combo.bind("<<ComboboxSelected>>", self.auto_save)

    def auto_save(self, *args):
        self.save_settings(silent=True)
        self.update_workers_config()

    def reset_settings(self):
        if messagebox.askyesno("Reset Config", "Are you sure you want to reset all configurations to default?"):
            self.ac_mode_var.set("Macro")
            self.ac_macro_interval_var.set("0.1")
            self.ac_hold_duration_var.set("0.0")
            self.ac_auto_scroll_var.set(False)
            self.ac_auto_scroll_interval_var.set("300.0")
            self.ac_action_var.set("Mouse: Left Click")
            self.fish_action_var.set("Mouse: Right Click")
            self.thresh_var.set("6")
            self.switch_delay_var.set("120")
            self.switch_mode_var.set("Mouse")
            
            if self.audio_combo['values']:
                self.audio_combo.current(0)
            
            self.toggle_ac_mode()
            self.save_settings(silent=False)
            self.sys_msg_var.set("Settings reset to defaults.")

    def update_workers_config(self):
        """Read inputs and apply them to the bot before running (Used by Start & Restart)"""
        # Parse text to number with fallback if box is empty or mistyped
        try:
            m_int = max(0.001, float(self.ac_macro_interval_var.get() or 0.1))
            h_dur = max(0.0, float(self.ac_hold_duration_var.get() or 0.0))
            s_int = max(1.0, float(self.ac_auto_scroll_interval_var.get() or 300.0))
        except ValueError:
            m_int, h_dur, s_int = 0.1, 0.0, 300.0
            
        self.ac_worker.set_config(
            self.ac_mode_var.get(), self.ac_action_var.get(),
            m_int, h_dur, self.ac_auto_scroll_var.get(), s_int
        )

        dev_idx = self.audio_map.get(self.audio_combo.get())
        if dev_idx is not None:
            try:
                t_val = int(self.thresh_var.get() or 6)
                s_val = int(self.switch_delay_var.get() or 120)
            except ValueError:
                t_val, s_val = 6, 120

            self.fish_worker.set_config(
                dev_idx, self.fish_action_var.get(), t_val,
                s_val, self.switch_mode_var.get()
            )

    def load_settings(self):
        loaded_device = None
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r') as f:
                    c = json.load(f)
                    self.ac_mode_var.set(c.get("ac_mode", "Macro"))
                    self.ac_macro_interval_var.set(str(c.get("ac_macro_interval", "0.1")))
                    self.ac_hold_duration_var.set(str(c.get("ac_hold_duration", "0.0")))
                    self.ac_auto_scroll_var.set(bool(c.get("ac_auto_scroll", False)))
                    self.ac_auto_scroll_interval_var.set(str(c.get("ac_auto_scroll_interval", "300.0")))
                    self.ac_action_var.set(c.get("ac_action", "Mouse: Left Click"))
                    self.fish_action_var.set(c.get("fish_action", "Mouse: Right Click"))
                    self.thresh_var.set(str(c.get("threshold", "6")))
                    self.switch_delay_var.set(str(c.get("switch_delay", "120")))
                    self.switch_mode_var.set(c.get("switch_mode", "Mouse"))
                    loaded_device = c.get("last_audio_device")
                    self.toggle_ac_mode()
            except: pass
        self.refresh_audio_devices(target=loaded_device)

    def save_settings(self, silent=False):
        try:
            with open(CONFIG_FILE, 'w') as f:
                json.dump({
                    "ac_mode": self.ac_mode_var.get(),
                    "ac_macro_interval": self.ac_macro_interval_var.get(),
                    "ac_hold_duration": self.ac_hold_duration_var.get(),
                    "ac_auto_scroll": self.ac_auto_scroll_var.get(),
                    "ac_auto_scroll_interval": self.ac_auto_scroll_interval_var.get(),
                    "ac_action": self.ac_action_var.get(),
                    "fish_action": self.fish_action_var.get(),
                    "threshold": self.thresh_var.get(),
                    "switch_delay": self.switch_delay_var.get(),
                    "switch_mode": self.switch_mode_var.get(),
                    "last_audio_device": self.audio_combo.get()
                }, f, indent=4)
            if not silent:
                self.sys_msg_var.set("Settings saved.")
        except Exception as e:
            if not silent:
                self.sys_msg_var.set(f"Save error: {e}")

    def on_tab_change(self, event):
        self.handle_stop() # Auto-stop on tab change to prevent conflicts

    def process_queue(self):
        try:
            while True:
                msg_type, data = self.queue.get_nowait()
                if msg_type == "sys_msg":
                    self.sys_msg_var.set(str(data))
                elif msg_type == "volume":
                    self.vol_var.set(min(data * 2, 100))
                elif msg_type == "status":
                    self.update_ui_state(data)
        except queue.Empty: pass
        self.after(100, self.process_queue)

    def update_ui_state(self, state):
        if state == "RUNNING":
            self.btn_toggle.config(text="⏸ PAUSE (F9)", bg=COLOR_RUNNING)
        elif state == "PAUSED":
            self.btn_toggle.config(text="▶ RESUME (F9)", bg=COLOR_IDLE)
        elif state == "STOPPED":
            self.btn_toggle.config(text="▶ START (F9)", bg=COLOR_IDLE)

    def on_key_press(self, key):
        try:
            if key == keyboard.Key.f9: self.after_idle(self.handle_toggle)
            elif key == keyboard.Key.f10: self.after_idle(self.handle_restart)
            elif key == keyboard.Key.f8: self.after_idle(self.handle_stop) # Hidden emergency stop
        except: pass

    def handle_toggle(self):
        tab = self.notebook.index(self.notebook.select())
        
        if tab == 0: # Auto Clicker
            is_active = self.ac_thread and self.ac_thread.is_alive()
            if is_active:
                self.ac_worker.set_paused(not self.ac_worker._is_paused)
            else:
                self.start_ac()

        elif tab == 1: # AFK Fishing
            is_active = self.fish_thread and self.fish_thread.is_alive()
            if is_active:
                self.fish_worker.set_paused(not self.fish_worker._is_paused)
            else:
                self.start_fish()

    def handle_restart(self):
        """Stop the program, load new settings, and run again"""
        tab = self.notebook.index(self.notebook.select())
        self.sys_msg_var.set("Restarting and applying new settings...")
        
        if tab == 0:
            if self.ac_thread and self.ac_thread.is_alive():
                self.ac_worker.stop()
                # Wait for thread to stop safely
                self.ac_thread.join(timeout=1.0)
            self.start_ac()
            
        elif tab == 1:
            if self.fish_thread and self.fish_thread.is_alive():
                self.fish_worker.stop()
                # Wait for thread to stop safely
                self.fish_thread.join(timeout=1.0)
            self.start_fish()

    def start_ac(self):
        self.update_workers_config()
        self.ac_thread = threading.Thread(target=self.ac_worker.run, daemon=True)
        self.ac_thread.start()

    def start_fish(self):
        self.update_workers_config()
        if self.fish_worker.device_index is None:
            messagebox.showerror("Error", "Select valid audio device!")
            return
        
        self.fish_thread = threading.Thread(target=self.fish_worker.run, daemon=True)
        self.fish_thread.start()

    def handle_stop(self):
        tab = self.notebook.index(self.notebook.select())
        if tab == 0 and self.ac_thread and self.ac_thread.is_alive():
            self.ac_worker.stop()
            self.update_ui_state("STOPPED")
        elif tab == 1 and self.fish_thread and self.fish_thread.is_alive():
            self.fish_worker.stop()
            self.update_ui_state("STOPPED")

    def on_close(self):
        self.save_settings() # Final save when window is closed
        if self.ac_thread and self.ac_thread.is_alive(): self.ac_worker.stop()
        if self.fish_thread and self.fish_thread.is_alive(): self.fish_worker.stop()
        self.listener.stop()
        self.destroy()

if __name__ == "__main__":
    app = App()
    app.protocol("WM_DELETE_WINDOW", app.on_close)
    app.mainloop()