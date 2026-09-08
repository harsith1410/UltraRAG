"""Central logging setup: one console stream plus a rotating file, shared by every module.

Call setup_logging() once at process start (main.py does). Everywhere else just do
`logger = logging.getLogger(__name__)` and log — the handlers live on the root logger.
"""
import logging
import logging.handlers
import os

from dotenv import load_dotenv

load_dotenv()

LOG_DIR = os.getenv("LOG_DIR", os.path.join(".", "logs"))
LOG_FILE = os.path.join(LOG_DIR, "rag.log")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
MAX_BYTES = 5 * 1024 * 1024
BACKUP_COUNT = 3

FORMAT = "%(asctime)s %(levelname)-8s %(name)-24s %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# these chatter at INFO/DEBUG about every socket and retry; we only want their problems
NOISY = ("httpx", "httpcore", "urllib3", "chromadb", "groq", "openai", "asyncio",
         "googleapiclient", "google", "google_auth_httplib2", "PIL", "watchfiles",
         "multipart", "sqlalchemy.engine")

_configured = False


def setup_logging(level: str = None) -> logging.Logger:
    """Attach handlers to the root logger. Safe to call more than once."""
    global _configured

    root = logging.getLogger()
    if _configured:
        return root

    resolved = (level or LOG_LEVEL).upper()
    root.setLevel(getattr(logging, resolved, logging.INFO))

    formatter = logging.Formatter(FORMAT, datefmt=DATE_FORMAT)

    console = logging.StreamHandler()
    console.setFormatter(formatter)
    root.addHandler(console)

    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            LOG_FILE, maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT, encoding="utf-8"
        )
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)
    except OSError as e:
        # a read-only or missing volume shouldn't stop the app from starting
        root.warning("file logging disabled (%s): %s", LOG_FILE, e)

    for name in NOISY:
        logging.getLogger(name).setLevel(logging.WARNING)

    _configured = True
    root.info("logging ready | level=%s file=%s", resolved, LOG_FILE)
    return root
