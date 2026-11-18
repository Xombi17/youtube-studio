#!/usr/bin/env python3
"""
ClipSurge — High-Performance Redis State, Lock & Task Queue Engine

Provides robust Redis primitives with transparent in-memory fallback:
1. Distributed stream locks (prevents duplicate capture of the same stream)
2. Decoupled clip export queue (`clipsurge:queue:exports`)
3. Autonomous publish & review queue (`clipsurge:queue:publish`)
4. Stream telemetry & status caching (`clipsurge:stream:<id>:state`)
5. Fallback: If Redis is temporarily unreachable, seamlessly uses local memory
   and threading locks so the pipeline never crashes.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import threading
import time
from pathlib import Path
from typing import Any

STUDIO_ROOT = Path(__file__).resolve().parent.parent
if str(STUDIO_ROOT) not in sys.path:
    sys.path.insert(0, str(STUDIO_ROOT))

logger = logging.getLogger("ClipSurge.Redis")

REDIS_HOST = os.environ.get("REDIS_HOST", "localhost")
REDIS_PORT = int(os.environ.get("REDIS_PORT", "6379"))
REDIS_DB = int(os.environ.get("REDIS_DB", "0"))
REDIS_PASSWORD = os.environ.get("REDIS_PASSWORD", None)

KEY_PREFIX = "clipsurge:"
QUEUE_EXPORTS = f"{KEY_PREFIX}queue:exports"
QUEUE_PUBLISH = f"{KEY_PREFIX}queue:publish"
LOCK_PREFIX = f"{KEY_PREFIX}lock:stream:"
STREAM_PREFIX = f"{KEY_PREFIX}stream:"
METRICS_KEY = f"{KEY_PREFIX}metrics"

# Global client and in-memory fallback structures
_redis_client = None
_redis_available = False
_local_locks: dict[str, float] = {}
_local_lock_guard = threading.Lock()
_local_queue_exports: list[dict[str, Any]] = []
_local_queue_publish: list[dict[str, Any]] = []
_local_stream_state: dict[str, dict[str, Any]] = {}


def get_redis_client():
    """Returns a connected Redis client, or None if unavailable."""
    global _redis_client, _redis_available
    if _redis_client is not None and _redis_available:
        return _redis_client

    try:
        import redis
        client = redis.Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            db=REDIS_DB,
            password=REDIS_PASSWORD,
            socket_timeout=2.0,
            socket_connect_timeout=2.0,
            decode_responses=True,
        )
        client.ping()
        _redis_client = client
        _redis_available = True
        return _redis_client
    except Exception as exc:
        _redis_available = False
        _redis_client = None
        return None


def is_redis_connected() -> bool:
    client = get_redis_client()
    return client is not None


# ==============================================================================
# 1. Distributed Stream Locks (Deduplication)
# ==============================================================================

def acquire_stream_lock(stream_url_or_id: str, ttl_sec: int = 3600) -> bool:
    """
    Acquires an exclusive lock for clipping a stream.
    Returns True if lock acquired, False if another worker already owns it.
    """
    key = f"{LOCK_PREFIX}{hash(stream_url_or_id)}"
    client = get_redis_client()
    if client:
        try:
            # SET NX EX
            acquired = client.set(key, f"worker:{os.getpid()}:{int(time.time())}", nx=True, ex=ttl_sec)
            return bool(acquired)
        except Exception as exc:
            logger.warning(f"Redis lock error: {exc}. Falling back to memory.")

    # Local fallback
    with _local_lock_guard:
        now = time.time()
        expiry = _local_locks.get(stream_url_or_id, 0)
        if expiry > now:
            return False
        _local_locks[stream_url_or_id] = now + ttl_sec
        return True


def release_stream_lock(stream_url_or_id: str) -> bool:
    """Releases the stream lock."""
    key = f"{LOCK_PREFIX}{hash(stream_url_or_id)}"
    client = get_redis_client()
    if client:
        try:
            client.delete(key)
            return True
        except Exception:
            pass

    with _local_lock_guard:
        _local_locks.pop(stream_url_or_id, None)
        return True


# ==============================================================================
# 2. Asynchronous Video Export Queue
# ==============================================================================

def push_export_job(job_data: dict[str, Any]) -> bool:
    """Pushes a clip export job into the background rendering queue."""
    client = get_redis_client()
    payload = json.dumps(job_data)
    if client:
        try:
            client.rpush(QUEUE_EXPORTS, payload)
            return True
        except Exception as exc:
            logger.warning(f"Failed to push export job to Redis: {exc}")

    # Fallback
    _local_queue_exports.append(job_data)
    return True


def pop_export_job(timeout: int = 2) -> dict[str, Any] | None:
    """Pops the next clip export job (blocking wait up to timeout seconds)."""
    client = get_redis_client()
    if client:
        try:
            item = client.blpop(QUEUE_EXPORTS, timeout=timeout)
            if item:
                # item is (queue_name, data)
                return json.loads(item[1])
            return None
        except Exception:
            pass

    # Fallback
    if _local_queue_exports:
        return _local_queue_exports.pop(0)
    time.sleep(min(timeout, 0.5))
    return None


# ==============================================================================
# 3. Autonomous Publish & Review Queue
# ==============================================================================

def push_publish_job(clip_record: dict[str, Any]) -> bool:
    """Pushes a staged clip to the publish reviewer queue."""
    client = get_redis_client()
    payload = json.dumps(clip_record)
    if client:
        try:
            client.rpush(QUEUE_PUBLISH, payload)
            return True
        except Exception as exc:
            logger.warning(f"Failed to push publish job to Redis: {exc}")

    _local_queue_publish.append(clip_record)
    return True


def pop_publish_job(timeout: int = 2) -> dict[str, Any] | None:
    """Pops the next publish review job."""
    client = get_redis_client()
    if client:
        try:
            item = client.blpop(QUEUE_PUBLISH, timeout=timeout)
            if item:
                return json.loads(item[1])
            return None
        except Exception:
            pass

    if _local_queue_publish:
        return _local_queue_publish.pop(0)
    time.sleep(min(timeout, 0.5))
    return None


# ==============================================================================
# 4. Stream Telemetry & Real-Time Metrics Cache
# ==============================================================================

def set_stream_telemetry(stream_slug: str, telemetry: dict[str, Any], ttl_sec: int = 60) -> None:
    """Stores high-frequency stream metrics (current virality score, chat rate, viewers, FPS)."""
    client = get_redis_client()
    key = f"{STREAM_PREFIX}{stream_slug}:state"
    if client:
        try:
            client.set(key, json.dumps(telemetry), ex=ttl_sec)
            return
        except Exception:
            pass

    _local_stream_state[stream_slug] = telemetry


def get_stream_telemetry(stream_slug: str) -> dict[str, Any] | None:
    """Fetches real-time stream metrics."""
    client = get_redis_client()
    key = f"{STREAM_PREFIX}{stream_slug}:state"
    if client:
        try:
            raw = client.get(key)
            if raw:
                return json.loads(raw)
            return None
        except Exception:
            pass

    return _local_stream_state.get(stream_slug)


def record_system_event(event_type: str, details: dict[str, Any]) -> None:
    """Appends an event to the global studio event stream."""
    client = get_redis_client()
    event = {
        "timestamp": time.time(),
        "type": event_type,
        "details": details,
    }
    if client:
        try:
            client.lpush(f"{KEY_PREFIX}events", json.dumps(event))
            client.ltrim(f"{KEY_PREFIX}events", 0, 999)
            return
        except Exception:
            pass


if __name__ == "__main__":
    print(f"ClipSurge Redis Engine Check:")
    print(f"Connected: {is_redis_connected()} (host={REDIS_HOST}:{REDIS_PORT})")
    test_key = "test_stream_123"
    print(f"Acquiring lock: {acquire_stream_lock(test_key, ttl_sec=5)}")
    print(f"Acquiring lock again (should be False): {acquire_stream_lock(test_key, ttl_sec=5)}")
    print(f"Releasing lock: {release_stream_lock(test_key)}")
    print(f"Acquiring lock after release (should be True): {acquire_stream_lock(test_key, ttl_sec=5)}")
    release_stream_lock(test_key)
