import asyncio
import logging
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession


from app import cache


@event.listens_for(AsyncSession, 'after_commit')
def handle_after_commit(session):

    keys_to_invalidate = set()

    all_touched_objects = list(session.new) + list(session.dirty) + list(session.deleted)

    for obj in all_touched_objects:
        if isinstance(obj, cache.CacheInvalidationMixin):
            keys_to_invalidate.update(obj.get_cache_keys_to_invalidate())

    if keys_to_invalidate:
        logging.info("CACHE INVALIDATION on commit %s:", keys_to_invalidate)

        async def delete_keys():
            for key in keys_to_invalidate:
                try:
                    await cache.cache_delete(key)
                except Exception as e:
                    logging.error("FAILED TO DELETE CACHE KEY %s: %s", key, e)

        asyncio.create_task(delete_keys())