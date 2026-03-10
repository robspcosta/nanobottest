"""Tool for managing a persistent semantic knowledge base (RAG) using PostgreSQL."""

import json
from pathlib import Path
from typing import Any, Awaitable, Callable
from loguru import logger
from nanobot.agent.tools.base import Tool

class KnowledgeTool(Tool):
    """
    Tool for managing a persistent semantic knowledge base.
    Uses pgvector in PostgreSQL for meaning-based search.
    """

    def __init__(self, db: Any = None, embed_callback: Callable[[str], Awaitable[list[float]]] | None = None):
        self._db = db
        self._embed_callback = embed_callback
        self._channel = None
        self._chat_id = None

    def set_context(self, channel: str, chat_id: str) -> None:
        """Set the current session context to isolate knowledge per user."""
        self._channel = channel
        self._chat_id = chat_id

    @property
    def name(self) -> str:
        return "manage_knowledge"

    @property
    def description(self) -> str:
        return (
            "Save important information to the long-term semantic knowledge base or search through it. "
            "Use this when the user asks to 'remember', 'save', or 'store' information for later. "
            "Supported actions: store, search, list."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["store", "search", "list"],
                    "description": "The action to perform.",
                },
                "content": {
                    "type": "string",
                    "description": "The information to save (for 'store').",
                },
                "query": {
                    "type": "string",
                    "description": "Search query or topic to find relevant knowledge (for 'search').",
                },
                "tag": {
                    "type": "string",
                    "description": "Optional tag to categorize the knowledge (for 'store').",
                }
            },
            "required": ["action"],
        }

    async def execute(self, **kwargs: Any) -> str:
        if not self._db:
            return "Error: Database not configured for knowledge management."
        if not self._channel or not self._chat_id:
            return "Error: User context not set."

        action = kwargs.get("action")

        if action == "store":
            content = kwargs.get("content")
            if not content:
                return "Error: Content is required for 'store' action."
            
            if not self._embed_callback:
                return "Error: Embedding generator not configured."
            
            try:
                embedding = await self._embed_callback(content)
                metadata = {"tag": kwargs.get("tag")}
                self._db.add_knowledge(self._channel, self._chat_id, content, embedding, metadata)
                return "Knowledge successfully stored in the semantic memory."
            except Exception as e:
                logger.error("Failed to store knowledge: {}", e)
                return f"Error storing knowledge: {str(e)}"

        if action == "search":
            query = kwargs.get("query")
            if not query:
                return "Error: Query is required for 'search' action."
            
            if not self._embed_callback:
                return "Error: Embedding generator not configured."

            try:
                embedding = await self._embed_callback(query)
                results = self._db.search_knowledge(self._channel, self._chat_id, embedding, limit=5)
                
                if not results:
                    return f"No semantic knowledge found for query: '{query}'"
                
                output = ["Semantic Search Results:"]
                for i, r in enumerate(results, 1):
                    tag = r["metadata"].get("tag")
                    tag_str = f" [{tag}]" if tag else ""
                    output.append(f"{i}.{tag_str} {r['content']}")
                
                return "\n\n".join(output)
            except Exception as e:
                logger.error("Failed to search knowledge: {}", e)
                return f"Error searching knowledge: {str(e)}"

        if action == "list":
             # We reuse search with a zero vector or just fetch recent if we had a list method
             # For now, let's keep it simple and suggest searching.
             return "To see what I know, please use the 'search' action with a topic."

        return f"Error: Unknown action '{action}'."
