# Moon Mart POS

A Windows desktop point-of-sale application built with Python, PyQt6, and SQLite. It supports barcode entry, a shopping cart, batch inventory, KHR/USD totals, business-day sales summaries, and thermal receipts with Khmer product names.

## Features

- Scan a barcode or type it and press Enter.
- Edit cart quantities, remove items, and calculate KHR and USD totals.
- Apply a whole-sale discount in KHR, with discounted checkout totals and receipts.
- Record sales as cash or KHQR payments.
- Deduct stock from batches with the earliest expiration date first.
- Reject insufficient-stock checkout, show the affected product, and roll back the whole sale.
- Add stock, remove stock, and edit product details.
- Summarize sales from 7 AM to the following day's 2 AM, using Bangkok time.
- Print wrapped receipts, rendering Khmer names as images to preserve character shaping.

**KHQR is a payment-method label in this application.** The program does not generate a payment QR code, contact a bank, or verify a transfer. Confirm payment separately before completing a sale.

## Requirements

- Windows, for the current `Win32Raw` printer integration.
- Python with pip and Tkinter. The isolated regression environment used Python 3.12.14; other Python versions have not been verified by that test run.
- Python packages: `PyQt6`, `python-escpos`, `pywin32`, and `Pillow`.
- A Khmer-capable font for Khmer receipts, such as Khmer UI, Noto Sans Khmer, or Khmer OS Battambang.
- For physical receipts: a configured Windows printer queue and a compatible ESC/POS printer. The current target is the HPRT HM-A200U.
- Optional: a barcode scanner configured as keyboard input with an Enter suffix, and DB Browser for SQLite for database administration.

SQLite support is included with Python; a separate database server is not required. Tkinter is currently imported by the application even though its main interface uses PyQt6.

## Install and run

