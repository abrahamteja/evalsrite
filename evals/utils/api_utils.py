import logging
import os

import backoff

EVALS_THREAD_TIMEOUT = float(os.environ.get("EVALS_THREAD_TIMEOUT", "40"))
EVALS_API_RETRY_MAX_TIME = float(os.environ.get("EVALS_API_RETRY_MAX_TIME", "300"))
logging.getLogger("httpx").setLevel(logging.WARNING)  # suppress "OK" logs from openai API calls


def create_retrying(func: callable, retry_exceptions: tuple[Exception], *args, **kwargs):
    """
    Retries given function if one of given exceptions is raised.

    Gives up after EVALS_API_RETRY_MAX_TIME seconds (default 300) so a
    persistent RateLimit/outage cannot hang an eval worker forever.
    """

    @backoff.on_exception(
        backoff.expo,
        retry_exceptions,
        max_value=60,
        factor=1.5,
        max_time=EVALS_API_RETRY_MAX_TIME,
    )
    def _call():
        return func(*args, **kwargs)

    return _call()
