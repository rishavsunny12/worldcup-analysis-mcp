import hashlib
import json
import logging

from cachetools import TTLCache

from config import settings

logger = logging.getLogger(__name__)


class CacheManager:
    def __init__(self):
        self._caches = {
            "live":      TTLCache(maxsize=50,  ttl=settings.CACHE_TTL_LIVE),
            "lineups":   TTLCache(maxsize=100, ttl=settings.CACHE_TTL_LINEUPS),
            "form":      TTLCache(maxsize=100, ttl=settings.CACHE_TTL_FORM),
            "fixtures":  TTLCache(maxsize=10,  ttl=settings.CACHE_TTL_FIXTURES),
            "standings": TTLCache(maxsize=20,  ttl=settings.CACHE_TTL_STANDINGS),
            "h2h":       TTLCache(maxsize=200, ttl=settings.CACHE_TTL_H2H),
            "scorers":   TTLCache(maxsize=5,   ttl=settings.CACHE_TTL_SCORERS),
            "squad":     TTLCache(maxsize=100, ttl=3600),
        }
        self._hits = {k: 0 for k in self._caches}
        self._misses = {k: 0 for k in self._caches}

    def _key(self, **kwargs) -> str:
        return hashlib.md5(json.dumps(kwargs, sort_keys=True).encode()).hexdigest()

    def get(self, cache_name: str, **kwargs):
        key = self._key(**kwargs)
        val = self._caches[cache_name].get(key)
        if val is not None:
            self._hits[cache_name] += 1
            logger.info(f"Cache hit [{cache_name}] {kwargs}")
        else:
            self._misses[cache_name] += 1
            logger.info(f"Cache miss [{cache_name}] {kwargs}")
        return val

    def set(self, cache_name: str, value, **kwargs):
        key = self._key(**kwargs)
        self._caches[cache_name][key] = value

    def stats(self) -> dict:
        return {k: {"hits": self._hits[k], "misses": self._misses[k]} for k in self._caches}


cache = CacheManager()
