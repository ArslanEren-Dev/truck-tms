"""Translation checks: every text the code uses exists in English and Turkish, with matching placeholders."""

import re
import string
from pathlib import Path

import pytest

import truck_tms
from truck_tms import database
from truck_tms.i18n import LANGUAGES, STRINGS, set_language, t

# scan the package that is actually imported (works for a source checkout and an installed wheel)
SOURCE = Path(truck_tms.__file__).resolve().parent
LITERAL = re.compile(r"""\bt\(\s*["']([a-z_]+(?:\.[a-z_0-9]+)+|[a-z_]+)["']""")
PREFIX = re.compile(r"""\bt\(\s*f?["']([a-z_]+\.)["']\s*\+""")


def _placeholders(text: str) -> set[str]:
    return {name for _, name, _, _ in string.Formatter().parse(text) if name}


def _used_keys() -> set[str]:
    keys = set()
    for path in SOURCE.rglob("*.py"):
        keys |= set(LITERAL.findall(path.read_text(encoding="utf-8")))
    return keys


def test_every_entry_has_every_language():
    missing = [(k, lang) for k, v in STRINGS.items() for lang in LANGUAGES if not v.get(lang, "").strip()]
    assert missing == []


@pytest.mark.parametrize("key", sorted(STRINGS))
def test_placeholders_match(key):
    entry = STRINGS[key]
    assert _placeholders(entry["en"]) == _placeholders(entry["tr"]), key


def test_every_key_used_in_code_exists():
    used = _used_keys()
    assert len(used) > 150  # the scan really found the calls
    assert sorted(k for k in used if k not in STRINGS) == []


def test_dynamic_keys_exist():
    """Keys built at run time, e.g. t("status." + load.status)."""
    groups = {
        "status.": database.TRUCK_STATUSES + database.LOAD_STATUSES + database.DRIVER_STATUSES,
        "category.": database.EXPENSE_CATEGORIES,
        "service.": database.SERVICE_TYPES,
        "stmt_status.": database.STATEMENT_STATUSES,
        "kind.": database.ITEM_KINDS,
        "pay.": database.PAY_TYPES,
        "theme.": ("light", "dark"),
        "unit.": ("mi", "km"),
        "weekday.": tuple(str(i) for i in range(7)),
        "export.": ("owner_pdf", "driver_pdf", "csv", "all", "pdf", "pdf_csv"),
        "page.": ("overview", "trucks", "drivers", "loads", "statements", "maintenance", "expenses",
                  "reports", "settings"),
        "import.field.": __import__("truck_tms.importer", fromlist=["FIELDS"]).FIELDS,
        "doc.kind.": database.DOCUMENT_KINDS,
        "dpay.": __import__("truck_tms.ui.driver_pay", fromlist=["PERIODS"]).PERIODS,
    }
    missing = [prefix + value for prefix, values in groups.items() for value in values
               if prefix + value not in STRINGS]
    assert missing == []
    # every dynamic prefix found in the code is covered above
    prefixes = set()
    for path in SOURCE.rglob("*.py"):
        prefixes |= set(PREFIX.findall(path.read_text(encoding="utf-8")))
    assert prefixes <= set(groups), prefixes - set(groups)


def test_empty_state_and_navigation_texts_exist():
    """Texts built with f-strings or chosen with "if": the scan above cannot see these."""
    import importlib

    importlib.import_module("truck_tms.ui.main_window")  # imports every page, so all CrudTab subclasses exist
    from truck_tms.ui.base import CrudTab

    keys ={"empty.filtered_title", "empty.filtered_hint", "nav.dark_mode", "nav.light_mode"}
    pages = {cls.empty_key for cls in CrudTab.__subclasses__()} | {CrudTab.empty_key}
    assert pages == {"generic", "trucks", "drivers", "loads", "statements", "maintenance", "expenses",
                     "invoices", "compliance"}
    for page in pages:
        keys |= {f"empty.{page}_title", f"empty.{page}_hint"}
    assert sorted(k for k in keys if k not in STRINGS) == []


def test_turkish_is_really_translated():
    """Catch copy-paste mistakes: most Turkish texts must differ from the English ones."""
    same = [k for k, v in STRINGS.items() if v["en"] == v["tr"]]
    allowed = {"app.title", "none", "load.load_number", "load.rate_per_mile", "load.tonu", "truck.model",
               "report.net", "unit.km", "pay.desc_per_mile",
               "doc.kind.rate_con", "import.field.load_number",
               "tab.ifta", "comp.kind.form_2290", "inv.method.quick_pay", "inv.method.factoring",
               }  # US industry terms kept in English on purpose
    assert sorted(set(same) - allowed) == []


def test_no_ampersand_in_button_or_menu_texts():
    """Qt turns '&' in buttons, tabs and menus into a shortcut letter, so 'A & B' shows as 'A _B'
    ('&File' on purpose is fine)."""
    for key, texts in STRINGS.items():
        if key.split(".")[0] in ("tab", "btn", "menu", "nav", "dash") or key.startswith("inv.method."):
            for lang, text in texts.items():
                assert "& " not in text, (key, lang)


def test_turkish_characters_are_intact():
    text = " ".join(v["tr"] for v in STRINGS.values())
    for ch in "çğıöşüÇİÖŞÜ":  # (no Turkish word starts with Ğ)
        assert ch in text
    assert "Ã" not in text and "Ä" not in text  # no broken UTF-8 (mojibake)


def test_percent_format_per_language():
    from truck_tms.statement import percent

    assert percent(10) == "10%"
    set_language("tr")
    assert percent(10) == "%10"
    assert t("btn.yes") == "Evet"
