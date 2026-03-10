"""Tool for managing tasks and lists."""

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from nanobot.agent.tools.base import Tool


class TaskTool(Tool):
    """
    Tool for managing tasks, lists, and dates.
    Tasks are stored persistently in the workspace.
    """

    def __init__(self, workspace: Path):
        self.workspace = workspace
        self.tasks_file = self.workspace / "tasks.json"
        self.md_file = self.workspace / "TASKS.md"

    @property
    def name(self) -> str:
        return "manage_tasks"

    @property
    def description(self) -> str:
        return (
            "Add, list, update, or delete tasks and managed lists. "
            "Use this for 'to-do' items, reminders, and general task management."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["add", "list", "complete", "delete", "update"],
                    "description": "The action to perform.",
                },
                "title": {
                    "type": "string",
                    "description": "Task title (required for 'add' and 'update').",
                },
                "id": {
                    "type": "integer",
                    "description": "Task ID (required for 'complete', 'delete', and 'update').",
                },
                "due_date": {
                    "type": "string",
                    "description": "Optional due date (YYYY-MM-DD).",
                },
                "priority": {
                    "type": "string",
                    "enum": ["low", "medium", "high"],
                    "description": "Optional priority level.",
                },
                "status": {
                    "type": "string",
                    "enum": ["pending", "completed"],
                    "description": "Filter for 'list' action or new status for 'update'.",
                },
            },
            "required": ["action"],
        }

    def _load_tasks(self) -> list[dict[str, Any]]:
        if not self.tasks_file.exists():
            return []
        try:
            with open(self.tasks_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []

    def _save_tasks(self, tasks: list[dict[str, Any]]) -> None:
        self.tasks_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.tasks_file, "w", encoding="utf-8") as f:
            json.dump(tasks, f, ensure_ascii=False, indent=2)
        self._update_md(tasks)

    def _update_md(self, tasks: list[dict[str, Any]]) -> None:
        """Update a human-readable TASKS.md file."""
        lines = ["# 📋 Task List\n"]
        
        pending = [t for t in tasks if t["status"] == "pending"]
        completed = [t for t in tasks if t["status"] == "completed"]

        lines.append("## ⏳ Pending Tasks")
        if not pending:
            lines.append("_No pending tasks._")
        for t in sorted(pending, key=lambda x: (x.get("priority") != "high", x.get("due_date") or "9999-99-99")):
            due = f" (Due: {t['due_date']})" if t.get("due_date") else ""
            prio = f" [{t['priority'].upper()}]" if t.get("priority") else ""
            lines.append(f"- [{t['id']}] {t['title']}{due}{prio}")

        lines.append("\n## ✅ Completed Tasks")
        if not completed:
            lines.append("_No completed tasks._")
        for t in completed[-10:]:  # Show last 10
            lines.append(f"- ~~[{t['id']}] {t['title']}~~")

        with open(self.md_file, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

    async def execute(self, **kwargs: Any) -> str:
        action = kwargs.get("action")
        tasks = self._load_tasks()

        if action == "add":
            title = kwargs.get("title")
            if not title:
                return "Error: Title is required for 'add' action."
            
            new_id = max([t["id"] for t in tasks] + [0]) + 1
            task = {
                "id": new_id,
                "title": title,
                "status": "pending",
                "due_date": kwargs.get("due_date"),
                "priority": kwargs.get("priority") or "medium",
                "created_at": datetime.now().isoformat(),
            }
            tasks.append(task)
            self._save_tasks(tasks)
            return f"Task added with ID {new_id}: '{title}'"

        if action == "list":
            status_filter = kwargs.get("status")
            filtered = tasks
            if status_filter:
                filtered = [t for t in tasks if t["status"] == status_filter]
            
            if not filtered:
                return "No tasks found."
            
            result = ["Current Tasks:"]
            for t in filtered:
                status_icon = "✅" if t["status"] == "completed" else "⏳"
                due = f" | Due: {t['due_date']}" if t.get("due_date") else ""
                prio = f" | Priority: {t['priority']}" if t.get("priority") else ""
                result.append(f"[{t['id']}] {status_icon} {t['title']}{due}{prio}")
            
            return "\n".join(result)

        if action == "complete":
            task_id = kwargs.get("id")
            for t in tasks:
                if t["id"] == task_id:
                    t["status"] = "completed"
                    t["completed_at"] = datetime.now().isoformat()
                    self._save_tasks(tasks)
                    return f"Task {task_id} marked as completed."
            return f"Error: Task with ID {task_id} not found."

        if action == "delete":
            task_id = kwargs.get("id")
            new_tasks = [t for t in tasks if t["id"] != task_id]
            if len(new_tasks) == len(tasks):
                return f"Error: Task with ID {task_id} not found."
            self._save_tasks(new_tasks)
            return f"Task {task_id} deleted."

        if action == "update":
            task_id = kwargs.get("id")
            if not task_id:
                return "Error: ID is required for 'update' action."
            
            for t in tasks:
                if t["id"] == task_id:
                    if "title" in kwargs: t["title"] = kwargs["title"]
                    if "due_date" in kwargs: t["due_date"] = kwargs["due_date"]
                    if "priority" in kwargs: t["priority"] = kwargs["priority"]
                    if "status" in kwargs: t["status"] = kwargs["status"]
                    self._save_tasks(tasks)
                    return f"Task {task_id} updated."
            return f"Error: Task with ID {task_id} not found."

        return f"Error: Unknown action '{action}'."
