"""
Adapter module to integrate the easy-catcher submodule with the Alps Toolkit.

Wraps the submodule's process_folder() into a process_dumps() function
compatible with the toolkit's Easy Catcher page (pages/4_📊_Easy_Catcher.py).
"""

import os
import sys
import importlib.util
from contextlib import contextmanager

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EASY_CATCHER_DIR = os.path.join(ROOT_DIR, 'easy-catcher')


@contextmanager
def _redirect_prints(log_cb=None):
    """Capture stdout prints and forward to log_cb if provided."""
    old_stdout = sys.stdout

    class TeeWriter:
        def write(self, text):
            if log_cb and text.strip():
                for line in text.rstrip('\n').split('\n'):
                    if line.strip():
                        log_cb(line)

        def flush(self):
            pass

    sys.stdout = TeeWriter()
    try:
        yield
    finally:
        sys.stdout = old_stdout


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
        },
        'login': {
            'username': '',
            'password': '',
        },
    }

    # Now that the submodule uses absolute paths for its own resources,
    # we no longer need to chdir — but it doesn't hurt for safety.
    original_cwd = os.getcwd()
    try:
        os.chdir(EASY_CATCHER_DIR)

        with _redirect_prints(log_cb):
            output_log = module.process_folder(process_root, config)

        return output_log  # path to the .log file, or None on failure
    finally:
        os.chdir(original_cwd)
