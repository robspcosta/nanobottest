"""Tool for advanced audio intelligence: summarization and action items."""

from typing import Any
from nanobot.agent.tools.base import Tool

class AudioTool(Tool):
    """
    Tool for analyzing transcriptions (usually from voice messages).
    Generates structured summaries, identifies decisions, and suggests tasks.
    """

    @property
    def name(self) -> str:
        return "analyze_audio"

    @property
    def description(self) -> str:
        return (
            "Analyze a transcription from an audio/voice message. "
            "It generates a structured summary in bullet points, identifies key decisions made, "
            "and suggests actionable tasks to be added to the task list."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "transcription": {
                    "type": "string",
                    "description": "The full text of the audio transcription to analyze.",
                },
                "focus": {
                    "type": "string",
                    "description": "Optional focus for the analysis (e.g., 'focus on financial decisions').",
                }
            },
            "required": ["transcription"],
        }

    async def execute(self, transcription: str, focus: str | None = None, **kwargs: Any) -> str:
        if len(transcription) < 50:
             return "This audio message seems too short for a deep analysis. I'll just treat it as a normal message."
        
        # We don't need a separate LLM call here because the Agent itself is an LLM.
        # By calling this tool, the Agent is instructing itself (or a subagent) 
        # to format its internal processing in a specific way.
        # However, to give a 'wow' effect, we can return a template for the Agent to fill.
        
        prompt = (
            "Please perform a deep analysis of the following transcription. "
            f"{f'Focus especially on: {focus}.' if focus else ''}\n\n"
            "STRUCTURE YOUR RESPONSE EXACTLY AS FOLLOWS:\n"
            "1. 📝 **Resumo Executivo**: (A brief 2-3 sentence summary)\n"
            "2. 📍 **Pontos Chave**: (Bullet points of main topics)\n"
            "3. ⚖️ **Decisões Tomadas**: (List of what was decided)\n"
            "4. ✅ **Tarefas Identificadas**: (List of items that should be added to the task list)\n\n"
            f"TRANSCRIPTION:\n{transcription}"
        )
        
        return prompt # The agent will see this and act on it.
