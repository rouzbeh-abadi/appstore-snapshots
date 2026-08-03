from pathlib import Path

import pytest
from PIL import Image

#: The languages from the folder screenshot in the brief.
LANGUAGES = ("de-DE", "en-US", "es-ES", "es-MX", "fr-FR", "it-IT", "pt-BR", "pt-PT", "zh-Hans")


def write_png(path: Path, size: tuple[int, int] = (1320, 2868)) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, color=(20, 20, 20)).save(path)
    return path


@pytest.fixture
def tree(tmp_path: Path) -> Path:
    """A realistic <device>/<language>/*.png tree."""
    for language in LANGUAGES:
        for index in (1, 2, 10):
            write_png(tmp_path / "iPhone-6.9" / language / f"{index}_home.png", (1320, 2868))
    for language in ("en-US", "de-DE"):
        write_png(tmp_path / "iPad-13-Landscape" / language / "01.png", (2752, 2064))
    return tmp_path
