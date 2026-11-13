import sqlite3
import shutil
import os
import sys

def migrate_database(db_path: str = "orders.db", backup: bool = True):
    print(f"Starting database migration for: {db_path}")
    if not os.path.exists(db_path):
        print(f"Error: Database file '{db_path}' not found.", file=sys.stderr)
        sys.exit(1)

    # 1. Back up DB file before migration
    if backup:
        backup_path = f"{db_path}.bak"
        shutil.copy2(db_path, backup_path)
        print(f"[OK] Database backed up to: {backup_path}")

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON;")
    cursor = conn.cursor()

    try:
        # 2. Check columns of orders table
        cursor.execute("PRAGMA table_info(orders);")
        columns = [row[1] for row in cursor.fetchall()]
        print(f"Existing columns in 'orders': {columns}")

        # 3. Add refunded_amount column if missing
        if "refunded_amount" not in columns:
            print("Adding 'refunded_amount' column to 'orders' table...")
            cursor.execute("ALTER TABLE orders ADD COLUMN refunded_amount REAL NOT NULL DEFAULT 0.0;")
            print("[OK] Column 'refunded_amount' added.")
        else:
            print("[INFO] Column 'refunded_amount' already exists.")

        # 4. Create refunds table if not exists
        print("Ensuring 'refunds' table exists...")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS refunds (
                refund_id TEXT PRIMARY KEY,
                order_id TEXT NOT NULL,
                amount REAL NOT NULL,
                reason TEXT NOT NULL,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (order_id) REFERENCES orders(order_id)
            );
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_refunds_order_id ON refunds(order_id);")
        print("[OK] 'refunds' table and index verified.")

        # 5. Populate refunded_amount and baseline refunds for existing historical rows
        # Case A: Fully refunded orders (ORD1003, ORD1011, etc.)
        cursor.execute("""
            SELECT order_id, order_price, order_date, payment_status, refunded_amount
            FROM orders
            WHERE payment_status = 'Refunded' OR order_status = 'Refunded';
        """)
        fully_refunded = cursor.fetchall()
        for oid, price, odate, pstatus, curr_ref in fully_refunded:
            if curr_ref == 0.0 or curr_ref is None:
                cursor.execute("UPDATE orders SET refunded_amount = ? WHERE order_id = ?", (price, oid))
                print(f"[SYNC] Updated {oid} refunded_amount to {price}")
            
            # Seed refund record if missing
            cursor.execute("SELECT COUNT(*) FROM refunds WHERE order_id = ?", (oid,))
            if cursor.fetchone()[0] == 0:
                ref_id = f"REF-HIST-{oid}"
                cursor.execute(
                    "INSERT INTO refunds (refund_id, order_id, amount, reason, created_at) VALUES (?, ?, ?, ?, ?)",
                    (ref_id, oid, price, "Historical full refund", f"{odate} 12:00:00")
                )
                print(f"[SYNC] Seeded historical refund {ref_id} for {oid}")

        # Case B: Partially refunded order (ORD1008)
        cursor.execute("""
            SELECT order_id, order_price, order_date, refunded_amount
            FROM orders
            WHERE order_id = 'ORD1008';
        """)
        ord1008 = cursor.fetchone()
        if ord1008:
            oid, price, odate, curr_ref = ord1008
            if curr_ref == 0.0 or curr_ref is None:
                initial_partial = 10000.0  # Historical partial refund
                cursor.execute("UPDATE orders SET refunded_amount = ? WHERE order_id = ?", (initial_partial, oid))
                print(f"[SYNC] Updated {oid} refunded_amount to {initial_partial}")
                
                cursor.execute("SELECT COUNT(*) FROM refunds WHERE order_id = ?", (oid,))
                if cursor.fetchone()[0] == 0:
                    ref_id = f"REF-HIST-{oid}"
                    cursor.execute(
                        "INSERT INTO refunds (refund_id, order_id, amount, reason, created_at) VALUES (?, ?, ?, ?, ?)",
                        (ref_id, oid, initial_partial, "Historical partial refund for accessory", f"{odate} 14:00:00")
                    )
                    print(f"[SYNC] Seeded historical refund {ref_id} for {oid}")

        conn.commit()
        print("\n[SUCCESS] Database migration completed successfully.")

    except Exception as e:
        conn.rollback()
        print(f"\n[ERROR] Migration failed: {e}", file=sys.stderr)
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    db_file = sys.argv[1] if len(sys.argv) > 1 else "orders.db"
    migrate_database(db_file)
