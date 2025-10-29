import asyncio
import os
import hashlib
import logging
from datetime import datetime
from enum import Enum
from typing import Any
from typing import Optional
from typing import Union
from uuid import UUID

import asyncpg
import base58
import structlog
from fastapi import FastAPI
from fastapi import Depends
from fastapi import HTTPException
from pydantic import BaseModel
from starlette.requests import Request


logging.basicConfig(
    level=logging.DEBUG,
    handlers=[logging.StreamHandler()]
)

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.JSONRenderer()
    ],
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True
)


logger = structlog.get_logger()


POSTGRES_URL = os.getenv("POSTGRES_URL")


class SuccessResponse(BaseModel):
    success: bool = True


app = FastAPI(
    title="Watcher link",
)

@app.on_event("startup")
async def startup():
    app.state.pg_pool = await asyncpg.create_pool(
        POSTGRES_URL,
        min_size=1,
        max_size=10,
    )

@app.on_event("shutdown")
async def shutdown():
    await app.state.pg_pool.close()


@app.get("/healthz", response_model=SuccessResponse)
async def heathcheck(request: Request):
    return {}


class WorkerStatusEnum(str, Enum):
    ONLINE = "online"
    OFFLINE = "offline"
    INACTIVE = "inactive"


class Worker(BaseModel):
    id: str
    name: str
    status: WorkerStatusEnum
    last_seen_at: datetime
    hashrate_th: str


class AggregatedStats(BaseModel):
    online: int
    offline: int
    inactive: int
    total_hashrate_th: str


class DashboardResponse(BaseModel):
    workers: list[Worker]
    agg: AggregatedStats



async def get_postgres_connect(request: Request):
    async with request.app.state.pg_pool.acquire() as conn:
        yield conn


@app.get("/public/w/{token}/dashboard", response_model=DashboardResponse)
async def public_dashboard(request: Request, token: str, conn=Depends(get_postgres_connect)):
    return await fetch_data_by_token(conn, token)


async def fetch_data_by_token(db_conn: asyncpg.Connection, token: str):
    payload_hash = decode_token(token)

    watcher_link_record = await get_watcher_link_record(db_conn, payload_hash)

    if not watcher_link_record:
        raise InvalidToken()

    user_id = watcher_link_record["user_id"]

    async with app.state.pg_pool.acquire() as conn1, app.state.pg_pool.acquire() as conn2:
        workers_task = fetch_workers_by_user_id(conn1, user_id)
        agg_task = get_aggregate_stats(conn2, user_id)
        workers, agg = await asyncio.gather(workers_task, agg_task)

    return DashboardResponse(workers=workers, agg=agg)


def decode_token(token: str) -> bytes:
    """
    Формат: Base58Check (как в биткоине): payload(16 bytes) + checksum(4 bytes = first4(sha256(sha256(payload)))), целиком закодировано Base58.
    """

    try:
        raw_payload = base58.b58decode(token)
    except ValueError:
        logger.debug(f"Invalid Base58 encoding for token: {token}")
        raise InvalidToken()

    if len(raw_payload) != 20:  # 16 bytest(payload) + 4 bytest(checksum)
        logger.debug(f"Invalid token length: expected 20 bytes, got {len(raw_payload)}")
        raise InvalidToken()

    payload = raw_payload[:16]
    checksum_from_token = raw_payload[16:]

    checksum = hashlib.sha256(hashlib.sha256(payload).digest()).digest()[:4]
    if checksum_from_token != checksum:
        logger.debug("Checksum mismatch")
        raise InvalidToken()

    logger.debug("Token decoded successfully")
    return hashlib.sha256(payload).digest()


async def fetch_workers_by_user_id(db_conn: asyncpg.Connection, user_id: Union[UUID, str]) -> list[Worker]:
    worker_records = await filter_workers_by_user_id(db_conn, user_id)

    if not worker_records:
        return []

    workers = []
    for record in worker_records:
        workers.append(
            Worker(
                id=str(record["id"]),
                name=record["name"],
                status=record["status"],
                last_seen_at=record["last_seen_at"],
                hashrate_th=str(record["hashrate_mh"]),  # TODO convert hashrate
            )
        )
    return workers


async def get_aggregate_stats(db_conn: asyncpg.Connection, user_id: Union[UUID, str]) -> AggregatedStats:
    agg_record = await aggregate_stats(db_conn, user_id)
    return AggregatedStats(
        online=agg_record["online"],
        offline=agg_record["offline"],
        inactive=agg_record["inactive"],
        total_hashrate_th=str(agg_record["total_hashrate_th"]),
    )


async def get_watcher_link_record(db_conn: asyncpg.Connection,  payload_hash: bytes) -> Optional[dict[str, Any]]:
    return await db_conn.fetchrow(
        """
        SELECT * FROM watcher_links
        WHERE
            payload_hash = $1
            AND revoked_at IS NULL
            AND expires_at > now()
        """,
        payload_hash,
    )


async def filter_workers_by_user_id(db_conn: asyncpg.Connection, user_id: Union[UUID, str]) -> list[dict[str, Any]]:
    return  await db_conn.fetch(
        """
        SELECT *
        FROM workers
        WHERE user_id = $1
        ORDER BY last_seen_at DESC
        """,
        user_id,
    )


async def aggregate_stats(db_conn: asyncpg.Connection, user_id: Union[UUID, str]) -> dict[str, Any]:
    record = await db_conn.fetchrow(
        """
        SELECT
            SUM(CASE WHEN status = 'online' THEN 1 ELSE 0 END) AS online,
            SUM(CASE WHEN status = 'offline' THEN 1 ELSE 0 END) AS offline,
            SUM(CASE WHEN status = 'inactive' THEN 1 ELSE 0 END) as inactive,
            COALESCE(ROUND(SUM(hashrate_mh) / 1000.0, 3), 0.000) AS total_hashrate_th
        FROM workers
        WHERE user_id = $1
        """,
        user_id,
    )
    if record:
        return record

    return {
        "online": 0,
        "offline": 0,
        "inactive": 0,
        "total_hashrate_th": "0.000",
    }


class APIException(HTTPException):
    status_code: int
    detail: str

    def __init__(self, detail: Optional[str] = None):
        if detail is not None:
            self.detail = detail
        super().__init__(self.status_code, self.detail)


class InvalidToken(APIException):
    status_code = 404
    detail = "Not found or invalid token"
