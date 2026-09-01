import asyncio
import logging

logger = logging.getLogger(__name__)

DDG_TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": "web_search_ddg",
        "description": "Поиск информации в интернете через DuckDuckGo. "
                       "Используй когда нужны актуальные данные, новости, "
                       "факты или информация, которой нет в твоей памяти.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Поисковый запрос (на русском или английском)"
                }
            },
            "required": ["query"]
        }
    }
}

DDG_TOOL_DEFINITION_EN = {
    "type": "function",
    "function": {
        "name": "web_search_ddg",
        "description": "Search information on the internet via DuckDuckGo. "
                       "Use when you need current data, news, "
                       "facts or information not in your memory.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query (in English or Russian)"
                }
            },
            "required": ["query"]
        }
    }
}

def get_ddg_tool_definition(lang: str = "en") -> dict:
    """Return DuckDuckGo tool definition translated for given language."""
    lang = lang if lang in ("en", "ru") else "en"
    return DDG_TOOL_DEFINITION if lang == "ru" else DDG_TOOL_DEFINITION_EN


class DuckDuckGoSearchTool:
    def __init__(self):
        self._initialized = False

    async def initialize(self):
        if self._initialized:
            return
        try:
            from ddgs import DDGS
            self._ddgs = DDGS()
            self._initialized = True
            logger.info("WebSearchTool initialized (DuckDuckGo)")
        except ImportError:
            logger.warning("duckduckgo_search not installed. Install: pip install duckduckgo-search")
            raise

    async def search(self, query: str, max_results: int = 5) -> str:
        if not self._initialized:
            await self.initialize()

        loop = asyncio.get_event_loop()

        def _do_search():
            results = []
            try:
                results = list(self._ddgs.text(query, max_results=max_results))
            except Exception:
                pass
            return results

        try:
            results = await loop.run_in_executor(None, _do_search)
        except Exception as e:
            logger.error(f"Search error: {e}")
            results = []

        if not results:
            # Fallback: прямой HTTP-запрос к DuckDuckGo HTML
            try:
                import httpx
                resp = await httpx.AsyncClient().post(
                    "https://html.duckduckgo.com/html/",
                    data={"q": query},
                    timeout=15,
                )
                import re
                links = re.findall(r'class="result__a"[^>]*href="([^"]*)"[^>]*>(.*?)</a>', resp.text)
                snippets = re.findall(r'class="result__snippet"[^>]*>(.*?)</td>', resp.text, re.DOTALL)
                results = []
                for i, (url, title) in enumerate(links[:max_results]):
                    title = re.sub(r'<[^>]+>', '', title).strip()
                    snippet = re.sub(r'<[^>]+>', '', snippets[i] if i < len(snippets) else '').strip()
                    results.append({"title": title, "href": url, "body": snippet})
            except Exception as e2:
                logger.error(f"Fallback search also failed: {e2}")
                return "[Поиск не дал результатов]"

        if not results:
            return "[Поиск не дал результатов]"

        formatted = []
        for i, r in enumerate(results, 1):
            if not isinstance(r, dict):
                continue
            title = r.get("title", "")
            href = r.get("href", "")
            body = r.get("body", "")
            formatted.append(f"{i}. {title}\n   {href}\n   {body}")

        return "\n\n".join(formatted) if formatted else "[Поиск не дал результатов]"

    async def close(self):
        self._initialized = False
