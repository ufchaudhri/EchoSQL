"""
Redis cache service for embedding caching and query result caching.
Handles both semantic embeddings and query result caching with TTL.
"""

import json
import hashlib
from typing import Optional, Any, Dict
from datetime import timedelta
import redis
import asyncio
from contextlib import asynccontextmanager


class RedisCache:
    """Redis cache for embeddings and query results."""
    
    def __init__(self, host: str = "localhost", port: int = 6379, db: int = 0):
        """
        Initialize Redis connection.
        
        Args:
            host: Redis server hostname (default: localhost)
            port: Redis server port (default: 6379)
            db: Redis database number (default: 0)
        """
        self.host = host
        self.port = port
        self.db = db
        self.client = None
        self.async_client = None
    
    def connect(self) -> bool:
        """Connect to Redis server."""
        try:
            self.client = redis.Redis(
                host=self.host,
                port=self.port,
                db=self.db,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_keepalive=True,
                health_check_interval=30
            )
            # Test connection
            self.client.ping()
            print(f"✓ Connected to Redis at {self.host}:{self.port}")
            return True
        except Exception as e:
            print(f"✗ Failed to connect to Redis: {e}")
            return False
    
    async def connect_async(self) -> bool:
        """Connect to Redis async client."""
        try:
            import redis.asyncio as aioredis
            self.async_client = aioredis.from_url(
                f"redis://{self.host}:{self.port}/{self.db}",
                decode_responses=True,
                socket_connect_timeout=5,
                socket_keepalive=True,
                health_check_interval=30
            )
            # Test connection
            await self.async_client.ping()
            print(f"✓ Connected to Redis (async) at {self.host}:{self.port}")
            return True
        except Exception as e:
            print(f"✗ Failed to connect to Redis (async): {e}")
            return False
    
    def close(self):
        """Close Redis connection."""
        if self.client:
            self.client.close()
    
    async def close_async(self):
        """Close async Redis connection."""
        if self.async_client:
            await self.async_client.close()
    
    # ==================== Embedding Cache ====================
    
    def cache_embedding(
        self,
        query: str,
        embedding: list,
        ttl_hours: int = 24
    ) -> bool:
        """
        Cache an embedding vector for a query.
        
        Args:
            query: The original query text
            embedding: Embedding vector (list of floats)
            ttl_hours: Time-to-live in hours (default: 24)
        
        Returns:
            True if cached successfully, False otherwise
        """
        try:
            key = f"embedding:{hashlib.md5(query.encode()).hexdigest()}"
            value = json.dumps({
                "query": query,
                "embedding": embedding,
                "cached_at": str(__import__('datetime').datetime.now())
            })
            ttl = timedelta(hours=ttl_hours)
            self.client.setex(key, ttl, value)
            return True
        except Exception as e:
            print(f"Error caching embedding: {e}")
            return False
    
    def get_embedding(self, query: str) -> Optional[Dict]:
        """
        Retrieve cached embedding for a query.
        
        Args:
            query: The query text to look up
        
        Returns:
            Dict with 'embedding' key if found, None otherwise
        """
        try:
            key = f"embedding:{hashlib.md5(query.encode()).hexdigest()}"
            cached = self.client.get(key)
            if cached:
                return json.loads(cached)
            return None
        except Exception as e:
            print(f"Error retrieving embedding: {e}")
            return None
    
    async def cache_embedding_async(
        self,
        query: str,
        embedding: list,
        ttl_hours: int = 24
    ) -> bool:
        """Async version of cache_embedding."""
        try:
            key = f"embedding:{hashlib.md5(query.encode()).hexdigest()}"
            value = json.dumps({
                "query": query,
                "embedding": embedding,
                "cached_at": str(__import__('datetime').datetime.now())
            })
            ttl = timedelta(hours=ttl_hours)
            await self.async_client.setex(key, ttl, value)
            return True
        except Exception as e:
            print(f"Error caching embedding (async): {e}")
            return False
    
    async def get_embedding_async(self, query: str) -> Optional[Dict]:
        """Async version of get_embedding."""
        try:
            key = f"embedding:{hashlib.md5(query.encode()).hexdigest()}"
            cached = await self.async_client.get(key)
            if cached:
                return json.loads(cached)
            return None
        except Exception as e:
            print(f"Error retrieving embedding (async): {e}")
            return None
    
    # ==================== Query Result Cache ====================
    
    def cache_query_result(
        self,
        sql_query: str,
        result: Any,
        ttl_minutes: int = 5
    ) -> bool:
        """
        Cache SQL query results.
        
        Args:
            sql_query: The SQL query string
            result: Query results (will be JSON serialized)
            ttl_minutes: Time-to-live in minutes (default: 5)
        
        Returns:
            True if cached successfully, False otherwise
        """
        try:
            key = f"query_result:{hashlib.md5(sql_query.encode()).hexdigest()}"
            value = json.dumps({
                "sql": sql_query,
                "result": result,
                "cached_at": str(__import__('datetime').datetime.now())
            }, default=str)  # default=str for datetime serialization
            ttl = timedelta(minutes=ttl_minutes)
            self.client.setex(key, ttl, value)
            return True
        except Exception as e:
            print(f"Error caching query result: {e}")
            return False
    
    def get_query_result(self, sql_query: str) -> Optional[Dict]:
        """
        Retrieve cached query results.
        
        Args:
            sql_query: The SQL query string to look up
        
        Returns:
            Dict with 'result' key if found, None otherwise
        """
        try:
            key = f"query_result:{hashlib.md5(sql_query.encode()).hexdigest()}"
            cached = self.client.get(key)
            if cached:
                return json.loads(cached)
            return None
        except Exception as e:
            print(f"Error retrieving query result: {e}")
            return None
    
    async def cache_query_result_async(
        self,
        sql_query: str,
        result: Any,
        ttl_minutes: int = 5
    ) -> bool:
        """Async version of cache_query_result."""
        try:
            key = f"query_result:{hashlib.md5(sql_query.encode()).hexdigest()}"
            value = json.dumps({
                "sql": sql_query,
                "result": result,
                "cached_at": str(__import__('datetime').datetime.now())
            }, default=str)
            ttl = timedelta(minutes=ttl_minutes)
            await self.async_client.setex(key, ttl, value)
            return True
        except Exception as e:
            print(f"Error caching query result (async): {e}")
            return False
    
    async def get_query_result_async(self, sql_query: str) -> Optional[Dict]:
        """Async version of get_query_result."""
        try:
            key = f"query_result:{hashlib.md5(sql_query.encode()).hexdigest()}"
            cached = await self.async_client.get(key)
            if cached:
                return json.loads(cached)
            return None
        except Exception as e:
            print(f"Error retrieving query result (async): {e}")
            return None
    
    # ==================== Cache Statistics ====================
    
    def get_stats(self) -> Dict[str, Any]:
        """Get Redis cache statistics."""
        try:
            info = self.client.info()
            return {
                "connected": True,
                "used_memory": info.get("used_memory_human", "N/A"),
                "used_memory_peak": info.get("used_memory_peak_human", "N/A"),
                "total_connections": info.get("total_connections_received", 0),
                "total_commands": info.get("total_commands_processed", 0),
                "db_keys": self.client.dbsize(),
            }
        except Exception as e:
            print(f"Error getting Redis stats: {e}")
            return {"connected": False, "error": str(e)}
    
    def clear_cache(self, pattern: Optional[str] = None) -> int:
        """
        Clear cache entries.
        
        Args:
            pattern: Optional pattern to match (e.g., 'embedding:*', 'query_result:*')
        
        Returns:
            Number of keys deleted
        """
        try:
            if pattern:
                keys = self.client.keys(pattern)
                if keys:
                    return self.client.delete(*keys)
                return 0
            else:
                # Clear entire database
                self.client.flushdb()
                return True
        except Exception as e:
            print(f"Error clearing cache: {e}")
            return 0


# Global instance
_redis_cache: Optional[RedisCache] = None


def get_redis_cache() -> RedisCache:
    """Get or create Redis cache instance."""
    global _redis_cache
    if _redis_cache is None:
        _redis_cache = RedisCache()
    return _redis_cache


@asynccontextmanager
async def redis_session():
    """Context manager for Redis async operations."""
    cache = get_redis_cache()
    await cache.connect_async()
    try:
        yield cache
    finally:
        await cache.close_async()
