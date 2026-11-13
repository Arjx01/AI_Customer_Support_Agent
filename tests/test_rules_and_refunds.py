import sqlite3
import pytest
from datetime import date, timedelta
from app.rules import check_refund_eligibility
from app.refunds import execute_refund
from app.db import get_order, get_refunds_for_order

def test_eligible_full_refund(temp_db):
    """Test full refund on an eligible delivered order and verify DB state."""
    # ORD1001 is Delivered, price=79900.0, refunded=0.0
    initial_order = get_order("ORD1001", db_path=temp_db)
    assert initial_order["delivery_status"] == "Delivered"
    assert initial_order["refunded_amount"] == 0.0

    # 1. Check eligibility
    eligibility = check_refund_eligibility("ORD1001", db_path=temp_db)
    assert eligibility.eligible is True
    assert eligibility.max_refundable == 79900.0
    assert eligibility.suggested_amount == 79900.0

    # 2. Execute refund
    result = execute_refund("ORD1001", amount=79900.0, reason="Customer dissatisfied", db_path=temp_db)
    assert result["success"] is True
    assert "REF-" in result["refund_id"]
    assert result["payment_status"] == "Refunded"
    assert result["order_status"] == "Refunded"
    assert result["remaining_balance"] == 0.0

    # 3. Assert DB state directly
    updated_order = get_order("ORD1001", db_path=temp_db)
    assert updated_order["payment_status"] == "Refunded"
    assert updated_order["order_status"] == "Refunded"
    assert updated_order["refunded_amount"] == 79900.0

    refund_rows = get_refunds_for_order("ORD1001", db_path=temp_db)
    assert len(refund_rows) == 1
    assert refund_rows[0]["amount"] == 79900.0
    assert refund_rows[0]["refund_id"] == result["refund_id"]

def test_eligible_partial_refund(temp_db):
    """Test single partial refund and assert DB state."""
    # ORD1004 is MacBook Air M3, price=114900.0
    initial_order = get_order("ORD1004", db_path=temp_db)
    initial_refunded = float(initial_order["refunded_amount"])
    price = float(initial_order["order_price"])
    partial_amount = 20000.0

    eligibility = check_refund_eligibility("ORD1004", amount=partial_amount, db_path=temp_db)
    assert eligibility.eligible is True

    result = execute_refund("ORD1004", amount=partial_amount, reason="Partial credit for cosmetic defect", db_path=temp_db)
    assert result["success"] is True
    assert result["payment_status"] == "Partially Refunded"
    assert result["order_status"] == "Partially Refunded"
    assert result["refunded_amount"] == partial_amount
    assert result["total_refunded_to_date"] == round(initial_refunded + partial_amount, 2)
    assert result["remaining_balance"] == round(price - (initial_refunded + partial_amount), 2)

    # Assert DB state
    order = get_order("ORD1004", db_path=temp_db)
    assert order["payment_status"] == "Partially Refunded"
    assert order["refunded_amount"] == round(initial_refunded + partial_amount, 2)

    refund_rows = get_refunds_for_order("ORD1004", db_path=temp_db)
    assert len(refund_rows) == 1
    assert refund_rows[0]["amount"] == partial_amount

def test_two_partial_refunds_summing_to_total(temp_db):
    """Test two consecutive partial refunds that together equal the total price."""
    # ORD1007: Samsung Watch, price=24999.0
    p1 = 10000.0
    p2 = 14999.0

    # First partial refund
    r1 = execute_refund("ORD1007", amount=p1, reason="First partial refund", db_path=temp_db)
    assert r1["success"] is True
    assert r1["payment_status"] == "Partially Refunded"
    assert r1["remaining_balance"] == p2

    order_mid = get_order("ORD1007", db_path=temp_db)
    assert order_mid["refunded_amount"] == p1

    # Second partial refund
    r2 = execute_refund("ORD1007", amount=p2, reason="Second partial refund", db_path=temp_db)
    assert r2["success"] is True
    assert r2["payment_status"] == "Refunded"
    assert r2["order_status"] == "Refunded"
    assert r2["remaining_balance"] == 0.0

    # Assert DB state
    order_final = get_order("ORD1007", db_path=temp_db)
    assert order_final["refunded_amount"] == 24999.0
    assert order_final["payment_status"] == "Refunded"

    refunds = get_refunds_for_order("ORD1007", db_path=temp_db)
    assert len(refunds) == 2
    assert sum(r["amount"] for r in refunds) == 24999.0

