#!/usr/bin/env python3
"""Create and seed the customer-support SQLite database.

Usage:
    python scripts/create_db.py                 # creates data/support.db
    python scripts/create_db.py --reset         # backs up and recreates it
    python scripts/create_db.py --db other.db
Dates are generated relative to today so refund-window scenarios stay valid.
"""
import argparse, shutil, sqlite3, sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCHEMA = Path(__file__).resolve().parent / "schema.sql"
NOW = datetime.now().replace(microsecond=0)


def ts(days_ago=0, hour=10):
    d = (NOW - timedelta(days=days_ago)).replace(hour=hour, minute=0, second=0)
    return d.strftime("%Y-%m-%d %H:%M:%S")


CUSTOMERS = [
    (1, "Aarav Sharma",  "aarav.sharma@example.com", "+91-98450-10001"),
    (2, "Priya Nair",    "priya.nair@example.com",   "+91-98450-10002"),
    (3, "Rohan Mehta",   "rohan.mehta@example.com",  "+91-98450-10003"),
    (4, "Sneha Kulkarni","sneha.k@example.com",      "+91-98450-10004"),
    (5, "Vikram Rao",    "vikram.rao@example.com",   "+91-98450-10005"),
]

# order_id, customer, ordered_days_ago, status, items[(name, category, qty, price, refundable)],
# payment(method, status), delivery(carrier, status, shipped_days_ago, eta_days_from_now, delivered_days_ago),
# refunds[(amount, type, reason, days_ago)]
ORDERS = [
    (1001, 1, 9, "delivered",
     [("Wireless Earbuds Pro", "Electronics", 1, 3499.00, 1), ("Phone Case", "Accessories", 2, 749.50, 1)],
     ("UPI", "paid"), ("BlueDart", "delivered", 8, None, 5), []),
    (1002, 2, 16, "delivered",
     [("27-inch 4K Monitor", "Electronics", 1, 12999.00, 1)],
     ("CARD", "paid"), ("Delhivery", "delivered", 15, None, 12), []),
    (1003, 3, 52, "delivered",
     [("Bluetooth Speaker", "Electronics", 1, 2999.00, 1)],
     ("CARD", "paid"), ("BlueDart", "delivered", 50, None, 45), []),
    (1004, 1, 6, "cancelled",
     [("Running Shoes", "Footwear", 1, 3999.00, 1)],
     ("UPI", "cancelled"), ("None", "cancelled", None, None, None), []),
    (1005, 4, 17, "delivered",
     [("Mechanical Keyboard", "Electronics", 1, 5499.00, 1)],
     ("NETBANKING", "refunded"), ("Delhivery", "delivered", 16, None, 10),
     [(5499.00, "full", "Defective key switches", 8)]),
    (1006, 5, 14, "delivered",
     [("Yoga Mat", "Fitness", 1, 1299.00, 1), ("Hydration Backpack", "Fitness", 1, 2499.00, 1),
      ("Fitness Tracker", "Electronics", 1, 3699.00, 1)],
     ("CARD", "partially_refunded"), ("EcomExpress", "delivered", 12, None, 8),
     [(1299.00, "partial", "Yoga mat returned - wrong colour", 5)]),
    (1007, 2, 3, "shipped",
     [("Laptop Backpack", "Accessories", 1, 1899.00, 1)],
     ("UPI", "paid"), ("BlueDart", "in_transit", 2, 2, None), []),
    (1008, 3, 1, "processing",
     [("Notebook Set", "Stationery", 3, 299.00, 1)],
     ("CARD", "paid"), ("None", "pending", None, 4, None), []),
    (1009, 4, 5, "shipped",
     [("Smart Watch", "Electronics", 1, 8999.00, 1)],
     ("CARD", "paid"), ("Delhivery", "out_for_delivery", 3, 0, None), []),
    (1010, 5, 6, "delivered",
     [("Gaming Mouse", "Electronics", 1, 2499.00, 1), ("Software License Key", "Digital", 1, 1999.00, 0)],
     ("UPI", "paid"), ("EcomExpress", "delivered", 5, None, 3), []),
    (1011, 1, 36, "delivered",
     [("Cotton Bedsheet Set", "Home", 1, 2199.00, 1)],
     ("COD", "paid"), ("BlueDart", "delivered", 34, None, 29), []),
    (1012, 2, 1, "processing",
     [("LED Desk Lamp", "Home", 1, 1599.00, 1)],
     ("UPI", "pending"), ("None", "pending", None, 5, None), []),
]


