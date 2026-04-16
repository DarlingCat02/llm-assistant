"""
База данных для хранения чатов.

Использует SQLite для хранения:
- Списка чатов (sessions)
- Сообщений в каждом чате
- Метаданных (время создания, последнее сообщение)

Архитектурные решения:
1. Отдельная БД для чатов (независимо от ChromaDB)
2. Асинхронный доступ через aiosqlite
3. Подготовка к масштабированию (легко заменить на PostgreSQL)
"""

import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional
from dataclasses import dataclass

import aiosqlite


logger = logging.getLogger(__name__)


@dataclass
class Chat:
    """Модель чата."""
    id: int
    title: str
    created_at: datetime
    updated_at: datetime
    
    @classmethod
    def from_row(cls, row: tuple) -> "Chat":
        return cls(
            id=row[0],
            title=row[1],
            created_at=datetime.fromisoformat(row[2]),
            updated_at=datetime.fromisoformat(row[3]),
        )


@dataclass
class Message:
    """Модель сообщения в чате."""
    id: int
    chat_id: int
    role: str  # 'user' или 'assistant'
    content: str
    created_at: datetime
    
    @classmethod
    def from_row(cls, row: tuple) -> "Message":
        return cls(
            id=row[0],
            chat_id=row[1],
            role=row[2],
            content=row[3],
            created_at=datetime.fromisoformat(row[4]),
        )


