import json
import pytest
from app.tools import (
    search_docs,
    get_order_details,
    get_payment_info,
    get_delivery_status,
    check_refund_eligibility,
    process_refund,
)

def test_search_docs_tool_bad_input():
    """Verify search_docs handles invalid/empty query gracefully."""
    for bad_input in ["", "   "]:
        raw_res = search_docs.invoke({"query": bad_input})
        data = json.loads(raw_res)
        assert data["success"] is False
        assert "error_code" in data
        assert "message" in data

def test_get_order_details_bad_input():
    """Verify get_order_details returns structured error on bad or nonexistent input."""
    # Empty string
    raw_res = get_order_details.invoke({"order_id": ""})
    data = json.loads(raw_res)
    assert data["success"] is False
    assert data["error_code"] == "INVALID_INPUT"

    # Nonexistent order ID
    raw_res = get_order_details.invoke({"order_id": "ORD999999"})
    data = json.loads(raw_res)
    assert data["success"] is False
    assert data["error_code"] == "ORDER_NOT_FOUND"

def test_get_payment_info_bad_input():
    """Verify get_payment_info returns structured error on bad input."""
    raw_res = get_payment_info.invoke({"order_id": ""})
    data = json.loads(raw_res)
    assert data["success"] is False
    assert data["error_code"] == "INVALID_INPUT"

    raw_res = get_payment_info.invoke({"order_id": "ORD999999"})
    data = json.loads(raw_res)
    assert data["success"] is False
    assert data["error_code"] == "ORDER_NOT_FOUND"

def test_get_delivery_status_bad_input():
    """Verify get_delivery_status returns structured error on bad input."""
    raw_res = get_delivery_status.invoke({"order_id": ""})
    data = json.loads(raw_res)
    assert data["success"] is False
    assert data["error_code"] == "INVALID_INPUT"

    raw_res = get_delivery_status.invoke({"order_id": "ORD999999"})
    data = json.loads(raw_res)
    assert data["success"] is False
    assert data["error_code"] == "ORDER_NOT_FOUND"

def test_check_refund_eligibility_bad_input():
    """Verify check_refund_eligibility handles bad input without raising."""
    raw_res = check_refund_eligibility.invoke({"order_id": ""})
    data = json.loads(raw_res)
    assert data["eligible"] is False
    assert "reason" in data

    raw_res = check_refund_eligibility.invoke({"order_id": "ORD1001", "amount": -100.0})
    data = json.loads(raw_res)
    assert data["eligible"] is False
    assert "greater than zero" in data["reason"].lower()

def test_process_refund_bad_input():
    """Verify process_refund handles invalid input without raising."""
    raw_res = process_refund.invoke({"order_id": "", "amount": 100.0, "reason": "test"})
    data = json.loads(raw_res)
    assert data["success"] is False
    assert "error_code" in data

    raw_res = process_refund.invoke({"order_id": "ORD1001", "amount": -50.0, "reason": "test"})
    data = json.loads(raw_res)
    assert data["success"] is False
    assert data["error_code"] == "INVALID_AMOUNT"
