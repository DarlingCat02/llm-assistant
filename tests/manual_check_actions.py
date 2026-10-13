"""Manual end-to-end check: real LLM + tools -> actions reported."""
import asyncio
import sys

sys.path.insert(0, ".")

from config import get_config
from src.main import Assistant


async def main():
    a = Assistant(get_config())
    await a.initialize()
    print("model:", a._config.llm.model)
    try:
        r = await a.process_message("Открой блокнот и напиши в ответ какое сегодня число")
        print("---")
        print("response:", (r.content or "")[:200])
        print("actions:", r.actions)
        for act in r.actions:
            print(f"  - {act.name} args={act.arguments} ok={act.ok} preview={act.result_preview[:60]!r}")
    finally:
        await a.close()


asyncio.run(main())