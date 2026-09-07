# Database Setup & Helper Module
import sqlite3
from datetime import date, datetime

DB_FILE = "moonmart.db"
UNCHANGED = object()  # Sentinel value to indicate unchanged fields

def get_db():
    """Get a connection to the SQLite database."""
    conn = sqlite3.connect(DB_FILE)
    conn.execute("PRAGMA foreign_keys = ON;")  # Enable foreign key support
    conn.execute("PRAGMA journal_mode = WAL;")  # Enable write-ahead logging
    conn.row_factory = sqlite3.Row  # Enable named column access
    return conn

def clean_up_db(): # Remove batches with zero quantity
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM batch_inventory WHERE quantity <= 0")
        conn.commit()


def init_db():
    
    #initialise application's db schemas
    with get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS categories (
                category_id INT PRIMARY KEY, 
                name VARCHAR(50) NOT NULL, 
                description TEXT);
            CREATE TABLE IF NOT EXISTS products (
                product_id INT PRIMARY KEY, 
                barcode VARCHAR(50) UNIQUE, 
                category_id INT, 
                name VARCHAR(100), 
                unit_cost INT, 
                retail_price INT, 
                retail_price_usd DECIMAL(6, 2), 
                reorder_level INT, 
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, 

                CONSTRAINT fk_category_id 
                    FOREIGN KEY (category_id) 
                    REFERENCES categories(category_id)
            );
            CREATE TABLE IF NOT EXISTS batch_inventory (
                batch_id INT PRIMARY KEY, 
                product_id INT,  --fk
                quantity INT NOT NULL, 
                received_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP, 
                expiration_date DATE,

                CONSTRAINT fk_product_id 
                    FOREIGN KEY (product_id) 
                    REFERENCES products(product_id)
            );
            CREATE TABLE IF NOT EXISTS sales_transactions (
                transaction_id INTEGER PRIMARY KEY, 
                discount_amount INT DEFAULT 0, 
                total_amount INT NOT NULL, 
                total_amount_usd DECIMAL(6, 2) NOT NULL, 
                payment_method TEXT NOT NULL CHECK (payment_method IN ('cash', 'KHQR')), 
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS pos_item_sales (
                sale_item_id INTEGER PRIMARY KEY, 
                transaction_id INTEGER,  --fk
                product_id INT,  --fk
                quantity INT NOT NULL, 
                unit_price INT NOT NULL, 
                line_total INT NOT NULL, 
                line_total_usd DECIMAL(6, 2) NOT NULL,

                CONSTRAINT fk_transaction_id 
                    FOREIGN KEY (transaction_id) 
                    REFERENCES sales_transactions(transaction_id) 

                CONSTRAINT fk_product_id 
                    FOREIGN KEY (product_id) 
                    REFERENCES products(product_id)
            );
            CREATE TABLE IF NOT EXISTS suppliers (
                supplier_id INT PRIMARY KEY, 
                company_name VARCHAR(100), 
                contact_person VARCHAR(100), 
                phone VARCHAR(20), 
                email VARCHAR(100)
            );
            CREATE TABLE IF NOT EXISTS purchase_orders (
                purchase_order_id INT PRIMARY KEY, 
                supplier_id INT,  --fk
                status TEXT NOT NULL CHECK (status IN ('pending', 'received', 'cancelled')), 
                total_cost INT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

                CONSTRAINT fk_supplier_id 
                    FOREIGN KEY (supplier_id) 
                    REFERENCES suppliers(supplier_id)
            );
            CREATE TABLE IF NOT EXISTS po_items (
                po_item_id INT PRIMARY KEY, 
                purchase_order_id INT,  --fk
                product_id INT,  --fk
                quantity_ordered INT NOT NULL, 
                unit_cost INT, 

                CONSTRAINT fk_purchase_order_id 
                    FOREIGN KEY (purchase_order_id) 
                    REFERENCES purchase_orders(purchase_order_id), 

                CONSTRAINT fk_product_id 
                    FOREIGN KEY (product_id) 
                    REFERENCES products(product_id)
            );
            CREATE INDEX IF NOT EXISTS idx_products_barcode ON products(barcode);
            CREATE INDEX IF NOT EXISTS idx_sales_created ON sales_transactions(created_at);
        """)

def get_product_by_barcode(barcode: str):
    with get_db() as conn:
        cursor = conn.cursor() # Creates a cursor object to execute SQL queries
        cursor.execute("SELECT * FROM products WHERE barcode = ?", (barcode,))
        return cursor.fetchone() # Loads only one row at a time, ideal for retrieving specific records
    
def process_checkout(cart_items: list, payment_method: str) -> int: # cart_items is a list of dictionaries containing name, product_id, quantity, unit_price, line_total, and line_total_usd for each item
    """Atomic checkout transaction."""
    total_amount = sum(item['line_total'] for item in cart_items)
    total_amount_usd = sum(item['line_total_usd'] for item in cart_items)

    with get_db() as conn:
        cursor = conn.cursor()

        # 1. Record Sale
        cursor.execute(
            "INSERT INTO sales_transactions (total_amount, total_amount_usd, payment_method) VALUES (?, ?, ?)",
            (total_amount, total_amount_usd, payment_method)
        )

        transaction_id = cursor.lastrowid

        # 2. Insert Line Items & Deduct Stock
        
        for item in cart_items:
            cursor.execute(
                """INSERT INTO pos_item_sales (transaction_id, product_id, quantity, unit_price, line_total, line_total_usd) 
                    VALUES (?, ?, ?, ?, ?, ?)""",
                (transaction_id, item['product_id'], item['quantity'], item['unit_price'], item['line_total'], item['line_total_usd'])
            )

            cursor.execute( # Fetch available batches sorted by FIFO
                """
                SELECT batch_id, quantity
                FROM batch_inventory
                WHERE product_id = ? AND quantity > 0
                ORDER BY expiration_date ASC
                """,
                (item['product_id'],)
            )

            batches = cursor.fetchall()
            requested_quantity = item['quantity'] # Quantity to be deducted from stock

            for batch in batches:
                if requested_quantity <= 0:
                    break

                deduct_quantity = min(batch['quantity'], requested_quantity) # Checks if the batch has enough quantity to fulfill the requested quantity

                cursor.execute(
                    "UPDATE batch_inventory SET quantity = quantity - ? WHERE batch_id = ?",
                    (deduct_quantity, batch['batch_id'])
                )
                
                requested_quantity -= deduct_quantity

            if requested_quantity > 0:
                raise ValueError(f"Insufficient stock for product_id {item['product_id']}") # Raises an error if the requested quantity exceeds available stock

        conn.commit()

        return transaction_id

def add_stock(barcode: str, quantity: int, exp_date: date): # Stock replenishment
    # if product already exists

    product = get_product_by_barcode(barcode)

    if product: # If product already exists
        product_id = product['product_id']
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """ INSERT INTO batch_inventory (product_id, quantity, expiration_date) 
                VALUES (?, ?, ?) """,
                (product_id, quantity, exp_date)
            )
            conn.commit()
            return cursor.fetchone() # Returns the last inserted row of batch_inventory table

    with get_db() as conn: # If product does not exist, add to product_id first
        cursor = conn.cursor()
        cursor.execute(
            """ INSERT INTO products (barcode) 
                VALUES (?) """,
            (barcode,)
        )
        conn.commit()
        add_stock(barcode, quantity, exp_date) # Recursively call add_stock to add the stock after adding the product

def delete_stock(barcode: str, quantity: int): # Stock removal
    product = get_product_by_barcode(barcode)

    if not product:
        raise ValueError(f"Product with barcode {barcode} does not exist.")

    product_id = product['product_id']
    product_name = product['name']
    with get_db() as conn: # Sorts batches by expiration date and deducts stock from the earliest batch first (FIFO)
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT batch_id, quantity
            FROM batch_inventory
            WHERE product_id = ? AND quantity > 0
            ORDER BY expiration_date ASC
            """,
            (product_id,)
        )

        batches = cursor.fetchall()
        requested_quantity = quantity

        for batch in batches:
            if requested_quantity <= 0:
                break

            deduct_quantity = min(batch['quantity'], requested_quantity)

            cursor.execute(
                "UPDATE batch_inventory SET quantity = quantity - ? WHERE batch_id = ?",
                (deduct_quantity, batch['batch_id'])
            )

            requested_quantity -= deduct_quantity

        if requested_quantity > 0:
            raise ValueError(f"Insufficient stock for {product_name}")

        conn.commit()

