"""The Streamlit page: pick an iPhone folder, pick an iPad folder, upload.

Everything else has a sensible default and lives under *Advanced*. Run it with::

    streamlit run streamlit_app.py
    # or: appstore-snapshots ui
"""

from __future__ import annotations

import threading
from pathlib import Path

import streamlit as st

from appstore_snapshots.connect import (
    AppStoreConnectClient,
    Credentials,
    SnapshotUploader,
    UploadOptions,
    env,
)
from appstore_snapshots.errors import SnapshotError
from appstore_snapshots.models import ProgressEvent, ScanResult
from appstore_snapshots.naming import APP_STORE_LOCALES
from appstore_snapshots.scanning import DEFAULT_LOCALE, SnapshotConfig, scan_devices
from appstore_snapshots.ui.folder_picker import folder_input

#: Always on the page.
BASE_SLOTS = (
    ("iphone", "iPhone folder", "…/screenshots/iPhone-6.9"),
    ("ipad", "iPad folder", "…/screenshots/iPad-13-Landscape"),
)

#: Ticked on at the top when you have them. Label -> slot.
OPTIONAL_SLOTS = {
    "Apple Watch": ("watch", "Apple Watch folder", "…/screenshots/Apple-Watch-Ultra"),
    "Mac": ("mac", "Mac folder", "…/screenshots/Mac"),
}


def main() -> None:
    st.set_page_config(page_title="App Store Snapshots", page_icon="📱")
    env.load()
    st.title("App Store snapshots")

    folders, default_locale, extra = _pick_folders()
    result = _scan(folders, default_locale)
    credentials, bundle_id = _app_store_config()
    _upload_section(result, credentials, bundle_id, extra)


# --------------------------------------------------------------------- folders