class ChatDatabase:
    """
    Менеджер базы данных чатов.
    
    Пример использования:
        db = ChatDatabase("./storage/chats.db")
        await db.initialize()
        
        # Создать чат
        chat_id = await db.create_chat("Новый чат")
        
        # Добавить сообщение
        await db.add_message(chat_id, "user", "Привет!")
        await db.add_message(chat_id, "assistant", "Здравствуйте!")
        
        # Получить историю
        messages = await db.get_chat_history(chat_id)
    """
    
    def __init__(self, db_path: str):
        """
        Инициализировать базу данных.
        
        Args:
            db_path: Путь к файлу базы данных.
        """
        self._db_path = Path(db_path)
        self._db: Optional[aiosqlite.Connection] = None
    
    async def initialize(self) -> None:
        """
        Инициализировать соединение и создать таблицы.
        """
        # Создаём директорию если не существует
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Подключаемся к БД
        self._db = await aiosqlite.connect(str(self._db_path))
        self._db.row_factory = aiosqlite.Row
        
        # Создаём таблицы
        await self._create_tables()
        
        logger.info(f"База данных чатов инициализирована: {self._db_path}")
    
    async def _create_tables(self) -> None:
        """Создать таблицы если не существуют."""
        if not self._db:
            raise RuntimeError("База данных не инициализирована")
        
        # Таблица чатов
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS chats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        
        # Таблица сообщений
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (chat_id) REFERENCES chats(id) ON DELETE CASCADE
            )
        """)
        
        # Индексы для ускорения поиска
        await self._db.execute("""
            CREATE INDEX IF NOT EXISTS idx_messages_chat_id 
            ON messages(chat_id)
        """)
        
        await self._db.execute("""
            CREATE INDEX IF NOT EXISTS idx_messages_created 
            ON messages(created_at)
        """)
        
        await self._db.commit()
    
    async def close(self) -> None:
        """Закрыть соединение с БД."""
        if self._db:
            await self._db.close()
            self._db = None
            logger.info("База данных чатов закрыта")
    
    # === CRUD для чатов ===
    
    async def create_chat(self, title: str = "Новый чат") -> int:
        """
        Создать новый чат.
        
        Args:
            title: Заголовок чата.
        
        Returns:
            int: ID созданного чата.
        """
        if not self._db:
            raise RuntimeError("База данных не инициализирована")
        
        now = datetime.now().isoformat()
        
        cursor = await self._db.execute(
            "INSERT INTO chats (title, created_at, updated_at) VALUES (?, ?, ?)",
            (title, now, now),
        )
        await self._db.commit()
        
        chat_id = cursor.lastrowid
        logger.info(f"Создан чат #{chat_id}: {title}")
        return chat_id
    
    async def get_chat(self, chat_id: int) -> Optional[Chat]:
        """
        Получить чат по ID.
        
        Args:
            chat_id: ID чата.
        
        Returns:
            Chat | None: Чат или None если не найден.
        """
        if not self._db:
            raise RuntimeError("База данных не инициализирована")
        
        cursor = await self._db.execute(
            "SELECT * FROM chats WHERE id = ?",
            (chat_id,),
        )
        row = await cursor.fetchone()
        
        if row is None:
            return None
        
        return Chat.from_row(tuple(row))
    
    async def get_all_chats(self) -> list[Chat]:
        """
        Получить все чаты.
        
        Returns:
            list[Chat]: Список чатов, отсортированных по дате обновления.
        """
        if not self._db:
            raise RuntimeError("База данных не инициализирована")
        
        cursor = await self._db.execute(
            "SELECT * FROM chats ORDER BY updated_at DESC",
        )
        rows = await cursor.fetchall()
        
        return [Chat.from_row(tuple(row)) for row in rows]
    
    async def update_chat_title(self, chat_id: int, title: str) -> None:
        """
        Обновить заголовок чата.
        
        Args:
            chat_id: ID чата.
            title: Новый заголовок.
        """
        if not self._db:
            raise RuntimeError("База данных не инициализирована")
        
        now = datetime.now().isoformat()
        
        await self._db.execute(
            "UPDATE chats SET title = ?, updated_at = ? WHERE id = ?",
            (title, now, chat_id),
        )
        await self._db.commit()
    
    async def delete_chat(self, chat_id: int) -> bool:
        """
        Удалить чат.
        
        Args:
            chat_id: ID чата.
        
        Returns:
            bool: True если чат удалён.
        """
        if not self._db:
            raise RuntimeError("База данных не инициализирована")
        
        cursor = await self._db.execute(
            "DELETE FROM chats WHERE id = ?",
            (chat_id,),
        )
        await self._db.commit()
        
        deleted = cursor.rowcount > 0
        if deleted:
            logger.info(f"Удалён чат #{chat_id}")
        
        return deleted
    
    # === CRUD для сообщений ===
    
    async def add_message(
        self,
        chat_id: int,
        role: str,
        content: str,
    ) -> int:
        """
        Добавить сообщение в чат.
        
        Args:
            chat_id: ID чата.
            role: Роль ('user' или 'assistant').
            content: Текст сообщения.
        
        Returns:
            int: ID сообщения.
        """
        if not self._db:
            raise RuntimeError("База данных не инициализирована")
        
        now = datetime.now().isoformat()
        
        cursor = await self._db.execute(
            "INSERT INTO messages (chat_id, role, content, created_at) VALUES (?, ?, ?, ?)",
            (chat_id, role, content, now),
        )
        await self._db.commit()
        
        # Обновляем время обновления чата
        await self._db.execute(
            "UPDATE chats SET updated_at = ? WHERE id = ?",
            (now, chat_id),
        )
        await self._db.commit()
        
        return cursor.lastrowid
    
    async def get_chat_history(self, chat_id: int) -> list[Message]:
        """
        Получить историю сообщений чата.
        
        Args:
            chat_id: ID чата.
        
        Returns:
            list[Message]: Список сообщений, отсортированных по времени.
        """
        if not self._db:
            raise RuntimeError("База данных не инициализирована")
        
        cursor = await self._db.execute(
            "SELECT * FROM messages WHERE chat_id = ? ORDER BY created_at ASC",
            (chat_id,),
        )
        rows = await cursor.fetchall()
        
        return [Message.from_row(tuple(row)) for row in rows]
    
    async def delete_message(self, message_id: int) -> bool:
        """
        Удалить сообщение.
        
        Args:
            message_id: ID сообщения.
        
        Returns:
            bool: True если сообщение удалено.
        """
        if not self._db:
            raise RuntimeError("База данных не инициализирована")
        
        cursor = await self._db.execute(
            "DELETE FROM messages WHERE id = ?",
            (message_id,),
        )
        await self._db.commit()
        
        return cursor.rowcount > 0
    
    async def clear_chat_history(self, chat_id: int) -> int:
        """
        Очистить историю чата.
        
        Args:
            chat_id: ID чата.
        
        Returns:
            int: Количество удалённых сообщений.
        """
        if not self._db:
            raise RuntimeError("База данных не инициализирована")
        
        cursor = await self._db.execute(
            "DELETE FROM messages WHERE chat_id = ?",
            (chat_id,),
        )
        await self._db.commit()
        
        return cursor.rowcount