def edit_product(barcode: str, category_id: int = UNCHANGED, name: str = UNCHANGED, unit_cost: int = UNCHANGED, retail_price: int = UNCHANGED, reorder_level: int = UNCHANGED): # Edit product information
    product = get_product_by_barcode(barcode)

    if not product:
        raise ValueError(f"Product with barcode {barcode} does not exist.")

    product_id = product['product_id']

    updates = {} # Dictionary to hold the fields to be updated

    if category_id is not UNCHANGED:
        updates['category_id'] = category_id

    if name is not UNCHANGED:
        updates['name'] = name

    if unit_cost is not UNCHANGED:
        updates['unit_cost'] = unit_cost

    if retail_price is not UNCHANGED:
        updates['retail_price'] = retail_price
        updates['retail_price_usd'] = round(int(retail_price) / 4000, 2)

    if reorder_level is not UNCHANGED:
        updates['reorder_level'] = reorder_level

    if not updates:
        print("No changes provided.")
        return

    # Dynamically build the SQL statement safely
    set_clause = ", ".join([f"{column} = ?" for column in updates.keys()])
    
    # Extract the values in the exact same order as the columns
    query_values = list(updates.values())

    # Append product_id for the WHERE clause
    query_values.append(product_id) 

    sql_query = f"UPDATE products SET {set_clause} WHERE product_id = ?;"

    # Execute the query
    with get_db() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(sql_query, query_values)
            conn.commit()
            print(f"Product {product_id} updated successfully.")
        except sqlite3.Error as e:
            print(f"Database error: {e}")
            conn.rollback()


def get_daily_sales_report(): # Generates a 7 AM to 2 AM local-time business-day sales report
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            WITH reporting_period AS (
                SELECT datetime(
                    CASE
                        WHEN time('now', 'localtime') < '07:00:00'
                            THEN date('now', 'localtime', '-1 day') || ' 07:00:00'
                        ELSE date('now', 'localtime') || ' 07:00:00'
                    END,
                    'utc'
                ) AS starts_at
            )
            SELECT 
                COUNT(transaction_id) as total_transactions,
                COALESCE(SUM(total_amount), 0) as revenue,
                COALESCE(SUM(total_amount_usd), 0.0) as revenue_usd
            FROM sales_transactions, reporting_period
            WHERE created_at >= reporting_period.starts_at
              AND created_at < datetime(reporting_period.starts_at, '+19 hours')
            """)
        return cursor.fetchone()