import os
import pytest
from langchain_core.messages import HumanMessage
from app.config import GEMINI_API_KEY
from app.graph import get_support_agent

# Skip all tests in module unless explicitly requested and API key is set
pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        not GEMINI_API_KEY or os.getenv("RUN_LIVE_TESTS", "").lower() not in ["1", "true", "yes"],
        reason="Live smoke tests require GEMINI_API_KEY and RUN_LIVE_TESTS=1 to avoid external latency/quota issues."
    )
]

def test_live_rag_policy_question():
    """Live smoke test: asks policy question, tests RAG retrieval and citation in LLM answer."""
    agent = get_support_agent()
    thread_id = "live_smoke_rag_1"
    
    result = agent.invoke(
        {"messages": [HumanMessage(content="What is your return and refund window?")]},
        config={"configurable": {"thread_id": thread_id}}
    )
    
    reply = result["messages"][-1].content
    assert reply
    # Must mention 30 days or window
    assert "30" in reply or "window" in reply.lower() or "refund" in reply.lower()
    # Must cite return policy
    assert "return_and_refund_policy" in reply.lower() or "source:" in reply.lower()

def test_live_order_status_lookup():
    """Live smoke test: asks for order status, tests live DB tool calling."""
    agent = get_support_agent()
    thread_id = "live_smoke_order_2"

    result = agent.invoke(
        {"messages": [HumanMessage(content="What is the current delivery status of order ORD1001?")]},
        config={"configurable": {"thread_id": thread_id}}
    )

    reply = result["messages"][-1].content
    assert reply
    assert "iphone" in reply.lower() or "delivered" in reply.lower()

def test_live_refund_eligibility_and_confirmation():
    """Live smoke test: asks if ORD1001 is eligible for refund, tests business rule and confirmation prompt."""
    agent = get_support_agent()
    thread_id = "live_smoke_refund_3"

    result = agent.invoke(
        {"messages": [HumanMessage(content="Can I request a refund for my order ORD1001?")]},
        config={"configurable": {"thread_id": thread_id}}
    )

    reply = result["messages"][-1].content
    assert reply
    assert "eligible" in reply.lower() or "79,900" in reply or "79900" in reply
    # Agent should ask for confirmation or confirm intent
    assert any(w in reply.lower() for w in ["confirm", "proceed", "like me to", "process"])
