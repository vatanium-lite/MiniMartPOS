import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import db


class TimestampImportTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.database = str(Path(directory.name) / "imports.db")
        database_patch = patch.object(db, "DB_FILE", self.database)
        database_patch.start()
        self.addCleanup(database_patch.stop)
        db.init_db()
        # Simulate DB Browser: a separate connection with no application helpers.
        self.conn = sqlite3.connect(self.database)
        self.addCleanup(self.conn.close)
        self.conn.execute("PRAGMA foreign_keys = ON")

    def assert_current_bangkok_time(self, value):
        difference = self.conn.execute(
            "SELECT abs(julianday(?) - julianday('now', '+7 hours')) * 86400",
            (value,),
        ).fetchone()[0]
        self.assertIsNotNone(difference, value)
        self.assertLess(difference, 5, value)

    def test_csv_values_and_timestamp_edits(self):
        # The actual schema defaults and their literal representations both work.
        cases = (
            ("products", "created_at", "barcode", "import-test"),
            ("batch_inventory", "received_date", "quantity", 1),
            ("sales_transactions", "created_at",
             "total_amount, total_amount_usd, payment_method", (4000, 1, "cash")),
            ("purchase_orders", "created_at", "status", "pending"),
        )
        for recursive in (0, 1):
            self.conn.execute(f"PRAGMA recursive_triggers = {recursive}")
            for table, column, required_columns, required_values in cases:
                with self.subTest(table=table, recursive=recursive):
                    values = required_values if isinstance(required_values, tuple) else (required_values,)
                    placeholders = ", ".join("?" for _ in values)
                    rowid = self.conn.execute(
                        f"INSERT INTO {table} ({required_columns}) VALUES ({placeholders})",
                        values,
                    ).lastrowid
                    read_value = lambda: self.conn.execute(
                        f"SELECT {column} FROM {table} WHERE rowid = ?", (rowid,)
                    ).fetchone()[0]
                    self.assert_current_bangkok_time(read_value())
                    self.conn.execute(f"DELETE FROM {table} WHERE rowid = ?", (rowid,))

                    default_text = next(
                        field[4] for field in self.conn.execute(f"PRAGMA table_info({table})")
                        if field[1] == column
                    )
                    for imported in (None, "", " \t\r\n", default_text,
                                     " ( DATETIME( 'now', '+7 hours' ) ) ",
                                     "CURRENT_TIMESTAMP", "(CURRENT_TIMESTAMP)"):
                        rowid = self.conn.execute(
                            f"INSERT INTO {table} ({required_columns}, {column}) "
                            f"VALUES ({placeholders}, ?)", (*values, imported),
                        ).lastrowid
                        self.assert_current_bangkok_time(read_value())
                        self.conn.execute(
                            f"UPDATE {table} SET {column} = ? WHERE rowid = ?",
                            (imported, rowid),
                        )
                        self.assert_current_bangkok_time(read_value())
                        self.conn.execute(f"DELETE FROM {table} WHERE rowid = ?", (rowid,))

    def test_explicit_dates_and_other_data_are_preserved(self):
        for value in ("2026-09-07 16:30:59", "2026-09-08T10:00:00+07:00", "unknown"):
            rowid = self.conn.execute(
                "INSERT INTO products (name, created_at) VALUES (?, ?)", ("Original", value)
            ).lastrowid
            self.conn.execute("UPDATE products SET name = 'Edited' WHERE rowid = ?", (rowid,))
            self.assertEqual(self.conn.execute(
                "SELECT created_at FROM products WHERE rowid = ?", (rowid,)
            ).fetchone()[0], value)
            self.conn.execute(
                "UPDATE products SET created_at = ? WHERE rowid = ?", (value, rowid)
            )
            self.assertEqual(self.conn.execute(
                "SELECT created_at FROM products WHERE rowid = ?", (rowid,)
            ).fetchone()[0], value)

    def test_existing_database_installation_and_restart(self):
        for name, in self.conn.execute("SELECT name FROM sqlite_master WHERE type = 'trigger'").fetchall():
            self.conn.execute(f'DROP TRIGGER "{name}"')
        old_values = ("2026-09-07 16:30:59", "(datetime('now', '+7 hours'))")
        self.conn.executemany("INSERT INTO products (created_at) VALUES (?)", [(v,) for v in old_values])
        self.conn.commit()
        db.init_db()
        db.init_db()
        self.assertEqual(self.conn.execute(
            "SELECT count(*) FROM sqlite_master WHERE type = 'trigger'"
        ).fetchone()[0], 8)
        self.assertEqual(tuple(row[0] for row in self.conn.execute(
            "SELECT created_at FROM products ORDER BY rowid"
        )), old_values)
        rowid = self.conn.execute(
            "INSERT INTO products (created_at) VALUES (?)", (old_values[1],)
        ).lastrowid
        self.assert_current_bangkok_time(self.conn.execute(
            "SELECT created_at FROM products WHERE rowid = ?", (rowid,)
        ).fetchone()[0])
        self.assertEqual(self.conn.execute("PRAGMA foreign_key_check").fetchall(), [])


if __name__ == "__main__":
    unittest.main()
