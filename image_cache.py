#!/usr/bin/env python3
"""Image caching system with SQLite database"""
import sqlite3
import os
import hashlib
import time
from typing import Optional, Dict, Any, Tuple
from pathlib import Path
import json

class ImageCache:
    """Manages persistent image cache with metadata"""

    def __init__(self, cache_dir: str = "image_cache", max_size_mb: int = 500):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)
        self.db_path = self.cache_dir / "cache.db"
        self.max_size_bytes = max_size_mb * 1024 * 1024
        self._init_database()

    def _init_database(self):
        """Initialize SQLite database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                search_key TEXT UNIQUE NOT NULL,
                file_path TEXT NOT NULL,
                metadata TEXT,
                artwork_url TEXT,
                file_size INTEGER,
                created_at REAL,
                last_accessed REAL,
                access_count INTEGER DEFAULT 0
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_search_key ON cache(search_key)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_last_accessed ON cache(last_accessed)
        """)

        conn.commit()
        conn.close()

    def _get_cache_key(self, search_term: str) -> str:
        """Generate cache key from search term"""
        return hashlib.md5(search_term.lower().encode()).hexdigest()

    def get(self, search_term: str) -> Optional[Dict[str, Any]]:
        """Get cached image and metadata"""
        cache_key = self._get_cache_key(search_term)

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT file_path, metadata, artwork_url
            FROM cache
            WHERE search_key = ?
        """, (cache_key,))

        result = cursor.fetchone()

        if result:
            file_path, metadata_json, artwork_url = result

            # Check if file still exists
            if os.path.exists(file_path):
                # Update access statistics
                cursor.execute("""
                    UPDATE cache
                    SET last_accessed = ?, access_count = access_count + 1
                    WHERE search_key = ?
                """, (time.time(), cache_key))
                conn.commit()
                conn.close()

                metadata = json.loads(metadata_json) if metadata_json else {}

                return {
                    'file_path': file_path,
                    'metadata': metadata,
                    'artwork_url': artwork_url
                }
            else:
                # File deleted, remove from database
                cursor.execute("DELETE FROM cache WHERE search_key = ?", (cache_key,))
                conn.commit()

        conn.close()
        return None

    def put(self, search_term: str, image_data: bytes, metadata: Dict[str, str], artwork_url: str) -> str:
        """Store image in cache"""
        cache_key = self._get_cache_key(search_term)

        # Generate filename
        filename = f"{cache_key}.jpg"
        file_path = self.cache_dir / filename

        # Save image file
        with open(file_path, 'wb') as f:
            f.write(image_data)

        file_size = len(image_data)

        # Store in database
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT OR REPLACE INTO cache
            (search_key, file_path, metadata, artwork_url, file_size, created_at, last_accessed, access_count)
            VALUES (?, ?, ?, ?, ?, ?, ?, COALESCE((SELECT access_count FROM cache WHERE search_key = ?), 0))
        """, (
            cache_key,
            str(file_path),
            json.dumps(metadata),
            artwork_url,
            file_size,
            time.time(),
            time.time(),
            cache_key
        ))

        conn.commit()
        conn.close()

        # Check cache size and cleanup if needed
        self._cleanup_if_needed()

        return str(file_path)

    def _cleanup_if_needed(self):
        """Remove old entries if cache size exceeds limit"""
        total_size = self._get_total_size()

        if total_size > self.max_size_bytes:
            print(f"Cache size ({total_size / 1024 / 1024:.1f} MB) exceeds limit, cleaning up...")
            self._remove_least_recently_used()

    def _get_total_size(self) -> int:
        """Get total cache size in bytes"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("SELECT SUM(file_size) FROM cache")
        result = cursor.fetchone()
        conn.close()

        return result[0] if result[0] else 0

    def _remove_least_recently_used(self):
        """Remove least recently used items until size is acceptable"""
        target_size = self.max_size_bytes * 0.8  # Clean to 80% of max

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Get entries sorted by last access
        cursor.execute("""
            SELECT search_key, file_path, file_size
            FROM cache
            ORDER BY last_accessed ASC
        """)

        entries = cursor.fetchall()
        current_size = self._get_total_size()

        for search_key, file_path, file_size in entries:
            if current_size <= target_size:
                break

            # Delete file
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
            except Exception as e:
                print(f"Error deleting cached file {file_path}: {e}")

            # Remove from database
            cursor.execute("DELETE FROM cache WHERE search_key = ?", (search_key,))
            current_size -= file_size

        conn.commit()
        conn.close()

        print(f"Cache cleaned up to {current_size / 1024 / 1024:.1f} MB")

    def clear(self):
        """Clear entire cache"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("SELECT file_path FROM cache")
        entries = cursor.fetchall()

        # Delete all files
        for (file_path,) in entries:
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
            except Exception as e:
                print(f"Error deleting {file_path}: {e}")

        # Clear database
        cursor.execute("DELETE FROM cache")
        conn.commit()
        conn.close()

        print("Cache cleared")

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*), SUM(file_size) FROM cache")
        count, total_size = cursor.fetchone()

        cursor.execute("SELECT SUM(access_count) FROM cache")
        total_accesses = cursor.fetchone()[0] or 0

        conn.close()

        return {
            'entry_count': count or 0,
            'total_size_mb': (total_size / 1024 / 1024) if total_size else 0,
            'max_size_mb': self.max_size_bytes / 1024 / 1024,
            'total_accesses': total_accesses
        }

    def list_all(self) -> list:
        """List all cached items with metadata"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT search_key, metadata, file_size, created_at, last_accessed, access_count
            FROM cache
            ORDER BY last_accessed DESC
        """)

        entries = []
        for row in cursor.fetchall():
            search_key, metadata_json, file_size, created_at, last_accessed, access_count = row
            metadata = json.loads(metadata_json) if metadata_json else {}

            entries.append({
                'search_key': search_key,
                'title': metadata.get('title', 'Unknown'),
                'artist': metadata.get('artist', 'Unknown'),
                'album': metadata.get('album', 'Unknown'),
                'file_size_mb': file_size / 1024 / 1024,
                'created_at': created_at,
                'last_accessed': last_accessed,
                'access_count': access_count
            })

        conn.close()
        return entries

if __name__ == "__main__":
    # Test cache
    cache = ImageCache()
    print("Cache stats:", cache.get_stats())
