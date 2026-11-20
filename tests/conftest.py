import os

# Run Qt without a screen (CI, headless test runs). Must be set before PySide6 is imported.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["TRUCK_TMS_NO_UPDATE_CHECK"] = "1"  # tests never go online
if os.name == "nt":
    os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")

import pytest  # noqa: E402

from truck_tms.i18n import set_language  # noqa: E402


@pytest.fixture(autouse=True)
def _english():
    set_language("en")
    yield
    set_language("en")
