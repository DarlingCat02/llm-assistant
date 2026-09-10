"""
Memory Manager - Long-term memory manager based on ChromaDB.
"""

# Disable HuggingFace online requests BEFORE all imports
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
    Memory entry.

    Attributes:
        id: Unique identifier (content hash)
        text: Entry text
        metadata: Additional data (type, timestamp, etc.)
        score: Relevance score (filled in during search)
    """
    id: str
    text: str
    metadata: dict = field(default_factory=dict)
    score: float = 0.0


class EmbeddingModel(Protocol):
    """
    Protocol for an embedding model.

    Defines the minimal interface for working with embeddings.
    Allows replacing sentence-transformers with any compatible library.
    """

    def encode(self, texts: list[str], **kwargs) -> list[list[float]]:
        """
        Create embeddings for texts.

        Args:
            texts: List of texts to encode.
            **kwargs: Additional parameters.

        Returns:
            list[list[float]]: List of embedding vectors.
        """
        ...


class IStorage(ABC):
    """
    Abstract vector storage interface.

    Allows replacing ChromaDB with another vector DB
    (FAISS, Qdrant, Weaviate) without changing MemoryManager code.
    """

    @abstractmethod
    async def add(self, entry: MemoryEntry) -> None:
        """Add an entry to the storage."""
        pass
    
    @abstractmethod
    async def search(self, query: str, limit: int) -> list[MemoryEntry]:
        """
        Find similar entries.

        Args:
            query: Query text.
            limit: Maximum number of results.

        Returns:
            list[MemoryEntry]: List of found entries.
        """
        pass
    
    @abstractmethod
    async def delete(self, entry_id: str) -> bool:
        """
        Delete an entry by ID.

        Args:
            entry_id: Entry identifier.

        Returns:
            bool: True if the entry was deleted.
        """
        pass
    
    @abstractmethod
    async def count(self) -> int:
        """Get the number of entries in the storage."""
        pass


class ChromaStorage(IStorage):
    """
    ChromaDB-based storage implementation.

    Uses persistent mode to save data to disk.
    Automatically creates the storage directory if needed.
    """
    
    def __init__(
        self,
        config: ChromaConfig,
        embedding_model: EmbeddingModel,
    ):
        """
        Initialize the ChromaDB storage.

        Args:
            config: ChromaDB configuration.
            embedding_model: Model for creating embeddings.
        """
        self._config = config
        self._embedding_model = embedding_model
        self._client: chromadb.Client | None = None
        self._collection: chromadb.Collection | None = None
    
    async def initialize(self) -> None:
        """
        Initialize the ChromaDB client and collection.

        Creates persistent storage in the specified directory.
        """
        # Disable HuggingFace online checks (model is loaded from cache)
        import os
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
        
        # Create the directory if it does not exist
        persist_path = Path(self._config.persist_dir)
        persist_path.mkdir(parents=True, exist_ok=True)
        
        # Initialize the client with persistent settings
        self._client = chromadb.PersistentClient(
            path=str(persist_path),
            settings=ChromaSettings(
                anonymized_telemetry=False,  # Disable telemetry
            ),
        )
        
        # Get or create the collection
        self._collection = self._client.get_or_create_collection(
            name=self._config.collection_name,
            metadata={"hnsw:space": "cosine"},  # Cosine distance
        )
        
        logger.info(
            f"ChromaDB initialized: {persist_path}, "
            f"collection: {self._config.collection_name}"
        )
    
    async def add(self, entry: MemoryEntry) -> None:
        """
        Add an entry to the storage.

        Automatically creates an embedding for the text.
        If an entry with the same ID exists, it is updated.

        Args:
            entry: Entry to add.
        """
        if not self._collection:
            raise RuntimeError("ChromaDB не инициализирован")
        
        # Create an embedding
        embedding = self._create_embedding(entry.text)
        
        # Add to the collection
        self._collection.upsert(
            ids=[entry.id],
            embeddings=[embedding],
            documents=[entry.text],
            metadatas=[entry.metadata],
        )
        
        logger.debug(f"Memory saved: {entry.id}")
    
    async def search(
        self,
        query: str,
        limit: int,
        min_similarity: float = 0.0,
    ) -> list[MemoryEntry]:
        """
        Find similar entries for a semantic query.

        Uses cosine distance to find the nearest vectors.

        Args:
            query: Query text.
            limit: Maximum number of results.
            min_similarity: Minimum similarity threshold.

        Returns:
            list[MemoryEntry]: Entries sorted by relevance.
        """
        if not self._collection:
            raise RuntimeError("ChromaDB не инициализирован")
        
        # Create an embedding for the query
        query_embedding = self._create_embedding(query)
        
        # Find similar entries
        results = self._collection.query(
            query_embeddings=[query_embedding],
            n_results=limit,
            include=["documents", "metadatas", "distances"],
        )
        
        # Convert to MemoryEntry
        entries = []
        if results["ids"] and results["ids"][0]:
            for i, doc_id in enumerate(results["ids"][0]):
                distance = results["distances"][0][i] if results["distances"] else 0.0
                # Convert distance to similarity (cosine distance -> similarity)
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
        
        logger.debug(f"Found {len(entries)} memory entries")
        return entries
    
    async def delete(self, entry_id: str) -> bool:
        """Delete an entry by ID."""
        if not self._collection:
            raise RuntimeError("ChromaDB не инициализирован")
        
        try:
            self._collection.delete(ids=[entry_id])
            logger.debug(f"Memory deleted: {entry_id}")
            return True
        except Exception:
            return False
    
    async def count(self) -> int:
        """Get the number of entries."""
        if not self._collection:
            raise RuntimeError("ChromaDB не инициализирован")
        
        return self._collection.count()
    
    def _create_embedding(self, text: str) -> list[float]:
        """
        Create an embedding for a text.

        Args:
            text: Text to encode.

        Returns:
            list[float]: Embedding vector.
        """
        embeddings = self._embedding_model.encode(
            [text],
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        return embeddings[0].tolist()


class MemoryManager:
    """
    Long-term memory manager.

    The main interface for working with the assistant memory.
    Automatically retrieves relevant context before generating a response.

    Features:
    - Record deduplication by content hash
    - Similarity threshold filtering
    - Async operations for non-blocking access

    Example usage:
        memory = MemoryManager()
        await memory.initialize()

        # Save a dialog
        await memory.save_dialog("User asked about the weather", "assistant")

        # Find context for a query
        contexts = await memory.search_context("What is the weather today?")
    """
    
    def __init__(
        self,
        chroma_config: ChromaConfig | None = None,
        memory_config: MemoryConfig | None = None,
    ):
        """
        Initialize the memory manager.

        Args:
            chroma_config: ChromaDB configuration.
            memory_config: Memory configuration.
        """
        self._chroma_config = chroma_config or get_config().chroma
        self._memory_config = memory_config or get_config().memory
        
        self._storage: IStorage | None = None
        self._embedding_model: EmbeddingModel | None = None
        self._initialized = False
        
        # Cache for avoiding duplicates
        self._seen_hashes: set[str] = set()
    
    async def initialize(self) -> None:
        """
        Initialize the memory manager.

        Loads the embedding model and initializes the storage.
        The model is loaded into CPU memory (not VRAM) to save GPU.

        Important: loads all existing IDs from ChromaDB into _seen_hashes
        so deduplication works across sessions.
        """
        if self._initialized:
            return

        # Load the embedding model
        # all-MiniLM-L6-v2: lightweight model (80MB), runs on CPU
        
        logger.info("Loading embedding model...")
        from sentence_transformers import SentenceTransformer
        
        # local_files_only=True — the most reliable way to disable HuggingFace requests
        self._embedding_model = SentenceTransformer(
            "all-MiniLM-L6-v2",
            device="cpu",
            local_files_only=True,
        )
        logger.info("Embedding model loaded")

        # Initialize the storage
        self._storage = ChromaStorage(
            config=self._chroma_config,
            embedding_model=self._embedding_model,
        )
        await self._storage.initialize()

        # Load existing IDs for deduplication across sessions
        # This avoids duplicating records on application restart
        await self._load_existing_hashes()

        self._initialized = True
        count = await self._storage.count()
        logger.info(f"Memory Manager initialized, entries: {count}")

    async def _load_existing_hashes(self) -> None:
        """
        Load all existing IDs from ChromaDB into _seen_hashes.

        Called on initialization so deduplication works
        across application sessions.
        """
        if not isinstance(self._storage, ChromaStorage) or not self._storage._collection:
            return
        
        # Get all IDs from the collection
        # ChromaDB returns IDs directly via get(), no embedding needed
        try:
            # Get all records (without embeddings and documents, IDs only)
            all_ids = self._storage._collection.get()["ids"]
            
            # Add all IDs to the set for deduplication
            for entry_id in all_ids:
                self._seen_hashes.add(entry_id)
            
            logger.debug(f"Loaded {len(self._seen_hashes)} existing IDs for deduplication")
        except Exception as e:
            logger.warning(f"Failed to load existing IDs: {e}")
    
    async def close(self) -> None:
        """
        Release resources.

        Called when the application shuts down.
        """
        self._initialized = False
        self._storage = None
        self._embedding_model = None
        logger.info("Memory Manager closed")
    
    def _generate_id(self, text: str) -> str:
        """
        Generate a unique ID for a record.

        Uses SHA-256 content hash for deduplication.

        Args:
            text: Record text.

        Returns:
            str: Unique identifier.
        """
        return hashlib.sha256(text.encode()).hexdigest()[:16]
    
    async def save(
        self,
        text: str,
        entry_type: str = "general",
        metadata: dict | None = None,
    ) -> bool:
        """
        Save a record to memory.

        Automatically skips duplicates.

        Args:
            text: Text to save.
            entry_type: Entry type (general, dialog, fact, etc.)
            metadata: Additional metadata.

        Returns:
            bool: True if the record was saved, False if duplicate.
        """
        if not self._initialized:
            raise RuntimeError("Memory Manager не инициализирован")
        
        # Check for duplicates
        entry_hash = self._generate_id(text)
        if entry_hash in self._seen_hashes:
            logger.debug(f"Duplicate memory skipped: {entry_hash}")
            return False
        
        # Create the entry
        entry = MemoryEntry(
            id=entry_hash,
            text=text,
            metadata={
                "type": entry_type,
                **(metadata or {}),
            },
        )
        
        # Save
        await self._storage.add(entry)
        self._seen_hashes.add(entry_hash)
        
        logger.info(f"Memory saved: {entry_type}, {len(text)} chars")
        return True
    
    async def save_dialog(
        self,
        user_message: str,
        assistant_response: str,
    ) -> bool:
        """
        Save a dialog to memory.

        Saves a question-answer pair as a single context.

        Args:
            user_message: User message.
            assistant_response: Assistant response.

        Returns:
            bool: True if saved.
        """
        # Build the dialog text
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
        Save a fact to memory.

        Function Calling can be used for fact extraction.

        Args:
            fact: Fact text.
            category: Fact category.

        Returns:
            bool: True if saved.
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
        Find similar records in memory.

        Args:
            query: Query text for search.
            limit: Maximum number of results.
            min_similarity: Minimum similarity threshold.

        Returns:
            list[MemoryEntry]: Found records sorted by relevance.
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
        Find context for a query.

        Returns only record texts for inclusion in the LLM prompt.
        Used for RAG (Retrieval Augmented Generation).

        Args:
            query: Query text for finding relevant context.

        Returns:
            list[str]: List of context texts to add to the prompt.
        """
        entries = await self.search(query)
        return [entry.text for entry in entries]
    
    async def get_stats(self) -> dict:
        """
        Get memory statistics.

        Returns:
            dict: Statistics (record count, types, etc.)
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
        Clear all memory.

        Warning: irreversible operation!
        """
        if not self._initialized:
            raise RuntimeError("Memory Manager не инициализирован")
        
        # Delete all records by fetching all IDs
        if self._storage._collection:
            all_ids = self._storage._collection.get()["ids"]
            if all_ids:
                self._storage._collection.delete(ids=all_ids)
        
        self._seen_hashes.clear()
        logger.warning("Memory completely cleared")
