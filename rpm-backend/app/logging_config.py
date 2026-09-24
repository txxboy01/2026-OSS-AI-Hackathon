import logging.config


def configure_logging(level="INFO"):
    # Root and third-party handlers never emit input, provider payloads or tracebacks.
    # Only RPM's explicit, allowlisted event object goes to stdout.
    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": True,
            "formatters": {"safe": {"format": "%(message)s"}},
            "handlers": {
                "discard": {"class": "logging.NullHandler"},
                "safe": {"class": "logging.StreamHandler", "stream": "ext://sys.stdout", "formatter": "safe"},
            },
            "root": {"level": "CRITICAL", "handlers": ["discard"]},
            "loggers": {"rpm.events": {"level": level, "handlers": ["safe"], "propagate": False}},
        }
    )
