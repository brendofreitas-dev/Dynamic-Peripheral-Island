"""Dynamic Peripheral Island (dpi_core) — core hardware telemetry & control package."""

from __future__ import annotations

from .hardware import (
    AjazzMouseDriver,
    FuxiHeadsetDriver,
    GamepadDriver,
    HardwareHubManager,
    K500KeyboardDriver,
    build_packet,
    is_activity_fresh,
    validate_hid_frame,
    verify_checksum,
)

__version__ = "1.0.0"

__all__ = [
    "__version__",
    "AjazzMouseDriver",
    "FuxiHeadsetDriver",
    "K500KeyboardDriver",
    "GamepadDriver",
    "HardwareHubManager",
    "build_packet",
    "verify_checksum",
    "validate_hid_frame",
    "is_activity_fresh",
]
