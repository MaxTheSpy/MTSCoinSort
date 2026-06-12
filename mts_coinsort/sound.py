# Auto-split from MTS CoinSort V0.2.0.
# Keep behavior changes small in this refactor; modules are wired together at startup.
from .common import *
from . import app_state as state


def sound_mode_label():
    if not state.COIN_SAVE_SOUND or state.COIN_SAVE_SOUND_MODE == 'off':
        return 'OFF'
    if state.COIN_SAVE_SOUND_MODE == 'custom':
        return 'CUSTOM'
    return 'DEFAULT'



def play_default_coin_saved_sound():
    """Play the built-in coin-saved confirmation sound."""
    try:
        if os.name == 'nt':
            import winsound
            winsound.Beep(880, 60)
        elif sys.stdout is not None:
            sys.stdout.write('\x07')
            sys.stdout.flush()
    except Exception:
        pass



def play_custom_sound_file(path):
    """Best-effort custom sound playback without extra Python dependencies.

    Windows supports WAV files through winsound. macOS uses afplay when
    available. Linux tries common desktop/audio players. If none work, the
    function returns False so callers can fall back to the default beep.
    """
    path = clean_user_path(path) if path else ''
    if not path or not os.path.exists(path):
        return False
    try:
        if os.name == 'nt':
            import winsound
            winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC)
            return True
        if sys.platform == 'darwin':
            subprocess.Popen(['afplay', path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        for player in ('paplay', 'aplay', 'ffplay'):
            if shutil.which(player):
                if player == 'ffplay':
                    subprocess.Popen([player, '-nodisp', '-autoexit', '-loglevel', 'quiet', path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                else:
                    subprocess.Popen([player, path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return True
    except Exception:
        return False
    return False



def play_coin_saved_sound(force=False):
    """Play the configured confirmation sound after a coin is saved.

    Default mode requires no sound files. Custom mode lets the user provide a
    local file path, usually a WAV file on Windows. Linux/macOS support depends
    on the system having a common command-line audio player installed.
    """
    if not force and (not state.COIN_SAVE_SOUND or state.COIN_SAVE_SOUND_MODE == 'off'):
        return
    mode = state.COIN_SAVE_SOUND_MODE if state.COIN_SAVE_SOUND_MODE in ('default', 'custom', 'off') else 'default'
    if mode == 'custom' and play_custom_sound_file(state.COIN_SAVE_SOUND_FILE):
        return
    play_default_coin_saved_sound()



def open_folder(path):
    """Open a folder in the OS file manager."""
    try:
        folder = clean_user_path(path)
        os.makedirs(folder, exist_ok=True)
        if os.name == 'nt':
            os.startfile(folder)
        elif sys.platform == 'darwin':
            subprocess.Popen(['open', folder], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            opener = shutil.which('xdg-open')
            if opener:
                subprocess.Popen([opener, folder], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                return False
        return True
    except Exception:
        return False



def open_sound_folder():
    """Open the folder containing the custom sound file, if one is set."""
    sound_file = str(state.COIN_SAVE_SOUND_FILE or '').strip()
    if not sound_file:
        clear()
        print(yellow('No custom sound file is set.'))
        print()
        print('Set one in Settings > Sound settings > Set custom sound file path.')
        print()
        print('Press any key to continue.')
        read_key()
        return False
    folder = os.path.dirname(clean_user_path(sound_file)) or state.DATA_DIR
    ok = open_folder(folder)
    if not ok:
        clear()
        print(red('Could not open the custom sound file folder automatically.'))
        print()
        print(folder)
        print()
        print('Press any key to continue.')
        read_key()
    return ok


