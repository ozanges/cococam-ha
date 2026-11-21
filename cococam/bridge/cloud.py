"""Shared CloudEdge account and camera selection."""

import os
import sys


def cloud_client(config):
    upstream = os.getenv("COCOCAM_UPSTREAM", "/opt/meari")
    if upstream not in sys.path:
        sys.path.insert(0, upstream)
    from debug_tools.bootstrap import _bootstrap_integration_modules

    modules = _bootstrap_integration_modules()
    api_module = modules["api"]
    api_module._password_variants = lambda value: [value]
    api = api_module.MeariApiClient(
        email=config["email"], password=config["password"],
        country_code=config.get("country", "FR"), phone_code=config.get("phone_code", "33"),
        app_profile="cloudedge",
    )
    return api, modules


def select_camera(api, config):
    name = (config.get("camera_name") or "").strip()
    matches = [device for device in api.get_camera_devices() if not name or device.get("deviceName") == name]
    return matches[0] if len(matches) == 1 else None
