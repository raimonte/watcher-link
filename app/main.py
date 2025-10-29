from datetime import datetime
from enum import Enum
from uuid import uuid4

from fastapi import FastAPI
from pydantic import BaseModel
from starlette.responses import Response
from starlette.requests import Request


class SuccessResponse(BaseModel):
    success: bool = True


app = FastAPI(
    title="Watcher link",
)

@app.get("/health", response_model=SuccessResponse)
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

"""
Example
{
  "workers": [
    {
      "id": "uuid",
      "name": "string",
      "status": "online|offline|inactive",
      "last_seen_at": "RFC3339Z",
      "hashrate_th": "string with 3 decimals"
    }
  ],
  "agg": {
    "online": 0,
    "offline": 0,
    "inactive": 0,
    "total_hashrate_th": "string with 3 decimals"
  }
}
"""


@app.get("/public/w/{token}/dashboard", response_model=DashboardResponse)
async def public_dashboard(token: str):
    workers = [
        Worker(
            id=str(uuid4()),
            name="worker-1",
            status="online",
            last_seen_at=datetime.utcnow(),
            hashrate_th="123.456",
        ),
        Worker(
            id=str(uuid4()),
            name="worker-2",
            status="offline",
            last_seen_at=datetime.utcnow(),
            hashrate_th="0.001",
        ),
    ]

    agg = AggregatedStats(
        online=1,
        offline=1,
        inactive=0,
        total_hashrate_th="123.457",
    )

    return DashboardResponse(workers=workers, agg=agg)
