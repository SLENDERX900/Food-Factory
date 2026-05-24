"""
Market-signal RAG memory.

Stores Pinterest and Reddit language patterns so generation can reuse authentic
phrasing without sounding templated.
"""

from __future__ import annotations

import hashlib
import shutil
import logging
import os
from pathlib import Path

import chromadb
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

DB_DIR = Path("data/chroma")
COLLECTION_NAME = "market_signals"
EMBED_MODEL = "all-MiniLM-L6-v2"
MAX_COLLECTION_SIZE = 200  # Reduced from 500 for tighter memory control

# Detect if running on Streamlit Cloud (no persistent storage available)
# Force ephemeral mode to prevent disk space errors
IS_STREAMLIT_CLOUD = True  # Always use in-memory mode for stability

_embedder = None
_collection = None
_client = None


def _get_embedder():
    global _embedder
    if _embedder is None:
        _embedder = SentenceTransformer(EMBED_MODEL)
    return _embedder


def _get_db_size_mb() -> float:
    """Calculate current database size in MB."""
    if not DB_DIR.exists():
        return 0.0
    total_size = 0
    try:
        for item in DB_DIR.rglob('*'):
            if item.is_file():
                total_size += item.stat().st_size
    except (OSError, PermissionError):
        return 0.0  # Can't access, assume empty
    return total_size / (1024 * 1024)


def _cleanup_old_entries(collection, keep_count: int = MAX_COLLECTION_SIZE):
    """Remove oldest entries to keep collection under size limit."""
    try:
        # Get all items
        all_items = collection.get()
        if all_items and 'ids' in all_items:
            total_items = len(all_items['ids'])
            if total_items > keep_count:
                # Delete oldest items (assuming sequential IDs)
                items_to_delete = total_items - keep_count
                ids_to_delete = all_items['ids'][:items_to_delete]
                collection.delete(ids=ids_to_delete)
                logger.info(f"Cleaned up {items_to_delete} old entries from ChromaDB")
    except Exception as e:
        logger.warning(f"Cleanup failed: {e}")


def _force_clear_db_directory():
    """Aggressively clear the DB directory including corrupted files."""
    try:
        if DB_DIR.exists():
            # Remove entire data directory
            shutil.rmtree(DB_DIR, ignore_errors=True)
            logger.warning("Force-cleared ChromaDB directory")
        # Also try to clear any temp files
        for temp_file in Path(".").glob("*.ldb"):
            try:
                temp_file.unlink()
            except:
                pass
    except Exception as e:
        logger.error(f"Force clear failed: {e}")


def _reset_database():
    """Clear the entire database if it's corrupted or full."""
    global _collection, _client
    try:
        if DB_DIR.exists():
            shutil.rmtree(DB_DIR)
            logger.warning("Reset ChromaDB database due to disk space/corruption")
        _collection = None
        _client = None
    except Exception as e:
        logger.error(f"Failed to reset database: {e}")


