import asyncio
import logging
from sqlalchemy import event
from sqlalchemy.orm import Session

from app import cache


@event.listens_for(Session, 'before_commit')
def handle_after_commit(session):
    keys_to_invalidate = set()

    all_touched_objects = list(session.new) + list(session.dirty) + list(session.deleted)

    for obj in all_touched_objects:
        if isinstance(obj, cache.CacheInvalidationMixin):
            keys = obj.get_cache_keys_to_invalidate()
            for key in keys:
                keys_to_invalidate.add(key)

    if keys_to_invalidate:
        logging.info(f"CACHE INVALIDATION scheduled for: {keys_to_invalidate}")

    try:
        loop = asyncio.get_event_loop()

        if loop.is_running():
            loop.create_task(delete_keys(keys_to_invalidate))
    except RuntimeError:
        logging.warning("No running event loop found. Cache not invalidated.")


async def delete_keys(keys):
    for key in keys:
        try:
            await cache.cache_delete(key)
        except Exception as e:
            logging.error(f"FAILED TO DELETE CACHE KEY {key}: {e}")
