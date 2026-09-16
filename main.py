# Main POS UI

import sys
import sqlite3
from decimal import Decimal, DecimalException
from tkinter import dialog
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QLineEdit, QTableWidget, QTableWidgetItem, 
                             QPushButton, QLabel, QMessageBox, QHeaderView, QDateEdit, QDialog,
                             QFormLayout, QDialogButtonBox, QAbstractItemView)
from PyQt6.QtCore import Qt, QDate, QRegularExpression
from PyQt6.QtGui import QRegularExpressionValidator

import db
import printer

def load_stylesheet(file_path): # Helper function to read the external CSS/QSS file safely.
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        print(f"Warning: Stylesheet file '{file_path}' not found.")
        return ""

class MoonMartPOS(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Moon Mart POS System")
        self.resize(1000, 600)

        """ cart is a list of dictionaries containing 
                            name,
                            product_id, 
                            quantity, 
                            unit_price, 
                            line_total, and 
                            line_total_usd for each item"""
        self.cart = []
        
        db.init_db()
        db.clean_up_db()
        self.init_ui()

    # Set up the GUI

    def init_ui(self):
        main_layout = QHBoxLayout() # Creates a horizontal layout manager
        left_panel = QVBoxLayout()
        right_panel = QVBoxLayout()

        # Barcode Input (Auto-focused for Scanner)
        self.barcode_input = QLineEdit() # Instantiates a single-line text input field
        self.barcode_input.setPlaceholderText("Scan or Enter Barcode...")
        self.barcode_input.setStyleSheet("placeholder-text-color: #a3a3a3;")
        self.barcode_input.setObjectName("main_barcode_input")
        self.barcode_input.returnPressed.connect(self.handle_barcode_scan) # Connects the signal (when pressed Enter/Return) to barcode handler method
        left_panel.addWidget(self.barcode_input)

        # Cart Table
        self.cart_table = QTableWidget(0, 6) # Creates a table widget with 0 rows and 5 columns
        self.cart_table.setHorizontalHeaderLabels(["Product Name", "Price", "Qty", "Line Total", "Line Total USD", ""])
        self.cart_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch) # Sets the first column to stretch and fill available space
        self.cart_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed) # Makes last column small
        self.cart_table.setColumnWidth(5, 30)
        self.cart_table.cellChanged.connect(self.handle_cell_changed) # Connects the signal (when a cell is changed) to the handle_cell_changed method
        left_panel.addWidget(self.cart_table)

        # Totals Display
        self.total_label = QLabel("TOTAL:\n\n0 KHR\n$ 0.000") # Displays text or image
        self.total_label.setObjectName("total_label")
        self.total_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        right_panel.addWidget(self.total_label)

        self.discount_input = QLineEdit()
        self.discount_input.setObjectName("discount_input")
        self.discount_input.setPlaceholderText("Discount (KHR)")
        self.discount_input.setAccessibleName("Whole-sale discount in KHR")
        self.discount_input.setToolTip("Whole-sale discount in KHR; blank means 0. USD conversion: 4,000 KHR = $1.")
        self.discount_input.setMaxLength(12)
        self.discount_input.setValidator(QRegularExpressionValidator(QRegularExpression('[0-9]*'), self.discount_input))
        discount_row = QWidget()
        discount_row.setObjectName("discount_row")
        discount_layout = QHBoxLayout(discount_row)
        discount_layout.setContentsMargins(0, 0, 0, 0)
        discount_layout.addStretch()
        discount_layout.addWidget(self.discount_input)
        right_panel.addWidget(discount_row, alignment=Qt.AlignmentFlag.AlignHCenter)
        self.discount_error = QLabel()
        self.discount_error.setObjectName("discount_error")
        self.discount_error.setWordWrap(True)
        self.discount_error.hide()
        right_panel.addWidget(self.discount_error)

        # Checkout Buttons
        btn_cash = QPushButton("Pay Cash")
        btn_cash.setObjectName("btn_cash")
        btn_cash.clicked.connect(lambda: self.process_payment("cash")) # Binds button click event to payment processor method with cash
        right_panel.addWidget(btn_cash, alignment=Qt.AlignmentFlag.AlignHCenter)

        btn_qr = QPushButton("Pay KHQR")
        btn_qr.setObjectName("btn_qr")
        btn_qr.clicked.connect(lambda: self.process_payment("KHQR")) 
        right_panel.addWidget(btn_qr, alignment=Qt.AlignmentFlag.AlignHCenter)
        self.payment_buttons = (btn_cash, btn_qr)

        # Daily Sales Report Button
        btn_report = QPushButton("Daily Sales Summary")
        btn_report.setObjectName("btn_report")
        btn_report.clicked.connect(self.show_daily_report)
        right_panel.addWidget(btn_report, alignment=Qt.AlignmentFlag.AlignHCenter)

        right_panel.addStretch()

        # Stock Replenishment Button
        btn_add_stock = QPushButton("Add Stock")
        btn_add_stock.setObjectName("btn_add_stock")
        btn_add_stock.setStyleSheet("background-color: #E67E22; color: white; font-size: 16px; padding: 10px;")
        btn_add_stock.clicked.connect(self.handle_add_stock)
        right_panel.addWidget(btn_add_stock, alignment=Qt.AlignmentFlag.AlignHCenter)

        # Stock Reduction Button
        btn_delete_stock = QPushButton("Delete Stock")
        btn_delete_stock.setObjectName("btn_delete_stock")
        btn_delete_stock.setStyleSheet("background-color: #E67E22; color: white; font-size: 16px; padding: 10px;")
        btn_delete_stock.clicked.connect(self.handle_delete_stock)
        right_panel.addWidget(btn_delete_stock, alignment=Qt.AlignmentFlag.AlignHCenter)

        # Stock Modification Button
        btn_edit_product = QPushButton("Edit Product")
        btn_edit_product.setObjectName("btn_edit_product")
        btn_edit_product.setStyleSheet("background-color: #E67E22; color: white; font-size: 16px; padding: 10px;")
        btn_edit_product.clicked.connect(self.handle_edit_product)
        right_panel.addWidget(btn_edit_product, alignment=Qt.AlignmentFlag.AlignHCenter)

        btn_add_product = QPushButton("Add Product")
        btn_add_product.setObjectName("btn_add_product")
        btn_add_product.clicked.connect(self.handle_add_product)
        right_panel.addWidget(btn_add_product, alignment=Qt.AlignmentFlag.AlignHCenter)

        # Let the table take extra width; keep the controls at their needed width.
        main_layout.addLayout(left_panel, 1)
        main_layout.addLayout(right_panel, 0)

        container = QWidget()
        container.setLayout(main_layout)
        self.setCentralWidget(container)
        self.discount_input.textChanged.connect(self.update_totals)
        self.update_totals()

    def update_totals(self):
        """Refresh the payable totals whenever the cart or whole-sale discount changes."""
        try:
            text = self.discount_input.text().strip()
            if text and (not text.isascii() or not text.isdigit()):
                raise ValueError("Discount must be a non-negative whole number in KHR.")
            discount = int(text) if text else 0
            total, total_usd = db.calculate_checkout_totals(self.cart, discount)
        except ValueError as error:
            self.total_label.setText("TOTAL:\n\nInvalid discount")
            self.discount_error.setText(str(error))
            self.discount_error.show()
            for button in self.payment_buttons:
                button.setEnabled(False)
            return None

        self.discount_error.clear()
        self.discount_error.hide()
        for button in self.payment_buttons:
            button.setEnabled(True)
        self.total_label.setText(f"TOTAL:\n\n{total} KHR\n$ {total_usd:.3f}")
        return total, total_usd, discount

    def handle_barcode_scan(self):
        barcode = self.barcode_input.text().strip()
        self.barcode_input.clear() # Clears the input field after scanning
        
        if not barcode:
            return  # Halts execution if the barcode is empty

        product = db.get_product_by_barcode(barcode)
        if not product:
            QMessageBox.warning(self, "Not Found", f"No product found for barcode: {barcode}")
            return

        existing_item = next( # Loops through the cart to find the first matching item
            (item for item in self.cart if item['product_id'] == product['product_id']), None # Returns item if it already exists in the cart, else None
        )
        try:
            price = product['retail_price']
            price_usd = product['retail_price_usd']
            if type(price) is not int or not 0 < price <= 9223372036854775807:
                raise ValueError("KHR price must be a positive integer within the supported range.")
            if isinstance(price_usd, bool) or not isinstance(price_usd, (int, float, Decimal)):
                raise ValueError("USD price must be a positive finite number.")
            if not Decimal(str(price_usd)).is_finite() or price_usd <= 0:
                raise ValueError("USD price must be a positive finite number.")

            previous_quantity = existing_item['quantity'] if existing_item is not None else 0 # If scanned item already exists, fetch its quantity, else 0
            if type(previous_quantity) is not int or previous_quantity < 0:
                raise ValueError("The cart quantity is invalid. Remove this item and scan it again.")
            if previous_quantity >= 1000:
                raise ValueError("Quantity should not be greater than 1000 units.")
            new_quantity = previous_quantity + 1
            new_line_total = new_quantity * price
            if new_line_total > 9223372036854775807:
                raise ValueError("The KHR line total exceeds the supported range.")
            new_line_total_usd = db.calculate_usd_line_total(new_quantity, price_usd)
            if new_line_total_usd <= 0:
                raise ValueError("The USD line total must be positive after rounding to three decimals.")

            # Prepare a separate candidate so failed calculations cannot change the cart.
            candidate = dict(existing_item) if existing_item is not None else { # Makes a copy of item if it already exists, else creates a new one
                'product_id': product['product_id'], 'name': product['name']
            }
            candidate.update(unit_price=price, unit_price_usd=price_usd,
                             quantity=new_quantity, line_total=new_line_total,
                             line_total_usd=new_line_total_usd)
            candidate_cart = [candidate if item is existing_item else item for item in self.cart] # Makes a copy of cart, changing only existing and newly scanned item while keeping other items as is
            if existing_item is None: 
                candidate_cart.append(candidate) # For newly scanned item that does not exist in the cart, add it
            subtotal, _ = db.calculate_checkout_totals(candidate_cart)
            if subtotal > 9223372036854775807:
                raise ValueError("The cart's KHR total exceeds the supported range.")
        except (DecimalException, OverflowError):
            QMessageBox.warning(self, "Invalid Price", f"Barcode: {barcode}\nThe USD amounts exceed the supported range.")
            return
        except ValueError as error:
            QMessageBox.warning(self, "Invalid Price", f"Barcode: {barcode}\n{error}")
            return

        # All checks passed: temporary candidate_cart's sub_total can be calculated, so we commit the candidate to the real cart
        if existing_item is None:
            self.cart.append(candidate) # Adds new item in the cart if not exist
        else:
            existing_item.update(candidate) # Updates the item if exist
        self.update_cart_ui()

    def update_cart_ui(self):

        self.cart_table.blockSignals(True)  # Temporarily blocks signals so setting items doesn't trigger cellChanged event

        self.cart_table.setRowCount(0)

        for row_idx, item in enumerate(self.cart):
            self.cart_table.insertRow(row_idx) # Creates a blank row at position row_idx
            self.cart_table.setItem(row_idx, 0, QTableWidgetItem(item['name']))
            self.cart_table.setItem(row_idx, 1, QTableWidgetItem(f"{item['unit_price']} KHR"))
            self.cart_table.setItem(row_idx, 2, QTableWidgetItem(str(item['quantity'])))
            self.cart_table.setItem(row_idx, 3, QTableWidgetItem(f"{item['line_total']} KHR"))
            self.cart_table.setItem(row_idx, 4, QTableWidgetItem(f"${item['line_total_usd']:.3f}"))

            btn_remove = QPushButton("✕")
            btn_remove.setFixedSize(40, 30)
            btn_remove.setObjectName("btn_remove")

            btn_remove.clicked.connect(
                lambda checked, row=row_idx: self.remove_cart_item(row) # clicked emits checked(boolean) argument, we use checked to catch that
            )                                                           # this can be simplified to lambda: self.remove_cart_item(row_idx)

            self.cart_table.setCellWidget(row_idx, 5, btn_remove)

            self.cart_table.verticalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)

            for col_idx in range(1, 5):
                self.cart_table.item(row_idx, col_idx).setTextAlignment(Qt.AlignmentFlag.AlignCenter)

        for row_idx in range(self.cart_table.rowCount()): # Makes quantity editable while keeping other columns read-only
            for col_idx in range(self.cart_table.columnCount() - 1):
                if col_idx == 2:
                    self.cart_table.item(row_idx, col_idx).setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEditable)
                else:
                    self.cart_table.item(row_idx, col_idx).setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)

        if not self.cart:
            self.discount_input.clear()
        self.update_totals()

        self.cart_table.blockSignals(False)  # Unblocks signals to resume operations

    def remove_cart_item(self, row_idx):
        if 0 <= row_idx < len(self.cart):
            self.cart.pop(row_idx)
            self.update_cart_ui()   

    def process_payment(self, payment_method: str):
        if not self.cart:
            QMessageBox.warning(self, "Empty Cart", "Please scan items before checking out.")
            return

        totals = self.update_totals()
        if totals is None:
            QMessageBox.warning(self, "Invalid Discount", self.discount_error.text())
            return
        total, total_usd, discount = totals

        try:
            transaction_id = db.process_checkout(self.cart, payment_method, discount_amount=discount)
        except ValueError as error:
            QMessageBox.warning(self, "Checkout Failed", str(error))
            return
        except sqlite3.OperationalError as operror:
            QMessageBox.warning(self, "Checkout Failed", str(operror))
            return


        # Trigger ESC/POS Thermal Print
        printer.print_receipt(transaction_id, self.cart, total, total_usd, payment_method, discount_amount=discount)

        QMessageBox.information(self, "Success", f"Sale #{transaction_id} completed successfully!")
        self.cart.clear()
        self.update_cart_ui()
        self.barcode_input.setFocus()

    def handle_cell_changed(self, row_idx, column_idx): # Handles quantity cell changes in the cart table
        if column_idx != 2:  # Only allow changes in the quantity column
            return

        if not 0 <= row_idx < len(self.cart):
            return

        quantity_item = self.cart_table.item(row_idx, 2) # Retrieves the changed quantity cell item at the specified row and column

        try:
            if not quantity_item or not quantity_item.text().isdigit():
                raise ValueError
            
            quantity = int(quantity_item.text()) # New quantity

            if quantity < 1:
                raise ValueError

            if quantity > 1000:
                raise OverflowError
            
            # Table rows follow the same order as the cart (sorting is disabled).
            item = self.cart[row_idx]
            item['quantity'] = quantity
            item['line_total'] = quantity * item['unit_price']
            item['line_total_usd'] = db.calculate_usd_line_total(quantity, item['unit_price_usd'])

            # Updates the affected cells
            self.cart_table.item(row_idx, 3).setText(
                f"{item['line_total']} KHR"
            )
            self.cart_table.item(row_idx, 4).setText(
                f"${item['line_total_usd']:.3f}"
            )

            self.update_totals()

            return         
        except (ValueError):
            # Restore the displayed quantity without triggering this handler again.
            signals_were_blocked = self.cart_table.blockSignals(True) # Sets blockSignals to True and returns previous state (False)
            try:
                previous_quantity = str(self.cart[row_idx]['quantity'])
                if quantity_item is not None:
                    quantity_item.setText(previous_quantity)
                else:
                    self.cart_table.setItem(row_idx, 2, QTableWidgetItem(previous_quantity))
            finally:
                self.cart_table.blockSignals(signals_were_blocked) # Re-activates signals
            QMessageBox.warning(
                self,
                "Invalid Quantity",
                "Please enter a valid positive integer for quantity."
            )
        except (OverflowError):
            # Restore the displayed quantity without triggering this handler again.
            signals_were_blocked = self.cart_table.blockSignals(True) # Sets blockSignals to True and returns previous state (False)
            try:
                previous_quantity = str(self.cart[row_idx]['quantity'])
                if quantity_item is not None:
                    quantity_item.setText(previous_quantity)
                else:
                    self.cart_table.setItem(row_idx, 2, QTableWidgetItem(previous_quantity))
            finally:
                self.cart_table.blockSignals(signals_were_blocked) # Re-activates signals
            QMessageBox.warning(
                self,
                "Invalid Quantity",
                "Quantity should not be greater than 1000 units."
            )



    def handle_add_stock(self):

        # Creates a popup dialog
        dialog = QDialog(self)
        dialog.setWindowTitle("Add Stock")
        dialog.setFixedSize(400, 200)

        form_layout = QFormLayout(dialog)

        barcode_input = QLineEdit()
        barcode_input.setPlaceholderText("Enter or scan barcode")
        barcode_input.setStyleSheet("placeholder-text-color: #a3a3a3;")
        form_layout.addRow("Barcode:", barcode_input)

        quantity_input = QLineEdit()
        quantity_input.setPlaceholderText("Enter quantity")
        quantity_input.setStyleSheet("placeholder-text-color: #a3a3a3;")
        form_layout.addRow("Quantity:", quantity_input)

        exp_date_input = QDateEdit()
        exp_date_input.setCalendarPopup(True)
        exp_date_input.setDate(QDate.currentDate())
        exp_date_input.setDisplayFormat("yyyy-MM-dd")
        form_layout.addRow("Expiration Date:", exp_date_input)

        # 3. Add OK and Cancel action buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        form_layout.addRow(button_box)

        def add_stock_submission(): # Helper function to process the stock addition form
            barcode = barcode_input.text().strip()
            quantity_text = quantity_input.text().strip()
            exp_date = exp_date_input.date().toString("yyyy-MM-dd")

            if not barcode:
                QMessageBox.warning(
                    dialog, "Input Error", "Please enter or scan a barcode."
                )
                return

            if not quantity_text:
                quantity_input.setFocus()
                return

            if not quantity_text.isdigit() or int(quantity_text) <= 0:
                QMessageBox.warning(
                    dialog,
                    "Input Error",
                    "Please enter a valid positive integer for quantity.",
                )
                return

            try:
                # Call database function
                db.add_stock(barcode, int(quantity_text), exp_date)

                QMessageBox.information(
                    dialog,
                    "Success",
                    f"Successfully added {quantity_text} units for barcode: {barcode}",
                )
                dialog.accept()  # Close the popup window

            except ValueError as e:
                QMessageBox.warning(dialog, "Cannot Add Stock", str(e))
                barcode_input.setFocus()
            except Exception as e:
                QMessageBox.critical(
                    dialog, "Database Error", f"Failed to update stock:\n{str(e)}"
                )

        button_box.accepted.connect(add_stock_submission) # If the user clicks OK (accepted), the add_stock_submission function is called
        button_box.rejected.connect(dialog.reject)

        # 4. Display the popup modally
        dialog.exec()


    def handle_delete_stock(self):

        dialog = QDialog(self)
        dialog.setWindowTitle("Delete Stock")
        dialog.setFixedSize(400, 200)

        form_layout = QFormLayout(dialog)

        barcode_input = QLineEdit()
        barcode_input.setPlaceholderText("Enter or scan barcode")
        barcode_input.setStyleSheet("placeholder-text-color: #a3a3a3")
        form_layout.addRow("Barcode:", barcode_input)

        quantity_input = QLineEdit()
        quantity_input.setPlaceholderText("Enter quantity")
        quantity_input.setStyleSheet("placeholder-text-color: #a3a3a3")
        form_layout.addRow("Quantity:", quantity_input)

        # 3. Add OK and Cancel action buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        form_layout.addRow(button_box)   

        def delete_stock_submission(): # Helper function to process the stock removal form
            barcode = barcode_input.text().strip()
            quantity_text = quantity_input.text().strip()

            if not barcode:
                QMessageBox.warning(
                    dialog, "Input Error", "Please enter or scan a barcode."
                )
                return

            if not quantity_text:
                quantity_input.setFocus()
                return

            if not quantity_text.isdigit() or int(quantity_text) <= 0:
                QMessageBox.warning(
                    dialog,
                    "Input Error",
                    "Please enter a valid positive integer for quantity.",
                )
                return

            try:
                # Call database function
                db.delete_stock(barcode, int(quantity_text))

                QMessageBox.information(
                    dialog,
                    "Success",
                    f"Successfully removed {quantity_text} units for barcode: {barcode}",
                )
                dialog.accept()  # Close the popup window

            except Exception as e:
                QMessageBox.critical(
                    dialog, "Database Error", f"Failed to update stock:\n{str(e)}"
                )


        button_box.accepted.connect(delete_stock_submission) # If the user clicks OK (accepted), the delete_stock_submission function is called
        button_box.rejected.connect(dialog.reject)

        dialog.exec()

    def handle_add_product(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Add Product")
        dialog.setMinimumWidth(460)
        form_layout = QFormLayout(dialog)

        name_input = QLineEdit()
        name_input.setObjectName("add_product_name")
        name_input.setPlaceholderText("Enter product name")
        form_layout.addRow("Name (required):", name_input)

        barcode_input = QLineEdit()
        barcode_input.setObjectName("add_product_barcode")
        barcode_input.setPlaceholderText("Enter or scan barcode")
        form_layout.addRow("Barcode (required):", barcode_input)

        unit_cost_input = QLineEdit()
        unit_cost_input.setObjectName("add_product_unit_cost")
        unit_cost_input.setPlaceholderText("Optional; blank means 0")
        form_layout.addRow("Unit cost (KHR):", unit_cost_input)

        price_input = QLineEdit()
        price_input.setObjectName("add_product_price")
        price_input.setPlaceholderText("Enter price in KHR")
        form_layout.addRow("Price (KHR, required):", price_input)

        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        form_layout.addRow(button_box)

        def add_product_submission():
            try:
                name = name_input.text().strip()
                barcode = barcode_input.text().strip()
                if not name:
                    name_input.setFocus()
                    raise ValueError("Product name is required.")
                if not barcode:
                    barcode_input.setFocus()
                    raise ValueError("Barcode is required.")

                def parse_khr(field, label, optional=False):
                    text = field.text().strip()
                    if optional and not text:
                        return 0
                    if not text:
                        field.setFocus()
                        raise ValueError(f"{label} is required.")
                    if not text.isascii() or not text.isdigit() or len(text) > 19:
                        field.setFocus()
                        raise ValueError(f"{label} must be a non-negative whole number in KHR (up to 19 digits).")
                    return int(text)

                unit_cost = parse_khr(unit_cost_input, "Unit cost", optional=True)
                price = parse_khr(price_input, "Price")
                db.add_product(name, barcode, price, unit_cost)
            except ValueError as error:
                QMessageBox.warning(dialog, "Cannot Add Product", str(error))
                return
            except Exception as error:
                QMessageBox.critical(dialog, "Database Error", f"Failed to add product:\n{error}")
                return

            QMessageBox.information(dialog, "Success", f"Product '{name}' added successfully. Use Add Stock to add inventory.")
            dialog.accept()

        button_box.accepted.connect(add_product_submission)
        button_box.rejected.connect(dialog.reject)
        name_input.setFocus()
        dialog.exec()

    def handle_edit_product(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Edit Product")
        dialog.setFixedSize(400, 400)

        form_layout = QFormLayout(dialog)

        barcode_input = QLineEdit()
        barcode_input.setPlaceholderText("Enter or scan barcode")
        barcode_input.setStyleSheet("placeholder-text-color: #a3a3a3;")
        form_layout.addRow("Barcode:", barcode_input)

        cat_id_input = QLineEdit()
        cat_id_input.setPlaceholderText("Enter category ID")
        cat_id_input.setStyleSheet("placeholder-text-color: #a3a3a3;")
        form_layout.addRow("Category ID:", cat_id_input)

        name_input = QLineEdit()
        name_input.setPlaceholderText("Enter product name")
        name_input.setStyleSheet("placeholder-text-color: #a3a3a3;")
        form_layout.addRow("Product Name:", name_input)

        unit_cost_input = QLineEdit()
        unit_cost_input.setPlaceholderText("Enter unit cost in KHR")
        unit_cost_input.setStyleSheet("placeholder-text-color: #a3a3a3;")
        form_layout.addRow("Unit Cost:", unit_cost_input)

        retail_price_input = QLineEdit()
        retail_price_input.setPlaceholderText("Enter retail price in KHR")
        retail_price_input.setStyleSheet("placeholder-text-color: #a3a3a3;")
        form_layout.addRow("Retail Price:", retail_price_input)

        reorder_level_input = QLineEdit()
        reorder_level_input.setPlaceholderText("Enter reorder level")
        reorder_level_input.setStyleSheet("placeholder-text-color: #a3a3a3;")
        form_layout.addRow("Reorder Level:", reorder_level_input)

        # 3. Add OK and Cancel action buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )
        form_layout.addRow(button_box)

        def edit_product_submission(): # Helper function to process the product editing form
            barcode = barcode_input.text().strip()
            cat_id_text = cat_id_input.text().strip()
            name = name_input.text().strip()
            unit_cost_text = unit_cost_input.text().strip()
            retail_price_text = retail_price_input.text().strip()
            reorder_level_text = reorder_level_input.text().strip()

            if not barcode:
                QMessageBox.warning(
                    dialog, "Input Error", "Please enter or scan a barcode."
                )
                return

            if cat_id_text and (not cat_id_text.isdigit() or int(cat_id_text) <= 0):
                QMessageBox.warning(
                    dialog,
                    "Input Error",
                    "Please enter a valid positive integer for category ID or leave blank.",
                )
                return

            if unit_cost_text and (not unit_cost_text.isdigit() or int(unit_cost_text) < 0):
                QMessageBox.warning(
                    dialog,
                    "Input Error",
                    "Please enter a valid non-negative integer for unit cost or leave blank.",
                )
                return

            if retail_price_text and (not retail_price_text.isdigit() or int(retail_price_text) < 0):
                QMessageBox.warning(
                    dialog,
                    "Input Error",
                    "Please enter a valid non-negative integer for retail price or leave blank.",
                )
                return

            if reorder_level_text and (not reorder_level_text.isdigit() or int(reorder_level_text) < 0):
                QMessageBox.warning(
                    dialog,
                    "Input Error",
                    "Please enter a valid non-negative integer for reorder level or leave blank.",
                )
                return

            user_inputs = {
                "category_id": int(cat_id_text) if cat_id_text else None,
                "name": name if name else None,
                "unit_cost": int(unit_cost_text) if unit_cost_text else None,
                "retail_price": int(retail_price_text) if retail_price_text else None,
                "reorder_level": int(reorder_level_text) if reorder_level_text else None
            }


            # Filters out None values, keeping only the fields that the user wants to update
            update_data = {                     
                key: value for key, value in user_inputs.items() if value is not None 
            }

            try:
                # Call database function
                db.edit_product(barcode, **update_data) # Unpacks the update_data dictionary into keyword arguments (leaves blank fields as default value defined in the database)

                QMessageBox.information(
                    dialog,
                    "Success",
                    f"Successfully updated product for barcode: {barcode}",
                )
                dialog.accept()  # Close the popup window

            except Exception as e:
                QMessageBox.critical(
                    dialog, "Database Error", f"Failed to update product:\n{str(e)}"
                )


        button_box.accepted.connect(edit_product_submission) # If the user clicks OK (accepted), the edit_product_submission function is called
        button_box.rejected.connect(dialog.reject)

        dialog.exec()    

    def show_daily_report(self):
        report = db.get_daily_sales_report()
        tx_count = report['total_transactions']
        revenue = report['revenue']
        revenue_usd = report['revenue_usd']

        QMessageBox.information(
            self, 
            "Business-Day Sales Summary (7 AM–2 AM)",
            f"Total Completed Transactions: {tx_count}\nTotal Daily Revenue: {revenue} KHR | ${revenue_usd:.3f}"
        )


if __name__ == "__main__":
    app = QApplication(sys.argv) # initializes the application with command-line arguments
    app.setStyleSheet(load_stylesheet("style.qss"))
    window = MoonMartPOS()
    window.show()
    sys.exit(app.exec()) # Passes the exit code from the application to the operating system once exec() finishes (i.e. last primary window closed)