def _get_collection():
    global _collection, _client
    if _collection is None:
        # STREAMLIT CLOUD: Use ephemeral in-memory client (no disk writes)
        if IS_STREAMLIT_CLOUD:
            logger.info("Using ephemeral in-memory ChromaDB for Streamlit Cloud")
            try:
                _client = chromadb.Client()  # In-memory, no persistence
                _collection = _client.get_or_create_collection(COLLECTION_NAME)
                return _collection
            except Exception as e:
                logger.critical(f"Ephemeral ChromaDB failed: {e}")
                raise
        
        # LOCAL: Use persistent client with aggressive cleanup
        try:
            DB_DIR.mkdir(parents=True, exist_ok=True)
            
            # Check available disk space - LOWERED to 50MB threshold
            db_size = _get_db_size_mb()
            if db_size > 50:  # If DB is over 50MB, clear it completely
                logger.warning(f"ChromaDB size ({db_size:.1f}MB) exceeds 50MB limit, force-clearing")
                _force_clear_db_directory()
            
            _client = chromadb.PersistentClient(path=str(DB_DIR))
            _collection = _client.get_or_create_collection(COLLECTION_NAME)
            
            # Clean up if too large
            _cleanup_old_entries(_collection, MAX_COLLECTION_SIZE // 2)  # Keep only half
            
        except Exception as e:
            logger.error(f"ChromaDB init failed: {e}")
            # Fallback: try to reset and recreate
            _force_clear_db_directory()
            try:
                DB_DIR.mkdir(parents=True, exist_ok=True)
                _client = chromadb.PersistentClient(path=str(DB_DIR))
                _collection = _client.get_or_create_collection(COLLECTION_NAME)
            except Exception as e2:
                logger.critical(f"ChromaDB completely failed: {e2}")
                # Last resort: use ephemeral client
                try:
                    _client = chromadb.Client()
                    _collection = _client.get_or_create_collection(COLLECTION_NAME)
                    logger.warning("Falling back to ephemeral in-memory ChromaDB")
                except Exception as e3:
                    logger.critical(f"All ChromaDB options failed: {e3}")
                    raise
    return _collection


def store_market_signals(signals: list[dict], *, platform: str) -> int:
    """Store market signals in ChromaDB with platform metadata."""
    if not signals:
        return 0
    
    signals = signals[:75]
    
    try:
        embedder = _get_embedder()
        collection = _get_collection()
        
        # Pre-cleanup if approaching limit
        if not IS_STREAMLIT_CLOUD:  # Only needed for persistent mode
            try:
                current = collection.count()
                if current > MAX_COLLECTION_SIZE:
                    _cleanup_old_entries(collection, MAX_COLLECTION_SIZE // 3)  # Keep only 1/3
            except Exception:
                pass

        texts = []
        ids = []
        metadatas = []
        for signal in signals:
            text = " ".join(
                part for part in [
                    signal.get("title", ""),
                    signal.get("description", ""),
                    signal.get("selftext", ""),
                    signal.get("snippet", ""),
                ] if part
            ).strip()
            if not text:
                continue
            signal_id = hashlib.sha1(
                f"{platform}|{text}|{signal.get('url','')}|{signal.get('pin_url','')}".encode("utf-8")
            ).hexdigest()
            texts.append(text)
            ids.append(signal_id)
            metadatas.append(
                {
                    "title": signal.get("title", ""),
                    "description": signal.get("description", "") or signal.get("selftext", "")[:300],
                    "image_url": signal.get("image_url", ""),
                    "pin_url": signal.get("pin_url", "") or signal.get("url", ""),
                    "source": signal.get("source", ""),
                    "platform": platform,
                    "subreddit": signal.get("subreddit", ""),
                    "recipe_name": signal.get("recipe_name", ""),
                    "query": signal.get("query", ""),
                }
            )
        if not texts:
            return 0

        embeddings = embedder.encode(texts).tolist()
        collection.upsert(ids=ids, embeddings=embeddings, documents=texts, metadatas=metadatas)
        return len(texts)
        
    except Exception as e:
        logger.error(f"Failed to store pins: {e}")
        if not IS_STREAMLIT_CLOUD:
            _force_clear_db_directory()
        return 0


def store_trending_pins(pins: list[dict]) -> int:
    return store_market_signals(pins, platform="pinterest")


def query_similar_trends(query_text: str, top_k: int = 5) -> list[dict]:
    """Query similar trends with error handling for disk issues."""
    if not query_text.strip():
        return []


def query_similar_market_signals(query_text: str, top_k: int = 8) -> list[dict]:
    if not query_text.strip():
        return []

    try:
        embedder = _get_embedder()
        collection = _get_collection()
        query_embedding = embedder.encode([query_text]).tolist()[0]
        results = collection.query(query_embeddings=[query_embedding], n_results=top_k)
        items = []
        for i, doc in enumerate(results.get("documents", [[]])[0]):
            meta = results.get("metadatas", [[]])[0][i] if results.get("metadatas") else {}
            items.append({"text": doc, **(meta or {})})
        return items
    except Exception as e:
        logger.error(f"Query failed: {e}")
        # Don't reset on ephemeral mode, just return empty
        if not IS_STREAMLIT_CLOUD:
            _force_clear_db_directory()
        return []
