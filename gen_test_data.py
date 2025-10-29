import asyncio
import hashlib
import random
import os
from datetime import datetime
from datetime import timedelta
from decimal import Decimal

import asyncpg
from faker import Faker


POSTGRES_URL = os.getenv("POSTGRES_URL")
if not POSTGRES_URL:
    raise ValueError("POSTGRES_URL is required")


async def gen_test_data():
    fake = Faker()
    conn = await asyncpg.connect(POSTGRES_URL)

    user_ids = []
    for i in range(10):
        user_id = fake.uuid4()
        user_ids.append(user_id)
        payload = os.urandom(16)
        payload_hash = hashlib.sha256(payload).digest()
        expires_at = datetime.utcnow() + timedelta(days=random.randint(-10, 10))
        revoked_at = None
        if i % 3 == 0:
            revoked_at  = datetime.utcnow() + timedelta(days=random.randint(-10, 0))
        await conn.execute(
            """
            INSERT INTO watcher_links (
                user_id,
                payload_hash,
                expires_at,
                revoked_at
            )
            VALUES ($1, $2, $3, $4)
            """,
            user_id,
            payload_hash,
            expires_at,
            revoked_at,
        )
        print(f"Created record in watcher_links with data: {user_id=}, {payload=}, {payload_hash}, {expires_at=}, {revoked_at=}")

    for i in range(10):
        user_id = user_ids[i]
        name = fake.word()
        last_seen_at = datetime.utcnow() - timedelta(days=random.randint(0, 10))
        hashrate_mh = Decimal(str(round(random.uniform(1000, 100000), 3)))
        status = random.choice(["online", "offline", "inactive"])
        await conn.execute(
            """
            INSERT INTO workers (
                user_id,
                name,
                last_seen_at,
                hashrate_mh,
                status
            )
            VALUES ($1, $2, $3, $4, $5)
            """,
            user_id,
            name,
            last_seen_at,
            hashrate_mh,
            status,
        )
        print(f"Created record in workers with data: {user_id=}, {name}, {last_seen_at=}, {hashrate_mh=}, {status=}")

    await conn.close()


if __name__ == "__main__":
    asyncio.run(gen_test_data())
