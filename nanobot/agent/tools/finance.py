"""Tool for tracking finances: income and expenses."""

import json
from typing import Any
from nanobot.agent.tools.base import Tool
from nanobot.db.manager import DatabaseManager

class FinanceTrackerTool(Tool):
    """
    Tool for managing personal finances.
    Users can log expenses, income, and see their balance.
    """

    def __init__(self, db: DatabaseManager):
        self.db = db
        self.channel = None
        self.chat_id = None

    def set_context(self, channel: str, chat_id: str) -> None:
        self.channel = channel
        self.chat_id = chat_id

    @property
    def name(self) -> str:
        return "manage_finances"

    @property
    def description(self) -> str:
        return (
            "Log income, expenses, and check financial summaries. "
            "Use this for personal expense tracking."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["add", "summary", "list"],
                    "description": "The action: 'add' to log a transaction, 'summary' for totals, 'list' for recent records."
                },
                "type": {
                    "type": "string",
                    "enum": ["income", "expense"],
                    "description": "Type of transaction (required for 'add')."
                },
                "amount": {
                    "type": "number",
                    "description": "Amount in currency (e.g., 50.00)."
                },
                "category": {
                    "type": "string",
                    "description": "Category (e.g., 'Food', 'Salary', 'Rent')."
                },
                "description": {
                    "type": "string",
                    "description": "Optional description."
                }
            },
            "required": ["action"]
        }

    async def execute(self, action: str, **kwargs: Any) -> str:
        if not self.channel or not self.chat_id:
            return "Error: User context not set."

        if action == "add":
            amount = kwargs.get("amount")
            t_type = kwargs.get("type")
            category = kwargs.get("category", "General")
            desc = kwargs.get("description", "")

            if amount is None or t_type is None:
                return "Error: Amount and type are required to add a record."

            # Convert to cents for storage if needed, but we used amount = Column(Integer)
            # Let's just store as amount * 100 to avoid floats
            stored_amount = int(float(amount) * 100)
            
            if self.db.add_finance_record(self.channel, self.chat_id, stored_amount, t_type, category, desc):
                return f"✅ Record added: {t_type.capitalize()} of R$ {float(amount):.2f} in '{category}'."
            return "❌ Failed to add record."

        elif action == "summary":
            summary = self.db.get_finance_summary(self.channel, self.chat_id)
            return (
                f"💰 **Resumo Financeiro**\n"
                f"- **Total Receitas**: R$ {summary['total_income']/100:.2f}\n"
                f"- **Total Despesas**: R$ {summary['total_expense']/100:.2f}\n"
                f"--- \n"
                f"💵 **Saldo Atual**: R$ {summary['balance']/100:.2f}"
            )

        return f"Unknown action: {action}"
