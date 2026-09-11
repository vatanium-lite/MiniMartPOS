"""Text width and job cleanup checks; all printing is simulated."""
import io
import unittest
from contextlib import redirect_stdout
from unittest.mock import MagicMock, patch

from escpos.printer import Dummy

import printer


class ReceiptLayoutTests(unittest.TestCase):
    def receipt(self, name='Milk', quantity=2, amount=8000, usd=2.0):
        fake = MagicMock()
        item = dict(name=name, quantity=quantity, line_total=amount, line_total_usd=usd)
        with patch.object(printer, 'Win32Raw', return_value=fake):
            printer.print_receipt(123, [item], amount, usd, 'cash')
        text = ''.join(call.args[0] for call in fake.text.call_args_list)
        self.assertTrue(text)
        self.assertTrue(all(len(line) <= printer.RECEIPT_COLUMNS for line in text.splitlines()))
        fake.close.assert_called_once()
        return fake, text

    def test_product_name_and_amounts_use_separate_lines(self):
        fake, text = self.receipt()
        self.assertIn('Milk\nQty: 2  8000 KHR  $2.00\n', text)
        self.assertEqual(fake.set.call_args_list[0].kwargs,
                         dict(align='center', bold=True, font='a', normal_textsize=True))

    def test_long_name_is_not_truncated(self):
        name = 'Angkor Milk 100 percent full cream family pack 1000 ml'
        fake, text = self.receipt(name)
        self.assertIn(name, ' '.join(text.split()))
        fake.image.assert_not_called()

    def test_long_unbroken_name_wraps_without_losing_characters(self):
        name = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ' * 5
        _, text = self.receipt(name)
        name_lines = text.split('-' * printer.RECEIPT_COLUMNS + '\n')[2].split('Qty:')[0]
        self.assertEqual(name_lines.replace('\n', ''), name)

    def test_large_amounts_and_quantities_wrap(self):
        _, text = self.receipt(quantity=123456, amount=987654321012345, usd=24691358025.99)
        self.assertIn('123456', text)
        self.assertIn('987654321012345', text)
        self.assertIn('$24691358025.99', text)

    def test_wrap_preserves_blank_lines_and_exact_width(self):
        text = 'A' * 32 + '\n\n' + 'B' * 33
        self.assertEqual(printer.wrap_receipt_text(text), 'A' * 32 + '\n\n' + 'B' * 32 + '\nB\n')

    def test_real_encoder_selects_font_a_and_normal_size(self):
        dummy = Dummy(profile='TM-T88IV')
        with patch.object(printer, 'Win32Raw', return_value=dummy):
            printer.print_receipt(1, [], 0, 0, 'cash')
        self.assertIn(b'\x1bM\x00', dummy.output)  # Font A.
        self.assertIn(b'\x1b!\x00', dummy.output)  # ESC ! resets double-width/height.

    def test_write_failure_still_closes_job(self):
        fake = MagicMock()
        fake.text.side_effect = OSError('Write failed')
        with patch.object(printer, 'Win32Raw', return_value=fake), redirect_stdout(io.StringIO()):
            printer.print_receipt(1, [], 0, 0, 'cash')
        fake.close.assert_called_once()


if __name__ == '__main__':
    unittest.main()
