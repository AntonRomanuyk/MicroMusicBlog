import logging
from sqlalchemy import event
from sqlalchemy.orm import Session


from app import cache


@event.listens_for(Session, 'before_commit')
def handle_before_commit(session: Session):

    keys_to_invalidate = set()

    all_touched_objects = list(session.new) + list(session.dirty) + list(session.deleted)

    for obj in all_touched_objects:
        if isinstance(obj, cache.CacheInvalidationMixin):
            keys = obj.get_cache_keys_to_invalidate()
            for key in keys:
                keys_to_invalidate.add(key)

    if keys_to_invalidate:
        logging.info(f"CACHE INVALIDATION on commit: {keys_to_invalidate}")

        for key in keys_to_invalidate:
            try:
                cache.cache_delete(key)
            except Exception as e:
                logging.error(f"FAILED TO DELETE CACHE KEY {key}: {e}")