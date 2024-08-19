import time
import os
import psutil
import pygetwindow as gw
from pynput import mouse, keyboard
from pystray import Icon, Menu, MenuItem
from PIL import Image, ImageDraw
import threading

# Set the inactivity threshold (in seconds)
inactivity_threshold = 30  

# Variables to track time since last activity and screensaver start time
last_activity_time = time.time()
screensaver_start_time = None

def start_screensaver():
    # Adjust this path to your screensaver executable if known
    screensaver_exe = "C:\\Windows\\System32\\scrnsave.scr"  # Example path
    os.system(f'"{screensaver_exe}" /start')

def update_activity_time(*args, **kwargs):
    global last_activity_time
    last_activity_time = time.time()

def is_video_playback_active():
    video_players = {"vlc.exe", "mpc-hc.exe", "wmplayer.exe"}
    for process in psutil.process_iter(['name']):
        if process.info['name'].lower() in video_players:
            return True
    return is_youtube_fullscreen()

def is_youtube_fullscreen():
    return any(window.isMaximized for window in gw.getWindowsWithTitle('YouTube'))

def is_screensaver_running():
    global screensaver_start_time
    return screensaver_start_time and time.time() - screensaver_start_time < inactivity_threshold

def monitor_inactivity():
    global last_activity_time, screensaver_start_time
    try:
        while True:
            if (time.time() - last_activity_time > inactivity_threshold and
                not is_video_playback_active() and
                not is_screensaver_running()):
                start_screensaver()
                screensaver_start_time = time.time()
            time.sleep(1)
    except KeyboardInterrupt:
        print("Script terminated by user.")
    finally:
        mouse_listener.stop()
        keyboard_listener.stop()

def create_image(width, height, color1, color2):
    image = Image.new('RGB', (width, height), color1)
    dc = ImageDraw.Draw(image)
    dc.rectangle((width // 2, 0, width, height // 2), fill=color2)
    dc.rectangle((0, height // 2, width // 2, height), fill=color2)
    return image

def setup_tray():
    icon = Icon("Inactivity Monitor")
    icon.icon = create_image(64, 64, 'black', 'white')
    icon.title = "Inactivity Monitor"
    icon.menu = Menu(MenuItem("Quit", lambda: icon.stop()))

    thread = threading.Thread(target=monitor_inactivity, daemon=True)
    thread.start()

    icon.run()

# Set up mouse and keyboard listeners
mouse_listener = mouse.Listener(on_move=update_activity_time, on_click=update_activity_time, on_scroll=update_activity_time)
keyboard_listener = keyboard.Listener(on_press=update_activity_time)

mouse_listener.start()
keyboard_listener.start()

# Start the system tray icon
setup_tray()
