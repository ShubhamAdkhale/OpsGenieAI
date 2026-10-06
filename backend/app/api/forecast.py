from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.serializers import DISCLAIMER, iso
from app.database import get_db
from app.models import Inventory, Product
from app.services import forecasting

router = APIRouter(tags=["forecast"])


@router.get("/forecast")
def get_forecast(db: Session = Depends(get_db)) -> dict:
    products = db.query(Product).order_by(Product.id).all()
    results = [forecasting.forecast_product(db, p).to_payload() for p in products]
    at_risk = [r for r in results if r["stockout_probability"] >= 0.5]
    return {
        "horizon_days": forecasting.HORIZON_DAYS,
        "products": results,
        "products_at_stockout_risk": len(at_risk),
        "total_recommended_reorder_units": sum(r["recommended_reorder_qty"] for r in results),
        "disclaimer": DISCLAIMER,
    }


@router.get("/inventory")
def get_inventory(db: Session = Depends(get_db)) -> list[dict]:
    rows = db.query(Inventory).order_by(Inventory.id).all()
    return [
        {
            "product_id": row.product_id,
            "product_name": row.product.name,
            "category": row.product.category,
            "current_stock": row.current_stock,
            "unit_value_inr": row.product.unit_value_inr,
            "stock_value_inr": round(row.current_stock * row.product.unit_value_inr, 2),
            "warehouse_city": row.warehouse_city,
            "updated_at": iso(row.updated_at),
        }
        for row in rows
    ]
