import os
import json
import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

# Путь к конфигу приложений
APPS_CONFIG_PATH = Path(__file__).parent.parent / "apps.json"


def _load_apps_config() -> dict:
    """Загрузить конфиг приложений."""
    if not APPS_CONFIG_PATH.exists():
        logger.warning(f"apps.json не найден: {APPS_CONFIG_PATH}")
        return {"apps": [], "default_save_folder": "", "blocked_apps": []}
    
    with open(APPS_CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _resolve_path(path: str) -> str:
    """Разрешить переменные окружения в пути."""
    if "%USERNAME%" in path:
        path = path.replace("%USERNAME%", os.environ.get("USERNAME", ""))
    return path


def _find_app(name: str) -> str | None:
    """Найти приложение по имени или алиасу."""
    config = _load_apps_config()
    name_lower = name.lower().strip()
    
    for app in config.get("apps", []):
        # Проверяем основное имя
        if app["name"].lower() == name_lower:
            return _resolve_path(app["path"])
        
        # Проверяем алиасы
        for alias in app.get("aliases", []):
            if alias.lower() == name_lower:
                return _resolve_path(app["path"])
    
    # Попробуем найти как exe в PATH
    for ext in ["", ".exe", ".cmd", ".bat"]:
        if name_lower.endswith(ext) or True:
            try:
                result = subprocess.run(
                    ["where", name_lower + ext],
                    capture_output=True, text=True, timeout=5
                )
                if result.returncode == 0 and result.stdout.strip():
                    return result.stdout.strip().split("\n")[0]
            except Exception:
                pass
    
    return None


# === Tool Definitions ===

FILE_CREATE_DEFINITION = {
    "type": "function",
    "function": {
        "name": "file_create",
        "description": "Создать файл с указанным содержимым. "
                       "Используй когда пользователь просит создать/написать файл.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Путь к файлу (например: notes.txt, C:\\docs\\file.txt)"
                },
                "content": {
                    "type": "string",
                    "description": "Содержимое файла"
                }
            },
            "required": ["path", "content"]
        }
    }
}

APP_OPEN_DEFINITION = {
    "type": "function",
    "function": {
        "name": "app_open",
        "description": "Открыть/запустить приложение на компьютере. "
                       "Используй когда пользователь просит открыть/запустить какое-то приложение.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Название приложения (например: notepad, telegram, chrome)"
                }
            },
            "required": ["name"]
        }
    }
}

FILE_OPEN_DEFINITION = {
    "type": "function",
    "function": {
        "name": "file_open",
        "description": "Открыть файл ассоциированным приложением. "
                       "Используй когда пользователь просит открыть конкретный файл.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Путь к файлу"
                }
            },
            "required": ["path"]
        }
    }
}

BROWSER_OPEN_DEFINITION = {
    "type": "function",
    "function": {
        "name": "browser_open",
        "description": "Открыть сайт/URL в браузере. "
                       "Используй когда пользователь просит открыть веб-сайт, страницу, ссылку.",
        "parameters": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "URL или название сайта (например: youtube.com, github.com)"
                }
            },
            "required": ["url"]
        }
    }
}


# === Tool Implementations ===

async def file_create(path: str, content: str) -> str:
    """Создать файл с содержимым."""
    try:
        # Если путь не абсолютный — используем default папку
        if not os.path.isabs(path):
            config = _load_apps_config()
            default_folder = _resolve_path(config.get("default_save_folder", ""))
            if not default_folder:
                default_folder = os.path.join(os.path.expanduser("~"), "Documents")
            path = os.path.join(default_folder, path)
        
        # Создаём директории если нужно
        os.makedirs(os.path.dirname(path), exist_ok=True)
        
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        
        logger.info(f"Файл создан: {path}")
        return f"Файл создан: {path} ({len(content)} символов)"
    
    except Exception as e:
        logger.error(f"Ошибка создания файла: {e}")
        return f"Ошибка: {e}"


async def app_open(name: str) -> str:
    """Открыть приложение или сайт."""
    config = _load_apps_config()
    
    # Проверяем заблокированные
    blocked = [b.lower() for b in config.get("blocked_apps", [])]
    if name.lower() in blocked:
        return f"Приложение '{name}' заблокировано в конфигурации"
    
    app_path = _find_app(name)
    
    if app_path:
        try:
            if os.path.isabs(app_path) and os.path.exists(app_path):
                if os.path.isdir(app_path) or app_path.lower().endswith(".lnk"):
                    os.startfile(app_path)
                else:
                    subprocess.Popen([app_path], cwd=os.path.dirname(app_path))
            else:
                subprocess.Popen([app_path], shell=True)
            
            logger.info(f"Приложение запущено: {name} ({app_path})")
            return f"Открыто: {name}"
        except Exception as e:
            logger.error(f"Ошибка запуска {name}: {e}")
            return f"Ошибка запуска {name}: {e}"
    
    # Если приложение не найдено — открываем как сайт
    logger.info(f"Приложение не найдено, открываю как сайт: {name}")
    return await browser_open(name)


async def file_open(path: str) -> str:
    """Открыть файл ассоциированным приложением."""
    try:
        if not os.path.exists(path):
            return f"Файл не найден: {path}"
        
        os.startfile(path)
        logger.info(f"Файл открыт: {path}")
        return f"Файл открыт: {path}"
    
    except Exception as e:
        logger.error(f"Ошибка открытия файла: {e}")
        return f"Ошибка: {e}"


async def browser_open(url: str) -> str:
    """Открыть сайт в браузере."""
    # Добавляем https:// если нет протокола
    if not url.startswith("http://") and not url.startswith("https://"):
        if "." not in url:
            url = url + ".com"
        url = "https://" + url

    config = _load_apps_config()
    browser_name = config.get("default_browser", "")

    if browser_name:
        browser_path = _find_app(browser_name)
        if browser_path and os.path.exists(browser_path):
            subprocess.Popen([browser_path, url])
            logger.info(f"Сайт открыт в {browser_name}: {url}")
            return f"Открыт сайт: {url}"

    os.startfile(url)
    logger.info(f"Сайт открыт в браузере по умолчанию: {url}")
    return f"Открыт сайт: {url}"
