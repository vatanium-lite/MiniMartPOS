"""Receipt rendering checks: no physical printer or database access."""
import io
import os
import unittest
from pathlib import Path
from contextlib import redirect_stdout
from unittest.mock import MagicMock, patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PIL import ImageChops
from PyQt6.QtGui import QFontDatabase, QGuiApplication
from escpos.printer import Dummy

import printer


class KhmerReceiptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QGuiApplication.instance() or QGuiApplication([])
        # Qt's offscreen backend may not discover Windows system fonts by itself.
        if not QFontDatabase.families(QFontDatabase.WritingSystem.Khmer):
            font_path = Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts' / 'KhmerUI.ttf'
            QFontDatabase.addApplicationFont(str(font_path))

    def item(self, name='ទឹកដោះគោ Angkor 100%'):
        return dict(name=name, quantity=2, line_total=8000, line_total_usd=2.0)

    def test_rendered_name_has_ink_and_white_margins(self):
        image = printer.render_khmer_name(self.item()['name'])
        self.assertEqual(image.mode, '1')
        self.assertEqual(image.width, printer.RECEIPT_WIDTH_DOTS)
        ink = ImageChops.invert(image.convert('L')).getbbox()
        self.assertIsNotNone(ink)
        self.assertGreater(ink[0], 0)
        self.assertGreater(ink[1], 0)
        self.assertLess(ink[2], image.width)
        self.assertLess(ink[3], image.height)

    def test_long_names_wrap_instead_of_truncating(self):
        short = printer.render_khmer_name('ទឹកដោះគោ')
        long = printer.render_khmer_name('ទឹកដោះគោ' * 12)
        self.assertEqual(long.width, short.width)
        self.assertGreater(long.height, short.height)

    def test_khmer_name_is_sent_as_image_not_text(self):
        fake = MagicMock()
        item = self.item()
        with patch.object(printer, 'Win32Raw', return_value=fake):
            printer.print_receipt(1, [item], 8000, 2.0, 'cash')
        fake.image.assert_called_once()
        self.assertEqual(fake.image.call_args.kwargs, dict(impl='bitImageRaster', center=False))
        text = ''.join(call.args[0] for call in fake.text.call_args_list)
        self.assertNotIn(item['name'], text)
        self.assertIn('Qty: 2  8000 KHR  $2.00', text)
        fake.close.assert_called_once()

    def test_real_encoder_outputs_raster_commands(self):
        dummy = Dummy(profile='TM-T88IV')
        with patch.object(printer, 'Win32Raw', return_value=dummy):
            printer.print_receipt(1, [self.item()], 8000, 2.0, 'cash')
        self.assertIn(b'\x1dv0', dummy.output)
        self.assertIn(b'TOTAL: 8000 KHR', dummy.output)

    def test_ascii_receipts_keep_existing_text_path(self):
        fake = MagicMock()
        with patch.object(printer, 'Win32Raw', return_value=fake):
            printer.print_receipt(1, [self.item('Milk')], 8000, 2.0, 'cash')
        fake.image.assert_not_called()
        self.assertIn('Milk', ''.join(call.args[0] for call in fake.text.call_args_list))
        fake.close.assert_called_once()

    def test_missing_font_fails_before_opening_printer(self):
        output = io.StringIO()
        with patch.object(printer.QFontDatabase, 'families', return_value=[]), \
                patch.object(printer, 'Win32Raw') as factory, redirect_stdout(output):
            printer.print_receipt(1, [self.item()], 8000, 2.0, 'cash')
        factory.assert_not_called()
        self.assertIn('Install a Khmer font', output.getvalue())

    def test_image_write_failure_still_closes_job(self):
        fake = MagicMock()
        fake.image.side_effect = OSError('Image write failed')
        output = io.StringIO()
        with patch.object(printer, 'Win32Raw', return_value=fake), redirect_stdout(output):
            printer.print_receipt(1, [self.item()], 8000, 2.0, 'cash')
        fake.close.assert_called_once()
        self.assertIn('Image write failed', output.getvalue())


if __name__ == '__main__':
    unittest.main()
