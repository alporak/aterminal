"""
Adapter module to integrate the easy-catcher submodule with the Alps Toolkit.

Wraps the submodule's process_folder() into a process_dumps() function
compatible with the toolkit's Easy Catcher page (pages/4_📊_Easy_Catcher.py).
"""

import os
import sys
import importlib.util
from contextlib import contextmanager
import getpass

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EASY_CATCHER_DIR = os.path.join(ROOT_DIR, 'easy-catcher')


@contextmanager
def _redirect_prints(log_cb=None):
    """Capture stdout and stderr prints and forward to log_cb if provided."""
    old_stdout = sys.stdout
    old_stderr = sys.stderr

    class TeeWriter:
        def write(self, text):
            # Only forward non-empty text
            if log_cb and text.strip():
                # Split by newlines to handle multiple lines in one write
                for line in text.rstrip('\n').split('\n'):
                    # Filter out tqdm's carriage returns to avoid mess
                    # Also strip ANSI codes if needed, but for now just stripped line
                    clean_line = line.strip().replace('\r', '')
                    if clean_line:
                        log_cb(clean_line)

        def flush(self):
            pass

    writer = TeeWriter()
    sys.stdout = writer
    sys.stderr = writer  # Capture stderr (where tqdm writes)
    try:
        yield
    finally:
        sys.stdout = old_stdout
        sys.stderr = old_stderr


def _load_easy_catcher_module():
    """Dynamically import easy_catcher.py from the submodule."""
    easy_catcher_path = os.path.join(EASY_CATCHER_DIR, 'easy_catcher.py')
    if not os.path.exists(easy_catcher_path):
        raise FileNotFoundError(f"Easy Catcher module not found: {easy_catcher_path}")

    # Ensure the submodule directory is in sys.path for its own imports (e.g., releasebook)
    if EASY_CATCHER_DIR not in sys.path:
        sys.path.insert(0, EASY_CATCHER_DIR)

    spec = importlib.util.spec_from_file_location('easy_catcher_module', easy_catcher_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def process_dumps(process_root, tool_paths, log_cb=None):
    """
    Adapter that wraps the easy-catcher submodule's process_folder() function.

    Args:
        process_root: Directory containing .dmp files to process.
        tool_paths:   Dict with keys 'CATCHER_EXE', 'CLG2TXT_EXE', 'DB_PATH'.
        log_cb:       Optional callback function for log messages.

    Returns:
        Path to the output .log file, or None on failure.
    """
    module = _load_easy_catcher_module()

    # Monkey-patch the module's global paths to use absolute toolkit settings
    catcher_exe = tool_paths.get(
        'CATCHER_EXE',
        os.path.join(EASY_CATCHER_DIR, 'catcher_mod', 'Catcher.exe'),
    )
    clg2txt_exe = tool_paths.get(
        'CLG2TXT_EXE',
        os.path.join(EASY_CATCHER_DIR, 'catcher_mod', 'Clg2Txt.exe'),
    )
    hex_ascii_exe = os.path.join(
        EASY_CATCHER_DIR, 'catcherLogFileToHexAndAscii', 'catcherLogToAscii.exe',
    )

    module.CATCHER_PATH = catcher_exe
    module.CLG2TXT_PATH = clg2txt_exe
    module.CATCHER_LOG_TO_HEX_AND_ASCII_PATH = hex_ascii_exe
    module.TEMP_FILENAME = os.path.join(process_root, 'tempfile.tmp')

    # Construct a config dict compatible with the submodule's expectations
    config = {
        'general': {
            'db_path': tool_paths.get('DB_PATH', ''),
            'sort_logs': True,
            'fw_type': 'public',
        },
        'login': {
            'username': '',
            'password': '',
        },
    }

    # Now that the submodule uses absolute paths for its own resources,
    # we no longer need to chdir — but it doesn't hurt for safety.
    # Monkey-patch getpass so it never blocks or crashes in the
    # non-interactive Streamlit environment (no console on Windows).
    _original_getpass = getpass.getpass

    def _no_interactive_getpass(prompt='Password: ', stream=None):
        raise RuntimeError(
            'Interactive password prompt is not available in the web UI. '
            'Please configure Releasebook credentials or provide a local '
            'Catcher database path in the toolkit settings.'
        )

    # Monkey-patch Releasebook.download_release_file to try both 'public' and 'private'
    # regardless of what's in the config, as fallback.
    Releasebook = module.Releasebook
    _original_download_release_file = Releasebook.download_release_file

    def _smart_download_release_file(self, release_data, out_file, file_type='public'):
        # 1. Try variable as requested
        res = _original_download_release_file(self, release_data, out_file, file_type)
        if res:
            return res
        
        # 2. If valid failure, try the alternative
        alt_type = 'private' if file_type == 'public' else 'public'
        # Log via print because we are inside _redirect_prints context
        print(f"Firmware type '{file_type}' not found, trying '{alt_type}'...")
        res = _original_download_release_file(self, release_data, out_file, file_type=alt_type)
        return res

    # Monkey-patch copy_catcher_db to search deeply in db_path (Release Vault) 
    # before attempting download.
    import shutil
    _original_copy_catcher_db = module.copy_catcher_db

    def _smart_copy_catcher_db(config, db_version, db_spec_id, dst_path, db_folder_name):
        base_db_path = config['general']['db_path']
        folder_name = "FMB.Ver.{}".format(db_version)
        if db_spec_id != '1':
            folder_name += "_{}".format(db_spec_id)
            
        # Check if standard location exists first (ReleaseVault/FMB.Ver.XX/Database)
        standard_path = os.path.join(base_db_path, folder_name, "Database")
        if os.path.exists(standard_path):
             return _original_copy_catcher_db(config, db_version, db_spec_id, dst_path, db_folder_name)

        # Search in immediate subdirectories (ReleaseVault/*/FMB.Ver.XX/Database)
        found_src = None
        try:
            if os.path.exists(base_db_path):
                for entry in os.scandir(base_db_path):
                    if entry.is_dir():
                        candidate = os.path.join(entry.path, folder_name, "Database")
                        if os.path.exists(candidate):
                            found_src = candidate
                            break
        except Exception:
            pass

        if found_src:
            print(f"Found local database for {folder_name} at: {found_src}")
            dst_db_path = os.path.join(dst_path, db_folder_name)
            if not os.path.exists(dst_db_path):
                shutil.copytree(found_src, dst_db_path)
            # We return True to indicate success, mimicking original function behavior
            return True
            
        # If not found, fall back to original (which will try download)
        return _original_copy_catcher_db(config, db_version, db_spec_id, dst_path, db_folder_name)

    original_cwd = os.getcwd()
    try:
        os.chdir(EASY_CATCHER_DIR)
        getpass.getpass = _no_interactive_getpass
        Releasebook.download_release_file = _smart_download_release_file
        module.copy_catcher_db = _smart_copy_catcher_db

        with _redirect_prints(log_cb):
            output_log = module.process_folder(process_root, config)

        return output_log  # path to the .log file, or None on failure
    except Exception as exc:
        if log_cb:
            log_cb(f'Error during Easy Catcher processing: {exc}')
        return None
    finally:
        getpass.getpass = _original_getpass
        Releasebook.download_release_file = _original_download_release_file
        module.copy_catcher_db = _original_copy_catcher_db
        os.chdir(original_cwd)
