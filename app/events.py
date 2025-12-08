import asyncio
import logging

from sqlalchemy import event
from sqlalchemy.orm import Session

from app import cache


@event.listens_for(Session, "before_commit")
def handle_before_commit(session: Session):
    keys_to_invalidate: set[str] = set()

    touched = list(session.new) + list(session.dirty) + list(session.deleted)
    for obj in touched:
        if isinstance(obj, cache.CacheInvalidationMixin):
            keys_to_invalidate.update(obj.get_cache_keys_to_invalidate())

    if not keys_to_invalidate:
        return

    logging.info(f"CACHE INVALIDATION scheduled for: {keys_to_invalidate}")

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        logging.warning("No running event loop found. Cache not invalidated.")
        return

    loop.create_task(_delete_keys(keys_to_invalidate))


async def _delete_keys(keys: set[str]):
    for key in keys:
        try:
            await cache.cache_delete(key)
        except Exception as exc:
            logging.error(f"FAILED TO DELETE CACHE KEY {key}: {exc}")
