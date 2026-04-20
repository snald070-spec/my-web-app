import logging
import logging.config
import os

def setup_logging():
    level = os.environ.get("LOG_LEVEL", "INFO").upper()
    log_dir = os.environ.get("LOG_DIR", os.path.join(os.path.dirname(__file__), "..", "logs"))
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, os.environ.get("LOG_FILE", "app.log"))
    error_log_file = os.path.join(log_dir, os.environ.get("ERROR_LOG_FILE", "error.log"))
    max_bytes = int(os.environ.get("LOG_MAX_BYTES", 2 * 1024 * 1024))  # 2MB 기본값
    backup_count = int(os.environ.get("LOG_BACKUP_COUNT", 5))

    logging.config.dictConfig({
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": {
                "format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S",
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "default",
            },
            "file": {
                "class": "logging.handlers.RotatingFileHandler",
                "formatter": "default",
                "filename": log_file,
                "maxBytes": max_bytes,
                "backupCount": backup_count,
                "encoding": "utf-8",
            },
            "error_file": {
                "class": "logging.handlers.RotatingFileHandler",
                "formatter": "default",
                "filename": error_log_file,
                "maxBytes": max_bytes,
                "backupCount": backup_count,
                "encoding": "utf-8",
                "level": "ERROR",
            },
        },
        "root": {
            "level": level,
            "handlers": ["console", "file", "error_file"],
        },
        "loggers": {
            "uvicorn.error": {"level": level, "handlers": ["console", "file", "error_file"], "propagate": False},
            "uvicorn.access": {"level": level, "handlers": ["console", "file"], "propagate": False},
        },
    })

    # (선택) 향후 슬랙/메일 등 알림 연동은 커스텀 핸들러 추가로 확장 가능
