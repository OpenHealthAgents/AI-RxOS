import contextvars
import logging

from pythonjsonlogger import jsonlogger

request_id_ctx = contextvars.ContextVar("request_id", default="unknown")
trace_id_ctx = contextvars.ContextVar("trace_id", default="unknown")


class RequestContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_ctx.get()
        record.trace_id = trace_id_ctx.get()
        return True


def set_request_context(
    request_id: str | None = None, trace_id: str | None = None
) -> None:
    if request_id:
        request_id_ctx.set(request_id)
    if trace_id:
        trace_id_ctx.set(trace_id)


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = jsonlogger.JsonFormatter(
            "%(asctime)s %(levelname)s %(name)s %(request_id)s %(trace_id)s %(message)s"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.addFilter(RequestContextFilter())
        logger.setLevel(logging.INFO)
    return logger
