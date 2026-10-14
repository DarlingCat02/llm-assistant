"""
Database for storing chats.

Uses SQLite to store:
- Chat list (sessions)
- Messages in each chat
- Metadata (creation time, last message)

Architecture decisions:
1. Separate DB for chats (independent of ChromaDB)
2. Async access via aiosqlite
3. Prepared for scaling (easy to replace with PostgreSQL)
"""

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional
from dataclasses import dataclass

import aiosqlite


logger = logging.getLogger(__name__)


@dataclass
class Chat:
    """Chat model."""
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
    """Chat message model."""
    id: int
    chat_id: int
    role: str  # 'user' or 'assistant'
    content: str
    created_at: datetime
    # Tool calls executed for this turn; empty for user messages and for
    # assistant messages from before this column existed.
    actions: list = None

    @classmethod
    def from_row(cls, row: tuple) -> "Message":
        actions = None
        if len(row) > 5 and row[5]:
            try:
                actions = json.loads(row[5])
            except (ValueError, TypeError):
                logger.warning(f"Message {row[0]}: unreadable actions column, ignored")
                actions = None
        return cls(
            id=row[0],
            chat_id=row[1],
            role=row[2],
            content=row[3],
            created_at=datetime.fromisoformat(row[4]),
            actions=actions,
        )


class ChatDatabase:
    """
    Chat database manager.

    Usage example:
        db = ChatDatabase("./storage/chats.db")
        await db.initialize()

        # Create a chat
        chat_id = await db.create_chat("New chat")

        # Add messages
        await db.add_message(chat_id, "user", "Hello!")
        await db.add_message(chat_id, "assistant", "Hi there!")

        # Get history
        messages = await db.get_chat_history(chat_id)
    """
    
    def __init__(self, db_path: str):
        """
        Initialize the database.

        Args:
            db_path: Path to the database file.
        """
        self._db_path = Path(db_path)
        self._db: Optional[aiosqlite.Connection] = None
    
    async def initialize(self) -> None:
        """
        Initialize the connection and create tables.
        """
        # Create the directory if it does not exist
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Connect to the DB
        self._db = await aiosqlite.connect(str(self._db_path))
        self._db.row_factory = aiosqlite.Row
        
        # Create tables
        await self._create_tables()
        
        logger.info(f"Chat database initialized: {self._db_path}")
    
    async def _create_tables(self) -> None:
        """Create tables if they do not exist."""
        if not self._db:
            raise RuntimeError("База данных не инициализирована")
        
        # Chats table
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS chats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        
        # Messages table
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

        # Tool calls shown under an assistant message. Kept as JSON text so the
        # collapsible "what did it actually run" block survives switching chats -
        # without it, reloading a chat rendered bare text and every executed
        # tool call was lost from the UI.
        columns = {
            row[1]
            for row in await (await self._db.execute("PRAGMA table_info(messages)")).fetchall()
        }
        if "actions" not in columns:
            await self._db.execute("ALTER TABLE messages ADD COLUMN actions TEXT")
        
        # Indexes to speed up lookups
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
        """Close the DB connection."""
        if self._db:
            await self._db.close()
            self._db = None
            logger.info("Chat database closed")
    
    # === CRUD for chats ===
    
    async def create_chat(self, title: str = "Новый чат") -> int:
        """
        Create a new chat.

        Args:
            title: Chat title.

        Returns:
            int: ID of the created chat.
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
        logger.info(f"Created chat #{chat_id}: {title}")
        return chat_id
    
    async def get_chat(self, chat_id: int) -> Optional[Chat]:
        """
        Get a chat by ID.

        Args:
            chat_id: Chat ID.

        Returns:
            Chat | None: Chat or None if not found.
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
        Get all chats.

        Returns:
            list[Chat]: List of chats, sorted by update date.
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
        Update the chat title.

        Args:
            chat_id: Chat ID.
            title: New title.
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
        Delete a chat.

        Args:
            chat_id: Chat ID.

        Returns:
            bool: True if the chat was deleted.
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
            logger.info(f"Deleted chat #{chat_id}")
        
        return deleted
    
    # === CRUD for messages ===
    
    async def add_message(
        self,
        chat_id: int,
        role: str,
        content: str,
        actions: list | None = None,
    ) -> int:
        """
        Add a message to the chat.

        Args:
            chat_id: Chat ID.
            role: Role ('user' or 'assistant').
            content: Message text.
            actions: Tool calls executed while producing it, for assistant turns.

        Returns:
            int: Message ID.
        """
        if not self._db:
            raise RuntimeError("База данных не инициализирована")

        now = datetime.now().isoformat()
        payload = json.dumps(actions, ensure_ascii=False) if actions else None

        cursor = await self._db.execute(
            "INSERT INTO messages (chat_id, role, content, created_at, actions) "
            "VALUES (?, ?, ?, ?, ?)",
            (chat_id, role, content, now, payload),
        )
        await self._db.commit()
        
        # Update the chat's updated timestamp
        await self._db.execute(
            "UPDATE chats SET updated_at = ? WHERE id = ?",
            (now, chat_id),
        )
        await self._db.commit()
        
        return cursor.lastrowid
    
    async def get_chat_history(self, chat_id: int) -> list[Message]:
        """
        Get the chat message history.

        Args:
            chat_id: Chat ID.

        Returns:
            list[Message]: List of messages, sorted by time.
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
        Delete a message.

        Args:
            message_id: Message ID.

        Returns:
            bool: True if the message was deleted.
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
        Clear the chat history.

        Args:
            chat_id: Chat ID.

        Returns:
            int: Number of deleted messages.
        """
        if not self._db:
            raise RuntimeError("База данных не инициализирована")
        
        cursor = await self._db.execute(
            "DELETE FROM messages WHERE chat_id = ?",
            (chat_id,),
        )
        await self._db.commit()
        
        return cursor.rowcount
