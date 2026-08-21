"""Rebuild Redis profile features from Postgres. Does not write vel:* INCR keys."""

from __future__ import annotations

import argparse

from redis import Redis

from payment_platform.config import Settings
from payment_platform.db import PostgresStore
from payment_platform.features.rebuild import FeatureRebuild


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Rebuild Redis customer/merchant/device hashes from Postgres (not Spark)"
    )
    parser.parse_args(argv)
    settings = Settings()
    db = PostgresStore(settings.database_url)
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    try:
        result = FeatureRebuild(db, redis).run()
        print(result)
        return 0
    finally:
        redis.close()
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
