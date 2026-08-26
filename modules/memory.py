from langchain_core.messages import HumanMessage, AIMessage


def format_chat_history(history: list[dict], window_size: int = 5) -> list:
    """Convert stored chat turns into LangChain message objects for the prompt."""
    recent = history[-window_size:] if len(history) > window_size else history
    messages = []
    for turn in recent:
        messages.append(HumanMessage(content=turn["human"]))
        messages.append(AIMessage(content=turn["ai"]))
    return messages
