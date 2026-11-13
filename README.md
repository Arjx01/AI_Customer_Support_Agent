# AI Customer Support Agent

A production-grade, autonomous Customer Support Agent built with **LangGraph**, **LangChain**, **SQLite**, and **Streamlit**. It integrates retrieval-augmented generation (RAG) over realistic knowledge base documentation, tool-assisted database lookups, business rule validation in pure Python, atomic transactional refund processing, and conversational memory persisted across threads.

---

## Features

1. **Knowledge-Based QA (RAG)**
   - 10 markdown documentation files covering return/refund policies, shipping & delivery, warranties, payment & billing, account management, product FAQs, and troubleshooting.
   - Vector similarity search via **ChromaDB** with sentence transformer embeddings.
   - Automated source citations (`[Source: filename.md - Section]`) in responses.
   - Relevance threshold scoring: queries below the threshold gracefully decline to answer and offer human agent escalation.

2. **Order Management & Database Tools**
   - Retrieves live order details, delivery tracking, and payment histories using parameterized SQLite queries.
   - Respects customer scoping and validates inputs.

3. **Intelligent & Safe Refund Handling**
   - **Deterministic Python Business Rules (NOT in prompt)**:
     - 30-day refund window from order date.
     - Delivered items only (items in transit, processing, or unfulfilled cannot be returned).
     - Non-refundable categories filter (e.g. digital software, gift cards).
     - Cancelled orders rejected.
     - Already fully refunded orders rejected.
     - Partial and full refunds supported, tracking cumulative refunded amounts against total paid price.
   - **ACID Transaction Execution**:
     - Inside a single SQLite transaction with row-level integrity.
     - Re-validates eligibility inside the transaction before committing.
     - Updates cumulative `refunded_amount`, sets `payment_status` and `order_status` ('Partially Refunded' or 'Refunded').
     - Inserts audit record with unique `refund_id` in `refunds` table.
     - Automatic rollback on any failure.
   - **Two-Phase Confirmation Safety Guard**:
     - LangGraph guard physically prevents `process_refund` from executing unless eligibility was verified and the customer explicitly confirmed the refund amount in conversation.

4. **Conversational Memory**
   - State persisted using LangGraph's `SqliteSaver` checkpointer keyed by `thread_id`.
   - Contextual reference resolution: follow-ups like *"refund it"*, *"when will it arrive?"*, or *"what about my second item?"* automatically resolve using conversation context without asking the customer to repeat their Order ID.

5. **Interactive Streamlit UI**
   - Chat interface with real-time streaming, conversation history, and thread management.
   - Source citation badges under RAG responses.
   - Live sidebar panel displaying current `orders` and `refunds` directly from SQLite with immediate post-refund updates.
   - Warning banner if required API keys are missing.

---

## Project Structure

```
AI_Customer_Support_Agent/
├── app/
│   ├── __init__.py
│   ├── config.py              # Environment configuration & defaults
│   ├── db.py                  # Database connection & query helper functions
│   ├── rules.py               # Pure Python business rules for refund eligibility
│   ├── refunds.py             # Transactional refund execution & rollback
│   ├── rag.py                 # ChromaDB vector store, chunking, and similarity search
│   ├── tools.py               # LangChain tools with structured JSON returns
│   ├── prompts.py             # System prompt & operational instructions
│   ├── llm.py                 # LLM provider factory (Gemini, OpenAI, Anthropic)
│   └── graph.py               # LangGraph StateGraph, confirmation guard, & checkpointer
├── ui/
│   └── streamlit_app.py       # Streamlit UI with live DB tables & chat
├── app.py                     # Root entry point forwarding to Streamlit UI
├── data/
│   ├── docs/                  # 10 realistic knowledge base markdown files
│   └── chroma_db/             # Persisted ChromaDB vector database
├── scripts/
│   ├── inspect_db.py          # Database schema inspector
│   ├── migrate_db.py          # Idempotent database migration & backup script
│   └── ingest_docs.py         # Document chunking & vector ingestion pipeline
├── tests/
│   ├── __init__.py
│   ├── conftest.py            # Isolated SQLite and Chroma fixtures
│   ├── test_rules_and_refunds.py # Unit tests for rules & transactional refunds
│   ├── test_rag.py            # RAG retrieval, threshold, & idempotency tests
│   ├── test_tools.py          # Structured error handling tests for all tools
│   ├── test_agent_flow.py     # Multi-turn conversation & guard tests (Mock LLM)
│   └── test_live_smoke.py     # Live LLM smoke tests (skipped when disabled)
├── orders.db                  # Primary SQLite database
├── orders.db.bak              # Pre-migration backup
├── chat_checkpoints.db        # LangGraph conversation state checkpointer
├── requirements.txt           # Python dependencies
├── .env.example               # Example environment configuration
├── .env                       # Local environment variables
├── ARCHITECTURE.md            # Architectural deep dive & design decisions
└── README.md                  # Project documentation
```