def test_partial_refund_exceeding_balance(temp_db):
    """Test that a refund exceeding the remaining balance is rejected and DB is untouched."""
    # ORD1007: Samsung Watch, price=24999.0
    initial_refunds = get_refunds_for_order("ORD1007", db_path=temp_db)
    initial_order = get_order("ORD1007", db_path=temp_db)

    # 1. Eligibility check fails
    eligibility = check_refund_eligibility("ORD1007", amount=30000.0, db_path=temp_db)
    assert eligibility.eligible is False
    assert "exceeds" in eligibility.reason.lower()

    # 2. Execution fails
    result = execute_refund("ORD1007", amount=30000.0, reason="Excessive refund", db_path=temp_db)
    assert result["success"] is False
    assert result["error_code"] in ["INELIGIBLE_REFUND", "EXCEEDS_BALANCE"]

    # Assert DB was untouched
    post_order = get_order("ORD1007", db_path=temp_db)
    assert post_order["refunded_amount"] == initial_order["refunded_amount"]
    assert post_order["payment_status"] == initial_order["payment_status"]
    assert len(get_refunds_for_order("ORD1007", db_path=temp_db)) == len(initial_refunds)

def test_refund_outside_window(temp_db):
    """Test that orders beyond the 30-day refund window are rejected."""
    # ORD1001 was placed 2026-11-01. Test with reference date 45 days later
    future_date = date(2026, 12, 20)
    eligibility = check_refund_eligibility(
        "ORD1001",
        reference_date=future_date,
        db_path=temp_db
    )
    assert eligibility.eligible is False
    assert "return window" in eligibility.reason.lower() or "exceeds" in eligibility.reason.lower()

def test_cancelled_order_ineligible(temp_db):
    """Test that cancelled orders cannot be refunded via return flow."""
    # ORD1006 is Cancelled
    eligibility = check_refund_eligibility("ORD1006", db_path=temp_db)
    assert eligibility.eligible is False
    assert "cancelled" in eligibility.reason.lower()

    result = execute_refund("ORD1006", amount=59900.0, reason="Try refund cancelled", db_path=temp_db)
    assert result["success"] is False

def test_already_fully_refunded_order(temp_db):
    """Test that already fully refunded orders are rejected."""
    # ORD1003 is already fully refunded (price=19998, refunded=19998)
    eligibility = check_refund_eligibility("ORD1003", db_path=temp_db)
    assert eligibility.eligible is False
    assert "already been fully refunded" in eligibility.reason.lower()

    result = execute_refund("ORD1003", amount=1000.0, reason="Over refund", db_path=temp_db)
    assert result["success"] is False

def test_in_transit_order_ineligible(temp_db):
    """Test that undelivered (In Transit) orders cannot be refunded."""
    # ORD1002 is In Transit
    eligibility = check_refund_eligibility("ORD1002", db_path=temp_db)
    assert eligibility.eligible is False
    assert "delivered" in eligibility.reason.lower()

def test_nonexistent_order(temp_db):
    """Test that querying a nonexistent order returns not found error."""
    eligibility = check_refund_eligibility("ORD9999", db_path=temp_db)
    assert eligibility.eligible is False
    assert "not found" in eligibility.reason.lower()

    result = execute_refund("ORD9999", amount=100.0, reason="Nonexistent", db_path=temp_db)
    assert result["success"] is False
    assert result["error_code"] == "ORDER_NOT_FOUND"

def test_invalid_amounts(temp_db):
    """Test that zero or negative refund amounts are rejected."""
    for bad_amt in [0, -50.0, -0.01]:
        eligibility = check_refund_eligibility("ORD1001", amount=bad_amt, db_path=temp_db)
        assert eligibility.eligible is False
        assert "greater than zero" in eligibility.reason.lower()

        res = execute_refund("ORD1001", amount=bad_amt, reason="Bad amount", db_path=temp_db)
        assert res["success"] is False
        assert res["error_code"] == "INVALID_AMOUNT"

def test_rollback_on_mid_transaction_failure(temp_db):
    """
    Test transactional integrity: simulate an unexpected failure before commit.
    Assert that the entire transaction is rolled back and DB state remains unchanged.
    """
    initial_order = get_order("ORD1001", db_path=temp_db)
    initial_refunds = get_refunds_for_order("ORD1001", db_path=temp_db)

    # Execute with simulated failure
    result = execute_refund(
        "ORD1001",
        amount=5000.0,
        reason="Testing rollback",
        db_path=temp_db,
        _simulate_failure_before_commit=True
    )
    assert result["success"] is False
    assert result["error_code"] == "TRANSACTION_FAILED"

    # Verify database state was NOT corrupted or partially updated
    post_order = get_order("ORD1001", db_path=temp_db)
    assert post_order["refunded_amount"] == initial_order["refunded_amount"]
    assert post_order["payment_status"] == initial_order["payment_status"]
    assert post_order["order_status"] == initial_order["order_status"]

    post_refunds = get_refunds_for_order("ORD1001", db_path=temp_db)
    assert len(post_refunds) == len(initial_refunds)
