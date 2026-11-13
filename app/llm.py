import os
from typing import Optional, Any
from langchain_core.language_models.chat_models import BaseChatModel
from app.config import (
    LLM_PROVIDER,
    LLM_MODEL,
    LLM_TEMPERATURE,
    GEMINI_API_KEY,
    OPENAI_API_KEY,
    ANTHROPIC_API_KEY,
)

def get_llm(
    provider: Optional[str] = None,
    model: Optional[str] = None,
    temperature: Optional[float] = None
) -> BaseChatModel:
    """
    Factory function returning an initialized LangChain ChatModel with native
    tool/function calling capabilities. Provider is configurable: 'gemini', 'openai', 'anthropic'.
    """
    prov = (provider or LLM_PROVIDER).lower()
    temp = temperature if temperature is not None else LLM_TEMPERATURE

    if prov in ["gemini", "google"]:
        api_key = GEMINI_API_KEY
        if not api_key:
            raise ValueError(
                "GEMINI_API_KEY (or GOOGLE_API_KEY) is not set. Please set it in your .env file."
            )
        from langchain_google_genai import ChatGoogleGenerativeAI
        m = model or LLM_MODEL or "gemini-3.5-flash-lite"
        
        primary_llm = ChatGoogleGenerativeAI(
            model=m,
            google_api_key=api_key,
            max_retries=2
        )
        
        # Add automated fallback to fast flash-lite model if primary encounters 503 high demand
        if m != "gemini-3.1-flash-lite":
            fallback_llm = ChatGoogleGenerativeAI(
                model="gemini-3.1-flash-lite",
                google_api_key=api_key,
                max_retries=2
            )
            return primary_llm.with_fallbacks([fallback_llm])
        
        return primary_llm

    elif prov in ["openai"]:
        api_key = OPENAI_API_KEY
        if not api_key:
            raise ValueError(
                "OPENAI_API_KEY is not set. Please set it in your .env file."
            )
        from langchain_openai import ChatOpenAI
        m = model or "gpt-4o-mini"
        return ChatOpenAI(
            model=m,
            api_key=api_key,
            temperature=temp
        )

    elif prov in ["anthropic", "claude"]:
        api_key = ANTHROPIC_API_KEY
        if not api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY is not set. Please set it in your .env file."
            )
        from langchain_anthropic import ChatAnthropic
        m = model or "claude-3-5-sonnet-20241022"
        return ChatAnthropic(
            model=m,
            api_key=api_key,
            temperature=temp
        )

    else:
        raise ValueError(
            f"Unsupported LLM provider '{prov}'. Supported options are: 'gemini', 'openai', 'anthropic'."
        )
