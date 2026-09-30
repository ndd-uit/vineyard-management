from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy import text

from app.database import engine
from app.auth import get_current_user
from app.routers.assistant_actions import router as assistant_actions_router
from app.routers.assistant_chat import router as assistant_chat_router
from app.routers.customer_payments import router as customer_payments_router
from app.routers.customers import router as customers_router
from app.routers.expenses import router as expenses_router
from app.routers.gardens import router as gardens_router
from app.routers.grape_varieties import router as grape_varieties_router
from app.routers.harvests import router as harvests_router
from app.routers.labor_records import router as labor_records_router
from app.routers.reports import router as reports_router
from app.routers.sales import router as sales_router
from app.routers.seasons import router as seasons_router
from app.routers.worker_payments import router as worker_payments_router
from app.routers.workers import router as workers_router


app = FastAPI(
    title="Vineyard Management API",
    version="1.0.0",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

for router in (
    gardens_router, grape_varieties_router, seasons_router, harvests_router,
    customers_router, sales_router, customer_payments_router, workers_router,
    labor_records_router, worker_payments_router, expenses_router, reports_router,
    assistant_actions_router, assistant_chat_router,
):
    app.include_router(router, dependencies=[Depends(get_current_user)])


@app.get("/health")
def health():
    return {
        "status": "ok"
    }


@app.get("/db-health", dependencies=[Depends(get_current_user)])
def db_health():
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))

        return {"database": "connected"}

    except Exception:
        raise HTTPException(status_code=503, detail="Database unavailable.") from None
