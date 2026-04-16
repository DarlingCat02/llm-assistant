"""
Background tasks for the assistant.
"""
import asyncio
import logging

import httpx

logger = logging.getLogger(__name__)


class KeepAliveTask:
    """Background task to keep Ollama model loaded in memory."""
    
    def __init__(self, ollama_url: str = "http://localhost:11434", interval: int = 60):
        self.ollama_url = ollama_url
        self.interval = interval
        self._task: asyncio.Task | None = None
        self._running = False
    
    async def start(self) -> None:
        """Start the keep-alive background task."""
        if self._running:
            return
        
        self._running = True
        self._task = asyncio.create_task(self._run())
        logger.info(f"Ollama keep-alive started (interval: {self.interval}s)")
    
    async def stop(self) -> None:
        """Stop the keep-alive background task."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Ollama keep-alive stopped")
    
    async def _run(self) -> None:
        """Background loop to ping Ollama."""
        async with httpx.AsyncClient(timeout=5.0) as client:
            while self._running:
                try:
                    response = await client.get(f"{self.ollama_url}/api/tags")
                    if response.status_code == 200:
                        logger.debug("Ollama keep-alive ping OK")
                    await asyncio.sleep(self.interval)
                except httpx.ConnectError:
                    logger.debug("Ollama not running, skipping keep-alive")
                    await asyncio.sleep(5)  # Retry sooner if Ollama is down
                except Exception as e:
                    logger.warning(f"Keep-alive error: {e}")
                    await asyncio.sleep(5)


# Global instance
_ollama_keep_alive: KeepAliveTask | None = None


def get_keep_alive() -> KeepAliveTask:
    """Get the global keep-alive instance."""
    global _ollama_keep_alive
    if _ollama_keep_alive is None:
        _ollama_keep_alive = KeepAliveTask()
    return _ollama_keep_alive


async def start_ollama_keep_alive(interval: int = 60) -> None:
    """Start Ollama keep-alive background task."""
    task = get_keep_alive()
    await task.start()


async def stop_ollama_keep_alive() -> None:
    """Stop Ollama keep-alive background task."""
    task = get_keep_alive()
    await task.stop()