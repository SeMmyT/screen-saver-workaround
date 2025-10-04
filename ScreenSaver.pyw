import time
import os
import psutil
import pygetwindow as gw
from pynput import mouse, keyboard
from pystray import Icon, Menu, MenuItem
from PIL import Image, ImageDraw
import threading
import subprocess

# --- Try importing the inputs library for gamepad support ---
try:
    import inputs
    gamepad_support_enabled = True
except ImportError:
    print("WARN: 'inputs' library not found. Gamepad monitoring disabled.")
    print("      Install it using: pip install inputs")
    gamepad_support_enabled = False
# ---

# --- Configuration ---
INACTIVITY_THRESHOLD = 60
SCREENSAVER_EXE = "scrnsave.scr"
SCREENSAVER_PATH = os.path.join(os.environ.get("SystemRoot", "C:\\Windows"), "System32", SCREENSAVER_EXE)

# --- Global State Variables ---
last_activity_time = time.time()
screensaver_active_by_script = False
stop_threads = threading.Event()
# A standard lock is sufficient with the corrected logic.
activity_lock = threading.Lock() 

# --- Helper Functions ---
def get_screensaver_process():
    """Finds and returns the psutil.Process object for the running screensaver."""
    try:
        for proc in psutil.process_iter(['name']):
            if proc.info['name'] == SCREENSAVER_EXE:
                return proc
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        pass # Ignore processes that disappear or we can't access
    return None

def start_screensaver():
    """Starts the screensaver and updates the state."""
    global screensaver_active_by_script
    # Check if it's somehow already running before we start it
    if get_screensaver_process():
        print("Screensaver process already running. Aborting start.")
        return
        
    print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} - Starting screensaver...")
    try:
        subprocess.Popen([SCREENSAVER_PATH, '/s'])
        with activity_lock:
            screensaver_active_by_script = True
    except FileNotFoundError:
        print(f"ERROR: Screensaver executable not found at {SCREENSAVER_PATH}")
    except Exception as e:
        print(f"ERROR: Failed to start screensaver: {e}")

def stop_screensaver_process():
    """
    Finds and kills the screensaver process. This function does NOT manage state.
    It's a simple "killer" function.
    """
    proc = get_screensaver_process()
    if proc:
        try:
            print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} - Terminating screensaver process (PID: {proc.pid}).")
            proc.kill()
            # proc.wait(timeout=3) # Optional: wait for process to die
            return True
        except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
            print(f"Could not terminate screensaver process: {e}")
    return False

def update_activity_time(*args, **kwargs):
    """Resets the last activity time and stops the screensaver if it's active."""
    global last_activity_time, screensaver_active_by_script
    
    # This entire block is now atomic and deadlock-free.
    with activity_lock:
        # First, check if there's even a need to stop anything.
        is_active = screensaver_active_by_script
        
        # Always update the activity time.
        last_activity_time = time.time()
        
        # If the screensaver was active, stop the process and update the flag.
        if is_active:
            print("Activity detected. Stopping screensaver.")
            if stop_screensaver_process():
                screensaver_active_by_script = False
            else:
                print("Screensaver process was not found (may have been closed manually).")
                # Correct the state if the process was already gone
                screensaver_active_by_script = False

def is_fullscreen_app_active():
    """Checks if the currently active window is fullscreen."""
    try:
        active_window = gw.getActiveWindow()
        if active_window:
            # Simple check for fullscreen: window dimensions match screen dimensions.
            # Use a small tolerance for borders.
            screen = gw.get_desktop_size()
            if (active_window.width >= screen.width - 10 and 
                active_window.height >= screen.height - 10):
                # print(f"DEBUG: Fullscreen window detected: {active_window.title}")
                return True
    except Exception:
        return False
    return False

def is_video_playback_active():
    """Checks if known video players are running or if an app is fullscreen."""
    video_players = {
        "vlc.exe", "mpc-hc.exe", "mpc-hc64.exe", "wmplayer.exe", 
        "potplayer.exe", "potplayer64.exe", "plex media player.exe", "kodi.exe"
    }
    try:
        for process in psutil.process_iter(['name']):
            if process.info['name'] and process.info['name'].lower() in video_players:
                # print(f"DEBUG: Video player process detected: {process.info['name']}")
                return True
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        pass

    if is_fullscreen_app_active():
        return True
        
    return False

