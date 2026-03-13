"""Tool for managing authorized users."""

from typing import Any
from loguru import logger
from nanobot.agent.tools.base import Tool

class UserTool(Tool):
    """
    Tool for managing authorized users.
    Allows admins to see, add or remove people who can use the bot.
    """

    def __init__(self, db: Any = None):
        self.db = db
        self.channel: str | None = None
        self.chat_id: str | None = None

    def set_context(self, channel: str, chat_id: str) -> None:
        self.channel = channel
        self.chat_id = chat_id

    @property
    def name(self) -> str:
        return "manage_access"

    @property
    def description(self) -> str:
        return (
            "List, authorize, or revoke access for users. "
            "Authorized users can interact with the bot. "
            "Actions: 'list', 'authorize' (requires platform and external_id), 'revoke' (requires platform and external_id)."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["list", "authorize", "revoke"],
                    "description": "The action to perform.",
                },
                "platform": {
                    "type": "string",
                    "enum": ["whatsapp", "telegram"],
                    "description": "The platform (whatsapp or telegram).",
                },
                "external_id": {
                    "type": "string",
                    "description": "The phone number (digits only for WhatsApp) or username/ID (Telegram).",
                },
            },
            "required": ["action"],
        }

    async def execute(self, **kwargs: Any) -> str:
        action = kwargs.get("action")
        platform = kwargs.get("platform")
        external_id = kwargs.get("external_id")

        if not self.db:
            return "Error: Database not configured."
        
        # Security: Only admins should manage users. 
        # (In local mode, the first user is auto-promoted to admin in loop.py)
        
        if action == "list":
            users = self.db.list_users()
            if not users:
                return "No users registered in the database."
            lines = [f"- {u['platform']}:{u['external_id']} (Role: {u['role']}, Active: {u['is_active']})" for u in users]
            return "Authorized users:\n" + "\n".join(lines)

        if action == "authorize":
            if not platform or not external_id:
                return "Error: Missing platform or external_id."
            
            # Check if user already exists
            if self.db.add_user(platform, external_id, role="user"):
                return f"User {external_id} on {platform} authorized successfully."
            else:
                # If exists but inactive, reactivate
                with self.db.SessionLocal() as session:
                    from nanobot.db.manager import User
                    from sqlalchemy import select
                    norm_id = self.db._normalize_id(platform, external_id)
                    db_id = f"{platform}:{norm_id}"
                    stmt = select(User).where(User.id == db_id)
                    user = session.execute(stmt).scalar_one_or_none()
                    if user:
                        user.is_active = True
                        session.commit()
                        return f"Access reactivated for {external_id} on {platform}."
                return f"User {external_id} is already authorized."

        if action == "revoke":
            if not platform or not external_id:
                return "Error: Missing platform or external_id."
            if self.db.remove_user(platform, external_id):
                return f"Access revoked for {external_id} on {platform}."
            return f"User {external_id} not found."

        return f"Unknown action: {action}"
