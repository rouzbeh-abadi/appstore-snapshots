"""The Streamlit page: pick an iPhone folder, pick an iPad folder, upload.

Everything else has a sensible default and lives under *Advanced*. Run it with::

    streamlit run streamlit_app.py
    # or: appstore-snapshots ui
"""

from __future__ import annotations

import os
import threading
from pathlib import Path

import streamlit as st

from appstore_snapshots.auth import Credentials, key_id_from_filename
from appstore_snapshots.client import AppStoreConnectClient
from appstore_snapshots.config import SnapshotConfig
from appstore_snapshots.errors import SnapshotError
from appstore_snapshots.locales import APP_STORE_LOCALES
from appstore_snapshots.models import ProgressEvent, ScanResult
from appstore_snapshots.scanner import DEFAULT_LOCALE, scan_devices
from appstore_snapshots.ui.folder_picker import folder_input
from appstore_snapshots.uploader import SnapshotUploader, UploadOptions

#: The two slots on the page. More can be added under Advanced.
SLOTS = (
    ("iphone", "iPhone folder", "…/screenshots/iPhone-6.9"),
    ("ipad", "iPad folder", "…/screenshots/iPad-13-Landscape"),
)


def main() -> None:
    st.set_page_config(page_title="App Store Snapshots", page_icon="📱")
    st.title("📱 App Store snapshots")

    folders, default_locale, extra = _pick_folders()
    result = _scan(folders, default_locale)
    credentials, bundle_id = _app_store_config()
    _upload_section(result, credentials, bundle_id, extra)


# --------------------------------------------------------------------- folders


def _pick_folders() -> tuple[list[Path], str, dict]:
    st.subheader("Screenshots")
    st.caption(
        "One folder per device. Screenshots inside are used as **en-US** unless the "
        "folder has language sub-folders (`de-DE`, `fr-FR`, …)."
    )

    folders: list[Path] = []
    for key, label, placeholder in SLOTS:
        folder = folder_input(label, key=key, placeholder=placeholder)
        if folder:
            folders.append(folder)

    with st.expander("Advanced"):
        default_locale = st.selectbox(
            "Locale for screenshots with no language folder",
            APP_STORE_LOCALES,
            index=APP_STORE_LOCALES.index(DEFAULT_LOCALE),
        )
        more = st.text_area(
            "More device folders",
            placeholder="One path per line — for a second iPhone size, a Mac, a Watch…",
            height=70,
        )
        for line in more.splitlines():
            if line.strip():
                folders.append(Path(line.strip()).expanduser())

        extra = {
            "replace": st.toggle(
                "Replace the screenshots already in each set",
                value=True,
                help="Off = append. A set holds at most 10 images, so appending overflows fast.",
            ),
            "version_id": st.text_input(
                "Version ID", placeholder="Leave empty for the latest editable version"
            ).strip(),
        }

    return folders, default_locale, extra


def _scan(folders: list[Path], default_locale: str) -> ScanResult | None:
    if not folders:
        return None

    # Pick up a snapshots.json sitting next to the folders, same as the CLI does.
    try:
        config = SnapshotConfig.discover(folders[0])
    except SnapshotError as exc:
        st.warning(f"Ignoring config file: {exc}")
        config = SnapshotConfig()
    if config.source:
        st.caption(f"Folder-name overrides from `{config.source}`")

    try:
        result = scan_devices(
            folders,
            default_locale=default_locale,
            device_overrides=config.devices,
            locale_overrides=config.languages,
        )
    except (SnapshotError, OSError) as exc:
        st.error(str(exc))
        return None

    for folder in folders:
        sets = [s for s in result.sets if s.source and folder in (s.source, *s.source.parents)]
        if sets:
            languages = ", ".join(sorted({s.locale for s in sets}))
            st.success(
                f"**{folder.name}** → {sets[0].display_type} · "
                f"{sum(len(s) for s in sets)} screenshot(s) · {languages}",
                icon="✅",
            )

    for issue in result.issues:
        st.warning(f"**{issue.path.name}** — {issue.reason}", icon="⚠️")
    return result


# ----------------------------------------------------------- app store config