def monitor_loop():
    """Main loop to check inactivity and trigger screensaver."""
    print("Inactivity monitor started.")
    while not stop_threads.is_set():
        try:
            # We only need the lock to read the initial state and idle time.
            with activity_lock:
                is_screensaver_on = screensaver_active_by_script
                idle_time = time.time() - last_activity_time
            
            # If our script has the screensaver on, do nothing in this loop.
            # The input listeners are now responsible for turning it off.
            if is_screensaver_on:
                time.sleep(1)
                continue
            
            if idle_time > INACTIVITY_THRESHOLD:
                print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} - Inactivity threshold reached. Checking conditions...")
                
                if not is_video_playback_active():
                    start_screensaver()
                else:
                    print("Video/Fullscreen detected, screensaver deferred. Resetting activity timer.")
                    update_activity_time("VideoPlayback")

            time.sleep(2)

        except Exception as e:
            print(f"ERROR in monitor_loop: {e}")
            time.sleep(5)

    print("Inactivity monitor thread stopped.")


def monitor_gamepad():
    """Monitors gamepad events and updates activity time."""
    if not gamepad_support_enabled:
        return

    print("Gamepad monitor started. NOTE: This may require running the script as Administrator.")
    gamepad_connected = True 
    while not stop_threads.is_set():
        try:
            events = inputs.get_gamepad()
            if not gamepad_connected:
                gamepad_connected = True
                print("Gamepad connected.")

            for event in events:
                if event.ev_type == 'Absolute' and abs(event.state) < 3000:
                    continue
                
                # print("DEBUG: Gamepad activity detected.")
                update_activity_time("Gamepad")
                break

        except inputs.UnpluggedError:
            if gamepad_connected:
                print("Gamepad unplugged. Waiting for connection...")
                gamepad_connected = False
            time.sleep(5)
        except Exception as e:
            if "No gamepad found" in str(e):
                if gamepad_connected:
                    print("No gamepad found. Waiting for connection...")
                    gamepad_connected = False
                time.sleep(5)
            else:
                print(f"ERROR in monitor_gamepad loop: {type(e).__name__}: {e}")
                time.sleep(5)

    print("Gamepad monitor thread stopped.")

# --- System Tray Setup ---
def create_image(width, height, color1, color2):
    image = Image.new('RGB', (width, height), color1)
    dc = ImageDraw.Draw(image)
    dc.rectangle((width // 2, 0, width, height // 2), fill=color2)
    dc.rectangle((0, height // 2, width // 2, height), fill=color2)
    return image

def on_quit(icon, item):
    """Callback function when 'Quit' is selected from the tray menu."""
    print("Quit requested. Stopping threads and cleaning up...")
    # Cleanly stop the screensaver if it's running
    if screensaver_active_by_script:
        stop_screensaver_process()
    stop_threads.set()
    icon.stop()

def setup_tray():
    icon = Icon("Inactivity Monitor")
    icon.icon = create_image(64, 64, 'black', 'darkgreen')
    icon.title = "Inactivity Monitor"
    icon.menu = Menu(MenuItem("Quit", on_quit))
    print("System tray icon running. Right-click to quit.")
    icon.run()

# --- Main Execution ---
if __name__ == "__main__":
    print("--- Inactivity Monitor ---")
    print(f"Screensaver will start after {INACTIVITY_THRESHOLD} seconds of inactivity.")
    print(f"Using screensaver: {SCREENSAVER_PATH}")
    if not os.path.exists(SCREENSAVER_PATH):
        print("\n!!! WARNING: Screensaver executable not found. Please check the SCREENSAVER_PATH variable. !!!\n")

    mouse_listener = mouse.Listener(on_move=update_activity_time, on_click=update_activity_time, on_scroll=update_activity_time)
    keyboard_listener = keyboard.Listener(on_press=update_activity_time)
    mouse_listener.start()
    keyboard_listener.start()

    monitor_thread = threading.Thread(target=monitor_loop, daemon=True)
    monitor_thread.start()

    if gamepad_support_enabled:
        gamepad_thread = threading.Thread(target=monitor_gamepad, daemon=True)
        gamepad_thread.start()

    setup_tray()
    
    print("Stopping input listeners...")
    mouse_listener.stop()
    keyboard_listener.stop()
    print("Application exited cleanly.")
