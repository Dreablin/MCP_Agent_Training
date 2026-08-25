from pathlib import Path

from nicegui import ui


def render_app_status(
    *,
    app_name: str,
    host: str,
    port: int,
    db_path: Path,
    openapi_path: str = "/docs",
    show_openapi_link: bool = True,
    title: str = "Состояние приложения",
    address_label: str = "Адрес",
    database_label: str = "База данных",
) -> None:
    with ui.card().classes("w-full max-w-xl"):
        ui.label(title).classes("text-h6")
        ui.label(app_name)
        ui.label(f"{address_label}: http://{host}:{port}")
        ui.label(f"{database_label}: {db_path}")
        if show_openapi_link:
            ui.link("OpenAPI", openapi_path)
