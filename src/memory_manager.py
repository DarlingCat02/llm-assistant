"""
Memory Manager - Менеджер долговременной памяти на основе ChromaDB.
"""

# Отключаем HuggingFace онлайн-запросы ДО всех импортов
import os
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"

import asyncio
import logging
import hashlib
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Protocol
from pathlib import Path

import chromadb
from chromadb.config import Settings as ChromaSettings

from config import get_config, ChromaConfig, MemoryConfig


logger = logging.getLogger(__name__)


@dataclass
class MemoryEntry:
    """
    Запись в памяти.
    
    Attributes:
        id: Уникальный идентификатор (хеш контента)
        text: Текст записи
        metadata: Дополнительные данные (тип, timestamp, etc.)
        score: Оценка релевантности (заполняется при поиске)
    """
    id: str
    text: str
    metadata: dict = field(default_factory=dict)
    score: float = 0.0


class EmbeddingModel(Protocol):
    """
    Протокол для модели эмбеддингов.
    
    Определяет минимальный интерфейс для работы с эмбеддингами.
    Позволяет заменить sentence-transformers на любую совместимую библиотеку.
    """
    
    def encode(self, texts: list[str], **kwargs) -> list[list[float]]:
        """
        Создать эмбеддинги для текстов.
        
        Args:
            texts: Список текстов для кодирования.
            **kwargs: Дополнительные параметры.
        
        Returns:
            list[list[float]]: Список векторов эмбеддингов.
        """
        ...


class IStorage(ABC):
    """
    Абстрактный интерфейс хранилища векторов.
    
    Позволяет заменить ChromaDB на другую векторную БД
    (FAISS, Qdrant, Weaviate) без изменения кода MemoryManager.
    """
    
    @abstractmethod
    async def add(self, entry: MemoryEntry) -> None:
        """Добавить запись в хранилище."""
        pass
    
    @abstractmethod
    async def search(self, query: str, limit: int) -> list[MemoryEntry]:
        """
        Найти похожие записи.
        
        Args:
            query: Текст запроса.
            limit: Максимальное количество результатов.
        
        Returns:
            list[MemoryEntry]: Список найденных записей.
        """
        pass
    
    @abstractmethod
    async def delete(self, entry_id: str) -> bool:
        """
        Удалить запись по ID.
        
        Args:
            entry_id: Идентификатор записи.
        
        Returns:
            bool: True если запись удалена.
        """
        pass
    
    @abstractmethod
    async def count(self) -> int:
        """Получить количество записей в хранилище."""
        pass


