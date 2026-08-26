import uvicorn

from apps.email_MCP.config import EmailMCPSettings, get_settings
from apps.email_MCP.server import create_app
from shared.logging import configure_logging, get_logger


def main(settings: EmailMCPSettings | None = None) -> None:
    resolved_settings = settings or get_settings()
    configure_logging(resolved_settings.log_level)

    logger = get_logger(__name__)
    logger.info(
        "Starting %s on %s:%s%s",
        resolved_settings.app_name,
        resolved_settings.host,
        resolved_settings.port,
        resolved_settings.streamable_http_path,
    )
    uvicorn.run(
        create_app(resolved_settings),
        host=resolved_settings.host,
        port=resolved_settings.port,
        log_level=resolved_settings.log_level.lower(),
    )


if __name__ == "__main__":
    main()
