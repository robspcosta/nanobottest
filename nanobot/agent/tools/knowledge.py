"""Tool for managing a persistent knowledge base (RAG)."""

import os
from pathlib import Path
from typing import Any

from nanobot.agent.tools.base import Tool
from nanobot.utils.helpers import ensure_dir


class KnowledgeTool(Tool):
    """
    Tool for managing a persistent knowledge base.
    Allows storing snippets of information and searching through them.
    """

    def __init__(self, workspace: Path):
        self.workspace = workspace
        self.knowledge_dir = ensure_dir(self.workspace / "knowledge")

    @property
    def name(self) -> str:
        return "manage_knowledge"

    @property
    def description(self) -> str:
        return (
            "Save important information to the long-term knowledge base or search through it. "
            "Use this when the user asks to 'remember', 'save', or 'store' information for later. "
            "Supported actions: store, search, list, read."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["store", "search", "list", "read"],
                    "description": "The action to perform.",
                },
                "title": {
                    "type": "string",
                    "description": "Title/filename for the knowledge entry (for 'store' and 'read').",
                },
                "content": {
                    "type": "string",
                    "description": "The information to save (for 'store').",
                },
                "query": {
                    "type": "string",
                    "description": "Search query to find relevant knowledge (for 'search').",
                },
            },
            "required": ["action"],
        }

    async def execute(self, **kwargs: Any) -> str:
        action = kwargs.get("action")

        if action == "store":
            title = kwargs.get("title")
            content = kwargs.get("content")
            if not title or not content:
                return "Error: Title and content are required for 'store' action."
            
            # Sanitize filename
            filename = "".join(c for c in title if c.isalnum() or c in (" ", "-", "_")).strip()
            filename = filename.replace(" ", "_") + ".md"
            file_path = self.knowledge_dir / filename
            
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(f"# {title}\n\n{content}\n")
            
            return f"Knowledge saved successfully to '{filename}'."

        if action == "list":
            files = list(self.knowledge_dir.glob("*.md"))
            if not files:
                return "The knowledge base is currently empty."
            
            result = ["Stored Knowledge:"]
            for f in files:
                result.append(f"- {f.stem.replace('_', ' ')}")
            return "\n".join(result)

        if action == "read":
            title = kwargs.get("title")
            if not title:
                return "Error: Title is required for 'read' action."
            
            filename = title.replace(" ", "_") + ".md"
            file_path = self.knowledge_dir / filename
            
            if not file_path.exists():
                return f"Error: Knowledge entry '{title}' not found."
            
            return file_path.read_text(encoding="utf-8")

        if action == "search":
            query = kwargs.get("query")
            if not query:
                return "Error: Query is required for 'search' action."
            
            query = query.lower()
            results = []
            
            for file_path in self.knowledge_dir.glob("*.md"):
                content = file_path.read_text(encoding="utf-8")
                if query in content.lower() or query in file_path.stem.lower():
                    # Extract a snippet
                    idx = content.lower().find(query)
                    start = max(0, idx - 50)
                    end = min(len(content), idx + 150)
                    snippet = "..." + content[start:end].replace("\n", " ") + "..."
                    results.append(f"### {file_path.stem.replace('_', ' ')}\n{snippet}\n")
            
            if not results:
                return f"No knowledge found for query: '{query}'"
            
            return "Search Results:\n\n" + "\n".join(results)

        return f"Error: Unknown action '{action}'."
