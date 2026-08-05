# appstore-snapshots

Upload App Store screenshots straight from your folders to App Store Connect —
no Fastlane, no Ruby.

The unit of work is a **device folder**: one folder holding the screenshots for
one device size. You point at an iPhone folder and an iPad folder, and each one
is read the way it happens to be arranged:

```
iPhone-6.9/                       <- pick this folder
  de-DE/   01_home.png  02_detail.png  03_settings.png
  en-US/   01_home.png  02_detail.png  03_settings.png
  es-ES/   …   es-MX/  …   fr-FR/  …
  it-IT/   …   pt-BR/  …   pt-PT/  …   zh-Hans/  …

iPad-13-Landscape/                <- and this one
  01.png                          <- no language folders here, so these
  02.png                             are taken as en-US
```

* **Language sub-folders present** → one screenshot set per language.
* **Screenshots sitting directly in the folder** → one set in the default locale
  (`en-US`, changeable).
* **Both** → the language folders win for their own locales, the loose files fill
  the default one.

From there it works out which App Store *screenshot display type* and *locale*
each folder means, creates the sets, uploads the images and puts them in order.

There is a command line interface and a Streamlit app.

---

## Install

Everything is managed by [uv](https://docs.astral.sh/uv/); the Python version is
pinned in `.python-version`, so this one command fetches Python 3.13, creates the
venv and installs every dependency:

```bash
cd appstore-snapshots
uv sync
```

## What you need from Apple

App Store Connect → **Users and Access → Integrations → Keys**, three things:

| Thing | Where | Notes |
| --- | --- | --- |
| **`.p8` private key** | “Download” next to the key | Downloadable **once**. Keep it out of git. |
| **Key ID** | The code in the key's row | Also inside the filename `AuthKey_<KeyID>.p8`, so the tool can usually infer it. |
| **Issuer ID** | The UUID above the key table | Same for every key in your team — this is the "other code". |

The key needs the **App Manager** role (or better) to edit version metadata.

Set them once in your shell if you like:

```bash
export ASC_KEY_PATH=~/private_keys/AuthKey_ABCD123456.p8
export ASC_KEY_ID=ABCD123456
export ASC_ISSUER_ID=69a6de70-xxxx-xxxx-xxxx-example
export ASC_BUNDLE_ID=com.example.myapp
```

Both the CLI and the UI pre-fill from these.

---

## Streamlit UI

```bash
uv run streamlit run streamlit_app.py
```

An ordinary Streamlit project — `streamlit_app.py` at the root, settings in
`.streamlit/config.toml`. (`uv run appstore-snapshots ui` opens the same page.)

The whole page is three things:

1. **iPhone folder** and **iPad folder** — type or paste a path, or press
   *Choose…* for the Finder dialog. Each one confirms what it found: the display
   type, the screenshot count and the languages.
2. **App Store Connect** — the `.p8` file (upload it or give its path), the Key ID,
   the Issuer ID and the app bundle ID. The key stays in memory; nothing is written
   to disk.
3. **Upload** — with a **dry run** checkbox that plans everything and changes
   nothing. It targets the newest editable version of the app by itself.

*Advanced* holds the rest: the locale for screenshots with no language folder,
extra device folders (a second iPhone size, a Mac, a Watch), replace-vs-append,
and pinning a specific version ID.

## Command line

Give it device folders with `-d` (repeatable), or a parent folder as a positional
argument to take every sub-folder as a device.

```bash
# See how the folders will be interpreted — no network calls
appstore-snapshots scan -d ./iPhone-6.9 -d ./iPad-13-Landscape

# Same thing, via the parent folder
appstore-snapshots scan ./screenshots

# Which apps and versions can this key see?
appstore-snapshots apps
appstore-snapshots versions 1234567890

# Plan the upload without changing anything
appstore-snapshots upload -d ./iPhone-6.9 -b com.example.myapp --dry-run

# Do it
appstore-snapshots upload -d ./iPhone-6.9 -d ./iPad-13-Landscape -b com.example.myapp

# Loose screenshots should be German rather than en-US
appstore-snapshots upload -d ./iPad-13-Landscape -b com.example.myapp --default-locale de-DE

# Narrow it down
appstore-snapshots upload ./screenshots -b com.example.myapp \
    --only-devices APP_IPHONE_67 --only-languages en-US,de-DE --keep-existing

# Every display type, with example folder names
appstore-snapshots devices
```

By default `upload` targets the newest **editable** version of the app and
**replaces** the screenshots already in each set — App Store Connect allows at
most 10 per set, so appending overflows fast. Use `--keep-existing` to append.

---

## Folder names it understands

**Devices.** Separators, case and orientation are all ignored, so
`iPhone-6.9`, `iphone_69`, `IPHONE 6.9 inch` and `iPhone-6.9-Portrait` are the
same thing. Literal API values (`APP_IPHONE_67`) work too.

| Folder | Display type |
| --- | --- |
| `iPhone-6.9`, `iPhone-6.7` | `APP_IPHONE_67` |
| `iPhone-6.5` | `APP_IPHONE_65` |
| `iPhone-6.1` | `APP_IPHONE_61` |
| `iPhone-5.5` | `APP_IPHONE_55` |
| `iPad-13-Landscape`, `iPad-12.9` | `APP_IPAD_PRO_3GEN_129` |
| `iPad-11` | `APP_IPAD_PRO_3GEN_11` |
| `iPad-9.7` | `APP_IPAD_97` |
| `Mac`, `Apple-TV`, `Vision-Pro` | `APP_DESKTOP`, `APP_APPLE_TV`, `APP_APPLE_VISION_PRO` |
| `Apple-Watch-Ultra`, `Watch-Series-7` | `APP_WATCH_ULTRA`, `APP_WATCH_SERIES_7` |

> Apple never added separate enum values for the 6.9-inch iPhone or the 13-inch
> iPad — those screenshots belong in the 6.7-inch and 12.9-inch (3rd gen) display
> types, whose accepted resolutions were widened instead. That is why both map to
> the same value above.

**Languages.** App Store locale codes are irregular: `de-DE` and `pt-BR` carry a
region, but Italian is just `it`. Folders are normalised accordingly —
`it-IT`, `it_it` and `Italian` all become `it`; `zh-CN` and `zh-Hans` become
`zh-Hans`.

## Custom names

Anything the guesser cannot handle goes in a `snapshots.json` next to your device
folders (see [`snapshots.example.json`](snapshots.example.json)):

```json
{
  "bundle_id": "com.example.myapp",
  "devices": { "Hero-Shots-Big-Phone": "APP_IPHONE_67" },
  "languages": { "brazil": "pt-BR" }
}
```

Overrides win over everything else. The UI picks the file up automatically; the
CLI takes `--config` too. Values are validated against the real API enums, so a typo
is caught before any network call.

## Other layouts

When you hand it a **parent** folder rather than device folders, it also
recognises two inverted arrangements:

* `<language>/<device>/*.png` — detected automatically.
* `<language>/*.png` with no device folder — images are grouped by their pixel
  size, using the known App Store screenshot resolutions.

`--layout` overrides the detection.

---

## Project layout

```
src/appstore_snapshots/
  auth.py            ES256 JWT from the .p8 + Key ID + Issuer ID
  client.py          App Store Connect REST client (apps, versions, screenshots)
  config.py          snapshots.json overrides
  display_types.py   folder name  -> screenshotDisplayType
  locales.py         folder name  -> App Store locale
  scanner.py         device folders -> ScreenshotSet objects
  uploader.py        reserve -> upload -> commit -> reorder, with progress events
  cli.py             typer CLI
  ui/streamlit_app.py  the Streamlit page
streamlit_app.py     root launcher for `streamlit run`
.streamlit/config.toml
.python-version      3.13, used by `uv sync`
```

Uploading one image is a four-step handshake: reserve an `appScreenshot` record
to get pre-signed upload operations, PUT the bytes to each operation, commit with
the file's MD5, then PATCH the set's relationship to fix the order. A reservation
that fails part-way is deleted so no half-uploaded image is left behind.

## Tests

```bash
uv run pytest
```

## Safety notes

* `.p8` files are gitignored; the UI never writes the key to disk.
* `--dry-run` (CLI) and the dry-run toggle (UI) make no write calls at all.
* Uploading **replaces** a set's contents by default. Check the plan first.
