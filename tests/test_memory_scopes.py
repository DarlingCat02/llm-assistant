"""
Memory scopes: shared "user" facts + isolated persona notes.

One ChromaDB collection, `scope` in the entry metadata.
"""

import pytest

from src.memory_manager import ChromaStorage, MemoryEntry


class FakeCollection:
    """Minimal in-memory stand-in for a Chroma collection."""

    def __init__(self):
        self.items = []  # (id, document, metadata)

    def upsert(self, ids, embeddings=None, documents=None, metadatas=None):
        for i, d, m in zip(ids, documents or [None] * len(ids), metadatas or [None] * len(ids)):
            self.items.append((i, d, m or {}))

    def get(self):
        return {"ids": [x[0] for x in self.items]}

    def query(self, query_embeddings=None, n_results=10, include=None, where=None):
        rows = self.items
        if where and "scope" in where:
            allowed = set(where["scope"].get("$in", []))
            rows = [r for r in rows if r[2].get("scope") in allowed]
        rows = rows[:n_results]
        return {
            "ids": [[r[0] for r in rows]],
            "documents": [[r[1] for r in rows]],
            "metadatas": [[r[2] for r in rows]],
            "distances": [[0.01 for _ in rows]],
        }

    def delete(self, ids=None, where=None):
        self.items = []


@pytest.fixture
def storage():
    s = ChromaStorage.__new__(ChromaStorage)
    s._collection = FakeCollection()
    s._embedding_model = None
    s._create_embedding = lambda text: [0.1] * 8
    return s


async def test_same_text_in_two_scopes_is_two_entries(storage):
    from src.memory_manager import MemoryManager

    m = MemoryManager.__new__(MemoryManager)
    m._storage = storage
    m._seen_hashes = set()
    m._initialized = True

    a = await m.save("любимый редактор — VS Code", scope="user")
    b = await m.save("любимый редактор — VS Code", scope="editor")

    assert a is True and b is True
    assert len(m._storage._collection.items) == 2


async def test_dedup_still_works_inside_one_scope(storage):
    from src.memory_manager import MemoryManager

    m = MemoryManager.__new__(MemoryManager)
    m._storage = storage
    m._seen_hashes = set()
    m._initialized = True

    assert await m.save("факт", scope="user") is True
    assert await m.save("факт", scope="user") is False
    assert len(m._storage._collection.items) == 1


async def test_scope_filtering(storage):
    from src.memory_manager import MemoryEntry
    await storage.add(MemoryEntry(id="1", text="факт о пользователе", metadata={"scope": "user"}))
    await storage.add(MemoryEntry(id="2", text="заметка персоны", metadata={"scope": "editor"}))

    only_user = await storage.search("что угодно", limit=10, scopes=["user"])
    assert [e.id for e in only_user] == ["1"]

    both = await storage.search("что угодно", limit=10, scopes=["user", "editor"])
    assert {e.id for e in both} == {"1", "2"}

    everything = await storage.search("что угодно", limit=10)
    assert {e.id for e in everything} == {"1", "2"}


def test_generate_id_depends_on_scope():
    from src.memory_manager import MemoryManager
    m = MemoryManager.__new__(MemoryManager)
    assert m._generate_id("x", "user") != m._generate_id("x", "editor")
    assert m._generate_id("x", "user") == m._generate_id("x", "user")


def test_assistant_memory_scopes():
    from src.main import Assistant
    from src.personas import Persona

    a = Assistant.__new__(Assistant)
    a._persona = None
    assert a.memory_scopes() is None

    a._persona = Persona(id="editor", name="Editor")
    assert a.memory_scopes() == ["user", "editor"]