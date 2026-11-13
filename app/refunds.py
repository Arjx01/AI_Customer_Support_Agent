import sqlite3
import uuid
from typing import Optional, Dict, Any
from app.config import DB_PATH
from app.db import get_connection
from app.rules import check_refund_eligibility

def execute_refund(
    order_id: str,
    amount: float,
    reason: str,
    customer_name: Optional[str] = None,
    db_path: Optional[str] = None,
    _simulate_failure_before_commit: bool = False
) -> Dict[str, Any]:
    """
    Executes an eligible refund inside a single ACID SQLite transaction.
    Re-validates eligibility inside the transaction, updates cumulative totals,
    inserts a refund record, and commits or rolls back on any error.
    """
    if not order_id or not isinstance(order_id, str):
        return {
            "success": False,
            "error_code": "INVALID_ORDER_ID",
            "message": "Order ID is required and must be a valid string."
        }
    order_id = order_id.strip().upper()

    try:
        amt = float(amount)
        if amt <= 0:
            return {
                "success": False,
                "error_code": "INVALID_AMOUNT",
                "message": "Refund amount must be greater than zero."
            }
        amt = round(amt, 2)
    except (ValueError, TypeError):
        return {
            "success": False,
            "error_code": "INVALID_AMOUNT",
            "message": "Refund amount must be a valid numerical value."
        }

    reason_clean = (reason or "Customer requested refund").strip()

    conn = get_connection(db_path)
    try:
        # Start transaction explicitly
        conn.execute("BEGIN IMMEDIATE;")
        cursor = conn.cursor()

        # Fetch current order state within transaction
        cursor.execute("""
            SELECT order_id, customer_name, product_name, order_date, 
                   order_price, payment_method, payment_status, 
                   delivery_status, order_status, refunded_amount
            FROM orders
            WHERE UPPER(order_id) = UPPER(?)
        """, (order_id,))
        row = cursor.fetchone()

        if not row:
            conn.rollback()
            return {
                "success": False,
                "error_code": "ORDER_NOT_FOUND",
                "message": f"Order '{order_id}' does not exist."
            }

        order_dict = dict(row)

        # Re-validate eligibility inside transaction
        eligibility = check_refund_eligibility(
            order_id=order_id,
            amount=amt,
            customer_name=customer_name,
            order=order_dict,
            db_path=db_path
        )

        if not eligibility.eligible:
            conn.rollback()
            return {
                "success": False,
                "error_code": "INELIGIBLE_REFUND",
                "message": eligibility.reason,
                "remaining_balance": eligibility.remaining_balance,
                "max_refundable": eligibility.max_refundable
            }

        order_price = float(order_dict["order_price"])
        prev_refunded = float(order_dict.get("refunded_amount", 0.0) or 0.0)
        new_refunded = round(prev_refunded + amt, 2)

        if new_refunded > order_price:
            conn.rollback()
            return {
                "success": False,
                "error_code": "EXCEEDS_BALANCE",
                "message": f"Refund of ₹{amt:.2f} would exceed total paid price of ₹{order_price:.2f} (already refunded: ₹{prev_refunded:.2f})."
            }

        # Generate unique refund ID
        refund_id = f"REF-{uuid.uuid4().hex[:8].upper()}"

        # Insert refund transaction record
        cursor.execute("""
            INSERT INTO refunds (refund_id, order_id, amount, reason, created_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP);
        """, (refund_id, order_id, amt, reason_clean))

        # Determine new status
        if new_refunded >= order_price:
            new_payment_status = "Refunded"
            new_order_status = "Refunded"
        else:
            new_payment_status = "Partially Refunded"
            new_order_status = "Partially Refunded"

        # Update orders table
        cursor.execute("""
            UPDATE orders
            SET refunded_amount = ?,
                payment_status = ?,
                order_status = ?
            WHERE UPPER(order_id) = UPPER(?);
        """, (new_refunded, new_payment_status, new_order_status, order_id))

        # Simulated failure hook for testing transaction rollback
        if _simulate_failure_before_commit:
            raise RuntimeError("Simulated failure occurred before transaction commit.")

        conn.commit()

        remaining_bal = round(order_price - new_refunded, 2)
        return {
            "success": True,
            "refund_id": refund_id,
            "order_id": order_id,
            "customer_name": order_dict.get("customer_name"),
            "product_name": order_dict.get("product_name"),
            "refunded_amount": amt,
            "total_refunded_to_date": new_refunded,
            "remaining_balance": remaining_bal,
            "payment_status": new_payment_status,
            "order_status": new_order_status,
            "message": f"Successfully processed refund of ₹{amt:.2f} for order {order_id}. Refund ID: {refund_id}."
        }

    except Exception as e:
        conn.rollback()
        return {
            "success": False,
            "error_code": "TRANSACTION_FAILED",
            "message": f"Database transaction failed: {str(e)}"
        }
    finally:
        conn.close()
