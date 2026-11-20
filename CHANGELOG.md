# Changelog · Sürüm notları

All notable changes to Truck TMS. Türkçe özet her sürümün altında.

## [0.6.0] — 2026-11-20

### Added
- **Invoices & receivables**: create an invoice from a load in one click (amount and broker filled in, numbers
  count up: `INV-0001`…). Payment terms, **quick pay / factoring** with the fee, partial payments, balance due,
  and a clean **PDF invoice**. The load status follows the invoice (*Invoiced* → *Paid*).
  The Invoices page shows open, overdue, collected (30 days), average days to pay and an **aging ring**
  (not due · 1–30 · 31–60 · 61–90 · 90+ days late).
- **Compliance reminders**: CDL, DOT medical card, drug & alcohol test, MVR, registration (IRP), insurance,
  annual DOT inspection, permits, UCR, Form 2290, MCS-150, IFTA license. *Valid / Expires soon (30 days) / Expired*,
  shown on the Overview too. A CDL date typed on the driver form appears automatically.
- **IFTA quarterly worksheet**: miles by state on every load, gallons + state on fuel expenses.
  Fleet MPG, taxable / tax-paid / net gallons and tax or credit per jurisdiction, for one truck or the fleet;
  your own rate table; PDF/CSV export and print; warnings for miles without a state split and missing rates.
- **Update check**: once a day the app asks GitHub for the latest release and shows *Update available*.
  Also in **Help → Check for updates**; can be turned off in Settings. Nothing about you or your data is sent.
- Overview: 8 key numbers (receivables and expiring documents added), expenses-by-category ring,
  late invoices and expiring documents in the reminders, *New invoice* quick button.
- Settings: invoice number prefix, default payment terms, update check on/off.

### Changed
- **Charts redesigned**: bars grow one after another with a gradient, smooth line curves, a highlight that glides
  with the mouse, value bubbles, rounded axes with short labels ($12.4k), and a new donut chart.
- Table rows highlight under the mouse; number boxes got themed arrows.
- Python **3.12+** is required (PySide6 6.12 crashes on 3.11 and older).

### Performance
Measured with 6,000 loads, 4,000 expenses and 60 trucks:

| | 0.5.0 | 0.6.0 |
|---|---|---|
| Overview refresh | 579 ms | **18 ms** |
| Overview charts (trends) | 497 ms | **9 ms** |
| Window opens | 1.8 s | **0.8 s** |
| Loads page refresh | 1.0 s | **0.39 s** |

- Settings are cached instead of read for every row.
- The trend charts filter in SQL, and *Recent loads* uses `LIMIT`.
- The truck list reads maintenance once.
- Tables size their columns from the first rows and repaint once.
- New indexes on dates and on links between tables.
- Demo data is seeded about 2.5× faster.

### Code quality
- New `printout.py` module: the money format, HTML escaping, page frame, company header and totals are shared by
  statements, truck reports, invoices and IFTA instead of being copied four times.
- List pages share filters, search, toolbar buttons and the row-selection check in one base class.
  Preview, print and PDF/CSV export are shared too.
- **ruff** lint rules are in `pyproject.toml` and run in CI.
- Tests time out after 2 minutes instead of hanging, and the test job is capped at 25 minutes.
- 815 automated tests on Windows and Linux, Python 3.12 and 3.13.
- Screenshots are rendered at 1.25× instead of 2×, which shrank the repository from 4.4 MB to 3.0 MB.
- Data file schema version 3; older files are upgraded automatically.

> **TR:** Faturalar ve alacak takibi, belge/süre hatırlatıcıları, IFTA çeyreklik tablosu ve güncelleme bildirimi
> eklendi. Grafikler yeniden tasarlandı. Büyük veride ana sayfa 30 kat, açılış 2 kat hızlandı. Tekrarlanan kodlar
> birleştirildi, otomatik kod denetimi ve test süre sınırları eklendi.

## [0.5.0]

### Added
- **Excel / CSV import** for loads (`.xlsx`, `.csv`), columns matched from English or Turkish headers, with a
  preview, US and Turkish number/date formats, Excel dates, missing trucks/drivers created, duplicates skipped,
  and a ready-made template.
- **Load documents**: drag rate confirmations, BOLs, PODs, invoices and receipts onto a load; copies are kept in a
  documents folder and included in backups and (optionally) statement exports.
- **Overview charts**: weekly gross, revenue per mile, top brokers (drawn by the app; no GPL Qt Charts).

### Changed
- New sidebar and Overview page.
- Every dialog redesigned with a header band and section cards.
- Toasts, empty-page hints and status badges.

> **TR:** Excel/CSV'den yük aktarma, yük belgeleri ve ana sayfa grafikleri eklendi. Kenar menüsü, ana sayfa ve tüm
> pencereler yeniden tasarlandı.

## Earlier versions (0.1 – 0.4): the foundation

- Trucks (plate and/or unit #, US makes, odometer, plate history), drivers and pay settings.
- Loads with `#` numbers, TONU, loaded/dead miles and the statement week.
- Weekly statements with fuel, tolls, dispatcher fee, driver pay, additions/deductions, driver payment tracking and
  the owner payout.
- Maintenance, expenses and the per-truck report.
- PDF/CSV export with folder and file name choice.
- Autosave, daily backups and backup copies.
- White and black themes, the start-up animation, and English and Turkish throughout.
- A one-file Windows exe built and released by GitHub Actions.

> **TR:** Tır, sürücü, yük, haftalık statement, bakım, masraf, tır raporu, PDF/CSV çıktı, otomatik kayıt ve yedek,
> beyaz/siyah tema, açılış animasyonu, Türkçe/İngilizce arayüz ve GitHub'ın derlediği tek dosyalık exe.
