from dataclasses import dataclass, asdict
from datetime import datetime, date
from typing import Optional, Dict, Any, Union
from app.config import REFUND_WINDOW_DAYS, NON_REFUNDABLE_KEYWORDS
from app.db import get_order

@dataclass
class RefundEligibilityResult:
    eligible: bool
    max_refundable: float
    remaining_balance: float
    reason: str
    order_id: Optional[str] = None
    customer_name: Optional[str] = None
    product_name: Optional[str] = None
    order_price: float = 0.0
    refunded_amount: float = 0.0
    days_since_order: int = 0
    suggested_amount: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

def check_refund_eligibility(
    order_id: str,
    amount: Optional[float] = None,
    customer_name: Optional[str] = None,
    reference_date: Optional[Union[date, str]] = None,
    db_path: Optional[str] = None,
    order: Optional[Dict[str, Any]] = None
) -> RefundEligibilityResult:
    """
    Pure Python business logic for refund eligibility.
    No LLM prompt dependency. Idempotent and deterministic.
    """
    if not order_id or not isinstance(order_id, str) or not order_id.strip():
        return RefundEligibilityResult(
            eligible=False,
            max_refundable=0.0,
            remaining_balance=0.0,
            reason="Invalid or missing order ID."
        )
    order_id = order_id.strip().upper()

    # 1. Fetch order if not provided
    if order is None:
        order = get_order(order_id, db_path=db_path)
    
    if not order:
        return RefundEligibilityResult(
            eligible=False,
            max_refundable=0.0,
            remaining_balance=0.0,
            reason=f"Order '{order_id}' was not found in our records.",
            order_id=order_id
        )

    # Extract order fields
    order_customer = order.get("customer_name", "")
    product_name = order.get("product_name", "")
    order_price = float(order.get("order_price", 0.0))
    refunded_amount = float(order.get("refunded_amount", 0.0))
    payment_status = order.get("payment_status", "")
    delivery_status = order.get("delivery_status", "")
    order_status = order.get("order_status", "")
    
    # 2. Customer authorization check (if customer provided)
    if customer_name and customer_name.strip():
        if customer_name.strip().lower() != order_customer.strip().lower():
            return RefundEligibilityResult(
                eligible=False,
                max_refundable=0.0,
                remaining_balance=round(order_price - refunded_amount, 2),
                reason=f"Access denied: Order '{order_id}' does not belong to customer '{customer_name}'.",
                order_id=order_id,
                customer_name=order_customer,
                product_name=product_name,
                order_price=order_price,
                refunded_amount=refunded_amount
            )

    # 3. Non-refundable item check
    product_lower = product_name.lower()
    for kw in NON_REFUNDABLE_KEYWORDS:
        if kw in product_lower:
            return RefundEligibilityResult(
                eligible=False,
                max_refundable=0.0,
                remaining_balance=round(order_price - refunded_amount, 2),
                reason=f"Item '{product_name}' falls into non-refundable category ('{kw}') as per company policy.",
                order_id=order_id,
                customer_name=order_customer,
                product_name=product_name,
                order_price=order_price,
                refunded_amount=refunded_amount
            )

    # 4. Cancelled order check
    if order_status.lower() == "cancelled" or delivery_status.lower() == "cancelled":
        return RefundEligibilityResult(
            eligible=False,
            max_refundable=0.0,
            remaining_balance=0.0,
            reason=f"Order '{order_id}' is cancelled. Cancelled orders cannot be refunded via return requests.",
            order_id=order_id,
            customer_name=order_customer,
            product_name=product_name,
            order_price=order_price,
            refunded_amount=refunded_amount
        )

    # 5. Remaining balance / Already refunded check
    remaining_balance = round(order_price - refunded_amount, 2)
    if remaining_balance <= 0.0 or payment_status.lower() == "refunded" or order_status.lower() == "refunded":
        return RefundEligibilityResult(
            eligible=False,
            max_refundable=0.0,
            remaining_balance=0.0,
            reason=f"Order '{order_id}' has already been fully refunded (total paid: ₹{order_price:.2f}, already refunded: ₹{refunded_amount:.2f}).",
            order_id=order_id,
            customer_name=order_customer,
            product_name=product_name,
            order_price=order_price,
            refunded_amount=refunded_amount
        )

    # 6. Delivery status check (must be Delivered)
    if delivery_status.lower() != "delivered":
        return RefundEligibilityResult(
            eligible=False,
            max_refundable=0.0,
            remaining_balance=remaining_balance,
            reason=f"Order '{order_id}' has not been delivered yet (current delivery status: '{delivery_status}'). Refunds can only be requested after successful delivery.",
            order_id=order_id,
            customer_name=order_customer,
            product_name=product_name,
            order_price=order_price,
            refunded_amount=refunded_amount
        )

    # 7. Payment status check
    if payment_status.lower() not in ["successful", "partially refunded"]:
        return RefundEligibilityResult(
            eligible=False,
            max_refundable=0.0,
            remaining_balance=0.0,
            reason=f"Order '{order_id}' payment status is '{payment_status}'. Refunds only apply to successfully paid orders.",
            order_id=order_id,
            customer_name=order_customer,
            product_name=product_name,
            order_price=order_price,
            refunded_amount=refunded_amount
        )

    # 8. Date / refund window check
    order_date_raw = order.get("order_date")
    if isinstance(order_date_raw, str):
        try:
            parsed_order_date = datetime.strptime(order_date_raw[:10], "%Y-%m-%d").date()
        except ValueError:
            parsed_order_date = date.today()
    elif isinstance(order_date_raw, (date, datetime)):
        parsed_order_date = order_date_raw if isinstance(order_date_raw, date) else order_date_raw.date()
    else:
        parsed_order_date = date.today()

    if reference_date is None:
        ref_d = date.today()
    elif isinstance(reference_date, str):
        ref_d = datetime.strptime(reference_date[:10], "%Y-%m-%d").date()
    else:
        ref_d = reference_date

    days_elapsed = (ref_d - parsed_order_date).days
    if days_elapsed > REFUND_WINDOW_DAYS:
        return RefundEligibilityResult(
            eligible=False,
            max_refundable=0.0,
            remaining_balance=remaining_balance,
            reason=f"Order '{order_id}' exceeds the {REFUND_WINDOW_DAYS}-day return window. Delivered/ordered on {parsed_order_date} ({days_elapsed} days ago).",
            order_id=order_id,
            customer_name=order_customer,
            product_name=product_name,
            order_price=order_price,
            refunded_amount=refunded_amount,
            days_since_order=days_elapsed
        )

    # 9. Amount validation
    if amount is not None:
        try:
            req_amt = float(amount)
        except (ValueError, TypeError):
            return RefundEligibilityResult(
                eligible=False,
                max_refundable=remaining_balance,
                remaining_balance=remaining_balance,
                reason="Invalid refund amount format. Must be a positive number.",
                order_id=order_id,
                customer_name=order_customer,
                product_name=product_name,
                order_price=order_price,
                refunded_amount=refunded_amount,
                days_since_order=days_elapsed
            )

        if req_amt <= 0:
            return RefundEligibilityResult(
                eligible=False,
                max_refundable=remaining_balance,
                remaining_balance=remaining_balance,
                reason="Refund amount must be greater than zero.",
                order_id=order_id,
                customer_name=order_customer,
                product_name=product_name,
                order_price=order_price,
                refunded_amount=refunded_amount,
                days_since_order=days_elapsed
            )

        if round(req_amt, 2) > remaining_balance:
            return RefundEligibilityResult(
                eligible=False,
                max_refundable=remaining_balance,
                remaining_balance=remaining_balance,
                reason=f"Requested refund of ₹{req_amt:.2f} exceeds remaining refundable balance of ₹{remaining_balance:.2f}.",
                order_id=order_id,
                customer_name=order_customer,
                product_name=product_name,
                order_price=order_price,
                refunded_amount=refunded_amount,
                days_since_order=days_elapsed
            )
        suggested = round(req_amt, 2)
    else:
        suggested = remaining_balance

    # Passed all rules!
    return RefundEligibilityResult(
        eligible=True,
        max_refundable=remaining_balance,
        remaining_balance=remaining_balance,
        reason="Order is fully eligible for refund.",
        order_id=order_id,
        customer_name=order_customer,
        product_name=product_name,
        order_price=order_price,
        refunded_amount=refunded_amount,
        days_since_order=days_elapsed,
        suggested_amount=suggested
    )
