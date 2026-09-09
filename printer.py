# Printer Handler

from escpos.printer import Win32Raw
from math import ceil
from PIL import Image
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QFontDatabase, QGuiApplication, QImage, QPainter, QTextDocument, QTextOption


RECEIPT_WIDTH_DOTS = 384
KHMER_FONT_SIZE = 26  # Pixels at the printer's native resolution.


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

def print_receipt(transaction_id: int, cart_items: list, total: int, total_usd: float, payment_method: str):
    printer = None
    try:
        # Render first: missing fonts must not leave a partly written print job.
        name_images = [
            render_khmer_name(item['name']) if contains_khmer(item['name']) else None
            for item in cart_items
        ]
        PRINTER_NAME = "HPRT HM-A200U(ESC)"  # Replace with the exact Windows printer name
        printer = Win32Raw(printer_name=PRINTER_NAME, profile="TM-T88IV")
        
        printer.set(align="center", bold=True)
        printer.text("MOON MART\n")
        printer.text("17Eo, St 108\n")
        printer.text("--------------------------------\n")
        
        printer.set(align="left", bold=False)
        printer.text(f"Receipt #: {transaction_id}\n")
        printer.text(f"--------------------------------\n")


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
                printer.text(
                    f"Qty: {item['quantity']}  {item['line_total']} KHR  ${item['line_total_usd']:.2f}\n"
                )
                continue
            name = item['name'][:18].ljust(18)
            qty = str(item['quantity']).rjust(3)
            price = f"{item['line_total']} KHR".rjust(10)
            price_usd = f"${item['line_total_usd']:.2f}".rjust(10)
            printer.text(f"{name} {qty} {price} {price_usd}\n")
            
        printer.text("--------------------------------\n")
        printer.set(align="right", bold=True)
        printer.text(f"TOTAL: {total} KHR\n")
        printer.text(f"TOTAL: ${total_usd:.2f}\n\n")
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
