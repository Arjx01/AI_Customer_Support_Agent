import os
import sys
import uuid
import re
from pathlib import Path
import streamlit as st

# Ensure project root is in sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
from app.config import (
    LLM_PROVIDER,
    LLM_MODEL,
    GEMINI_API_KEY,
    OPENAI_API_KEY,
    ANTHROPIC_API_KEY,
    DB_PATH
)
from app.db import get_all_orders, get_all_refunds
from app.llm import get_llm
from app.graph import get_support_agent

st.set_page_config(
    page_title="AI Customer Support Agent",
    page_icon="🎧",
    layout="wide"
)

# Custom CSS for modern styling
st.markdown("""
<style>
    .source-box {
        background-color: #f0f4f8;
        border-left: 4px solid #1E88E5;
        padding: 8px 12px;
        border-radius: 4px;
        font-size: 0.85em;
        margin-top: 6px;
        color: #2c3e50;
    }
    .status-badge {
        display: inline-block;
        padding: 2px 8px;
        border-radius: 12px;
        font-size: 0.8em;
        font-weight: bold;
    }
    .badge-delivered { background-color: #e8f5e9; color: #2e7d32; }
    .badge-refunded { background-color: #ffebee; color: #c62828; }
    .badge-transit { background-color: #fff3e0; color: #ef6c00; }
</style>
""", unsafe_allow_html=True)

# 1. Check API Key configuration
def check_api_key_configured():
    provider = LLM_PROVIDER.lower()
    if provider in ["gemini", "google"]:
        return bool(GEMINI_API_KEY)
    elif provider == "openai":
        return bool(OPENAI_API_KEY)
    elif provider in ["anthropic", "claude"]:
        return bool(ANTHROPIC_API_KEY)
    return False

api_key_ok = check_api_key_configured()

# Initialize session state
if "thread_id" not in st.session_state:
    st.session_state.thread_id = str(uuid.uuid4())[:8]

if "messages" not in st.session_state:
    st.session_state.messages = []

if "customer_name" not in st.session_state:
    st.session_state.customer_name = "Rahul Sharma"

def extract_text_content(content) -> str:
    """Safely extracts string content whether LLM returns str or list of dicts."""
    if isinstance(content, str):
        return content
    elif isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                parts.append(item.get("text", ""))
            else:
                parts.append(str(item))
        return "".join(parts)
    return str(content or "")

# Helper to format citations
def extract_sources(text: str):
    matches = re.findall(r"\[Source:\s*([^\]]+)\]", text)
    return matches

# Sidebar
with st.sidebar:
    st.title("🎧 Support Desk")
    st.caption(f"Provider: **{LLM_PROVIDER.upper()}**")
    st.caption(f"Active Thread ID: `{st.session_state.thread_id}`")

    # Dynamic model selector
    if LLM_PROVIDER.lower() in ["gemini", "google"]:
        gemini_models = [
            "gemini-3.5-flash-lite",
            "gemini-3.1-flash-lite",
            "gemini-3.5-flash",
            "gemini-3.8-flash"
        ]
        curr_m = st.session_state.get("selected_model", LLM_MODEL)
        default_idx = gemini_models.index(curr_m) if curr_m in gemini_models else 0
        st.session_state.selected_model = st.selectbox(
            "Active Model:",
            gemini_models,
            index=default_idx,
            help="gemini-3.5-flash-lite is recommended for ultra-fast response without 503 high-demand limits."
        )
    else:
        st.session_state.selected_model = LLM_MODEL

    if st.button("🔄 New Conversation", use_container_width=True):
        st.session_state.thread_id = str(uuid.uuid4())[:8]
        st.session_state.messages = []
        st.rerun()

    st.divider()

    # Customer Selector
    st.subheader("👤 Customer Context")
    orders_data = get_all_orders()
    customer_list = sorted(list(set(o["customer_name"] for o in orders_data)))
    selected_customer = st.selectbox(
        "Active Customer Profile:",
        ["Guest (Unauthenticated)"] + customer_list,
        index=customer_list.index("Rahul Sharma") + 1 if "Rahul Sharma" in customer_list else 0
    )
    st.session_state.customer_name = None if selected_customer.startswith("Guest") else selected_customer

    st.divider()

    # Quick test prompts
    st.subheader("💡 Example Queries")
    example_prompts = [
        "What is your return and refund policy?",
        "Can you check the delivery status of ORD1001?",
        "I want to request a refund for ORD1001.",
        "What are the specifications of the iPhone 16?",
        "My wireless mouse is lagging, how can I troubleshoot it?"
    ]
    for prompt in example_prompts:
        if st.button(prompt, key=f"btn_{prompt[:20]}", use_container_width=True):
            st.session_state["preset_input"] = prompt
            st.rerun()

    st.divider()

    # Live Database View
    st.subheader("📦 Live Orders & Refunds")
    st.caption("Auto-refreshes directly from SQLite database")
    
    tab1, tab2 = st.tabs(["Orders", "Refunds"])
    with tab1:
        if orders_data:
            orders_display = [
                {
                    "Order ID": o["order_id"],
                    "Customer": o["customer_name"],
                    "Product": o["product_name"],
                    "Price (₹)": f"{o['order_price']:,.2f}",
                    "Refunded (₹)": f"{o['refunded_amount']:,.2f}",
                    "Payment": o["payment_status"],
                    "Delivery": o["delivery_status"]
                }
                for o in orders_data
            ]
            st.dataframe(orders_display, use_container_width=True, hide_index=True)
        else:
            st.info("No orders in database.")

    with tab2:
        refunds_data = get_all_refunds()
        if refunds_data:
            refunds_display = [
                {
                    "Refund ID": r["refund_id"],
                    "Order ID": r["order_id"],
                    "Amount (₹)": f"{r['amount']:,.2f}",
                    "Reason": r["reason"],
                    "Date": str(r["created_at"])[:16]
                }
                for r in refunds_data
            ]
            st.dataframe(refunds_display, use_container_width=True, hide_index=True)
        else:
            st.info("No refund transactions recorded yet.")

