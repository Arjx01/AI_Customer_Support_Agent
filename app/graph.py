import re
import json
import sqlite3
from typing import Annotated, Sequence, Optional, Dict, Any, List
from typing_extensions import TypedDict

from langchain_core.messages import (
    BaseMessage,
    SystemMessage,
    HumanMessage,
    AIMessage,
    ToolMessage,
)
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.checkpoint.sqlite import SqliteSaver

from app.config import CHECKPOINT_DB_PATH
from app.prompts import SYSTEM_PROMPT
from app.tools import ALL_TOOLS
from app.llm import get_llm

class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]
    current_order_id: Optional[str]
    customer_name: Optional[str]
    pending_refund: Optional[Dict[str, Any]]

# Tool mapping by name
TOOL_MAP = {t.name: t for t in ALL_TOOLS}

CONFIRMATION_KEYWORDS = {
    "yes", "confirm", "proceed", "go ahead", "refund it", "please do",
    "sure", "ok", "okay", "yep", "do it", "process it", "please refund"
}

REJECTION_KEYWORDS = {
    "no", "cancel", "don't", "stop", "nevermind", "never mind", "abort"
}

def extract_order_id(text: str) -> Optional[str]:
    """Finds order IDs like ORD1001 in text."""
    if not text:
        return None
    match = re.search(r"\b(ORD\d{3,6})\b", text, re.IGNORECASE)
    return match.group(1).upper() if match else None

def check_user_confirmation(user_text: str) -> Optional[bool]:
    """Returns True if user confirmed, False if user cancelled/rejected, None otherwise."""
    text_lower = user_text.lower()
    for word in REJECTION_KEYWORDS:
        if re.search(rf"\b{re.escape(word)}\b", text_lower):
            return False
    for word in CONFIRMATION_KEYWORDS:
        if re.search(rf"\b{re.escape(word)}\b", text_lower):
            return True
    return None

def agent_node(state: AgentState, llm=None) -> Dict[str, Any]:
    """
    Agent node: analyzes state, resolves active context, binds tools, and calls LLM.
    """
    messages = list(state.get("messages", []))
    current_order_id = state.get("current_order_id")
    customer_name = state.get("customer_name")
    pending_refund = state.get("pending_refund")

    # 1. Inspect recent messages to track order ID and confirmation status
    for m in reversed(messages):
        if isinstance(m, HumanMessage):
            detected_id = extract_order_id(str(m.content))
            if detected_id:
                current_order_id = detected_id

            # Check if user is confirming or cancelling a pending refund
            if pending_refund and pending_refund.get("eligible"):
                confirm_status = check_user_confirmation(str(m.content))
                if confirm_status is True:
                    pending_refund["confirmed"] = True
                elif confirm_status is False:
                    pending_refund = None
            break

    # 2. Build system message with active context injection
    sys_content = SYSTEM_PROMPT
    context_notes = []
    if current_order_id:
        context_notes.append(f"CURRENT ACTIVE ORDER ID: {current_order_id}")
    if customer_name:
        context_notes.append(f"AUTHENTICATED CUSTOMER: {customer_name}")
    if pending_refund:
        stat = "CONFIRMED BY CUSTOMER" if pending_refund.get("confirmed") else "AWAITING CUSTOMER CONFIRMATION"
        context_notes.append(
            f"PENDING REFUND: Order {pending_refund.get('order_id')}, Amount ₹{pending_refund.get('amount')}, Status: {stat}"
        )

    if context_notes:
        sys_content += "\n\n### ACTIVE CONVERSATION CONTEXT\n" + "\n".join(f"- {note}" for note in context_notes)

    # 3. Assemble prompt messages for LLM
    final_messages = [SystemMessage(content=sys_content)]
    for msg in messages:
        if not isinstance(msg, SystemMessage):
            final_messages.append(msg)

    # 4. Invoke LLM with tools bound
    active_llm = llm or get_llm()
    llm_with_tools = active_llm.bind_tools(ALL_TOOLS)
    response = llm_with_tools.invoke(final_messages)

    return {
        "messages": [response],
        "current_order_id": current_order_id,
        "customer_name": customer_name,
        "pending_refund": pending_refund
    }

