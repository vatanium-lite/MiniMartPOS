# Printer Handler

from escpos.printer import Win32Raw
from math import ceil
from textwrap import wrap
from PIL import Image
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QFontDatabase, QGuiApplication, QImage, QPainter, QTextDocument, QTextOption


# HM-A200U: 48 mm printable width at 8 dots/mm (58 mm paper).
# https://www.hprt.com/Product/Portable-Thermal-Receipt-Printer-HM-A200U.html
RECEIPT_WIDTH_DOTS = 384
RECEIPT_COLUMNS = 32  # Normal-size Font A; do not use double-width text.
KHMER_FONT_SIZE = 26  # Pixels at the printer's native resolution.


def wrap_receipt_text(text: str) -> str:
    """Fit text to the receipt, preserving paragraphs and splitting long words."""
    return '\n'.join(
        line
        for paragraph in text.split('\n')
        for line in (wrap(paragraph, width=RECEIPT_COLUMNS, break_on_hyphens=False) or [''])
    ) + '\n'


def render_khmer_name(name: str) -> Image.Image:
    """Shape and wrap a Khmer name with Qt, then return printable black/white pixels."""
    if QGuiApplication.instance() is None:
        raise RuntimeError("Khmer receipt rendering requires the POS application to be running.")

    available_fonts = QFontDatabase.families(QFontDatabase.WritingSystem.Khmer)
    preferred_fonts = ('Khmer UI', 'Noto Sans Khmer', 'Khmer OS Battambang', 'Khmer OS')
    family = next((font for font in preferred_fonts if font in available_fonts), None)
    if family is None:
        family = next(iter(available_fonts), None)
    if family is None:
        raise RuntimeError("Install a Khmer font, such as Khmer UI or Noto Sans Khmer, to print Khmer receipts.")

    font = QFont(family)
    font.setPixelSize(KHMER_FONT_SIZE)
    document = QTextDocument()
    document.setDefaultFont(font)
    document.setDocumentMargin(4)
    option = QTextOption()
    option.setWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
    document.setDefaultTextOption(option)
    document.setPlainText(name)  # Product names are text, never HTML.
    document.setTextWidth(RECEIPT_WIDTH_DOTS)

    canvas = QImage(RECEIPT_WIDTH_DOTS, ceil(document.size().height()), QImage.Format.Format_RGBA8888)
    canvas.fill(Qt.GlobalColor.white)
    painter = QPainter(canvas)
    try:
        document.drawContents(painter)
    finally:
        painter.end()

    pixels = canvas.constBits().asstring(canvas.sizeInBytes())
    bitmap = Image.frombytes('RGBA', (canvas.width(), canvas.height()), pixels).convert('L')
    return bitmap.point(lambda value: 255 if value >= 160 else 0, mode='1')


def contains_khmer(text: str) -> bool:
    return any('\u1780' <= char <= '\u17ff' or '\u19e0' <= char <= '\u19ff' for char in text)

def print_receipt(transaction_id: int, cart_items: list, total: int, total_usd: float, payment_method: str, discount_amount: int = 0):
    printer = None
    try:
        # Render first: missing fonts must not leave a partly written print job.
        name_images = [
            render_khmer_name(item['name']) if contains_khmer(item['name']) else None
            for item in cart_items
        ]
        PRINTER_NAME = "HPRT HM-A200U(ESC)"  # Replace with the exact Windows printer name
        printer = Win32Raw(printer_name=PRINTER_NAME, profile="TM-T88IV")
        
        printer.set(align="center", bold=True, font="a", normal_textsize=True)
        printer.text("MOON MART\n")
        printer.text("17Eo, St 108\n")
        printer.text('-' * RECEIPT_COLUMNS + '\n')
        
        printer.set(align="left", bold=False)
        printer.text(wrap_receipt_text(f"Receipt #: {transaction_id}"))
        printer.text('-' * RECEIPT_COLUMNS + '\n')


        """ cart_items is a list of dictionaries containing 
                    name, # product name
                    product_id, 
                    quantity, 
                    unit_price, 
                    line_total, and 
                    line_total_usd for each item"""
        
        for item, name_image in zip(cart_items, name_images):
            if name_image is not None:
                # Send pixels instead of passing Khmer through an ESC/POS code page.
                printer.image(name_image, impl="bitImageRaster", center=False)
            else:
                printer.text(wrap_receipt_text(item['name']))
            # Keep the full name above the amounts instead of squeezing four columns.
            printer.text(wrap_receipt_text(
                f"Qty: {item['quantity']}  {item['line_total']} KHR  ${item['line_total_usd']:.3f}"
            ))
            
        printer.text('-' * RECEIPT_COLUMNS + '\n')
        printer.set(align="right", bold=True)
        if discount_amount:
            subtotal = sum(item['line_total'] for item in cart_items)
            subtotal_usd = sum(item['line_total_usd'] for item in cart_items)
            printer.text(wrap_receipt_text(f"Subtotal: {subtotal} KHR"))
            printer.text(wrap_receipt_text(f"Subtotal: ${subtotal_usd:.3f}"))
            printer.text(wrap_receipt_text(f"Discount: -{discount_amount} KHR"))
            discount_usd = round(max(0, subtotal_usd - total_usd), 3)
            printer.text(wrap_receipt_text(f"Discount: -${discount_usd:.3f}"))
        printer.text(wrap_receipt_text(f"TOTAL: {total} KHR"))
        printer.text(wrap_receipt_text(f"TOTAL: ${total_usd:.3f}"))
        printer.text('\n')
        printer.set(align="center", bold=False)
        printer.text("Thank you for shopping!\n")
        printer.text("\n\n\n")
    except Exception as e:
        print(f"[Printer Error] Receipt #{transaction_id} was not printed: {e}")
    finally:
        if printer is not None:
            try:
                printer.close()  # End the Windows RAW job even after a receipt error.
            except Exception as e:
                print(f"[Printer Error] Could not close print job for receipt #{transaction_id}: {e}")
