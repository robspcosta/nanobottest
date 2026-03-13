"""Extra utility tools for weather, finance, and system status."""

import os
import httpx
from typing import Any
from nanobot.agent.tools.base import Tool
from loguru import logger

class SystemStatusTool(Tool):
    """Tool to check the health of Nanobot services (Ollama, Whisper, DB)."""

    @property
    def name(self) -> str:
        return "system_status"

    @property
    def description(self) -> str:
        return "Check the health and connectivity of the Nanobot services (LLM, Transcription, Database)."

    @property
    def parameters(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}}

    async def execute(self, **kwargs: Any) -> str:
        ollama_url = os.environ.get("NANOBOT_PROVIDERS__CUSTOM__API_BASE", "Not set")
        whisper_url = os.environ.get("WHISPER_API_URL", "Not set")
        db_url = os.environ.get("NANOBOT_DATABASE_URL", "Not set")

        results = ["🖥️ **Nanobot System Status**"]

        # Check Ollama
        try:
            async with httpx.AsyncClient() as client:
                r = await client.get(f"{ollama_url.replace('/v1', '')}/api/tags", timeout=5.0)
                if r.status_code == 200:
                    results.append("✅ **LLM (Ollama)**: Online")
                else:
                    results.append(f"⚠️ **LLM (Ollama)**: Status {r.status_code}")
        except Exception as e:
            results.append(f"❌ **LLM (Ollama)**: Offline ({str(e)})")

        # Check Whisper
        try:
            async with httpx.AsyncClient() as client:
                # Try health or just the root
                r = await client.get(whisper_url.split("/transcribe")[0] + "/health", timeout=5.0)
                if r.status_code == 200:
                    results.append("✅ **Transcription (Whisper)**: Online")
                else:
                    # Fallback to checking the transcribe endpoint with GET (should 405 or 404 but respond)
                    r = await client.get(whisper_url, timeout=5.0)
                    results.append(f"✅ **Transcription (Whisper)**: Responding (Status {r.status_code})")
        except Exception as e:
            results.append(f"❌ **Transcription (Whisper)**: Offline ({str(e)})")

        # Check Database
        if "postgresql" in db_url:
            results.append("✅ **Database (PostgreSQL)**: Configured")
        else:
            results.append("⚠️ **Database**: Using SQLite or Not configured")

        return "\n".join(results)

class WeatherTool(Tool):
    """Tool to check weather using wttr.in."""

    @property
    def name(self) -> str:
        return "get_weather"

    @property
    def description(self) -> str:
        return "Check the current weather for a specific city."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "city": {"type": "string", "description": "Name of the city (e.g., 'Sao Paulo')"}
            },
            "required": ["city"]
        }

    async def execute(self, city: str, **kwargs: Any) -> str:
        try:
            async with httpx.AsyncClient() as client:
                # Use wttr.in with format for plain text
                r = await client.get(f"https://wttr.in/{city}?format=%C+%t+&lang=pt", timeout=10.0)
                if r.status_code == 200:
                    return f"Previsão para {city}: {r.text.strip()}"
                return f"Não consegui obter o clima para '{city}'."
        except Exception as e:
            return f"Erro ao buscar clima: {str(e)}"

class FinanceTool(Tool):
    """Tool to check currency rates."""

    @property
    def name(self) -> str:
        return "get_finance"

    @property
    def description(self) -> str:
        return "Check currency exchange rates (USD, EUR, BTC) to BRL."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "symbols": {"type": "string", "description": "Comma separated symbols, e.g. 'USD-BRL,EUR-BRL,BTC-BRL'"}
            }
        }

    async def execute(self, symbols: str = "USD-BRL,EUR-BRL,BTC-BRL", **kwargs: Any) -> str:
        try:
            async with httpx.AsyncClient() as client:
                r = await client.get(f"https://economia.awesomeapi.com.br/last/{symbols}", timeout=10.0)
                r.raise_for_status()
                data = r.json()
                
                lines = ["💹 **Cotações Financeiras**"]
                for key, val in data.items():
                    name = val.get('name', key)
                    bid = val.get('bid', 'N/A')
                    lines.append(f"- **{name}**: R$ {bid}")
                return "\n".join(lines)
        except Exception as e:
            return f"Erro ao buscar cotações: {str(e)}"

class NewsTool(Tool):
    """Tool to fetch top news using G1 RSS."""

    @property
    def name(self) -> str:
        return "get_news"

    @property
    def description(self) -> str:
        return "Fetch the latest top news from Brazil."

    @property
    def parameters(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}}

    async def execute(self, **kwargs: Any) -> str:
        try:
            async with httpx.AsyncClient() as client:
                r = await client.get("https://g1.globo.com/index/feed/pagina-1.ghtml", timeout=10.0)
                r.raise_for_status()
                content = r.text
                import re
                titles = re.findall(r'<title><!\[CDATA\[(.*?)\]\]></title>', content)
                links = re.findall(r'<link>(.*?)</link>', content)
                if not titles:
                    return "Não encontrei notícias recentes no momento."
                lines = ["📰 **Últimas Notícias (G1)**"]
                for i, (t, l) in enumerate(zip(titles[1:6], links[1:6]), 1):
                    lines.append(f"{i}. {t}\n   🔗 {l}")
                return "\n".join(lines)
        except Exception as e:
            return f"Erro ao buscar notícias: {str(e)}"
