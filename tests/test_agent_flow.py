import json
import sqlite3
import pytest
from typing import Any, List, Optional, Sequence
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, ToolMessage
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.outputs import ChatResult, ChatGeneration
from langgraph.checkpoint.sqlite import SqliteSaver

from app.graph import build_graph, get_checkpointer
from app.db import get_order, get_refunds_for_order

class DeterministicMockLLM(BaseChatModel):
    """
    Mock LLM that deterministically simulates intelligent tool-calling
    and multi-turn customer support conversations without external API calls.
    """
    bound_tools: List[Any] = []

    @property
    def _llm_type(self) -> str:
        return "deterministic-mock"

    def bind_tools(self, tools: Sequence[Any], **kwargs: Any):
        self.bound_tools = list(tools)
        return self

    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[Any] = None,
        **kwargs: Any
    ) -> ChatResult:
        last_msg = messages[-1]

        # Case 1: Prior message was a ToolMessage (handling tool output)
        if isinstance(last_msg, ToolMessage):
            tool_name = last_msg.name
            try:
                content_json = json.loads(last_msg.content)
            except Exception:
                content_json = {}

            if tool_name == "get_order_details":
                if content_json.get("success"):
                    order = content_json["order"]
                    text = f"Your order {order['order_id']} for {order['product_name']} is currently {order['delivery_status']}."
                else:
                    text = f"I'm sorry, but {content_json.get('message', 'we could not find that order.')}"
                return ChatResult(generations=[ChatGeneration(message=AIMessage(content=text))])

            elif tool_name == "check_refund_eligibility":
                if content_json.get("eligible"):
                    max_amt = content_json.get("max_refundable", 0.0)
                    oid = content_json.get("order_id", "your order")
                    text = (
                        f"Order {oid} is eligible for a refund of ₹{max_amt:,.2f}. "
                        f"Would you like me to proceed with processing this refund?"
                    )
                else:
                    text = f"I checked your order, but it is not eligible for a refund: {content_json.get('reason')}."
                return ChatResult(generations=[ChatGeneration(message=AIMessage(content=text))])

            elif tool_name == "process_refund":
                if content_json.get("success"):
                    ref_id = content_json.get("refund_id")
                    amt = content_json.get("refunded_amount")
                    text = f"Your refund of ₹{amt:,.2f} has been processed successfully under Refund ID: {ref_id}."
                else:
                    text = f"Could not process refund: {content_json.get('message')}"
                return ChatResult(generations=[ChatGeneration(message=AIMessage(content=text))])

            else:
                return ChatResult(generations=[ChatGeneration(message=AIMessage(content="I have processed that request."))])

        # Case 2: Last message is from Human
        human_text = str(last_msg.content).lower()

        # Missing order ID query
        if ("refund" in human_text or "order" in human_text) and not any(f"ord{d}" in human_text for d in ["1001", "1002", "1003", "1004", "1005", "1006", "1007", "1008", "9999"]):
            # Check if active order is present in system prompt
            sys_msg = messages[0].content if messages else ""
            if "CURRENT ACTIVE ORDER ID:" not in sys_msg:
                return ChatResult(generations=[ChatGeneration(message=AIMessage(
                    content="I would be happy to help you with that! Could you please provide your Order ID?"
                ))])

        # Multi-turn Turn 1: Lookup order
        if "status" in human_text or "where is" in human_text or "details" in human_text:
            from app.graph import extract_order_id
            detected = extract_order_id(human_text)
            oid = detected if detected else "ORD1001"
            return ChatResult(generations=[ChatGeneration(message=AIMessage(
                content="",
                tool_calls=[{"name": "get_order_details", "args": {"order_id": oid}, "id": "call_order"}]
            ))])

        # Multi-turn Turn 2: Request refund (or follow up "refund it")
        if "refund" in human_text and not any(k in human_text for k in ["yes", "confirm", "proceed", "go ahead"]):
            from app.graph import extract_order_id
            detected = extract_order_id(human_text)
            if detected:
                oid = detected
            elif "CURRENT ACTIVE ORDER ID: " in messages[0].content:
                import re
                m = re.search(r"CURRENT ACTIVE ORDER ID:\s*(ORD\d+)", messages[0].content)
                oid = m.group(1) if m else "ORD1001"
            else:
                oid = "ORD1001"
            return ChatResult(generations=[ChatGeneration(message=AIMessage(
                content="",
                tool_calls=[{"name": "check_refund_eligibility", "args": {"order_id": oid}, "id": "call_elig"}]
            ))])

        # Multi-turn Turn 3: User confirms
        if any(k in human_text for k in ["yes", "confirm", "proceed", "go ahead"]):
            from app.graph import extract_order_id
            oid = "ORD1001"
            amt = 79900.0
            sys_msg = messages[0].content if messages else ""
            if "PENDING REFUND: Order " in sys_msg:
                import re
                m = re.search(r"PENDING REFUND: Order (ORD\d+), Amount ₹([\d\.]+)", sys_msg)
                if m:
                    oid = m.group(1)
                    amt = float(m.group(2))
            elif "CURRENT ACTIVE ORDER ID: " in sys_msg:
                import re
                m = re.search(r"CURRENT ACTIVE ORDER ID:\s*(ORD\d+)", sys_msg)
                if m:
                    oid = m.group(1)
            return ChatResult(generations=[ChatGeneration(message=AIMessage(
                content="",
                tool_calls=[{"name": "process_refund", "args": {"order_id": oid, "amount": amt, "reason": "Confirmed by user"}, "id": "call_proc"}]
            ))])

        return ChatResult(generations=[ChatGeneration(message=AIMessage(
            content="How can I assist you further?"
        ))])

