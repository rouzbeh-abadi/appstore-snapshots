"""Upload App Store screenshots laid out as ``<device>/<language>/*.png``."""

from __future__ import annotations

from .auth import Credentials, TokenProvider
from .client import App, AppStoreConnectClient, AppStoreVersion
from .config import SnapshotConfig
from .display_types import DISPLAY_TYPE_LABELS, DISPLAY_TYPES, resolve_display_type
from .errors import (
    ApiError,
    CredentialsError,
    ScanError,
    SnapshotError,
    UnknownDeviceError,
    UnknownLocaleError,
    UploadError,
)
from .locales import APP_STORE_LOCALES, resolve_locale
from .models import ProgressEvent, ScanResult, Screenshot, ScreenshotSet, UploadReport
from .scanner import DEFAULT_LOCALE, device_display_type, scan, scan_device, scan_devices
from .uploader import SnapshotUploader, UploadOptions

__version__ = "0.1.0"

__all__ = [
    "APP_STORE_LOCALES",
    "DEFAULT_LOCALE",
    "DISPLAY_TYPES",
    "DISPLAY_TYPE_LABELS",
    "ApiError",
    "App",
    "AppStoreConnectClient",
    "AppStoreVersion",
    "Credentials",
    "CredentialsError",
    "ProgressEvent",
    "ScanError",
    "ScanResult",
    "Screenshot",
    "ScreenshotSet",
    "SnapshotConfig",
    "SnapshotError",
    "SnapshotUploader",
    "TokenProvider",
    "UnknownDeviceError",
    "UnknownLocaleError",
    "UploadError",
    "UploadOptions",
    "UploadReport",
    "__version__",
    "device_display_type",
    "resolve_display_type",
    "resolve_locale",
    "scan",
    "scan_device",
    "scan_devices",
]
