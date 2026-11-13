import os
import shutil
import sqlite3
import pytest
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

@pytest.fixture
def temp_db(tmp_path):
    """
    Creates an isolated copy of the real orders.db for testing,
    so that the real database is NEVER touched by tests.
    """
    original_db = BASE_DIR / "orders.db"
    test_db_path = tmp_path / "test_orders.db"
    
    if original_db.exists():
        shutil.copy2(original_db, test_db_path)
    else:
        # Fallback creation if not found
        conn = sqlite3.connect(test_db_path)
        conn.execute("""
            CREATE TABLE orders (
                order_id TEXT PRIMARY KEY,
                customer_name TEXT NOT NULL,
                product_name TEXT NOT NULL,
                order_date DATE NOT NULL,
                order_price REAL NOT NULL,
                payment_method TEXT NOT NULL,
                payment_status TEXT NOT NULL,
                delivery_status TEXT NOT NULL,
                order_status TEXT NOT NULL,
                refunded_amount REAL NOT NULL DEFAULT 0.0
            );
        """)
        conn.execute("""
            CREATE TABLE refunds (
                refund_id TEXT PRIMARY KEY,
                order_id TEXT NOT NULL,
                amount REAL NOT NULL,
                reason TEXT NOT NULL,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (order_id) REFERENCES orders(order_id)
            );
        """)
        conn.commit()
        conn.close()

    yield str(test_db_path)

@pytest.fixture
def temp_chroma(tmp_path):
    """Creates an isolated Chroma DB directory for testing."""
    chroma_test_dir = tmp_path / "chroma_test"
    chroma_test_dir.mkdir(parents=True, exist_ok=True)
    yield str(chroma_test_dir)
