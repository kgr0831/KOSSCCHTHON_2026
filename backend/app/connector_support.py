"""Shared, non-secret selection rules for paired CLI connector PCs."""


def selected_cli_connection(settings, *, provider=None, device_id=None):
    if not settings:
        return None
    family = provider if provider is not None else settings.cli_provider
    device = device_id if device_id is not None else settings.cli_device_id
    return next((item for item in settings.cli_connections
                 if item.get("provider") == family and item.get("device_id") == device), None)


def connector_execution_target(settings):
    connection = selected_cli_connection(settings)
    if (settings and settings.transport in ("cli", "hybrid") and connection
            and connection.get("status") == "connected" and settings.cli_device_id):
        return "pc:" + settings.cli_device_id
    return "server"
