import sqlite3
from typing import Optional, List, Dict, Any
from app.config import DB_PATH

def get_connection(db_path: Optional[str] = None) -> sqlite3.Connection:
    """Returns a SQLite connection with row_factory and foreign keys enabled."""
    path = db_path or DB_PATH
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def get_order(order_id: str, db_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Retrieve an order by its ID safely using parameterized query."""
    if not order_id or not isinstance(order_id, str):
        return None
    order_id = order_id.strip()
    
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT order_id, customer_name, product_name, order_date, 
                   order_price, payment_method, payment_status, 
                   delivery_status, order_status, refunded_amount
            FROM orders
            WHERE UPPER(order_id) = UPPER(?)
        """, (order_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

def get_orders_for_customer(customer_name: str, db_path: Optional[str] = None) -> List[Dict[str, Any]]:
    """Retrieve all orders for a given customer name."""
    if not customer_name or not isinstance(customer_name, str):
        return []
    customer_name = customer_name.strip()
    
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT order_id, customer_name, product_name, order_date, 
                   order_price, payment_method, payment_status, 
                   delivery_status, order_status, refunded_amount
            FROM orders
            WHERE LOWER(customer_name) = LOWER(?)
            ORDER BY order_date DESC
        """, (customer_name,))
        return [dict(row) for row in cursor.fetchall()]

def get_all_orders(db_path: Optional[str] = None) -> List[Dict[str, Any]]:
    """Retrieve all orders for admin or sidebar display."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT order_id, customer_name, product_name, order_date, 
                   order_price, payment_method, payment_status, 
                   delivery_status, order_status, refunded_amount
            FROM orders
            ORDER BY order_date DESC, order_id ASC
        """)
        return [dict(row) for row in cursor.fetchall()]

def get_refunds_for_order(order_id: str, db_path: Optional[str] = None) -> List[Dict[str, Any]]:
    """Retrieve all refund transactions for an order."""
    if not order_id or not isinstance(order_id, str):
        return []
    order_id = order_id.strip()
    
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT refund_id, order_id, amount, reason, created_at
            FROM refunds
            WHERE UPPER(order_id) = UPPER(?)
            ORDER BY created_at DESC
        """, (order_id,))
        return [dict(row) for row in cursor.fetchall()]

def get_all_refunds(db_path: Optional[str] = None) -> List[Dict[str, Any]]:
    """Retrieve all refund records."""
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT refund_id, order_id, amount, reason, created_at
            FROM refunds
            ORDER BY created_at DESC
        """)
        return [dict(row) for row in cursor.fetchall()]