Open PowerShell in the project directory containing `main.py`, then run:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install PyQt6 python-escpos pywin32 Pillow
.\.venv\Scripts\python.exe main.py
```

These commands use the virtual environment directly; activation is not required. Dependencies are not currently pinned to specific versions.

Always start the program from the project directory. Both `moonmart.db` and `style.qss` are resolved relative to the working directory, so starting elsewhere can create a different empty database or fail to load the stylesheet.

On startup, the application initializes missing tables and timestamp triggers and removes inventory batches whose quantity is zero or less. It does not insert sample products. Existing tables are not automatically rebuilt when their `CREATE TABLE IF NOT EXISTS` definitions change.

## Add your first product

1. Open **Add Stock**.
2. Enter the barcode, a positive whole-number quantity, and the expiration date.
3. If the barcode is new, the application creates a product placeholder and its stock batch.
4. Open **Edit Product** for the same barcode and supply a name and retail price in KHR. Add cost, reorder level, and category ID if needed.
5. Scan the barcode to add the completed product to the cart.

When you edit the KHR retail price, the application sets the USD retail price to KHR / 4000, rounded half up to three decimal places. For example, 500 KHR becomes $0.125. USD amounts are displayed with three decimal places throughout the cart, totals, receipts, and sales summary. Existing product prices and historical sales are not automatically repriced. A category ID must already exist in the `categories` table; there is no category-management dialog. Leaving an edit field blank preserves its current value rather than clearing it.

New products without prices cannot be scanned into the cart. Current scan validation also rejects zero prices, so free-item sales are not supported through barcode entry.

## Make a sale

1. Focus the barcode field and scan a product, or type its barcode and press Enter.
2. Scan again to increase its quantity, or edit the **Qty** cell directly.
3. Use the row's **×** button to remove an item. Invalid quantities are rejected and the previous quantity is restored.
4. Optionally enter a whole-number **Discount (KHR)** below Total. Blank means no discount.
5. Confirm payment, then click **Pay Cash** or **Pay KHQR**.

The discount is applied once to the entire sale, leaving product prices and line totals unchanged. Its USD equivalent uses 4,000 KHR per dollar, rounded to three decimal places (half up). It is deducted from the sum of the stored USD line totals, so imported USD prices are preserved. Discounts that exceed either subtotal are rejected, and payment buttons are disabled until corrected. Reducing the cart can make a previously valid discount too large; adjust it before checkout.

Successful sales store the KHR discount in `sales_transactions.discount_amount` and the discounted amounts in the transaction totals. The daily summary therefore reports revenue after discounts. Receipts show subtotal, discount, and payable totals when a discount is applied. The discount is cleared when checkout succeeds or the cart is emptied; it stays entered after a failed checkout. A discount equal to the whole subtotal is allowed if neither currency total becomes negative.

Successful checkout records the sale and its line items, deducts stock, attempts receipt printing, and clears the cart. Manual quantity edits use the USD unit price saved in the cart; they do not independently convert the KHR line total.

If stock is insufficient, the entire database transaction is rolled back, including earlier deductions in the same checkout. The cart remains available for correction. The warning identifies the first insufficient-stock product and shows requested and available quantities. No partial sale is completed.

**Receipt printing happens after the sale is committed.** Printer errors are logged to the terminal and do not undo the sale. Do not repeat checkout just to obtain another receipt, as that would record another sale. There is currently no receipt-reprint screen.

## Inventory and product editing

- **Add Stock:** creates a new batch for the barcode and expiration date.
- **Delete Stock:** removes the requested quantity, starting with the earliest-expiring batch. It does not delete the product record. Insufficient stock causes the removal transaction to roll back.
- **Edit Product:** changes only supplied fields. Invalid category references produce a database-error message rather than a success message.

Expiration dates determine deduction order, but the application does not automatically block the sale of expired stock. Review and remove unsuitable stock as part of store operations.

## Business-day sales summary

Click **Daily Sales Summary** to see transaction count and total revenue in KHR and USD.

- Time zone: Bangkok, represented by a fixed UTC+7 offset.
- Start: 07:00, inclusive.
- End: 02:00 the next day, exclusive.
- Before 07:00, the summary selects the business day that started yesterday.

For example, at 01:00 on September 10, the report covers September 9 at 07:00 through September 10 at 02:00. Between 02:00 and 07:00, it continues to show that previous business period. Sales made during that gap are stored but excluded from this reporting window.

New timestamp defaults use `datetime('now', '+7 hours')`. Persistent database triggers replace missing timestamps and recognized literal default-expression text from imports with the current Bangkok timestamp. Existing valid timestamps are left unchanged; old UTC timestamps are not converted automatically. The report compares stored timestamps as Bangkok-local values, so mixed historical time zones require care.

## Thermal printer setup

1. Install the HPRT HM-A200U Windows driver, connect the printer, load paper, and verify that the Windows queue can print.
2. Check the queue name in Windows and match it to `PRINTER_NAME` inside `print_receipt()` in `printer.py`. The current value is:

   ```python
   PRINTER_NAME = "HPRT HM-A200U(ESC)"
   ```

3. Restart the POS after changing printer settings or code.
4. Verify a receipt on the physical printer before using the setup for live sales.

HPRT specifies 58 mm paper with a maximum 48 mm printable width at 8 dots/mm, giving 384 printable dots. See the [HM-A200U product specifications](https://www.hprt.com/Product/Portable-Thermal-Receipt-Printer-HM-A200U.html).

Current receipt settings in `printer.py`:

| Setting | Purpose |
| --- | --- |
| `RECEIPT_WIDTH_DOTS = 384` | Width of rendered Khmer name images. |
| `RECEIPT_COLUMNS = 32` | Maximum length of native text lines, with normal-size Font A selected. |
| `KHMER_FONT_SIZE = 26` | Khmer image font size in pixels. |
| `profile="TM-T88IV"` | Current ESC/POS library profile; this is not an HM-A200U-specific profile. |
| `impl="bitImageRaster"` | ESC/POS image command used for Khmer names. |

Product names appear above quantities and amounts; long text wraps instead of being truncated. Khmer names are shaped by Qt and sent as black-and-white images, rather than encoded through the printer's native character pages. This requires a running Qt application and an installed Khmer font. Names already stored as question marks in the database cannot be recovered by the renderer.

Printer jobs are closed in a `finally` block, including after write failures. Cleanup errors are also logged. Simulated tests verify the generated commands, but cannot establish that a particular printer, driver, connection, or firmware prints correctly. A failed write can leave a partial receipt on paper.

## Database and backups

The application uses `moonmart.db`, with foreign-key enforcement enabled on its own connections and SQLite WAL journaling.

Main tables:

- `categories`, `products`, and `batch_inventory`: product catalog and stock.
- `sales_transactions` and `pos_item_sales`: completed sales and line items.
- `suppliers`, `purchase_orders`, and `po_items`: schema definitions exist, but there are no supplier or purchase-order workflows in the current UI.

Back up the database before imports or manual SQL edits. Use a SQLite-aware backup for a running database, or close the POS and all database editors before making a file backup. Do not delete an active `moonmart.db-wal` file; it can contain committed data not yet written to the main database file.

Git ignores database files, WAL/shared-memory files, Python caches, and virtual environments. **Git is not a backup of your sales data.** There is no automatic backup or restore workflow in the application.

For external imports, preserve barcodes as text, use Unicode product names, and populate both retail prices. Run the application once to initialize the schema and triggers before importing into its tables. Recreating a table through an external tool can remove its constraints and triggers.

## Customize the interface

Edit `style.qss` and restart the POS. It controls the main colors, font sizes, table styling, report-button appearance, and shared right-panel button widths.

To resize the right-panel buttons, change both `min-width` and `max-width` in the shared button selector at the end of the stylesheet. These values describe the content width; horizontal padding and borders add to the visible width.

Some stock-button colors and padding are also set inline in `main.py`; inline styles can override conflicting settings in `style.qss`.

## Run the included tests

From the project directory, using the same virtual environment:

```powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -p "test_*.py" -v
```

The included tests cover discount validation and checkout, discounted reporting, Khmer rendering, receipt width/wrapping, font commands, and printer cleanup. They use temporary databases, offscreen Qt rendering, and simulated printers; they do not write to the live sales database or send physical print jobs. Khmer rendering tests require a suitable font. On Windows, the test setup attempts to load `C:/Windows/Fonts/KhmerUI.ttf` if the offscreen backend does not discover one.

A separate, temporary development test harness also exercises the broader POS workflows, including stock, timestamps, and UI interactions. That harness is not included in this repository; the command above runs the included discount and receipt tests, not that broader development suite.

## Troubleshooting

- **The app opens with no products:** confirm that you launched it from the directory containing your intended `moonmart.db`.
- **No unit price warning:** complete both KHR and USD prices. Editing the KHR retail price through the POS also recalculates USD. Zero prices are currently rejected when scanning.
- **No receipt or a stuck queue:** inspect the terminal for `[Printer Error]`, check the exact queue name, and verify Windows printing independently. Do not repeat a committed sale to troubleshoot printing.
- **Khmer appears as boxes:** install a Khmer-capable font and restart the application. Check the source product name if it already contains `???`.
- **A style change is not visible:** restart the POS and confirm that the correct `style.qss` is being loaded. Check for conflicting inline styles.
- **Foreign-key error when editing a category:** use an ID present in `categories`, or leave the category field blank to preserve the current value.

## Project files

```text
main.py                      Desktop UI, cart, dialogs, and payment actions
db.py                        SQLite schema, inventory, checkout, and reports
printer.py                   ESC/POS receipt layout and Khmer image rendering
style.qss                    Qt stylesheet
tests/test_printer_khmer.py   Khmer receipt tests
tests/test_printer_layout.py  Receipt width and command tests
tests/test_discount.py        Discount UI, checkout, reporting, and receipt tests
moonmart.db                  Local application data (generated, Git-ignored)
```
