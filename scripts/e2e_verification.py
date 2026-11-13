import os
import sys
import json
import sqlite3
from pathlib import Path

# Ensure UTF-8 stdout on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from langchain_core.messages import HumanMessage
from app.graph import build_graph, get_checkpointer
from tests.test_agent_flow import DeterministicMockLLM
from app.db import get_order, get_refunds_for_order
from app.rag import search_docs

def run_end_to_end_verification():
    print("=" * 60)
    print("AI CUSTOMER SUPPORT AGENT: END-TO-END VERIFICATION")
    print("=" * 60)

    # 1. Product & Policy Question with Citations
    print("\n--- STEP 1: Product / Policy Question (RAG) ---")
    query = "What is your return and refund window?"
    print(f"Customer Question: '{query}'")
    rag_result = search_docs(query)
    print(f"RAG Success: {rag_result['success']}")
    print(f"Found: {rag_result['found']}")
    print(f"Top Score: {rag_result['best_score']}")
    print(f"Citations: {rag_result['formatted_sources']}")
    assert rag_result["found"] is True
    assert "return_and_refund_policy.md" in rag_result["formatted_sources"]

    # 2. Multi-turn conversation with Agent
    print("\n--- STEP 2: Multi-turn Conversation with Agent ---")
    mock_llm = DeterministicMockLLM()
    checkpointer = get_checkpointer()
    agent = build_graph(checkpointer=checkpointer, llm=mock_llm)

    thread_id = "e2e_verification_thread_01"
    config = {"configurable": {"thread_id": thread_id}}

    # Turn A: Look up order ORD1004 (MacBook Air M3, price=114900.0)
    print("\n[Turn 1] Customer: 'What are the details of my order ORD1004?'")
    s1 = agent.invoke(
        {"messages": [HumanMessage(content="What are the details of my order ORD1004?")]},
        config=config
    )
    reply1 = s1["messages"][-1].content
    print(f"Agent Reply: {reply1}")
    assert "ORD1004" in reply1

    # Use isolated test database copy for e2e run
    test_db = "orders_e2e_test.db"
    import shutil
    shutil.copy2("orders.db", test_db)
    
    import app.db, app.refunds
    orig_db = app.db.DB_PATH
    app.db.DB_PATH = test_db
    app.refunds.DB_PATH = test_db

    try:
        # Check baseline DB state before refund
        order_before = get_order("ORD1004", db_path=test_db)
        print(f"\nDB State Before Refund: Order Price: INR {order_before['order_price']}, Refunded Amount: INR {order_before['refunded_amount']}, Payment Status: {order_before['payment_status']}")
        initial_refunded = order_before["refunded_amount"]
        refund_amount = 15000.0

        # Turn B: Request partial refund (resolving ORD1004 from context)
        print("\n[Turn 2] Customer: 'I want to request a partial refund for it.'")
        s2 = agent.invoke(
            {"messages": [HumanMessage(content="I want to request a partial refund for it.")]},
            config=config
        )
        reply2 = s2["messages"][-1].content
        print(f"Agent Reply: {reply2}")
        assert "eligible for a refund" in reply2.lower()
        assert s2["pending_refund"] is not None
        assert s2["pending_refund"]["eligible"] is True

        # Turn C: Confirm refund
        print("\n[Turn 3] Customer: 'Yes, please confirm and process the refund.'")
        s2["pending_refund"]["amount"] = refund_amount
        s3 = agent.invoke(
            {
                "messages": [HumanMessage(content="Yes, please confirm and process the refund.")],
                "pending_refund": {"order_id": "ORD1004", "amount": refund_amount, "eligible": True, "confirmed": True}
            },
            config=config
        )
        reply3 = s3["messages"][-1].content
        print(f"Agent Reply: {reply3}")

        # 3. Direct DB Query Verification
        print("\n--- STEP 3: Direct Database Verification (orders_e2e_test.db) ---")
        conn = sqlite3.connect(test_db)
        cursor = conn.cursor()

        cursor.execute("SELECT order_id, customer_name, product_name, order_price, refunded_amount, payment_status, order_status FROM orders WHERE order_id = 'ORD1004';")
        order_row = cursor.fetchone()
        print(f"Updated Orders Row: {order_row}")

        cursor.execute("SELECT refund_id, order_id, amount, reason, created_at FROM refunds WHERE order_id = 'ORD1004' ORDER BY created_at DESC LIMIT 1;")
        refund_row = cursor.fetchone()
        print(f"New Refunds Audit Row: {refund_row}")
        conn.close()

        assert order_row[4] == initial_refunded + refund_amount, f"Expected refunded_amount to be {initial_refunded + refund_amount}, got {order_row[4]}"
        assert order_row[5] == "Partially Refunded", f"Expected payment_status to be 'Partially Refunded', got {order_row[5]}"
        assert refund_row is not None
        assert refund_row[1] == "ORD1004"
        assert refund_row[2] == refund_amount

        print("\n" + "=" * 60)
        print("ALL END-TO-END VERIFICATION CHECKS PASSED SUCCESSFULLY!")
        print("=" * 60)
    finally:
        app.db.DB_PATH = orig_db
        app.refunds.DB_PATH = orig_db
        if os.path.exists(test_db):
            os.remove(test_db)

if __name__ == "__main__":
    run_end_to_end_verification()
