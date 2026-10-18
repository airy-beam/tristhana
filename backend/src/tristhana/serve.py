"""`tristhana-serve`: the container entry point (Cloud Run).

A script rather than a shell CMD, because exec-form CMD can't expand $PORT.
"""


def main() -> None:
    import uvicorn

    from tristhana.settings import get_settings

    uvicorn.run(
        "tristhana.main:app",
        host="0.0.0.0",  # noqa: S104 - only Google's front end reaches the container
        port=get_settings().port,
        workers=1,
        proxy_headers=True,
        forwarded_allow_ips="*",
        access_log=False,  # Cloud Run already writes a request log
        log_config=None,  # keep our JSON logging (tristhana.logs)
        timeout_graceful_shutdown=8,
    )
