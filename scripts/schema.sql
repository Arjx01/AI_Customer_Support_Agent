-- Customer Support Agent database schema (SQLite)
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS customers (
    customer_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT NOT NULL,
    email        TEXT NOT NULL UNIQUE,
    phone        TEXT,
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS orders (
    order_id         INTEGER PRIMARY KEY,
    customer_id      INTEGER NOT NULL REFERENCES customers(customer_id),
    order_date       TEXT NOT NULL,
    status           TEXT NOT NULL CHECK (status IN ('processing','shipped','delivered','cancelled')),
    total_amount     REAL NOT NULL CHECK (total_amount >= 0),
    currency         TEXT NOT NULL DEFAULT 'INR',
    refunded_amount  REAL NOT NULL DEFAULT 0 CHECK (refunded_amount >= 0),
    refund_status    TEXT NOT NULL DEFAULT 'none' CHECK (refund_status IN ('none','partial','full')),
    updated_at       TEXT NOT NULL DEFAULT (datetime('now')),
    CHECK (refunded_amount <= total_amount)
);

CREATE TABLE IF NOT EXISTS order_items (
    item_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id      INTEGER NOT NULL REFERENCES orders(order_id),
    product_name  TEXT NOT NULL,
    category      TEXT NOT NULL,
    quantity      INTEGER NOT NULL CHECK (quantity > 0),
    unit_price    REAL NOT NULL CHECK (unit_price >= 0),
    refundable    INTEGER NOT NULL DEFAULT 1 CHECK (refundable IN (0,1))
);

CREATE TABLE IF NOT EXISTS payments (
    payment_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id         INTEGER NOT NULL UNIQUE REFERENCES orders(order_id),
    method           TEXT NOT NULL CHECK (method IN ('UPI','CARD','NETBANKING','COD')),
    status           TEXT NOT NULL CHECK (status IN ('pending','paid','cancelled','partially_refunded','refunded')),
    amount           REAL NOT NULL CHECK (amount >= 0),
    transaction_ref  TEXT,
    paid_at          TEXT
);

CREATE TABLE IF NOT EXISTS deliveries (
    delivery_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id            INTEGER NOT NULL UNIQUE REFERENCES orders(order_id),
    carrier             TEXT,
    tracking_number     TEXT,
    status              TEXT NOT NULL CHECK (status IN ('pending','in_transit','out_for_delivery','delivered','cancelled')),
    shipped_at          TEXT,
    estimated_delivery  TEXT,
    delivered_at        TEXT
);

CREATE TABLE IF NOT EXISTS refunds (
    refund_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id     INTEGER NOT NULL REFERENCES orders(order_id),
    payment_id   INTEGER NOT NULL REFERENCES payments(payment_id),
    amount       REAL NOT NULL CHECK (amount > 0),
    refund_type  TEXT NOT NULL CHECK (refund_type IN ('full','partial')),
    reason       TEXT,
    status       TEXT NOT NULL DEFAULT 'completed' CHECK (status IN ('completed','failed')),
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_orders_customer   ON orders(customer_id);
CREATE INDEX IF NOT EXISTS idx_items_order       ON order_items(order_id);
CREATE INDEX IF NOT EXISTS idx_refunds_order     ON refunds(order_id);
