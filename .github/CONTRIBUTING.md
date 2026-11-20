# Contributing to Truck TMS

Thanks for helping! Bug reports, ideas, translations and pull requests are all welcome.
*Türkçe yazabilirsiniz; issues and pull requests in Turkish or English are both fine.*

## Reporting a problem

Open an [issue](https://github.com/ArslanEren-Dev/truck-tms/issues/new/choose) and include:

- what you did, what you expected, and what happened instead;
- the version (**Help → About Truck TMS**) and your Windows / macOS / Linux version;
- a screenshot if it helps. **Do not attach your data file**: it contains your business data.

## Working on the code

```bash
git clone https://github.com/ArslanEren-Dev/truck-tms.git
cd truck-tms
python -m venv .venv
.venv\Scripts\activate            # macOS/Linux: source .venv/bin/activate
pip install -e ".[dev]"
pytest                            # the whole suite runs in about 30 seconds
truck-tms --db demo.db --demo     # try your change with sample data
```

House rules:

- **No new runtime dependencies** unless they are clearly worth it and have an MIT/BSD/Apache/LGPL-compatible
  license. GPL-only components (for example Qt Charts) cannot be used. See
  [docs/THIRD_PARTY_LICENSES.md](../docs/THIRD_PARTY_LICENSES.md).
- **Every text the user sees goes through `t("...")`** and needs English *and* Turkish in `truck_tms/i18n.py`.
  `tests/test_i18n.py` fails if a translation or a `{placeholder}` is missing.
- Keep logic GUI-free where possible (`database.py`, `statement.py`, `report.py`, `importer.py`) and add a test
  for it.
- No network access unless the user asks for it (see the privacy notes in
  [docs/CODE_SIGNING.md](../docs/CODE_SIGNING.md)).
- After changing the interface, `python docs/make_media.py` regenerates the screenshots and the banner.

## Adding a language

Add the language code to `LANGUAGES` in `truck_tms/i18n.py` and a translation to every entry of `STRINGS`.
The tests tell you which ones are missing.

## Pull requests

Keep them focused, describe what changed and why, and make sure `pytest` passes. GitHub Actions runs the
tests on Windows and Linux for every pull request.