def tool_node(state: AgentState) -> Dict[str, Any]:
    """
    Executes tool calls requested by the LLM with strict safety guards.
    """
    messages = state.get("messages", [])
    last_message = messages[-1]
    current_order_id = state.get("current_order_id")
    pending_refund = state.get("pending_refund")
    tool_messages = []

    if not isinstance(last_message, AIMessage) or not last_message.tool_calls:
        return {}

    for tool_call in last_message.tool_calls:
        tool_name = tool_call["name"]
        tool_args = dict(tool_call.get("args", {}))
        call_id = tool_call.get("id", f"call_{tool_name}")

        # If tool takes order_id and was not provided or empty, inject current_order_id if known
        if "order_id" in tool_args and not tool_args["order_id"] and current_order_id:
            tool_args["order_id"] = current_order_id
        elif "order_id" in tool_args and tool_args["order_id"]:
            current_order_id = str(tool_args["order_id"]).strip().upper()

        # REFUND CONFIRMATION GUARD
        if tool_name == "process_refund":
            target_order = tool_args.get("order_id") or current_order_id
            target_amt = tool_args.get("amount")
            
            # Verify that eligibility was checked and user explicitly confirmed
            is_confirmed = (
                pending_refund is not None
                and pending_refund.get("order_id") == target_order
                and pending_refund.get("eligible") is True
                and pending_refund.get("confirmed") is True
            )
            
            # Check also if the last human message contained explicit affirmative confirmation
            last_human = next((m for m in reversed(messages) if isinstance(m, HumanMessage)), None)
            if last_human and check_user_confirmation(str(last_human.content)) is True:
                # User did explicitly say yes/confirm in their message!
                if pending_refund and pending_refund.get("order_id") == target_order:
                    pending_refund["confirmed"] = True
                    is_confirmed = True

            if not is_confirmed:
                # Guard rejects execution!
                error_response = {
                    "success": False,
                    "error_code": "CONFIRMATION_REQUIRED",
                    "message": (
                        "Refund execution blocked by system guard: Store policy requires checking "
                        "refund eligibility first with 'check_refund_eligibility' and receiving "
                        "explicit customer confirmation of the refund amount before processing."
                    ),
                    "action_required": "Please verify eligibility and ask the customer to confirm the refund amount."
                }
                tool_messages.append(
                    ToolMessage(content=json.dumps(error_response), tool_call_id=call_id, name=tool_name)
                )
                continue

        # Execute tool
        selected_tool = TOOL_MAP.get(tool_name)
        if not selected_tool:
            error_response = {
                "success": False,
                "error_code": "TOOL_NOT_FOUND",
                "message": f"Tool '{tool_name}' is not recognized."
            }
            tool_messages.append(
                ToolMessage(content=json.dumps(error_response), tool_call_id=call_id, name=tool_name)
            )
            continue

        try:
            tool_output_str = selected_tool.invoke(tool_args)
            
            # Update pending_refund state on check_refund_eligibility
            if tool_name == "check_refund_eligibility":
                try:
                    out_json = json.loads(tool_output_str)
                    if out_json.get("eligible"):
                        pending_refund = {
                            "order_id": out_json.get("order_id") or tool_args.get("order_id"),
                            "amount": out_json.get("suggested_amount") or out_json.get("max_refundable"),
                            "eligible": True,
                            "confirmed": False
                        }
                    else:
                        pending_refund = None
                except Exception:
                    pass

            # Clear pending_refund on successful process_refund
            if tool_name == "process_refund":
                try:
                    out_json = json.loads(tool_output_str)
                    if out_json.get("success"):
                        pending_refund = None
                except Exception:
                    pass

            tool_messages.append(
                ToolMessage(content=str(tool_output_str), tool_call_id=call_id, name=tool_name)
            )

        except Exception as e:
            error_response = {
                "success": False,
                "error_code": "TOOL_EXECUTION_ERROR",
                "message": f"Tool execution failed: {str(e)}"
            }
            tool_messages.append(
                ToolMessage(content=json.dumps(error_response), tool_call_id=call_id, name=tool_name)
            )

    return {
        "messages": tool_messages,
        "current_order_id": current_order_id,
        "pending_refund": pending_refund
    }

def should_continue(state: AgentState) -> str:
    """Conditional edge: if last message has tool calls, route to tools; otherwise END."""
    messages = state.get("messages", [])
    if not messages:
        return END
    last_msg = messages[-1]
    if isinstance(last_msg, AIMessage) and getattr(last_msg, "tool_calls", None):
        return "tools"
    return END

def build_graph(checkpointer: Optional[Any] = None, llm: Optional[Any] = None):
    """
    Builds and compiles the customer support LangGraph StateGraph.
    """
    workflow = StateGraph(AgentState)

    # Bind node functions (allowing llm injection for tests)
    workflow.add_node("agent", lambda state: agent_node(state, llm=llm))
    workflow.add_node("tools", tool_node)

    workflow.set_entry_point("agent")

    workflow.add_conditional_edges(
        "agent",
        should_continue,
        {
            "tools": "tools",
            END: END
        }
    )
    workflow.add_edge("tools", "agent")

    # If checkpointer provided, compile with checkpointer
    if checkpointer is not None:
        return workflow.compile(checkpointer=checkpointer)
    return workflow.compile()

_checkpointer_instance = None

def get_checkpointer(db_path: Optional[str] = None) -> SqliteSaver:
    """Returns singleton SqliteSaver checkpointer for thread persistence."""
    global _checkpointer_instance
    if _checkpointer_instance is not None:
        return _checkpointer_instance

    path = db_path or CHECKPOINT_DB_PATH
    conn = sqlite3.connect(path, check_same_thread=False)
    saver = SqliteSaver(conn)
    saver.setup()
    _checkpointer_instance = saver
    return _checkpointer_instance

def get_support_agent(checkpointer: Optional[Any] = None, llm: Optional[Any] = None):
    """Returns compiled agent runnable with checkpointer."""
    cp = checkpointer if checkpointer is not None else get_checkpointer()
    return build_graph(checkpointer=cp, llm=llm)