def build(db_path: Path):
    con = sqlite3.connect(db_path)
    con.execute("PRAGMA foreign_keys = ON")
    con.execute("PRAGMA journal_mode = WAL")
    con.executescript(SCHEMA.read_text())
    cur = con.cursor()

    for cid, name, email, phone in CUSTOMERS:
        cur.execute("INSERT INTO customers (customer_id, name, email, phone, created_at) VALUES (?,?,?,?,?)",
                    (cid, name, email, phone, ts(120)))

    for oid, cid, ordered, status, items, (method, pstatus), \
            (carrier, dstatus, shipped, eta, delivered), refunds in ORDERS:
        total = round(sum(q * p for _, _, q, p, _ in items), 2)
        refunded = round(sum(r[0] for r in refunds), 2)
        rstatus = "none" if refunded == 0 else ("full" if refunded >= total else "partial")
        cur.execute("""INSERT INTO orders (order_id, customer_id, order_date, status, total_amount, currency,
                       refunded_amount, refund_status, updated_at) VALUES (?,?,?,?,?,?,?,?,?)""",
                    (oid, cid, ts(ordered), status, total, "INR", refunded, rstatus, ts(0)))
        for name, cat, qty, price, refundable in items:
            cur.execute("""INSERT INTO order_items (order_id, product_name, category, quantity, unit_price, refundable)
                           VALUES (?,?,?,?,?,?)""", (oid, name, cat, qty, price, refundable))
        paid_at = ts(ordered) if pstatus not in ("pending", "cancelled") and method != "COD" else \
                  (ts(delivered) if method == "COD" and delivered is not None else None)
        cur.execute("""INSERT INTO payments (order_id, method, status, amount, transaction_ref, paid_at)
                       VALUES (?,?,?,?,?,?)""",
                    (oid, method, pstatus, total, f"TXN{oid}{method[:2]}", paid_at))
        payment_id = cur.lastrowid
        cur.execute("""INSERT INTO deliveries (order_id, carrier, tracking_number, status, shipped_at,
                       estimated_delivery, delivered_at) VALUES (?,?,?,?,?,?,?)""",
                    (oid, None if carrier == "None" else carrier,
                     None if carrier == "None" else f"TRK{oid}9{oid % 7}",
                     dstatus, ts(shipped) if shipped is not None else None,
                     (NOW + timedelta(days=eta)).strftime("%Y-%m-%d") if eta is not None else None,
                     ts(delivered) if delivered is not None else None))
        for amount, rtype, reason, days in refunds:
            cur.execute("""INSERT INTO refunds (order_id, payment_id, amount, refund_type, reason, status, created_at)
                           VALUES (?,?,?,?,?,?,?)""", (oid, payment_id, amount, rtype, reason, "completed", ts(days)))
    con.commit()
    return con


def verify(con):
    q = lambda s: con.execute(s).fetchall()
    assert not q("PRAGMA foreign_key_check"), "foreign key violations"
    assert not q("""SELECT o.order_id FROM orders o JOIN order_items i USING(order_id)
                    GROUP BY o.order_id HAVING ROUND(SUM(i.quantity*i.unit_price),2) != o.total_amount"""), "item totals mismatch"
    assert not q("""SELECT o.order_id FROM orders o LEFT JOIN refunds r ON r.order_id=o.order_id AND r.status='completed'
                    GROUP BY o.order_id HAVING ROUND(COALESCE(SUM(r.amount),0),2) != o.refunded_amount"""), "refund totals mismatch"
    assert not q("SELECT 1 FROM orders o JOIN payments p USING(order_id) WHERE p.amount != o.total_amount"), "payment mismatch"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(ROOT / "data" / "support.db"))
    ap.add_argument("--reset", action="store_true", help="back up and recreate an existing DB")
    a = ap.parse_args()
    db = Path(a.db)
    db.parent.mkdir(parents=True, exist_ok=True)
    if db.exists():
        if not a.reset:
            sys.exit(f"{db} already exists. Use --reset to back it up and recreate it.")
        backup = db.with_suffix(f".backup-{NOW.strftime('%Y%m%d-%H%M%S')}.db")
        shutil.copy(db, backup)
        for ext in ("", "-wal", "-shm"):
            Path(str(db) + ext).unlink(missing_ok=True)
        print(f"Backed up existing DB to {backup}")
    con = build(db)
    verify(con)
    for t in ("customers", "orders", "order_items", "payments", "deliveries", "refunds"):
        print(f"{t:12s} {con.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]} rows")
    print(f"Database ready: {db}")
    con.close()


if __name__ == "__main__":
    main()