class ChromaStorage(IStorage):
    """
    Реализация хранилища на основе ChromaDB.
    
    Использует persistent mode для сохранения данных на диск.
    Автоматически создаёт директорию storage при необходимости.
    """
    
    def __init__(
        self,
        config: ChromaConfig,
        embedding_model: EmbeddingModel,
    ):
        """
        Инициализировать ChromaDB хранилище.
        
        Args:
            config: Конфигурация ChromaDB.
            embedding_model: Модель для создания эмбеддингов.
        """
        self._config = config
        self._embedding_model = embedding_model
        self._client: chromadb.Client | None = None
        self._collection: chromadb.Collection | None = None
    
    async def initialize(self) -> None:
        """
        Инициализировать ChromaDB клиент и коллекцию.
        
        Создаёт persistent хранилище в указанной директории.
        """
        # Отключаем онлайн-проверки HuggingFace (модель загружается из кэша)
        import os
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
        
        # Создаём директорию если не существует
        persist_path = Path(self._config.persist_dir)
        persist_path.mkdir(parents=True, exist_ok=True)
        
        # Инициализируем клиент с persistent настройками
        self._client = chromadb.PersistentClient(
            path=str(persist_path),
            settings=ChromaSettings(
                anonymized_telemetry=False,  # Отключаем телеметрию
            ),
        )
        
        # Получаем или создаём коллекцию
        self._collection = self._client.get_or_create_collection(
            name=self._config.collection_name,
            metadata={"hnsw:space": "cosine"},  # Косинусное расстояние
        )
        
        logger.info(
            f"ChromaDB инициализирован: {persist_path}, "
            f"коллекция: {self._config.collection_name}"
        )
    
    async def add(self, entry: MemoryEntry) -> None:
        """
        Добавить запись в хранилище.
        
        Автоматически создаёт эмбеддинг для текста.
        Если запись с таким ID существует, она обновляется.
        
        Args:
            entry: Запись для добавления.
        """
        if not self._collection:
            raise RuntimeError("ChromaDB не инициализирован")
        
        # Создаём эмбеддинг
        embedding = self._create_embedding(entry.text)
        
        # Добавляем в коллекцию
        self._collection.upsert(
            ids=[entry.id],
            embeddings=[embedding],
            documents=[entry.text],
            metadatas=[entry.metadata],
        )
        
        logger.debug(f"Память сохранена: {entry.id}")
    
    async def search(
        self,
        query: str,
        limit: int,
        min_similarity: float = 0.0,
    ) -> list[MemoryEntry]:
        """
        Найти похожие записи по семантическому запросу.
        
        Использует косинусное расстояние для поиска ближайших векторов.
        
        Args:
            query: Текст запроса.
            limit: Максимальное количество результатов.
            min_similarity: Минимальный порог схожести.
        
        Returns:
            list[MemoryEntry]: Отсортированные по релевантности записи.
        """
        if not self._collection:
            raise RuntimeError("ChromaDB не инициализирован")
        
        # Создаём эмбеддинг для запроса
        query_embedding = self._create_embedding(query)
        
        # Ищем похожие
        results = self._collection.query(
            query_embeddings=[query_embedding],
            n_results=limit,
            include=["documents", "metadatas", "distances"],
        )
        
        # Преобразуем в MemoryEntry
        entries = []
        if results["ids"] and results["ids"][0]:
            for i, doc_id in enumerate(results["ids"][0]):
                distance = results["distances"][0][i] if results["distances"] else 0.0
                # Конвертируем расстояние в схожесть (cosine distance -> similarity)
                similarity = 1.0 - distance
                
                if similarity >= min_similarity:
                    entries.append(
                        MemoryEntry(
                            id=doc_id,
                            text=results["documents"][0][i],
                            metadata=results["metadatas"][0][i] or {},
                            score=similarity,
                        )
                    )
        
        logger.debug(f"Найдено {len(entries)} записей в памяти")
        return entries
    
    async def delete(self, entry_id: str) -> bool:
        """Удалить запись по ID."""
        if not self._collection:
            raise RuntimeError("ChromaDB не инициализирован")
        
        try:
            self._collection.delete(ids=[entry_id])
            logger.debug(f"Память удалена: {entry_id}")
            return True
        except Exception:
            return False
    
    async def count(self) -> int:
        """Получить количество записей."""
        if not self._collection:
            raise RuntimeError("ChromaDB не инициализирован")
        
        return self._collection.count()
    
    def _create_embedding(self, text: str) -> list[float]:
        """
        Создать эмбеддинг для текста.
        
        Args:
            text: Текст для кодирования.
        
        Returns:
            list[float]: Вектор эмбеддинга.
        """
        embeddings = self._embedding_model.encode(
            [text],
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        return embeddings[0].tolist()


class MemoryManager:
    """
    Менеджер долговременной памяти.
    
    Основной интерфейс для работы с памятью ассистента.
    Автоматически извлекает релевантный контекст перед генерацией ответа.
    
    Особенности:
    - Дедупликация записей по хешу контента
    - Фильтрация по порогу схожести
    - Асинхронные операции для неблокирующего доступа
    
    Пример использования:
        memory = MemoryManager()
        await memory.initialize()
        
        # Сохранить диалог
        await memory.save_dialog("Пользователь спросил про погоду", "assistant")
        
        # Найти контекст для запроса
        contexts = await memory.search_context("Какая сегодня погода?")
    """
    
    def __init__(
        self,
        chroma_config: ChromaConfig | None = None,
        memory_config: MemoryConfig | None = None,
    ):
        """
        Инициализировать менеджер памяти.
        
        Args:
            chroma_config: Конфигурация ChromaDB.
            memory_config: Конфигурация памяти.
        """
        self._chroma_config = chroma_config or get_config().chroma
        self._memory_config = memory_config or get_config().memory
        
        self._storage: IStorage | None = None
        self._embedding_model: EmbeddingModel | None = None
        self._initialized = False
        
        # Кэш для избежания дубликатов
        self._seen_hashes: set[str] = set()
    
    async def initialize(self) -> None:
        """
        Инициализировать менеджер памяти.

        Загружает модель эмбеддингов и инициализирует хранилище.
        Модель загружается в CPU память (не VRAM) для экономии GPU.
        
        Важно: загружает все существующие ID из ChromaDB в _seen_hashes
        для работы дедупликации между сессиями.
        """
        if self._initialized:
            return

        # Загружаем модель эмбеддингов
        # all-MiniLM-L6-v2: легковесная модель (80MB), работает на CPU
        
        logger.info("Загрузка модели эмбеддингов...")
        from sentence_transformers import SentenceTransformer
        
        # local_files_only=True — самый надёжный способ отключить запросы к HuggingFace
        self._embedding_model = SentenceTransformer(
            "all-MiniLM-L6-v2",
            device="cpu",
            local_files_only=True,
        )
        logger.info("Модель эмбеддингов загружена")

        # Инициализируем хранилище
        self._storage = ChromaStorage(
            config=self._chroma_config,
            embedding_model=self._embedding_model,
        )
        await self._storage.initialize()

        # Загружаем существующие ID для дедупликации между сессиями
        # Это позволяет не дублировать записи при перезапуске приложения
        await self._load_existing_hashes()

        self._initialized = True
        count = await self._storage.count()
        logger.info(f"Memory Manager инициализирован, записей в памяти: {count}")

    async def _load_existing_hashes(self) -> None:
        """
        Загрузить все существующие ID из ChromaDB в _seen_hashes.
        
        Вызывается при инициализации для работы дедупликации
        между сессиями приложения.
        """
        if not isinstance(self._storage, ChromaStorage) or not self._storage._collection:
            return
        
        # Получаем все ID из коллекции
        # ChromaDB позволяет получить все ID через query с пустым эмбеддингом
        try:
            # Получаем все записи (без эмбеддингов и документов, только ID)
            all_ids = self._storage._collection.get()["ids"]
            
            # Добавляем все ID в множество для дедупликации
            for entry_id in all_ids:
                self._seen_hashes.add(entry_id)
            
            logger.debug(f"Загружено {len(self._seen_hashes)} существующих ID для дедупликации")
        except Exception as e:
            logger.warning(f"Не удалось загрузить существующие ID: {e}")
    
    async def close(self) -> None:
        """
        Освободить ресурсы.
        
        Вызывается при завершении работы приложения.
        """
        self._initialized = False
        self._storage = None
        self._embedding_model = None
        logger.info("Memory Manager закрыт")
    
    def _generate_id(self, text: str) -> str:
        """
        Сгенерировать уникальный ID для записи.
        
        Использует SHA-256 хеш контента для дедупликации.
        
        Args:
            text: Текст записи.
        
        Returns:
            str: Уникальный идентификатор.
        """
        return hashlib.sha256(text.encode()).hexdigest()[:16]
    
    async def save(
        self,
        text: str,
        entry_type: str = "general",
        metadata: dict | None = None,
    ) -> bool:
        """
        Сохранить запись в памяти.
        
        Автоматически пропускает дубликаты.
        
        Args:
            text: Текст для сохранения.
            entry_type: Тип записи (general, dialog, fact, etc.)
            metadata: Дополнительные метаданные.
        
        Returns:
            bool: True если запись сохранена, False если дубликат.
        """
        if not self._initialized:
            raise RuntimeError("Memory Manager не инициализирован")
        
        # Проверяем на дубликаты
        entry_hash = self._generate_id(text)
        if entry_hash in self._seen_hashes:
            logger.debug(f"Дубликат памяти пропущен: {entry_hash}")
            return False
        
        # Создаём запись
        entry = MemoryEntry(
            id=entry_hash,
            text=text,
            metadata={
                "type": entry_type,
                **(metadata or {}),
            },
        )
        
        # Сохраняем
        await self._storage.add(entry)
        self._seen_hashes.add(entry_hash)
        
        logger.info(f"Память сохранена: {entry_type}, {len(text)} символов")
        return True
    
    async def save_dialog(
        self,
        user_message: str,
        assistant_response: str,
    ) -> bool:
        """
        Сохранить диалог в памяти.
        
        Сохраняет пару вопрос-ответ как единый контекст.
        
        Args:
            user_message: Сообщение пользователя.
            assistant_response: Ответ ассистента.
        
        Returns:
            bool: True если сохранено.
        """
        # Формируем текст диалога
        dialog_text = f"User: {user_message}\nAssistant: {assistant_response}"
        
        return await self.save(
            text=dialog_text,
            entry_type="dialog",
            metadata={
                "user_message": user_message,
                "assistant_response": assistant_response,
            },
        )
    
    async def save_fact(self, fact: str, category: str = "general") -> bool:
        """
        Сохранить факт в памяти.
        
        Для извлечения фактов можно использовать Function Calling.
        
        Args:
            fact: Текст факта.
            category: Категория факта.
        
        Returns:
            bool: True если сохранено.
        """
        return await self.save(
            text=fact,
            entry_type="fact",
            metadata={"category": category},
        )
    
    async def search(
        self,
        query: str,
        limit: int | None = None,
        min_similarity: float | None = None,
    ) -> list[MemoryEntry]:
        """
        Найти похожие записи в памяти.
        
        Args:
            query: Текст запроса для поиска.
            limit: Максимальное количество результатов.
            min_similarity: Минимальный порог схожести.
        
        Returns:
            list[MemoryEntry]: Найденные записи, отсортированные по релевантности.
        """
        if not self._initialized:
            raise RuntimeError("Memory Manager не инициализирован")
        
        limit = limit if limit is not None else self._memory_config.search_results
        min_similarity = min_similarity if min_similarity is not None else self._memory_config.similarity_threshold
        
        return await self._storage.search(
            query=query,
            limit=limit,
            min_similarity=min_similarity,
        )
    
    async def search_context(self, query: str) -> list[str]:
        """
        Найти контекст для запроса.

        Возвращает только тексты записей для включения в промпт LLM.
        Используется для RAG (Retrieval Augmented Generation).

        Args:
            query: Текст запроса для поиска релевантного контекста.

        Returns:
            list[str]: Список текстов контекста для добавления в промпт.
        """
        entries = await self.search(query)
        return [entry.text for entry in entries]
    
    async def get_stats(self) -> dict:
        """
        Получить статистику памяти.
        
        Returns:
            dict: Статистика (количество записей, типы, etc.)
        """
        if not self._initialized:
            raise RuntimeError("Memory Manager не инициализирован")
        
        count = await self._storage.count()
        
        return {
            "total_entries": count,
            "seen_hashes": len(self._seen_hashes),
        }
    
    async def clear(self) -> None:
        """
        Очистить всю память.
        
        Внимание: необратимая операция!
        """
        if not self._initialized:
            raise RuntimeError("Memory Manager не инициализирован")
        
        # Удаляем все записи через получение всех ID
        if self._storage._collection:
            all_ids = self._storage._collection.get()["ids"]
            if all_ids:
                self._storage._collection.delete(ids=all_ids)
        
        self._seen_hashes.clear()
        logger.warning("Память полностью очищена")