def _app_store_config() -> tuple[Credentials | None, str]:
    st.subheader("App Store Connect")
    st.caption(
        "From **Users and Access → Integrations → Keys**: the `.p8` file, the Key ID "
        "beside it, and the Issuer ID above the table."
    )

    uploaded = st.file_uploader("Private key (.p8)", type=["p8"])
    p8_path = st.text_input(
        "…or path to the .p8 on this machine",
        value=os.environ.get("ASC_KEY_PATH", ""),
        placeholder="~/private_keys/AuthKey_ABCD123456.p8",
    ).strip()

    guessed = os.environ.get("ASC_KEY_ID", "")
    if uploaded is not None:
        guessed = key_id_from_filename(uploaded.name) or guessed
    elif p8_path:
        guessed = key_id_from_filename(p8_path) or guessed

    left, right = st.columns(2)
    key_id = left.text_input("Key ID", value=guessed, placeholder="ABCD123456")
    issuer_id = right.text_input(
        "Issuer ID",
        value=os.environ.get("ASC_ISSUER_ID", ""),
        placeholder="69a6de70-…",
    )
    bundle_id = st.text_input(
        "App bundle ID",
        value=os.environ.get("ASC_BUNDLE_ID", ""),
        placeholder="com.example.myapp",
    ).strip()

    credentials = None
    if (uploaded is not None or p8_path) and key_id and issuer_id:
        try:
            credentials = (
                Credentials.from_p8_bytes(uploaded.getvalue(), key_id, issuer_id)
                if uploaded is not None
                else Credentials.from_p8_file(p8_path, key_id, issuer_id)
            )
        except SnapshotError as exc:
            st.error(str(exc))

    return credentials, bundle_id


# ---------------------------------------------------------------------- upload


def _upload_section(
    result: ScanResult | None,
    credentials: Credentials | None,
    bundle_id: str,
    extra: dict,
) -> None:
    st.divider()

    missing = []
    if not result or not result.sets:
        missing.append("a device folder with screenshots in it")
    if not credentials:
        missing.append("the .p8 file, Key ID and Issuer ID")
    if not bundle_id:
        missing.append("the app bundle ID")
    if missing:
        st.info("Still needed: " + "; ".join(missing) + ".")
        return

    assert result is not None and credentials is not None
    total = result.total_screenshots
    dry_run = st.checkbox("Dry run — plan it, change nothing", value=False)
    label = f"{'Simulate' if dry_run else 'Upload'} {total} screenshot(s)"
    if not st.button(label, type="primary"):
        return

    _run_upload(result, credentials, bundle_id, extra, dry_run)


def _run_upload(
    result: ScanResult,
    credentials: Credentials,
    bundle_id: str,
    extra: dict,
    dry_run: bool,
) -> None:
    progress = st.progress(0.0, text="Connecting…")
    log = st.container(height=280)
    pending: list[str] = []
    icons = {"file_error": "❌", "set_start": "📦", "file_done": "✅", "done": "🏁"}

    def on_progress(event: ProgressEvent) -> None:
        # Parallel uploads call back from worker threads, which have no Streamlit
        # script context — buffer those and flush on the next main-thread event.
        pending.append(f"{icons.get(event.kind, '•')} {event.message}")
        if threading.current_thread() is not threading.main_thread():
            return
        if event.total:
            progress.progress(min(event.fraction, 1.0), text=event.message[:110])
        for line in pending:
            log.write(line)
        pending.clear()

    client = AppStoreConnectClient(credentials)
    try:
        app = client.find_app(bundle_id)
        if not app:
            raise SnapshotError(f"No app with bundle ID {bundle_id!r} is visible to this API key.")
        log.write(f"📱 {app.name}")

        version_id = extra["version_id"]
        if not version_id:
            version = client.latest_editable_version(app.id)
            if not version:
                raise SnapshotError(
                    "This app has no App Store version whose metadata can be edited. "
                    "Create the next version in App Store Connect first."
                )
            log.write(f"🏷️ Version {version.version_string} ({version.state})")
            version_id = version.id

        report = SnapshotUploader(
            client,
            UploadOptions(replace_existing=extra["replace"], dry_run=dry_run),
            on_progress=on_progress,
        ).upload(version_id, result.sets)
    except Exception as exc:
        progress.empty()
        st.error(str(exc))
        return

    progress.progress(1.0, text="Finished")
    if report.errors:
        for error in report.errors:
            st.error(error)
    elif dry_run:
        st.info(f"Dry run OK — {report.uploaded} screenshot(s) would be uploaded.")
    else:
        st.success(
            f"Uploaded {report.uploaded} screenshot(s). "
            "Check them in App Store Connect before submitting."
        )
        st.balloons()


if __name__ == "__main__":
    main()
