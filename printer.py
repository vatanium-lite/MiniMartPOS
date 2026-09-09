# Printer Handler

from escpos.printer import Win32Raw

def print_receipt(transaction_id: int, cart_items: list, total: int, total_usd: float, payment_method: str):
    printer = None
    try:
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
        
        for item in cart_items:
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
