"""Tool for managing personal contacts."""

from typing import Any
from loguru import logger
from nanobot.agent.tools.base import Tool

class ContactTool(Tool):
    """
    Tool for managing personal contacts for messaging.
    Each user can save their own contacts (name -> platform ID).
    """

    def __init__(self, db: Any = None):
        self.db = db
        self.channel = None
        self.chat_id = None

    def set_context(self, channel: str, chat_id: str) -> None:
        self.channel = channel
        self.chat_id = chat_id

    @property
    def name(self) -> str:
        return "manage_contacts"

    @property
    def description(self) -> str:
        return (
            "Save, search, or list personal contacts. "
            "Allows looking up platform IDs (phone numbers or usernames) by name for messaging. "
            "Actions: 'save' (requires name, platform, external_id), 'search' (requires name), 'list'."
        )

    async def run(self, action: str, name: str | None = None, platform: str | None = None, external_id: str | None = None) -> str:
        if not self.db:
            return "Error: Database not configured."
        if not self.channel or not self.chat_id:
            return "Error: User context not set."

        if action == "save":
            if not name or not platform or not external_id:
                return "Error: Missing name, platform, or external_id for 'save' action."
            # Normalize platform
            platform = platform.lower()
            if platform not in ("whatsapp", "telegram"):
                 return f"Error: Unsupported platform '{platform}'. Use 'whatsapp' or 'telegram'."
            
            self.db.save_contact(self.channel, self.chat_id, name, platform, external_id)
            return f"Contact '{name}' saved successfully for {platform} ({external_id})."

        elif action == "search":
            if not name:
                return "Error: Missing name for 'search' action."
            contact = self.db.get_contact(self.channel, self.chat_id, name)
            if contact:
                return f"Contact found: {contact['name']} ({contact['platform']}: {contact['external_id']})"
            return f"Contact '{name}' not found."

        elif action == "list":
            contacts = self.db.list_contacts(self.channel, self.chat_id)
            if not contacts:
                return "You have no saved contacts."
            lines = [f"- {c['name']}: {c['platform']} ({c['external_id']})" for c in contacts]
            return "Your contacts:\n" + "\n".join(lines)

        return f"Unknown action: {action}"