def _pick_folders() -> tuple[list[Path], str, dict]:
    st.subheader("Screenshots")
    st.caption("One folder per device — language sub-folders if any, otherwise **en-US**.")

    checkboxes = st.columns(len(OPTIONAL_SLOTS) + 1)
    wanted = [
        slot
        for column, (label, slot) in zip(checkboxes, OPTIONAL_SLOTS.items(), strict=False)
        if column.checkbox(label)
    ]

    folders: list[Path] = []
    for key, label, placeholder in (*BASE_SLOTS, *wanted):
        folder = folder_input(label, key=key, placeholder=placeholder)
        if folder:
            folders.append(folder)

    with st.expander("Advanced"):
        # Keys matter here: the upload does a rerun to disable its button, and
        # only keyed widgets keep their value across it.
        default_locale = st.selectbox(
            "Locale for screenshots with no language folder",
            APP_STORE_LOCALES,
            index=APP_STORE_LOCALES.index(DEFAULT_LOCALE),
            key="default_locale",
        )
        extra = {
            "replace": st.toggle(
                "Replace the screenshots already in each set",
                value=True,
                key="replace_existing",
                help="Off = append. A set holds at most 10 images, so appending overflows fast.",
            )
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

    try:
        key_id, issuer_id = env.require_key_and_issuer()
    except SnapshotError as exc:
        st.error(str(exc))
        return None, ""

    key_path = env.get(env.KEY_PATH)
    st.caption(
        f"Key ID `{key_id}`, Issuer ID"
        + (f" and `{Path(key_path).name}`" if key_path else "")
        + " from `.env`",
        help=str(env.source()),
    )

    credentials = None
    try:
        if key_path:
            credentials = Credentials.from_p8_file(key_path, key_id, issuer_id)
        else:
            # No ASC_KEY_PATH in .env — take the key through the browser instead.
            uploaded = st.file_uploader("Private key (.p8)", type=["p8"])
            if uploaded is not None:
                credentials = Credentials.from_p8_bytes(uploaded.getvalue(), key_id, issuer_id)
    except SnapshotError as exc:
        st.error(str(exc))

    bundle_id = st.text_input(
        "App bundle ID",
        value=env.get(env.BUNDLE_ID),
        placeholder="com.example.myapp",
    ).strip()

    return credentials, bundle_id


# ---------------------------------------------------------------------- upload


def _missing(
    result: ScanResult | None, credentials: Credentials | None, bundle_id: str
) -> list[str]:
    """What still has to be filled in, phrased as things to fix."""
    problems = []
    if not result or not result.sets:
        problems.append("Choose a device folder that has screenshots in it.")
    if not credentials:
        problems.append("Add the .p8 private key — set `ASC_KEY_PATH` in .env or upload it above.")
    if not bundle_id:
        problems.append("Fill in the app bundle ID.")
    return problems


def _upload_section(
    result: ScanResult | None,
    credentials: Credentials | None,
    bundle_id: str,
    extra: dict,
) -> None:
    st.divider()

    dry_run = st.checkbox("Dry run — plan it, change nothing", key="dry_run")
    total = result.total_screenshots if result else 0
    uploading = st.session_state.get("uploading", False)

    verb = "Simulate" if dry_run else "Upload"
    label = f"{verb} {total} screenshot(s)" if total else verb
    # The button stays enabled so pressing it explains what is missing, rather
    # than a permanent "still needed" notice sitting under an empty form.
    clicked = st.button(
        "Uploading…" if uploading else label,
        type="primary",
        disabled=uploading,
        width="stretch",
    )

    if clicked and not uploading:
        problems = _missing(result, credentials, bundle_id)
        if problems:
            for problem in problems:
                st.error(problem, icon="⚠️")
            return
        # Re-run first so the button is re-rendered disabled *before* the upload
        # starts; otherwise it stays live for the whole run and can be pressed twice.
        st.session_state["uploading"] = True
        st.rerun()

    if uploading:
        try:
            outcome = _run_upload(result, credentials, bundle_id, extra, dry_run)  # type: ignore[arg-type]
        except Exception as exc:  # never leave the button stuck on "Uploading…"
            outcome = {"error": str(exc), "lines": []}
        finally:
            st.session_state["uploading"] = False
        # Stash the outcome and re-run, so the button comes back enabled with the
        # result still on screen instead of staying disabled until the next click.
        st.session_state["last_run"] = outcome
        st.rerun()

    _render_last_run()


def _render_last_run() -> None:
    """Show the previous run's outcome, which survived the re-enabling re-run."""
    outcome = st.session_state.get("last_run")
    if not outcome:
        return

    if outcome.get("version"):
        st.info(outcome["version"], icon="🏷️")
    if outcome.get("error"):
        st.error(outcome["error"])
    for message in outcome.get("errors", []):
        st.error(message)
    if outcome.get("success"):
        st.success(outcome["success"])
    if outcome.get("warning"):
        st.warning(outcome["warning"], icon="⚠️")
    if outcome.get("lines"):
        with st.expander(f"Log — {len(outcome['lines'])} line(s)"):
            for line in outcome["lines"]:
                st.write(line)


def _run_upload(
    result: ScanResult,
    credentials: Credentials,
    bundle_id: str,
    extra: dict,
    dry_run: bool,
) -> dict:
    """Do the upload, streaming progress live, and return what to show afterwards."""
    progress = st.progress(0.0, text="Connecting…")
    log = st.container(height=280)
    lines: list[str] = []
    pending: list[str] = []
    icons = {"file_error": "❌", "set_start": "📦", "file_done": "✅", "done": "🏁"}
    outcome: dict = {"lines": lines}

    def write(line: str) -> None:
        lines.append(line)
        log.write(line)

    def on_progress(event: ProgressEvent) -> None:
        # Parallel uploads call back from worker threads, which have no Streamlit
        # script context — buffer those and flush on the next main-thread event.
        pending.append(f"{icons.get(event.kind, '•')} {event.message}")
        if threading.current_thread() is not threading.main_thread():
            return
        if event.total:
            progress.progress(min(event.fraction, 1.0), text=event.message[:110])
        for line in pending:
            write(line)
        pending.clear()

    client = AppStoreConnectClient(credentials)
    try:
        app = client.find_app(bundle_id)
        if not app:
            raise SnapshotError(f"No app with bundle ID {bundle_id!r} is visible to this API key.")
        write(f"📱 {app.name}")

        version = client.latest_editable_version(app.id)
        if not version:
            raise SnapshotError(
                "This app has no App Store version whose metadata can be edited. "
                "Create the next version in App Store Connect first."
            )
        # Name the version on the page, not just in the log — writing to the wrong
        # one is the quiet way for an upload to look like it did nothing.
        outcome["version"] = (
            f"Wrote to **{app.name}** version **{version.version_string}** ({version.state})."
        )
        st.info(outcome["version"], icon="🏷️")

        report = SnapshotUploader(
            client,
            UploadOptions(replace_existing=extra["replace"], dry_run=dry_run),
            on_progress=on_progress,
        ).upload(version.id, result.sets)
    except Exception as exc:
        progress.empty()
        outcome["error"] = str(exc)
        return outcome

    progress.progress(1.0, text="Finished")
    if report.errors:
        outcome["errors"] = list(report.errors)
    elif dry_run:
        outcome["success"] = (
            f"Dry run OK — {report.uploaded} screenshot(s) would be uploaded, "
            f"{report.deleted} existing one(s) removed first. Nothing was changed."
        )
    else:
        outcome["success"] = (
            f"Uploaded {report.uploaded} screenshot(s) and removed {report.deleted} old one(s) "
            f"across {report.sets_touched} set(s). Check them in App Store Connect."
        )
        if extra["replace"] and report.deleted == 0:
            outcome["warning"] = (
                "Replace was on but there was nothing to remove — those sets were already "
                "empty. If you expected old screenshots to be swapped out, check that the "
                "version named above is the one you are looking at in App Store Connect."
            )
        st.balloons()
    return outcome


if __name__ == "__main__":
    main()
