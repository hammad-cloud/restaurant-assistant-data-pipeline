# ==========================================
# 1. IMPORTS
# ==========================================

# Import os to pass the src folder to the child process
import os

# Import subprocess to run a failing script in a separate Python process
import subprocess

# Import sys to reuse the current Python interpreter
import sys

# Import Path to locate the src folder
from pathlib import Path


# ==========================================
# 2. TEST HELPERS
# ==========================================

# Locate the src folder so the child process can import logging_config
SRC_DIR = Path(__file__).resolve().parent.parent / "src"

# Script that mirrors the pipeline's hook setup, then fails on purpose
FAILING_SCRIPT = """
import sys
from pathlib import Path
from logging_config import configure_logging, handle_uncaught_exception

logger = configure_logging(Path(__file__).parent)
sys.excepthook = lambda exception_type, exception, traceback: (
    handle_uncaught_exception(exception_type, exception, traceback, logger)
)

logger.info("Restaurant data pipeline started.")
raise {error}
logger.info("Restaurant data pipeline completed successfully.")
"""


def run_failing_script(tmp_path, error):
    """
    Run the failing script inside tmp_path and return the result and log text.
    """

    # Write the script into the temporary folder, away from real data
    script = tmp_path / "failing_pipeline.py"
    script.write_text(FAILING_SCRIPT.format(error=error), encoding="utf-8")

    # Run it as a real process so the exception hook and exit code are real
    result = subprocess.run(
        [sys.executable, str(script)],
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": str(SRC_DIR)}
    )

    # Read the log written under the temporary folder
    log_file = tmp_path / "data" / "logs" / "restaurant_pipeline.log"
    return result, log_file.read_text(encoding="utf-8")


# ==========================================
# 3. UNEXPECTED EXCEPTION TESTS
# ==========================================

def test_unexpected_exception_is_logged_with_traceback(tmp_path):
    result, log_text = run_failing_script(
        tmp_path, 'RuntimeError("simulated pipeline failure")'
    )

    # The failure and its complete traceback are in the log file
    assert "CRITICAL | Unexpected pipeline failure." in log_text
    assert "Traceback (most recent call last):" in log_text
    assert "RuntimeError: simulated pipeline failure" in log_text

    # The traceback is still shown in the terminal
    assert "RuntimeError: simulated pipeline failure" in result.stderr

    # The process reports failure and never logs success
    assert result.returncode != 0
    assert "completed successfully" not in log_text


def test_keyboard_interrupt_is_not_logged_as_failure(tmp_path):
    result, log_text = run_failing_script(tmp_path, "KeyboardInterrupt")

    # Ctrl+C is not recorded as a pipeline failure
    assert "Unexpected pipeline failure." not in log_text

    # Python's default handler still reports it and exits with an error
    assert "KeyboardInterrupt" in result.stderr
    assert result.returncode != 0
    assert "completed successfully" not in log_text
