import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.documents import Document

load_dotenv()

# Instructs the LLM to ground answers in retrieved docs and avoid hallucination
_SYSTEM_PROMPT = """\
You are the Zapit AI Assistant, an expert on the Zapit enterprise file transfer application.
Your role is to provide accurate, helpful answers about Zapit installation, configuration, commands,
troubleshooting, error codes, security, encryption, transfer modes, and operations.

Guidelines:
- Answer ONLY using the retrieved context provided below (Zapit documentation).
- If the answer is not found in the context, respond with:
  "I couldn't find that information in the Zapit documentation. Please refer to the official Zapit guide or contact your system administrator."
- Do NOT invent, assume, or infer information beyond what the documentation states.
- For commands, always display them in code blocks for clarity.
- Be professional, precise, and concise.
- At the end of your answer, list the source documents used.

Retrieved Context:
{context}
"""


def _get_llm(config: dict):
    provider = config["llm"]["provider"].lower()
    temperature = config["llm"].get("temperature", 0.3)
    if provider == "openai":
        return ChatOpenAI(
            model=config["llm"]["openai_model"],
            temperature=temperature,
            api_key=os.getenv("OPENAI_API_KEY"),
        )
    elif provider == "gemini":
        return ChatGoogleGenerativeAI(
            model=config["llm"]["gemini_model"],
            temperature=temperature,
            google_api_key=os.getenv("GOOGLE_API_KEY"),
        )
    raise ValueError(f"Unsupported LLM provider: {provider}")


def _build_prompt() -> ChatPromptTemplate:
    return ChatPromptTemplate.from_messages([
        ("system", _SYSTEM_PROMPT),
        MessagesPlaceholder(variable_name="chat_history"),
        ("human", "{question}"),
    ])


def format_context_and_sources(
    ranked_docs: list[tuple[Document, float]],
) -> tuple[str, list[str]]:
    """Extract combined context string and deduplicated source filenames."""
    context_parts: list[str] = []
    sources: list[str] = []
    seen: set[str] = set()

    for doc, _ in ranked_docs:
        context_parts.append(doc.page_content)
        src = doc.metadata.get("source_file") or doc.metadata.get("source", "Unknown")
        if src not in seen:
            sources.append(src)
            seen.add(src)

    context = "\n\n---\n\n".join(context_parts)
    return context, sources


def answer_question(
    question: str,
    ranked_docs: list[tuple[Document, float]],
    chat_history: list,
    config: dict,
) -> str:
    llm = _get_llm(config)
    prompt = _build_prompt()
    context, _ = format_context_and_sources(ranked_docs)

    chain = prompt | llm
    response = chain.invoke({
        "context": context,
        "chat_history": chat_history,
        "question": question,
    })
    return response.content
