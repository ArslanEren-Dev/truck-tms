# Changelog · Sürüm notları

All notable changes to Truck TMS. Türkçe özet her sürümün altında.

## [Unreleased]

### Fixed
- **Load board and invoices stay in step**: dropping a card on *Invoiced* or *Paid* now opens the invoice
  (a new one filled from the load, or the existing one to record the payment) instead of only changing the status.
  A load that has an invoice can no longer be dragged back to an earlier column; the app explains why.
- **Overpaid invoices**: the invoice form shows *Overpaid by …* in red and asks before saving when the amount
  received plus the fee is more than the invoice amount.
- **Loads without a date**: the Loads page now says how many loads have no pickup or delivery date, because
  reports, driver pay and statements (unless a week is chosen) cannot count them.

### Changed
- PySide6 6.12 or newer is required (the version the app is built and tested with); package classifiers now list
  Windows, macOS, Linux and Python 3.12/3.13.
- `.gitignore` also skips attached-document folders, backups, SQLite journal files, the self-test log and tool caches.
- README: system requirements (Windows 10 or 11, 64-bit), the two-day rule of the *Today* invoice reminder, how
  undated loads are handled and how the update check works.

**Türkçe:** yük panosu artık faturayla uyumlu (Faturalandı/Ödendi sütunu fatura penceresini açar, faturalı yük geri
çekilemez), fazla ödemede uyarı, tarihsiz yükler için uyarı, PySide6 ≥ 6.12, daha eksiksiz `.gitignore` ve README.

## [0.7.0] — 2026-11-24

### Added
- **Load board**: the Loads page has a *List* / *Board* switch. The board shows one column per status
  (Planned → Dispatched → In Transit → Delivered → Invoiced → Paid) with the count and gross of each.
  Drag a card to another column to change the load's status. The app remembers which view you used.
- **Details panel**: click a load (in the list or on the board) and a panel slides in from the right with the route,
  dates, truck, driver, the profit breakdown with a margin gauge, the invoice status and documents.
  Edit or invoice from there; Esc closes it.
- **Today**: the Overview lists today's pickups and deliveries, late deliveries, and delivered loads still waiting
  for an invoice (after 2 days), each with a one-click *Open* or *Invoice* button.
- **Getting started**: an empty file shows three steps (add a truck, a driver, the first load) with buttons.
- **Installer**: releases now include `TruckTMS-Setup.exe` next to the portable `TruckTMS.exe`. It installs for the
  current user without administrator rights, adds Start menu and optional desktop shortcuts, and can be removed from
  Windows settings. Uninstalling never touches your data file. GitHub builds it and tests a silent install,
  the installed app's self-test and the uninstall on every release.
- **Profit per load**: the Loads page shows an *Est. profit* and *Profit/mi* column (green or red) and the total.
  Estimate = gross − dispatch fee − driver pay − fuel (the truck's fuel cost per mile from its fuel expenses,
  or the fleet average). The load form shows the same breakdown while you type.
- **Driver Pay page**: what every driver earned in a period (this month, last month, this quarter, this year or
  any dates): loads, miles, gross, pay, pay per mile and % of gross. Export to PDF/CSV or print.
- **Quick search (Ctrl+K)**: one box finds loads, trucks, drivers, invoices and pages; Enter opens the record.
- **Keyboard shortcuts**: Ctrl+N new record on the current page, Ctrl+F search box, Ctrl+1…9 pages, Enter to edit
  and Delete to delete the selected row, F5 reload; Help → Keyboard Shortcuts (F1) lists them all.

### Changed
- **New look**: a gradient hero band on the Overview with a greeting, the date and glass-style quick buttons;
  weekly trend lines and ▲▼ change badges on the gross and miles cards; a colored status edge on every list row;
  the Segoe UI Variable font.
- **Animations**: cards fade in one after another, numbers glide to their new value instead of restarting at zero,
  a deleted row turns red before it disappears, the "Saved" check mark draws itself, the load form has a profit
  gauge that sweeps as you type, and the start-up screen turns from dusk to night while city windows light up.
- New data file moved to **Ctrl+Shift+N** (Ctrl+N now adds a record).
- The driver pay rules live in one place (`profit.py`) and are shared by statements, the Driver Pay page and
  the profit estimate.
- Build scripts moved to `packaging/` (`build_exe.ps1`, `build_installer.ps1`, `TruckTMS.iss`).
- Labels, buttons, table headers and dialog titles now use the same capitalization everywhere, in English and
  Turkish (for example *New Invoice*, *Invoice Date*, *DOT Medical Card*); Turkish spelling follows TDK (*dâhil*).
- Unused translations were removed; 898 tests.

**Türkçe:** sürükle-bırak yük panosu, sağdan açılan yük detay paneli, "Bugün" listesi, boş dosya için başlangıç
rehberi, kurulum programı (TruckTMS-Setup.exe), yük başına tahmini kâr ve mil başına kâr, dönemlik sürücü ödeme özeti
(PDF/CSV), Ctrl+K hızlı arama ve klavye kısayolları. Yeni görünüm: renk geçişli üst bant, mini trend grafikleri,
satırlarda renkli durum şeridi; sırayla beliren kartlar, kayarak değişen sayılar, kâr göstergesi ve gece olan
başlangıç ekranı.

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
- **Update check**: once a day the app asks GitHub for the latest release and shows *Update Available*.
  Also in **Help → Check for Updates**; can be turned off in Settings. Nothing about you or your data is sent.
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
