import json
from typing import Optional, Dict, Any
from langchain_core.tools import tool

from app.db import get_order, get_refunds_for_order
from app.rules import check_refund_eligibility as evaluate_eligibility
from app.refunds import execute_refund
from app.rag import search_docs as execute_search_docs

@tool
def search_docs(query: str) -> str:
    """
    Search product documentation, return and refund policy, warranty, shipping,
    billing, and troubleshooting guides for answers to customer questions.
    Returns matching document chunks, citation sources, and relevance scores.
    """
    try:
        result = execute_search_docs(query)
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({
            "success": False,
            "error_code": "TOOL_SEARCH_ERROR",
            "message": f"Error searching knowledge base: {str(e)}"
        })

@tool
def get_order_details(order_id: str) -> str:
    """
    Retrieve comprehensive details about an order from the database, including
    customer name, product purchased, order date, order price, payment status,
    delivery status, order status, and total amount refunded to date.
    """
    try:
        if not order_id or not isinstance(order_id, str):
            return json.dumps({
                "success": False,
                "error_code": "INVALID_INPUT",
                "message": "Order ID must be a non-empty string."
            })
        order = get_order(order_id)
        if not order:
            return json.dumps({
                "success": False,
                "error_code": "ORDER_NOT_FOUND",
                "message": f"Order '{order_id}' was not found in our database. Please verify the order ID."
            })
        order_dict = dict(order)
        remaining = round(order_dict["order_price"] - order_dict.get("refunded_amount", 0.0), 2)
        order_dict["remaining_balance"] = remaining
        return json.dumps({
            "success": True,
            "order": order_dict
        }, indent=2)
    except Exception as e:
        return json.dumps({
            "success": False,
            "error_code": "TOOL_ORDER_ERROR",
            "message": f"Error retrieving order details: {str(e)}"
        })

@tool
def get_payment_info(order_id: str) -> str:
    """
    Retrieve payment information for an order, including payment method (UPI,
    Credit Card, Debit Card, Net Banking), payment status, original price,
    cumulative refunded amount, remaining refundable balance, and transaction history.
    """
    try:
        if not order_id or not isinstance(order_id, str):
            return json.dumps({
                "success": False,
                "error_code": "INVALID_INPUT",
                "message": "Order ID must be a non-empty string."
            })
        order = get_order(order_id)
        if not order:
            return json.dumps({
                "success": False,
                "error_code": "ORDER_NOT_FOUND",
                "message": f"Order '{order_id}' was not found in our database."
            })
        
        refunds = get_refunds_for_order(order_id)
        order_dict = dict(order)
        price = float(order_dict["order_price"])
        refunded = float(order_dict.get("refunded_amount", 0.0) or 0.0)
        remaining = round(price - refunded, 2)

        return json.dumps({
            "success": True,
            "order_id": order_dict["order_id"],
            "payment_method": order_dict["payment_method"],
            "payment_status": order_dict["payment_status"],
            "order_price": price,
            "refunded_amount": refunded,
            "remaining_balance": remaining,
            "refund_history": refunds
        }, indent=2)
    except Exception as e:
        return json.dumps({
            "success": False,
            "error_code": "TOOL_PAYMENT_ERROR",
            "message": f"Error retrieving payment info: {str(e)}"
        })

@tool
def get_delivery_status(order_id: str) -> str:
    """
    Retrieve real-time delivery and shipping status for an order, including
    order date, product name, customer name, and current fulfillment state
    (e.g., Delivered, In Transit, Shipped, Processing, Not Dispatched).
    """
    try:
        if not order_id or not isinstance(order_id, str):
            return json.dumps({
                "success": False,
                "error_code": "INVALID_INPUT",
                "message": "Order ID must be a non-empty string."
            })
        order = get_order(order_id)
        if not order:
            return json.dumps({
                "success": False,
                "error_code": "ORDER_NOT_FOUND",
                "message": f"Order '{order_id}' was not found in our database."
            })
        order_dict = dict(order)
        return json.dumps({
            "success": True,
            "order_id": order_dict["order_id"],
            "customer_name": order_dict["customer_name"],
            "product_name": order_dict["product_name"],
            "delivery_status": order_dict["delivery_status"],
            "order_status": order_dict["order_status"],
            "order_date": order_dict["order_date"]
        }, indent=2)
    except Exception as e:
        return json.dumps({
            "success": False,
            "error_code": "TOOL_DELIVERY_ERROR",
            "message": f"Error retrieving delivery status: {str(e)}"
        })

@tool
def check_refund_eligibility(order_id: str, amount: Optional[float] = None) -> str:
    """
    Evaluate business rules for refund eligibility on an order.
    Checks delivery status, 30-day window, cancellation status, non-refundable
    categories, and remaining balance. If an amount is provided, checks if that
    partial amount can be refunded.
    Returns eligibility status, max refundable amount, and exact reasons.
    DOES NOT execute the refund.
    """
    try:
        result = evaluate_eligibility(order_id=order_id, amount=amount)
        data = result.to_dict()
        data["success"] = True
        return json.dumps(data, indent=2)
    except Exception as e:
        return json.dumps({
            "success": False,
            "error_code": "TOOL_ELIGIBILITY_ERROR",
            "message": f"Error checking refund eligibility: {str(e)}"
        })

@tool
def process_refund(order_id: str, amount: float, reason: str) -> str:
    """
    Execute a refund for an eligible order inside a single atomic database transaction.
    IMPORTANT: This tool should ONLY be called after eligibility has been verified
    with check_refund_eligibility AND the customer has explicitly confirmed the refund amount.
    Supports both full and partial refunds. Updates order payment status, cumulative
    refunded total, and creates an audit refund record with a unique Refund ID.
    """
    try:
        result = execute_refund(order_id=order_id, amount=amount, reason=reason)
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({
            "success": False,
            "error_code": "TOOL_PROCESS_REFUND_ERROR",
            "message": f"Error executing refund: {str(e)}"
        })

# List of all available agent tools
ALL_TOOLS = [
    search_docs,
    get_order_details,
    get_payment_info,
    get_delivery_status,
    check_refund_eligibility,
    process_refund,
]