# Main Chat Interface
st.header("🛒 E-Commerce Support Assistant")
st.write("Welcome! Ask questions about our products, store policies, check your orders, or process returns.")

# API Key Warning Banner if missing
if not api_key_ok:
    st.error(
        f"""
        ⚠️ **Configuration Required**: No API key detected for provider **{LLM_PROVIDER}**.
        
        Please configure your `.env` file with your credentials (e.g., `GEMINI_API_KEY=your_key` or `OPENAI_API_KEY=your_key`).
        The agent will remain offline until a valid API key is provided.
        """
    )

# Display existing messages
for msg in st.session_state.messages:
    role = msg.get("role", "assistant")
    with st.chat_message(role):
        st.markdown(msg.get("content", ""))
        sources = msg.get("sources", [])
        if sources:
            with st.expander("📚 Verified Documentation Sources", expanded=False):
                for src in sources:
                    st.markdown(f"- `{src}`")

# Handle user input (from chat_input or preset button)
user_prompt = st.chat_input("Type your question or request here...")
if "preset_input" in st.session_state:
    user_prompt = st.session_state.pop("preset_input")

if user_prompt:
    if not api_key_ok:
        st.warning("Cannot send message: Please configure your API key in `.env` first.")
    else:
        # Display user message
        st.session_state.messages.append({"role": "user", "content": user_prompt})
        with st.chat_message("user"):
            st.markdown(user_prompt)

        # Execute agent
        with st.chat_message("assistant"):
            with st.spinner("Analyzing request and consulting records..."):
                try:
                    active_model = st.session_state.get("selected_model", LLM_MODEL)
                    llm = get_llm(model=active_model)
                    agent = get_support_agent(llm=llm)
                    config = {
                        "configurable": {
                            "thread_id": st.session_state.thread_id
                        }
                    }

                    initial_input = {
                        "messages": [HumanMessage(content=user_prompt)],
                        "customer_name": st.session_state.customer_name
                    }

                    final_state = agent.invoke(initial_input, config=config)
                    all_returned_messages = final_state.get("messages", [])
                    
                    # Locate final assistant response
                    assistant_msg = None
                    for m in reversed(all_returned_messages):
                        if isinstance(m, AIMessage) and m.content:
                            assistant_msg = m.content
                            break

                    raw_reply = extract_text_content(assistant_msg) or "I have processed your request. How else may I assist you?"
                    
                    # Extract sources for display
                    sources = extract_sources(raw_reply)
                    clean_reply = re.sub(r"\[Source:\s*[^\]]+\]", "", raw_reply).strip()

                    st.markdown(clean_reply)
                    if sources:
                        with st.expander("📚 Verified Documentation Sources", expanded=True):
                            for src in sources:
                                st.markdown(f"- `{src}`")

                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": clean_reply,
                        "sources": sources
                    })
                    st.rerun()

                except Exception as e:
                    err_str = str(e)
                    if "503" in err_str or "high demand" in err_str.lower():
                        error_msg = (
                            "⚠️ **Model High Demand (503)**: Google's servers for the selected model "
                            "are currently experiencing high traffic. Please switch to "
                            "`gemini-3.5-flash-lite` in the sidebar for immediate, ultra-fast responses."
                        )
                    else:
                        error_msg = f"An error occurred while processing your request: {err_str}"
                    st.error(error_msg)
                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": error_msg
                    })
