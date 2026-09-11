"""Whole-sale discount integration tests; temporary databases and simulated printing."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PyQt6.QtGui import QFont, QFontDatabase
from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QMessageBox

import db
import main
import printer


class DiscountTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])
        font_dir = Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts'
        for name in ('arial.ttf', 'KhmerUI.ttf'):
            QFontDatabase.addApplicationFont(str(font_dir / name))
        cls.application.setFont(QFont('Arial', 9))
        cls.application.setStyleSheet(main.load_stylesheet(str(Path(main.__file__).with_name('style.qss'))))

    def setUp(self):
        folder = tempfile.TemporaryDirectory(prefix='moonmart-discount-')
        self.addCleanup(folder.cleanup)
        self.patch(db, 'DB_FILE', str(Path(folder.name) / 'test.db'))
        self.connections = []
        original_get_db = db.get_db

        def tracked_connection():
            connection = original_get_db()
            self.connections.append(connection)
            return connection

        self.patch(db, 'get_db', tracked_connection)
        self.addCleanup(lambda: [connection.close() for connection in self.connections])
        db.init_db()
        self.conn = db.get_db()
        self.conn.executescript("""
            INSERT INTO products (product_id, barcode, name, retail_price, retail_price_usd)
                VALUES (1, '001', 'Milk', 4000, 1), (2, '002', 'Chips', 8000, 2);
            INSERT INTO batch_inventory (batch_id, product_id, quantity, expiration_date)
                VALUES (1, 1, 10, '2027-01-01'), (2, 2, 10, '2027-02-01');
        """)
        self.warning = self.patch(QMessageBox, 'warning', MagicMock())
        self.patch(QMessageBox, 'information', MagicMock())
        self.errors = []
        self.patch(sys, 'excepthook', lambda kind, error, traceback: self.errors.append(str(error)))
        self.window = main.MoonMartPOS()
        self.addCleanup(self.window.close)

    def patch(self, target, name, value):
        replacement = patch.object(target, name, value)
        replacement.start()
        self.addCleanup(replacement.stop)
        return value

    def scan(self, barcode='001'):
        self.window.barcode_input.setText(barcode)
        QTest.keyClick(self.window.barcode_input, Qt.Key.Key_Return)
        self.application.processEvents()
        self.assertEqual(self.errors, [])

    def stored_sale(self):
        return self.conn.execute('SELECT discount_amount, total_amount, total_amount_usd FROM sales_transactions').fetchone()

    def test_blank_and_zero_discount_leave_subtotal_unchanged(self):
        self.scan()
        for text in ('', '0'):
            self.window.discount_input.setText(text)
            self.assertEqual(self.window.update_totals(), (4000, 1.0, 0))

    def test_discount_updates_total_without_changing_lines(self):
        self.scan()
        self.scan('002')
        self.window.discount_input.setText('1000')
        self.assertEqual(self.window.update_totals(), (11000, 2.75, 1000))
        self.assertEqual([item['line_total'] for item in self.window.cart], [4000, 8000])
        self.assertEqual(self.window.cart_table.item(0, 3).text(), '4000 KHR')
        self.assertIn('11000 KHR', self.window.total_label.text())

    def test_discount_persists_across_quantity_changes_and_scans(self):
        self.scan()
        self.window.discount_input.setText('1000')
        self.window.cart_table.item(0, 2).setText('3')
        self.assertEqual(self.window.update_totals(), (11000, 2.75, 1000))
        self.scan()
        self.assertEqual(self.window.update_totals(), (15000, 3.75, 1000))

    def test_invalid_text_blocks_checkout_even_if_set_programmatically(self):
        self.scan()
        for text in ('-1', '1.5', 'abc'):
            with self.subTest(text=text), patch.object(printer, 'print_receipt') as receipt:
                self.window.discount_input.setText(text)
                self.assertIsNone(self.window.update_totals())
                self.window.process_payment('cash')
                self.assertIsNone(self.stored_sale())
                receipt.assert_not_called()
        self.assertEqual(self.errors, [])

    def test_keyboard_rejects_non_integer_characters(self):
        self.scan()
        field = self.window.discount_input
        QTest.keyClicks(field, 'a-1.5')
        self.assertEqual(field.text(), '15')

    def test_excess_discount_blocks_both_payment_buttons(self):
        self.scan()
        self.window.discount_input.setText('4001')
        self.assertTrue(all(not button.isEnabled() for button in self.window.payment_buttons))
        self.assertIsNone(self.window.update_totals())
        self.window.discount_input.setText('1000')
        self.assertTrue(all(button.isEnabled() for button in self.window.payment_buttons))

    def test_discount_revalidated_after_removing_product(self):
        self.scan()
        self.scan('002')
        self.window.discount_input.setText('5000')
        self.window.remove_cart_item(1)
        self.assertIsNone(self.window.update_totals())
        self.assertEqual(self.window.discount_input.text(), '5000')

    def test_emptying_cart_resets_discount(self):
        self.scan()
        self.window.discount_input.setText('1000')
        self.window.remove_cart_item(0)
        self.assertEqual(self.window.discount_input.text(), '')
        self.assertEqual(self.window.update_totals(), (0, 0.0, 0))

    def checkout(self, method):
        self.scan()
        self.window.discount_input.setText('1000')
        with patch.object(printer, 'print_receipt') as receipt:
            self.window.process_payment(method)
            self.assertEqual(receipt.call_args.args[2:5], (3000, 0.75, method))
            self.assertEqual(receipt.call_args.kwargs, dict(discount_amount=1000))
        self.assertEqual(tuple(self.stored_sale()), (1000, 3000, 0.75))
        self.assertEqual(self.conn.execute('SELECT quantity FROM batch_inventory WHERE batch_id=1').fetchone()[0], 9)
        self.assertEqual(self.conn.execute('SELECT line_total FROM pos_item_sales').fetchone()[0], 4000)
        self.assertEqual(self.window.cart, [])
        self.assertEqual(self.window.discount_input.text(), '')

    def test_cash_checkout_records_net_amount(self):
        self.checkout('cash')

    def test_khqr_checkout_records_net_amount(self):
        self.checkout('KHQR')

    def test_full_discount_allows_zero_total_sale(self):
        self.scan()
        self.window.discount_input.setText('4000')
        self.assertEqual(self.window.update_totals(), (0, 0.0, 4000))
        with patch.object(printer, 'print_receipt'):
            self.window.process_payment('cash')
        self.assertEqual(tuple(self.stored_sale()), (4000, 0, 0))

    def test_insufficient_stock_preserves_discount_and_rolls_back(self):
        self.scan()
        self.window.cart_table.item(0, 2).setText('11')
        self.window.discount_input.setText('1000')
        with patch.object(printer, 'print_receipt') as receipt:
            self.window.process_payment('cash')
            receipt.assert_not_called()
        self.assertIsNone(self.stored_sale())
        self.assertEqual(self.window.discount_input.text(), '1000')
        self.assertEqual(self.conn.execute('SELECT quantity FROM batch_inventory WHERE batch_id=1').fetchone()[0], 10)

    def test_database_rejects_invalid_discount_before_writing(self):
        self.scan()
        for discount in (-1, 1.5, '100', True, 4001):
            with self.subTest(discount=discount), self.assertRaises(ValueError):
                db.process_checkout(self.window.cart, 'cash', discount)
        self.assertIsNone(self.stored_sale())

    def test_discount_uses_fixed_exchange_rate_and_cent_rounding(self):
        self.scan()
        self.window.cart[0]['line_total_usd'] = 1.10
        self.assertEqual(db.calculate_checkout_totals(self.window.cart, 1000), (3000, 0.85))
        self.assertEqual(db.calculate_checkout_totals(self.window.cart, 20), (3980, 1.09))
        self.window.cart[0]['line_total_usd'] = 0.50
        with self.assertRaises(ValueError):
            db.calculate_checkout_totals(self.window.cart, 3000)

    def test_summary_uses_discounted_revenue(self):
        self.checkout('cash')
        # Set the test sale to the selected business-day start, regardless of run time.
        self.conn.execute("UPDATE sales_transactions SET created_at=datetime('now', 'start of day', '+7 hours')")
        self.conn.commit()
        report = db.get_daily_sales_report()
        self.assertEqual((report['total_transactions'], report['revenue'], report['revenue_usd']), (1, 3000, 0.75))

    def test_receipt_displays_subtotal_discount_and_net_total(self):
        self.scan()
        fake = MagicMock()
        with patch.object(printer, 'Win32Raw', return_value=fake):
            printer.print_receipt(1, self.window.cart, 3000, 0.75, 'cash', discount_amount=1000)
        text = ''.join(call.args[0] for call in fake.text.call_args_list)
        for detail in ('Subtotal: 4000 KHR', 'Discount: -1000 KHR', 'Discount: -$0.25', 'TOTAL: 3000 KHR', 'TOTAL: $0.75'):
            self.assertIn(detail, text)
        self.assertTrue(all(len(line) <= printer.RECEIPT_COLUMNS for line in text.splitlines()))
        fake.close.assert_called_once()

    def test_discount_input_is_below_total_and_above_payment(self):
        self.scan()
        self.window.discount_input.setText('1000')
        self.window.show()
        self.application.processEvents()
        field = self.window.discount_input.geometry()
        self.assertGreater(field.top(), self.window.total_label.geometry().bottom())
        self.assertLess(field.bottom(), self.window.payment_buttons[0].geometry().top())
        self.assertEqual(self.errors, [])


if __name__ == '__main__':
    unittest.main()
