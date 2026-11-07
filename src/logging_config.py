
# ==========================================
# 1. IMPORTS
# ==========================================

# Import logging to record pipeline events and errors.
import logging

# Import Path to manage project directories.
from pathlib import Path


# ==========================================
# 2. LOGGING CONFIGURATION
# ==========================================

def configure_logging(project_root: Path) -> logging.Logger:
    """
    Configure file and console logging for the restaurant pipeline.

    Args:
        project_root: Root directory of the project.

    Returns:
        Configured restaurant pipeline logger.
    """

    # Define the directory where pipeline logs will be stored.
    log_dir = project_root / "data" / "logs"

    # Create the directory if it does not already exist.
    log_dir.mkdir(parents=True, exist_ok=True)

    # Define the log file path.
    log_file = log_dir / "restaurant_pipeline.log"

    # Create a dedicated logger for the restaurant pipeline.
    logger = logging.getLogger("restaurant_pipeline")

    # Record informational messages and more serious events.
    logger.setLevel(logging.INFO)

    # Prevent duplicate handlers if configuration runs again.
    if not logger.handlers:

        # Define a consistent format for every log message.
        formatter = logging.Formatter(
            fmt="%(asctime)s | %(levelname)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )

        # Create a handler that writes logs to a file.
        file_handler = logging.FileHandler(
            log_file,
            encoding="utf-8"
        )

        # Create a handler that displays logs in the terminal.
        console_handler = logging.StreamHandler()

        # Apply the same format to both handlers.
        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)

        # Attach both handlers to the pipeline logger.
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)

    return logger