---

## Prerequisites

- **Python**: 3.10, 3.11, or 3.12
- **Operating System**: Windows, macOS, or Linux
- **SQLite**: Built into standard Python

---

## Installation & Setup

### 1. Clone or Open Workspace
```bash
cd AI_Customer_Support_Agent
```

### 2. Create and Activate Virtual Environment
On Windows (PowerShell):
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```
On macOS / Linux:
```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Configure Environment Variables
Copy `.env.example` to `.env` and configure your API key and provider:
```bash
cp .env.example .env
```
Edit `.env`:
```env
LLM_PROVIDER=gemini
LLM_MODEL=gemini-3.8-flash
LLM_TEMPERATURE=0.0
GEMINI_API_KEY=your_gemini_api_key_here

# For OpenAI:
# LLM_PROVIDER=openai
# LLM_MODEL=gpt-4o-mini
# OPENAI_API_KEY=your_openai_key_here

# For Anthropic:
# LLM_PROVIDER=anthropic
# LLM_MODEL=claude-3-5-sonnet-20241022
# ANTHROPIC_API_KEY=your_anthropic_key_here
```

---

## Database Migration & Ingestion

### 1. Run Database Migration (Idempotent)
Backs up `orders.db` to `orders.db.bak`, adds the `refunded_amount` column to `orders`, creates the `refunds` audit table, and initializes baseline refund states. Safe to run multiple times:
```bash
python scripts/migrate_db.py
```

### 2. Ingest Documentation into Vector Store
Chunks all 10 markdown documents from `data/docs/` with section header preservation and embeds them into ChromaDB:
```bash
python scripts/ingest_docs.py
```

---

## Running the Application

Launch the Streamlit web interface:
```bash
streamlit run app.py
```
Open `http://localhost:8501` in your browser.

---

## Running Tests

All unit, integration, RAG, tool, and agent flow tests run completely offline without consuming API credits by using temporary database copies and mock agents:

```bash
pytest -v
```

To run optional live LLM tests against the real Gemini API:
```bash
$env:RUN_LIVE_TESTS="1"; pytest -v tests/test_live_smoke.py
```

---

## Example Conversations

### Scenario 1: Multi-Turn Order Lookup & Full Refund
- **User**: "What is the status of my order ORD1001?"
- **Agent**: "Your order ORD1001 for iPhone 16 was placed on 2026-11-01 and has been successfully **Delivered**. The total paid was ₹79,900.00 via UPI."
- **User**: "Can I get a refund for it?" *(Follow-up without repeating order ID)*
- **Agent**: "I checked your order ORD1001. It is within the 30-day return window and delivered. You are eligible for a full refund of **₹79,900.00** back to your original UPI account. Would you like me to go ahead and process this refund?"
- **User**: "Yes, please proceed."
- **Agent**: "Your refund of ₹79,900.00 for order ORD1001 has been processed successfully. **Refund ID: REF-E84A91B2**. The amount will reflect in your UPI account within 3 to 5 business days."

### Scenario 2: Policy Knowledge Retrieval (RAG)
- **User**: "What is your return policy and how many days do I have?"
- **Agent**: "You may request a return and refund within **30 days of the delivery date** for items marked as Delivered. Products must be in their original packaging. Non-refundable items include digital gift cards and software licenses. [Source: return_and_refund_policy.md - Refund Window]"

### Scenario 3: Out of Scope / Low Confidence Query
- **User**: "How do I bake sourdough bread?"
- **Agent**: "I could not find relevant documentation addressing that topic in our customer support knowledge base. Would you like me to connect you with a human support specialist?"

---

## Troubleshooting

1. **Missing or Invalid API Key**:
   If `GEMINI_API_KEY` is missing or invalid, Streamlit will display an amber configuration banner and decline user queries until an API key is provided in `.env`.
2. **PyTorch / SentenceTransformers First Load**:
   On the first run of the ingestion script, sentence transformers loads weights from local cache or huggingface hub. Subsequent queries are near-instantaneous.
3. **Database Locks**:
   SQLite is configured with `timeout=30.0` and `check_same_thread=False` to handle concurrent Streamlit UI queries cleanly.
