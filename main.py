import os
from datetime import datetime, date, time as dtime
from io import BytesIO
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from database import create_document, get_documents, db

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ProductionInput(BaseModel):
    # Use Optional with string forward refs to avoid evaluation issues in class scope
    date: Optional['date'] = None
    time: Optional['dtime'] = None
    shift: Optional[str] = None
    line: Optional[str] = None
    product: Optional[str] = None
    operator: Optional[str] = None
    count: int = Field(..., ge=0)
    defects: Optional[int] = Field(default=0, ge=0)
    notes: Optional[str] = None


class ProductionRecord(ProductionInput):
    date: 'date'
    time: Optional['dtime']
    shift: str


@app.get("/")
def read_root():
    return {"message": "Production Tracking API"}


@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }

    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Configured"
            response["database_name"] = db.name if hasattr(db, 'name') else "✅ Connected"
            response["connection_status"] = "Connected"
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️  Connected but Error: {str(e)[:50]}"
        else:
            response["database"] = "⚠️  Available but not initialized"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"

    response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
    response["database_name"] = "✅ Set" if os.getenv("DATABASE_NAME") else "❌ Not Set"
    return response


# Utility to compute shift based on time
FIRST_SHIFT_START = dtime(7, 0)
FIRST_SHIFT_END = dtime(15, 30)  # exclusive upper bound for A
SECOND_SHIFT_START = dtime(15, 30)
SECOND_SHIFT_END = dtime(23, 59, 59)


def compute_shift(entry_time: dtime) -> str:
    if entry_time >= FIRST_SHIFT_START and entry_time < FIRST_SHIFT_END:
        return "A"
    if entry_time >= SECOND_SHIFT_START and entry_time <= SECOND_SHIFT_END:
        return "B"
    raise HTTPException(status_code=400, detail="Time outside defined shifts (A: 07:00-15:30, B: 15:30-24:00)")


@app.post("/api/production")
def create_production(record: ProductionInput):
    now = datetime.now()
    rec_date: date = record.date or now.date()
    rec_time: Optional[dtime] = record.time or dtime(now.hour, now.minute, now.second)

    rec_shift = record.shift
    if rec_shift is None:
        if rec_time is None:
            raise HTTPException(status_code=400, detail="time is required if shift not provided")
        rec_shift = compute_shift(rec_time)
    else:
        if rec_time is not None:
            expected = compute_shift(rec_time)
            if expected != rec_shift:
                pass
        if rec_shift not in ("A", "B"):
            raise HTTPException(status_code=400, detail="shift must be 'A' or 'B'")

    doc = ProductionRecord(
        date=rec_date,
        time=rec_time,
        shift=rec_shift,
        line=record.line,
        product=record.product,
        operator=record.operator,
        count=record.count,
        defects=record.defects or 0,
        notes=record.notes,
    ).model_dump()

    inserted_id = create_document("productionrecord", doc)

    return {
        "status": "ok",
        "id": inserted_id,
        "date": rec_date.isoformat(),
        "shift": rec_shift,
        "message": "Production record saved"
    }


@app.get("/api/production")
def list_production(
    date_str: Optional[str] = Query(default=None, description="Filter by date YYYY-MM-DD"),
    shift: Optional[str] = Query(default=None, description="Filter by shift A or B"),
):
    filter_q = {}
    if date_str:
        try:
            d = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format, expected YYYY-MM-DD")
        filter_q["date"] = d
    if shift:
        if shift not in ("A", "B"):
            raise HTTPException(status_code=400, detail="shift must be 'A' or 'B'")
        filter_q["shift"] = shift

    docs = get_documents("productionrecord", filter_q)

    def to_jsonable(x: dict):
        y = x.copy()
        if "_id" in y:
            y["_id"] = str(y["_id"])  # type: ignore
        if isinstance(y.get("date"), date):
            y["date"] = y["date"].isoformat()
        if isinstance(y.get("time"), dtime):
            y["time"] = y["time"].strftime("%H:%M")
        if isinstance(y.get("created_at"), datetime):
            y["created_at"] = y["created_at"].isoformat()
        if isinstance(y.get("updated_at"), datetime):
            y["updated_at"] = y["updated_at"].isoformat()
        return y

    return [to_jsonable(doc) for doc in docs]


@app.get("/api/production/export")
def export_production(
    date_str: str = Query(..., description="Date YYYY-MM-DD"),
    shift: str = Query(..., description="Shift A or B"),
):
    if shift not in ("A", "B"):
        raise HTTPException(status_code=400, detail="shift must be 'A' or 'B'")
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format, expected YYYY-MM-DD")

    records = get_documents("productionrecord", {"date": d, "shift": shift})

    try:
        from openpyxl import Workbook
    except Exception:
        raise HTTPException(status_code=500, detail="Excel engine not available. Contact administrator.")

    wb = Workbook()
    ws = wb.active
    ws.title = f"{date_str}-Shift-{shift}"

    headers = [
        "Date", "Time", "Shift", "Line", "Product", "Operator", "Good Count", "Defects", "Notes"
    ]
    ws.append(headers)

    total_good = 0
    total_def = 0

    for r in records:
        r_date = r.get("date")
        r_time = r.get("time")
        if isinstance(r_date, date):
            r_date_str = r_date.isoformat()
        else:
            r_date_str = str(r_date)
        if isinstance(r_time, dtime):
            r_time_str = r_time.strftime("%H:%M")
        else:
            r_time_str = r_time or ""
        ws.append([
            r_date_str,
            r_time_str,
            r.get("shift", ""),
            r.get("line", ""),
            r.get("product", ""),
            r.get("operator", ""),
            int(r.get("count", 0) or 0),
            int(r.get("defects", 0) or 0),
            r.get("notes", ""),
        ])
        total_good += int(r.get("count", 0) or 0)
        total_def += int(r.get("defects", 0) or 0)

    ws.append(["", "", "", "", "", "Totals", total_good, total_def, ""])

    for col in ws.columns:
        max_length = 0
        col_letter = col[0].column_letter  # type: ignore
        for cell in col:
            try:
                max_length = max(max_length, len(str(cell.value)))
            except Exception:
                pass
        ws.column_dimensions[col_letter].width = min(max_length + 2, 40)

    output = BytesIO()
    wb.save(output)
    output.seek(0)

    file_name = f"production_{date_str}_shift_{shift}.xlsx"
    headers_dict = {
        'Content-Disposition': f'attachment; filename="{file_name}"'
    }
    return StreamingResponse(output, media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', headers=headers_dict)


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