def test_multiturn_agent_conversation_with_context_and_refund(temp_db):
    """
    Test full multi-turn conversation:
    Turn 1: Ask about order ORD1001 -> Agent looks up details
    Turn 2: Follow-up 'Can I refund it?' WITHOUT repeating order ID -> Agent resolves context and checks eligibility
    Turn 3: Customer confirms 'Yes, please proceed' -> Agent processes refund
    Verify: DB state changed, refund row inserted!
    """
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    saver = SqliteSaver(conn)
    saver.setup()

    mock_llm = DeterministicMockLLM()
    # Temporarily monkey-patch DB_PATH in db module or pass through
    import app.db, app.refunds, app.rules
    orig_db = app.db.DB_PATH
    app.db.DB_PATH = temp_db
    app.refunds.DB_PATH = temp_db

    try:
        agent = build_graph(checkpointer=saver, llm=mock_llm)
        thread_id = "test_thread_multi"
        cfg = {"configurable": {"thread_id": thread_id}}

        # Turn 1: Lookup
        t1_state = agent.invoke(
            {"messages": [HumanMessage(content="What is the status of my order ORD1001?")]},
            config=cfg
        )
        assert t1_state["current_order_id"] == "ORD1001"
        last_t1_msg = t1_state["messages"][-1].content
        assert "ORD1001" in last_t1_msg
        assert "Delivered" in last_t1_msg

        # Turn 2: Follow up without repeating ORD1001!
        t2_state = agent.invoke(
            {"messages": [HumanMessage(content="Can I get a refund for it?")]},
            config=cfg
        )
        assert t2_state["current_order_id"] == "ORD1001"
        assert t2_state["pending_refund"] is not None
        assert t2_state["pending_refund"]["eligible"] is True
        last_t2_msg = t2_state["messages"][-1].content
        assert "eligible for a refund" in last_t2_msg.lower()
        assert "proceed" in last_t2_msg.lower() or "confirm" in last_t2_msg.lower()

        # Verify DB is NOT updated yet before confirmation!
        order_pre = get_order("ORD1001", db_path=temp_db)
        assert order_pre["refunded_amount"] == 0.0

        # Turn 3: User confirms
        t3_state = agent.invoke(
            {"messages": [HumanMessage(content="Yes, please proceed with the refund!")]},
            config=cfg
        )
        last_t3_msg = t3_state["messages"][-1].content
        assert "processed successfully" in last_t3_msg.lower() or "refund id" in last_t3_msg.lower()

        # VERIFY DATABASE WAS UPDATED!
        order_post = get_order("ORD1001", db_path=temp_db)
        assert order_post["payment_status"] == "Refunded"
        assert order_post["order_status"] == "Refunded"
        assert order_post["refunded_amount"] == 79900.0

        refunds = get_refunds_for_order("ORD1001", db_path=temp_db)
        assert len(refunds) == 1
        assert refunds[0]["amount"] == 79900.0

    finally:
        app.db.DB_PATH = orig_db
        app.refunds.DB_PATH = orig_db

def test_missing_order_id_followup():
    """Verify agent asks a targeted follow-up question when order ID is missing."""
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    saver = SqliteSaver(conn)
    saver.setup()
    mock_llm = DeterministicMockLLM()
    agent = build_graph(checkpointer=saver, llm=mock_llm)

    res = agent.invoke(
        {"messages": [HumanMessage(content="I want to refund my purchased smartphone.")]},
        config={"configurable": {"thread_id": "missing_id_thread"}}
    )
    reply = res["messages"][-1].content
    assert "order id" in reply.lower()

def test_invalid_order_message(temp_db):
    """Verify querying an invalid order returns a polite not-found message."""
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    saver = SqliteSaver(conn)
    saver.setup()
    mock_llm = DeterministicMockLLM()
    agent = build_graph(checkpointer=saver, llm=mock_llm)

    res = agent.invoke(
        {"messages": [HumanMessage(content="Please check status of ORD9999")]},
        config={"configurable": {"thread_id": "invalid_order_thread"}}
    )
    reply = res["messages"][-1].content
    assert "could not find that order" in reply.lower() or "not found" in reply.lower()

def test_ineligible_refund_explanation(temp_db):
    """Verify attempting to refund an ineligible order explains the exact reason."""
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    saver = SqliteSaver(conn)
    saver.setup()
    mock_llm = DeterministicMockLLM()
    agent = build_graph(checkpointer=saver, llm=mock_llm)

    res = agent.invoke(
        {"messages": [HumanMessage(content="I want to refund order ORD1002")]},
        config={"configurable": {"thread_id": "ineligible_order_thread"}}
    )
    reply = res["messages"][-1].content
    assert "not eligible" in reply.lower()
    assert "delivered" in reply.lower()

def test_refund_guard_blocks_unconfirmed_execution():
    """
    Verify that the system guard in tool_node physically blocks process_refund
    if called prematurely without customer confirmation.
    """
    from app.graph import tool_node

    # Simulate an AI message attempting to process refund without prior confirmation
    unauthorized_call = AIMessage(
        content="",
        tool_calls=[{
            "name": "process_refund",
            "args": {"order_id": "ORD1001", "amount": 79900.0, "reason": "Premature call"},
            "id": "premature_1"
        }]
    )

    state = {
        "messages": [
            HumanMessage(content="Can you refund ORD1001?"),
            unauthorized_call
        ],
        "current_order_id": "ORD1001",
        "pending_refund": None  # Not confirmed!
    }

    result = tool_node(state)
    tool_msg = result["messages"][0]
    output = json.loads(tool_msg.content)

    assert output["success"] is False
    assert output["error_code"] == "CONFIRMATION_REQUIRED"
    assert "blocked by system guard" in output["message"].lower()
