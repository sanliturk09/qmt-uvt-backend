import os
import calendar
from datetime import datetime, date, timedelta
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from database import get_db_cursor
from auth import verify_password, hash_password, create_access_token, get_current_user, require_role

app = FastAPI(title="UVT Üretim Takip API", version="1.0.0")

class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    role: str
    factory: str
    full_name: str

class StationLiveStatus(BaseModel):
    category_id: int
    station_code: str
    station_name: str
    status: str
    current_op_id: Optional[int] = None
    sap_doc_num: Optional[int] = None
    item_code: Optional[str] = None
    item_description: Optional[str] = None
    operator_name: Optional[str] = None
    pause_reason: Optional[str] = None
    started_at: Optional[str] = None

class ScheduleJobRequest(BaseModel):
    operation_id: int
    scheduled_date: Optional[str] = None
    workstation_id: Optional[int] = None

class BulkScheduleJobRequest(BaseModel):
    operation_ids: List[int]
    scheduled_date: str
    workstation_id: Optional[int] = None

class CockpitOperationItem(BaseModel):
    id: int
    sap_doc_entry: int
    sap_doc_num: int
    item_code: str
    item_description: Optional[str] = None
    category_id: Optional[int] = None
    category_name: Optional[str] = None
    stage_order: int
    status: str
    is_unlocked: bool
    scheduled_date: Optional[str] = None
    planned_qty: float
    completed_qty: float
    planned_duration_min: float = 0.0
    assigned_workstation_id: Optional[int] = None
    workstation_code: Optional[str] = None
    progress_pct: Optional[float] = 0.0
    progress_pct: Optional[float] = 0.0
    elapsed_work_seconds: float = 0.0
    is_overdue: bool = False

class UserCreateRequest(BaseModel):
    username: str
    password: str
    full_name: str
    factory_location: str
    role: str
    categories: List[str]

class UserResponse(BaseModel):
    id: int
    username: str
    full_name: str
    factory_location: str
    role: str
    is_active: bool
    categories: List[str]

class UpdateDailyCapacityRequest(BaseModel):
    category_id: int
    work_date: str
    worker_count: int

class MonthDayCapacity(BaseModel):
    work_date: str
    total_load_min: float
    capacity_min: float
    occupancy_pct: float
    status_color: str

class SyncResponse(BaseModel):
    message: str
    synced_orders_count: int
    synced_operations_count: int

class OperationResponse(BaseModel):
    id: int
    sap_doc_entry: int
    sap_doc_num: int
    item_code: str
    item_description: Optional[str]
    category_name: str
    stage_order: int
    status: str
    is_unlocked: bool
    is_scheduled_today: bool
    scheduled_date: Optional[str]
    next_category_name: Optional[str]
    planned_qty: float
    completed_qty: float
    assigned_workstation_id: Optional[int] = None
    assigned_workstation_id: Optional[int] = None
    planned_duration_min: float = 0.0
    elapsed_work_seconds: float = 0.0

class JobActionRequest(BaseModel):
    operation_id: int
    target_user_id: Optional[int] = None
    batch_number: Optional[str] = None
    operator_note: Optional[str] = None
    completed_qty: Optional[float] = 0.0
    scrapped_qty: Optional[float] = 0.0

class OfflineLogItem(BaseModel):
    operation_id: int
    event_type: str
    timestamp: str
    batch_number: Optional[str] = None
    operator_note: Optional[str] = None
    completed_qty: Optional[float] = 0.0
    scrapped_qty: Optional[float] = 0.0

class OfflineSyncRequest(BaseModel):
    logs: List[OfflineLogItem]

class WorkstationItem(BaseModel):
    id: int
    category_id: int
    station_code: str
    station_name: str


@app.get("/")
def serve_index():
    return FileResponse("static/index.html")

@app.get("/station")
def serve_station():
    return FileResponse("static/station.html")

@app.get("/cockpit")
def serve_cockpit():
    return FileResponse("static/cockpit.html")


class CloseOrdersRequest(BaseModel):
    sap_doc_entries: List[int]

@app.get("/api/cockpit/shipping-orders")
def get_shipping_orders(current_user: dict = Depends(get_current_user)):
    if current_user.get("role") not in ["ADMIN", "PLANNER"]:
        raise HTTPException(status_code=403, detail="Bu işlem için yetkiniz yok.")

    factory = current_user.get("factory", "TR")
    try:
        with get_db_cursor() as cur:
            cur.execute("""
                SELECT 
                    po.sap_doc_entry,
                    po.sap_doc_num,
                    po.item_code,
                    po.item_description,
                    po.planned_qty,
                    po.plan_due_date,
                    ISNULL(MAX(op.completed_qty), po.planned_qty) AS completed_qty
                FROM dbo.ProductionOrders po
                INNER JOIN dbo.ProductionOperations op ON po.sap_doc_entry = op.sap_doc_entry
                WHERE po.sap_factory = ? 
                  AND (po.status IS NULL OR po.status != 'CLOSED')
                GROUP BY 
                    po.sap_doc_entry, po.sap_doc_num, po.item_code, 
                    po.item_description, po.planned_qty, po.plan_due_date
                HAVING 
                    COUNT(CASE WHEN op.status != 'COMPLETED' THEN 1 END) = 0
                ORDER BY po.sap_doc_num DESC
            """, (factory,))
            rows = cur.fetchall()

            result = []
            for r in rows:
                due_d = r[5].isoformat() if hasattr(r[5], 'isoformat') else (str(r[5]) if r[5] else None)
                result.append({
                    "sap_doc_entry": r[0],
                    "sap_doc_num": r[1],
                    "item_code": r[2],
                    "item_description": r[3],
                    "planned_qty": float(r[4] or 0),
                    "due_date": due_d,
                    "completed_qty": float(r[6] or 0)
                })
            return result
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/cockpit/close-orders")
def close_production_orders(data: CloseOrdersRequest, current_user: dict = Depends(get_current_user)):
    if current_user.get("role") not in ["ADMIN", "PLANNER"]:
        raise HTTPException(status_code=403, detail="Bu işlem için yetkiniz yok.")

    if not data.sap_doc_entries:
        raise HTTPException(status_code=400, detail="Hiç sipariş seçilmedi.")

    try:
        with get_db_cursor() as cur:
            placeholders = ",".join(["?"] * len(data.sap_doc_entries))

            cur.execute(f"""
                UPDATE dbo.ProductionOrders
                SET status = 'CLOSED'
                WHERE sap_doc_entry IN ({placeholders})
            """, tuple(data.sap_doc_entries))

            cur.execute(f"""
                UPDATE dbo.ProductionOperations
                SET status = 'COMPLETED'
                WHERE sap_doc_entry IN ({placeholders})
            """, tuple(data.sap_doc_entries))

        return {"message": f"{len(data.sap_doc_entries)} adet sipariş tamamlandı ve arşivlendi."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



@app.post("/api/login", response_model=TokenResponse)
def login(data: LoginRequest):
    with get_db_cursor() as cur:
        cur.execute(
            "SELECT id, password_hash, full_name, factory_location, role, is_active FROM dbo.Users WHERE username = ?",
            (data.username,)
        )
        user = cur.fetchone()

        if not user or not verify_password(data.password, user[1]):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Geçersiz kullanıcı adı veya şifre.")

        if not user[5]:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Kullanıcı hesabı pasif durumdadır.")

        user_id, full_name, factory, role = user[0], user[2], user[3], user[4]
        token_data = {"sub": str(user_id), "user_id": user_id, "username": data.username, "role": role, "factory": factory}
        token = create_access_token(token_data)

        return {
            "access_token": token,
            "token_type": "bearer",
            "role": role,
            "factory": factory,
            "full_name": full_name
        }


@app.post("/api/users", status_code=status.HTTP_201_CREATED)
def create_user(data: UserCreateRequest, current_user: dict = Depends(require_role(["ADMIN"]))):
    if data.factory_location not in ["TR", "DE"]:
        raise HTTPException(status_code=400, detail="Fabrika konumu sadece 'TR' veya 'DE' olabilir.")
    if data.role not in ["ADMIN", "PLANNER", "OPERATOR"]:
        raise HTTPException(status_code=400, detail="Geçersiz rol tanımı.")

    hashed_pwd = hash_password(data.password)

    with get_db_cursor() as cur:
        cur.execute("SELECT id FROM dbo.Users WHERE username = ?", (data.username,))
        if cur.fetchone():
            raise HTTPException(status_code=400, detail="Bu kullanıcı adı zaten kullanımda.")

        cur.execute("""
            INSERT INTO dbo.Users (username, password_hash, full_name, factory_location, role, is_active)
            OUTPUT INSERTED.id
            VALUES (?, ?, ?, ?, ?, 1)
        """, (data.username, hashed_pwd, data.full_name, data.factory_location, data.role))
        new_user_id = cur.fetchone()[0]

        for cat in data.categories:
            cur.execute("INSERT INTO dbo.UserCategories (user_id, category_name) VALUES (?, ?)", (new_user_id, cat.upper()))

    return {"message": "Personel başarıyla oluşturuldu.", "user_id": new_user_id}


@app.get("/api/users", response_model=List[UserResponse])
def list_users(current_user: dict = Depends(require_role(["ADMIN", "PLANNER"]))):
    with get_db_cursor() as cur:
        cur.execute("SELECT id, username, full_name, factory_location, role, is_active FROM dbo.Users")
        users = cur.fetchall()

        result = []
        for u in users:
            uid = u[0]
            cur.execute("SELECT category_name FROM dbo.UserCategories WHERE user_id = ?", (uid,))
            cats = [row[0] for row in cur.fetchall()]
            result.append({
                "id": uid,
                "username": u[1],
                "full_name": u[2],
                "factory_location": u[3],
                "role": u[4],
                "is_active": bool(u[5]),
                "categories": cats
            })
        return result


@app.post("/api/jobs/sync-from-sap", response_model=SyncResponse)
def sync_jobs_from_sap(current_user: dict = Depends(require_role(["ADMIN", "PLANNER"]))):
    factory = current_user.get("factory", "TR")
    view_name = f"dbo.vw_SAP_ReleasedOperations_{factory}"

    with get_db_cursor() as cur:
        cur.execute(f"""
            INSERT INTO dbo.ProductionOrders 
                (sap_factory, sap_doc_entry, sap_doc_num, item_code, item_description, planned_qty, status, plan_start_date, plan_due_date)
            SELECT DISTINCT 
                v.sap_factory, v.sap_doc_entry, v.sap_doc_num, v.item_code, v.item_description, v.planned_qty, 'RELEASED', v.plan_start_date, v.plan_due_date
            FROM {view_name} v
            WHERE NOT EXISTS (
                SELECT 1 FROM dbo.ProductionOrders po 
                WHERE po.sap_factory = v.sap_factory AND po.sap_doc_entry = v.sap_doc_entry
            )
        """)
        synced_orders_count = cur.rowcount

        cur.execute(f"""
            INSERT INTO dbo.ProductionOperations
                (sap_doc_entry, sap_line_num, stage_id, stage_order, resource_code, category_name, category_id, status, is_unlocked, planned_qty, completed_qty, scrapped_qty, planned_duration_min)
            SELECT 
                v.sap_doc_entry,
                v.sap_line_num,
                v.stage_id,
                v.stage_order,
                v.resource_code,
                v.category_name,
                sc.id AS category_id,
                CASE WHEN v.stage_order = 1 THEN 'PENDING' ELSE 'LOCKED' END AS status,
                CASE WHEN v.stage_order = 1 THEN 1 ELSE 0 END AS is_unlocked,
                v.planned_qty,
                0.0,
                0.0,
                ISNULL(v.planned_duration_min, 0.0)
            FROM {view_name} v
            LEFT JOIN dbo.StationCategories sc ON 
                v.category_name COLLATE Latin1_General_CI_AI LIKE '%' + sc.code + '%' 
                OR sc.category_name COLLATE Latin1_General_CI_AI LIKE '%' + v.category_name + '%'
                OR v.category_name COLLATE Latin1_General_CI_AI LIKE '%' + sc.category_name + '%'
            WHERE NOT EXISTS (
                SELECT 1 FROM dbo.ProductionOperations op 
                WHERE op.sap_doc_entry = v.sap_doc_entry AND op.sap_line_num = v.sap_line_num
            )
        """)
        synced_ops_count = cur.rowcount

    return {
        "message": "SAP verileri başarıyla senkronize edildi.",
        "synced_orders_count": synced_orders_count if synced_orders_count >= 0 else 0,
        "synced_operations_count": synced_ops_count if synced_ops_count >= 0 else 0
    }

@app.get("/api/jobs/queue", response_model=List[OperationResponse])
def get_job_queue(
        category_id: Optional[int] = None,
        workstation_id: Optional[int] = None,
        current_user: dict = Depends(get_current_user)
):
    try:
        factory = current_user.get("factory", "TR")
        user_role = current_user.get("role")
        raw_id = current_user.get("user_id") or current_user.get("sub") or current_user.get("id")
        user_id = int(raw_id) if raw_id else 0

        with get_db_cursor() as cur:
            user_cat_ids = []

            if user_role == "OPERATOR":
                cur.execute("SELECT category_id FROM dbo.UserCategories WHERE user_id = ?", (user_id,))
                user_cat_ids = [int(r[0]) for r in cur.fetchall()]
                if not user_cat_ids:
                    return []

            query = """
                WITH OpElapsed AS (
                    SELECT 
                        operation_id,
                        SUM(DATEDIFF(second, actual_start_utc, ISNULL(actual_end_utc, GETUTCDATE()))) AS elapsed_sec
                    FROM dbo.JobTimeLogs
                    WHERE event_type = 'START'
                    GROUP BY operation_id
                ),
                OpsWithNext AS (
                    SELECT 
                        op.id, op.sap_doc_entry, po.sap_doc_num, po.item_code, 
                        po.item_description, op.category_name, op.stage_order, 
                        op.status, op.is_unlocked, op.scheduled_date, op.planned_qty, op.completed_qty,
                        op.category_id, po.sap_factory, op.assigned_workstation_id,
                        sc.code AS category_code,
                        ISNULL(op.planned_duration_min, 0.0) AS planned_duration_min,
                        LEAD(op.category_name) OVER (PARTITION BY op.sap_doc_entry ORDER BY op.stage_order ASC) AS next_stage_name
                    FROM dbo.ProductionOperations op
                    INNER JOIN dbo.ProductionOrders po ON op.sap_doc_entry = po.sap_doc_entry
                    LEFT JOIN dbo.StationCategories sc ON op.category_id = sc.id
                )
                SELECT 
                    o.id, o.sap_doc_entry, o.sap_doc_num, o.item_code, 
                    o.item_description, o.category_name, o.stage_order, 
                    o.status, o.is_unlocked, o.scheduled_date, o.planned_qty, o.completed_qty, 
                    o.next_stage_name, o.assigned_workstation_id, o.planned_duration_min,
                    ISNULL(oe.elapsed_sec, 0.0) AS elapsed_sec
                FROM OpsWithNext o
                LEFT JOIN OpElapsed oe ON o.id = oe.operation_id
                WHERE o.sap_factory = ? 
                  AND o.is_unlocked = 1 
                  AND o.status != 'COMPLETED'
            """
            params = [factory]

            if user_role == "OPERATOR":
                placeholders = ",".join(["?"] * len(user_cat_ids))
                query += f" AND o.category_id IN ({placeholders})"
                params.extend(user_cat_ids)

                cur.execute("SELECT username FROM dbo.Users WHERE id = ?", (user_id,))
                u_row = cur.fetchone()
                uname = (u_row[0] if u_row else "").upper().replace(" ", "").replace("-", "")

                if uname.startswith("KYN"):
                    num_part = ''.join(filter(str.isdigit, uname))
                    if num_part:
                        formatted_code = f"KYN-{int(num_part):02d}"
                        query += """
                            AND o.assigned_workstation_id = (
                                SELECT TOP 1 id FROM dbo.Workstations 
                                WHERE station_code = ? AND is_active = 1
                            )
                        """
                        params.append(formatted_code)

                query += """
                    AND (
                        o.category_code NOT IN ('LZR', 'KYN')
                        OR (
                            o.category_code IN ('LZR', 'KYN') 
                            AND o.scheduled_date <= CAST(GETDATE() AS DATE) 
                            AND o.assigned_workstation_id IS NOT NULL
                        )
                    )
                """
            else:
                if category_id:
                    query += " AND o.category_id = ?"
                    params.append(category_id)

            if workstation_id:
                query += " AND o.assigned_workstation_id = ?"
                params.append(workstation_id)

            query += """
                ORDER BY 
                    CASE 
                        WHEN o.status = 'IN_PROGRESS' THEN 1
                        WHEN o.status = 'PAUSED' THEN 2
                        WHEN o.status = 'PENDING' THEN 3
                        ELSE 4
                    END ASC,
                    o.stage_order ASC,
                    o.sap_doc_num ASC
            """
            cur.execute(query, tuple(params))
            rows = cur.fetchall()

            result = []
            for r in rows:
                sched_date = r[9].isoformat() if hasattr(r[9], 'isoformat') else (str(r[9]) if r[9] else None)

                result.append({
                    "id": r[0],
                    "sap_doc_entry": r[1],
                    "sap_doc_num": r[2],
                    "item_code": r[3],
                    "item_description": r[4],
                    "category_name": r[5],
                    "stage_order": r[6],
                    "status": r[7],
                    "is_unlocked": bool(r[8]),
                    "is_scheduled_today": True,
                    "scheduled_date": sched_date,
                    "next_category_name": r[12] or "Sevkiyat / Depo",
                    "planned_qty": float(r[10]),
                    "completed_qty": float(r[11]),
                    "assigned_workstation_id": r[13],
                    "planned_duration_min": float(r[14]),
                    "elapsed_work_seconds": float(r[15])
                })

            return result

    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/jobs/start")
def start_job(data: JobActionRequest, current_user: dict = Depends(get_current_user)):
    raw_id = current_user.get("user_id") or current_user.get("sub")
    user_id = int(raw_id) if raw_id else 0

    if data.target_user_id and current_user.get("role") in ["ADMIN", "PLANNER"]:
        user_id = data.target_user_id

    with get_db_cursor() as cur:
        cur.execute("SELECT status, is_unlocked FROM dbo.ProductionOperations WHERE id = ?", (data.operation_id,))
        op = cur.fetchone()
        if not op:
            raise HTTPException(status_code=404, detail="Operasyon bulunamadı.")

        status_val, is_unlocked = op[0], bool(op[1])

        if not is_unlocked:
            raise HTTPException(status_code=400, detail="Bu operasyon henüz kilitli! Önceki operasyon tamamlanmalıdır.")

        if status_val == "IN_PROGRESS":
            raise HTTPException(status_code=400, detail="Bu operasyon zaten çalışıyor.")

        cur.execute("""
            UPDATE dbo.ProductionOperations 
            SET status = 'IN_PROGRESS', assigned_user_id = ? 
            WHERE id = ?
        """, (user_id, data.operation_id))

        cur.execute("""
            INSERT INTO dbo.JobTimeLogs (operation_id, user_id, event_type, batch_number, operator_note, actual_start_utc)
            VALUES (?, ?, 'START', ?, ?, GETUTCDATE())
        """, (data.operation_id, user_id, data.batch_number, data.operator_note))

    return {"message": "İş başlatıldı.", "operation_id": data.operation_id, "status": "IN_PROGRESS"}


@app.post("/api/jobs/pause")
def pause_job(data: JobActionRequest, current_user: dict = Depends(get_current_user)):
    raw_id = current_user.get("user_id") or current_user.get("sub")
    user_id = int(raw_id) if raw_id else 0

    if data.target_user_id and current_user.get("role") in ["ADMIN", "PLANNER"]:
        user_id = data.target_user_id

    with get_db_cursor() as cur:
        cur.execute("SELECT status FROM dbo.ProductionOperations WHERE id = ?", (data.operation_id,))
        op = cur.fetchone()
        if not op or op[0] != "IN_PROGRESS":
            raise HTTPException(status_code=400, detail="Sadece devam eden işler duraklatılabilir.")

        cur.execute("UPDATE dbo.ProductionOperations SET status = 'PAUSED' WHERE id = ?", (data.operation_id,))

        cur.execute("""
            UPDATE dbo.JobTimeLogs
            SET actual_end_utc = GETUTCDATE()
            WHERE id = (
                SELECT TOP 1 id 
                FROM dbo.JobTimeLogs 
                WHERE operation_id = ? AND event_type = 'START' AND actual_end_utc IS NULL 
                ORDER BY id DESC
            )
        """, (data.operation_id,))

        cur.execute("""
            INSERT INTO dbo.JobTimeLogs (operation_id, user_id, event_type, operator_note, actual_start_utc, actual_end_utc)
            VALUES (?, ?, 'PAUSE', ?, GETUTCDATE(), GETUTCDATE())
        """, (data.operation_id, user_id, data.operator_note))

    return {"message": "İş duraklatıldı.", "operation_id": data.operation_id, "status": "PAUSED"}

@app.post("/api/jobs/complete")
def complete_job(data: JobActionRequest, current_user: dict = Depends(get_current_user)):
    raw_id = current_user.get("user_id") or current_user.get("sub")
    user_id = int(raw_id) if raw_id else 0

    if data.target_user_id and current_user.get("role") in ["ADMIN", "PLANNER"]:
        user_id = data.target_user_id

    with get_db_cursor() as cur:
        cur.execute("""
            SELECT sap_doc_entry, stage_order, status 
            FROM dbo.ProductionOperations 
            WHERE id = ?
        """, (data.operation_id,))
        op = cur.fetchone()
        if not op:
            raise HTTPException(status_code=404, detail="Operasyon bulunamadı.")

        doc_entry, current_stage_order = op[0], op[1]

        cur.execute("""
            UPDATE dbo.ProductionOperations 
            SET status = 'COMPLETED', 
                completed_qty = completed_qty + ?, 
                scrapped_qty = scrapped_qty + ?
            WHERE id = ?
        """, (data.completed_qty or 0.0, data.scrapped_qty or 0.0, data.operation_id))

        cur.execute("""
            UPDATE dbo.JobTimeLogs
            SET actual_end_utc = GETUTCDATE()
            WHERE id = (
                SELECT TOP 1 id 
                FROM dbo.JobTimeLogs 
                WHERE operation_id = ? AND event_type = 'START' AND actual_end_utc IS NULL 
                ORDER BY id DESC
            )
        """, (data.operation_id,))

        cur.execute("""
            INSERT INTO dbo.JobTimeLogs (operation_id, user_id, event_type, batch_number, operator_note, completed_qty, scrapped_qty, actual_start_utc, actual_end_utc)
            VALUES (?, ?, 'COMPLETE', ?, ?, ?, ?, GETUTCDATE(), GETUTCDATE())
        """, (data.operation_id, user_id, data.batch_number, data.operator_note, data.completed_qty or 0.0, data.scrapped_qty or 0.0))

        cur.execute("""
            SELECT TOP 1 id 
            FROM dbo.ProductionOperations 
            WHERE sap_doc_entry = ? AND stage_order > ? AND status != 'COMPLETED'
            ORDER BY stage_order ASC
        """, (doc_entry, current_stage_order))
        next_op = cur.fetchone()

        unlocked_next_id = None
        if next_op:
            unlocked_next_id = next_op[0]
            today_str = date.today().isoformat()

            cur.execute("""
                SELECT sc.code, op.stage_order, sc.id
                FROM dbo.ProductionOperations op
                INNER JOIN dbo.StationCategories sc ON op.category_id = sc.id
                WHERE op.id = ?
            """, (unlocked_next_id,))
            next_info = cur.fetchone()
            next_code = next_info[0] if next_info else ""
            next_stage_order = next_info[1] if next_info else 1
            next_cat_id = next_info[2] if next_info else None

            if next_code == 'KYN':
                if next_stage_order == 1:
                    cur.execute("""
                        UPDATE dbo.ProductionOperations 
                        SET is_unlocked = 1, 
                            status = 'PENDING', 
                            assigned_workstation_id = NULL
                        WHERE id = ?
                    """, (unlocked_next_id,))
                else:
                    cur.execute("""
                        SELECT 
                            ws.id,
                            ws.station_code,
                            ISNULL(SUM(o.planned_duration_min), 0.0) AS today_load_min
                        FROM dbo.Workstations ws
                        LEFT JOIN dbo.ProductionOperations o 
                            ON ws.id = o.assigned_workstation_id 
                            AND o.scheduled_date = CAST(GETDATE() AS DATE)
                            AND o.status != 'COMPLETED'
                        WHERE ws.category_id = ? 
                          AND ws.is_active = 1
                          AND ws.station_code LIKE 'KYN%'
                        GROUP BY ws.id, ws.station_code
                        ORDER BY today_load_min ASC, ws.station_code DESC
                    """, (next_cat_id,))
                    best_ws = cur.fetchone()
                    best_ws_id = best_ws[0] if best_ws else None

                    cur.execute("""
                        UPDATE dbo.ProductionOperations 
                        SET is_unlocked = 1, 
                            status = 'PENDING',
                            scheduled_date = ISNULL(scheduled_date, ?),
                            assigned_workstation_id = ?
                        WHERE id = ?
                    """, (today_str, best_ws_id, unlocked_next_id))


            elif next_code == 'LZR':
                cur.execute("""
                    UPDATE dbo.ProductionOperations 
                    SET is_unlocked = 1, 
                        status = 'PENDING'
                    WHERE id = ?
                """, (unlocked_next_id,))

            else:
                cur.execute("""
                    SELECT TOP 1 id FROM dbo.Workstations 
                    WHERE category_id = ? AND is_active = 1
                """, (next_cat_id,))
                ws_row = cur.fetchone()
                default_ws_id = ws_row[0] if ws_row else None

                cur.execute("""
                    UPDATE dbo.ProductionOperations 
                    SET is_unlocked = 1, 
                        status = 'PENDING',
                        scheduled_date = ISNULL(scheduled_date, ?),
                        assigned_workstation_id = ISNULL(assigned_workstation_id, ?)
                    WHERE id = ?
                """, (today_str, default_ws_id, unlocked_next_id))

    return {
        "message": "Operasyon başarıyla tamamlandı.",
        "completed_operation_id": data.operation_id,
        "next_unlocked_operation_id": unlocked_next_id
    }
@app.get("/api/cockpit/workstations", response_model=List[WorkstationItem])
def get_workstations(category_id: Optional[int] = None, current_user: dict = Depends(get_current_user)):
    with get_db_cursor() as cur:
        query = "SELECT id, category_id, station_code, station_name FROM dbo.Workstations WHERE is_active = 1"
        params = []
        if category_id:
            query += " AND category_id = ?"
            params.append(category_id)
        query += " ORDER BY station_code ASC"
        cur.execute(query, tuple(params))
        rows = cur.fetchall()
        return [{"id": r[0], "category_id": r[1], "station_code": r[2], "station_name": r[3]} for r in rows]


@app.get("/api/cockpit/operations", response_model=List[CockpitOperationItem])
def get_cockpit_operations(
        target_date: Optional[str] = None,
        category_id: Optional[int] = None,
        only_unscheduled: bool = False,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        current_user: dict = Depends(require_role(["ADMIN", "PLANNER"]))
):
    factory = current_user.get("factory", "TR")

    with get_db_cursor() as cur:
        query = """
            WITH OpElapsed AS (
                SELECT 
                    operation_id,
                    SUM(DATEDIFF(second, actual_start_utc, ISNULL(actual_end_utc, GETUTCDATE()))) AS elapsed_sec
                FROM dbo.JobTimeLogs
                WHERE event_type = 'START'
                GROUP BY operation_id
            ),
            OrderDurations AS (
                SELECT 
                    sap_doc_entry,
                    SUM(planned_duration_min) AS total_order_duration,
                    SUM(CASE WHEN status = 'COMPLETED' THEN planned_duration_min ELSE 0.0 END) AS completed_order_duration
                FROM dbo.ProductionOperations
                GROUP BY sap_doc_entry
            )
            SELECT 
                op.id, op.sap_doc_entry, po.sap_doc_num, po.item_code, 
                po.item_description, op.category_id, op.category_name, 
                op.stage_order, op.status, op.is_unlocked, op.scheduled_date, 
                op.planned_qty, op.completed_qty,
                ISNULL(op.planned_duration_min, 0.0) AS planned_duration_min,
                op.assigned_workstation_id,
                ws.station_code AS workstation_code,
                ISNULL(od.total_order_duration, 0.0) AS total_order_duration,
                ISNULL(od.completed_order_duration, 0.0) AS completed_order_duration,
                ISNULL(oe.elapsed_sec, 0.0) AS elapsed_sec
            FROM dbo.ProductionOperations op
            INNER JOIN dbo.ProductionOrders po ON op.sap_doc_entry = po.sap_doc_entry
            LEFT JOIN dbo.Workstations ws ON op.assigned_workstation_id = ws.id
            LEFT JOIN OrderDurations od ON op.sap_doc_entry = od.sap_doc_entry
            LEFT JOIN OpElapsed oe ON op.id = oe.operation_id
            WHERE po.sap_factory = ? AND op.status != 'COMPLETED'
        """
        params = [factory]

        if only_unscheduled:
            query += " AND op.is_unlocked = 1 AND op.scheduled_date IS NULL"
        else:
            if target_date:
                query += " AND op.scheduled_date = ?"
                params.append(target_date)
            elif start_date and end_date:
                query += " AND op.scheduled_date BETWEEN ? AND ?"
                params.extend([start_date, end_date])

        if category_id:
            query += " AND op.category_id = ?"
            params.append(category_id)

        query += " ORDER BY po.sap_doc_num ASC, op.stage_order ASC"

        cur.execute(query, tuple(params))
        rows = cur.fetchall()

        result = []
        for r in rows:
            sched = r[10].isoformat() if hasattr(r[10], 'isoformat') else (str(r[10]) if r[10] else None)
            total_dur = float(r[16] or 0.0)
            comp_dur = float(r[17] or 0.0)
            plan_dur = float(r[13] or 0.0)
            elapsed_sec = float(r[18] or 0.0)
            elapsed_min = elapsed_sec / 60.0

            is_overdue = (r[8] == 'IN_PROGRESS' or r[8] == 'PAUSED') and (elapsed_min > plan_dur and plan_dur > 0)

            current_progress_dur = comp_dur + min(elapsed_min, plan_dur)
            calculated_pct = round((current_progress_dur / total_dur * 100), 1) if total_dur > 0 else 0.0

            result.append({
                "id": r[0],
                "sap_doc_entry": r[1],
                "sap_doc_num": r[2],
                "item_code": r[3],
                "item_description": r[4],
                "category_id": r[5],
                "category_name": r[6],
                "stage_order": r[7],
                "status": r[8],
                "is_unlocked": bool(r[9]),
                "scheduled_date": sched,
                "planned_qty": float(r[11]),
                "completed_qty": float(r[12]),
                "planned_duration_min": plan_dur,
                "assigned_workstation_id": r[14],
                "workstation_code": r[15],
                "progress_pct": calculated_pct,
                "elapsed_work_seconds": elapsed_sec,
                "is_overdue": is_overdue
            })

        return result

@app.post("/api/cockpit/schedule")
def schedule_operation(
        payload: ScheduleJobRequest,
        current_user: dict = Depends(require_role(["ADMIN", "PLANNER"]))
):
    with get_db_cursor() as cur:
        cur.execute("SELECT id FROM dbo.ProductionOperations WHERE id = ?", (payload.operation_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Operasyon bulunamadı.")

        cur.execute("""
            UPDATE dbo.ProductionOperations
            SET scheduled_date = ?,
                assigned_workstation_id = ?
            WHERE id = ?
        """, (payload.scheduled_date, payload.workstation_id, payload.operation_id))

    return {"message": "Operasyon başarıyla çizelgelendi.", "operation_id": payload.operation_id}


@app.get("/api/cockpit/station-status", response_model=List[StationLiveStatus])
def get_station_status(current_user: dict = Depends(require_role(["ADMIN", "PLANNER"]))):
    factory = current_user.get("factory", "TR")

    with get_db_cursor() as cur:
        cur.execute("SELECT id, code, category_name FROM dbo.StationCategories ORDER BY id ASC")
        stations = cur.fetchall()

        result = []
        for st_id, st_code, st_name in stations:
            cur.execute("""
                SELECT TOP 1 
                    op.id, po.sap_doc_num, po.item_code, po.item_description, 
                    op.status, op.assigned_user_id
                FROM dbo.ProductionOperations op
                INNER JOIN dbo.ProductionOrders po ON op.sap_doc_entry = po.sap_doc_entry
                WHERE po.sap_factory = ? 
                  AND op.category_id = ? 
                  AND op.status IN ('IN_PROGRESS', 'PAUSED')
                ORDER BY op.id DESC
            """, (factory, st_id))
            active_op = cur.fetchone()

            if not active_op:
                result.append({
                    "category_id": st_id,
                    "station_code": st_code,
                    "station_name": st_name,
                    "status": "IDLE",
                    "current_op_id": None,
                    "sap_doc_num": None,
                    "item_code": None,
                    "item_description": None,
                    "operator_name": None,
                    "pause_reason": None,
                    "started_at": None
                })
            else:
                op_id, doc_num, item_code, item_desc, op_status, assigned_uid = active_op
                station_state = "RUNNING" if op_status == "IN_PROGRESS" else "PAUSED"

                cur.execute("""
                    SELECT TOP 1 
                        tl.operator_note, tl.actual_start_utc, u.full_name, u.username
                    FROM dbo.JobTimeLogs tl
                    LEFT JOIN dbo.Users u ON tl.user_id = u.id
                    WHERE tl.operation_id = ?
                    ORDER BY tl.id DESC
                """, (op_id,))
                log_row = cur.fetchone()

                pause_reason = log_row[0] if (log_row and station_state == "PAUSED") else None
                started_at = log_row[1].isoformat() if (log_row and hasattr(log_row[1], 'isoformat')) else (str(log_row[1]) if (log_row and log_row[1]) else None)
                operator_name = log_row[2] or log_row[3] if log_row else None

                result.append({
                    "category_id": st_id,
                    "station_code": st_code,
                    "station_name": st_name,
                    "status": station_state,
                    "current_op_id": op_id,
                    "sap_doc_num": doc_num,
                    "item_code": item_code,
                    "item_description": item_desc,
                    "operator_name": operator_name,
                    "pause_reason": pause_reason,
                    "started_at": started_at
                })

        return result


@app.get("/api/cockpit/station-workload/{category_id}")
def get_station_workload(category_id: int, current_user: dict = Depends(require_role(["ADMIN", "PLANNER"]))):
    factory = current_user.get("factory", "TR")

    with get_db_cursor() as cur:
        query = """
            SELECT 
                op.id, op.sap_doc_entry, po.sap_doc_num, po.item_code, po.item_description,
                op.stage_order, op.status, op.is_unlocked, op.scheduled_date, 
                op.planned_qty, op.completed_qty
            FROM dbo.ProductionOperations op
            INNER JOIN dbo.ProductionOrders po ON op.sap_doc_entry = po.sap_doc_entry
            WHERE po.sap_factory = ? AND op.category_id = ? AND op.status != 'COMPLETED'
            ORDER BY op.is_unlocked DESC, po.sap_doc_num ASC
        """
        cur.execute(query, (factory, category_id))
        rows = cur.fetchall()

        workload = []
        for r in rows:
            op_id, doc_entry, doc_num, item_code, item_desc, stg_order, status, is_unlocked, sched_date, plan_q, comp_q = r
            sched_str = sched_date.isoformat() if hasattr(sched_date, 'isoformat') else (str(sched_date) if sched_date else None)

            blocking_station = None
            if not is_unlocked and stg_order > 1:
                cur.execute("""
                    SELECT TOP 1 category_name, status 
                    FROM dbo.ProductionOperations 
                    WHERE sap_doc_entry = ? AND stage_order < ? 
                    ORDER BY stage_order DESC
                """, (doc_entry, stg_order))
                prev_st = cur.fetchone()
                if prev_st:
                    blocking_station = f"{prev_st[0]} ({prev_st[1]})"

            workload.append({
                "id": op_id,
                "sap_doc_num": doc_num,
                "item_code": item_code,
                "item_description": item_desc,
                "stage_order": stg_order,
                "status": status,
                "is_unlocked": bool(is_unlocked),
                "scheduled_date": sched_str,
                "planned_qty": float(plan_q),
                "completed_qty": float(comp_q),
                "blocking_station": blocking_station
            })

        return workload

@app.post("/api/cockpit/daily-capacity")
def set_daily_capacity(payload: UpdateDailyCapacityRequest, current_user: dict = Depends(require_role(["ADMIN", "PLANNER"]))):
    SHIFT_MINUTES = 510.0
    total_cap = payload.worker_count * SHIFT_MINUTES

    with get_db_cursor() as cur:
        cur.execute("""
            MERGE dbo.DailyStationCapacity AS target
            USING (SELECT ? AS category_id, ? AS work_date) AS source
            ON (target.category_id = source.category_id AND target.work_date = source.work_date)
            WHEN MATCHED THEN
                UPDATE SET worker_count = ?, capacity_minutes = ?
            WHEN NOT MATCHED THEN
                INSERT (category_id, work_date, worker_count, capacity_minutes)
                VALUES (?, ?, ?, ?);
        """, (payload.category_id, payload.work_date, payload.worker_count, total_cap,
              payload.category_id, payload.work_date, payload.worker_count, total_cap))

    return {"message": "Kapasite güncellendi.", "worker_count": payload.worker_count, "capacity_minutes": total_cap}


@app.get("/api/cockpit/station-capacity")
def get_station_capacity(
        category_id: int,
        week_start: str,
        current_user: dict = Depends(require_role(["ADMIN", "PLANNER"]))
):
    factory = current_user.get("factory", "TR")
    SHIFT_MINUTES = 510.0

    with get_db_cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM dbo.Workstations WHERE category_id = ? AND is_active = 1", (category_id,))
        default_worker_count = cur.fetchone()[0] or 1

        cur.execute("""
            SELECT work_date, worker_count, capacity_minutes 
            FROM dbo.DailyStationCapacity
            WHERE category_id = ? AND work_date >= ? AND work_date <= DATEADD(day, 6, CAST(? AS DATE))
        """, (category_id, week_start, week_start))
        custom_caps = {str(r[0]): {"workers": r[1], "capacity_min": float(r[2])} for r in cur.fetchall()}

        cur.execute("""
            SELECT 
                op.scheduled_date, 
                ISNULL(SUM(op.planned_duration_min), 0) AS total_load_min,
                COUNT(op.id) AS job_count
            FROM dbo.ProductionOperations op
            INNER JOIN dbo.ProductionOrders po ON op.sap_doc_entry = po.sap_doc_entry
            WHERE po.sap_factory = ? 
              AND op.category_id = ? 
              AND op.scheduled_date >= ?
              AND op.scheduled_date <= DATEADD(day, 6, CAST(? AS DATE))
              AND op.status != 'COMPLETED'
            GROUP BY op.scheduled_date
        """, (factory, category_id, week_start, week_start))

        load_rows = cur.fetchall()
        daily_loads = {str(r[0]): {"load_min": float(r[1]), "job_count": r[2]} for r in load_rows}

        return {
            "category_id": category_id,
            "default_workers": default_worker_count,
            "shift_minutes": SHIFT_MINUTES,
            "custom_capacities": custom_caps,
            "daily_loads": daily_loads
        }


@app.get("/api/cockpit/monthly-capacity", response_model=List[MonthDayCapacity])
def get_monthly_capacity(
    category_id: int,
    year: int,
    month: int,
    current_user: dict = Depends(require_role(["ADMIN", "PLANNER"]))
):
    factory = current_user.get("factory", "TR")
    SHIFT_MINUTES = 510.0

    last_day = calendar.monthrange(year, month)[1]
    start_str = f"{year:04d}-{month:02d}-01"
    end_str = f"{year:04d}-{month:02d}-{last_day:02d}"

    with get_db_cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM dbo.Workstations WHERE category_id = ? AND is_active = 1", (category_id,))
        default_workers = cur.fetchone()[0] or 1
        default_capacity = default_workers * SHIFT_MINUTES

        cur.execute("""
            SELECT work_date, capacity_minutes FROM dbo.DailyStationCapacity
            WHERE category_id = ? AND work_date BETWEEN ? AND ?
        """, (category_id, start_str, end_str))
        custom_caps = {str(r[0]): float(r[1]) for r in cur.fetchall()}

        cur.execute("""
            SELECT op.scheduled_date, ISNULL(SUM(op.planned_duration_min), 0)
            FROM dbo.ProductionOperations op
            INNER JOIN dbo.ProductionOrders po ON op.sap_doc_entry = po.sap_doc_entry
            WHERE po.sap_factory = ? AND op.category_id = ? AND op.scheduled_date BETWEEN ? AND ?
              AND op.status != 'COMPLETED'
            GROUP BY op.scheduled_date
        """, (factory, category_id, start_str, end_str))
        loads = {str(r[0]): float(r[1]) for r in cur.fetchall()}

    result = []
    curr = date(year, month, 1)
    end_date = date(year, month, last_day)

    while curr <= end_date:
        d_str = curr.strftime("%Y-%m-%d")
        cap = custom_caps.get(d_str, default_capacity)
        load = loads.get(d_str, 0.0)
        pct = (load / cap * 100.0) if cap > 0 else 0.0

        if pct >= 100.0:
            color = "red"
        elif pct >= 70.0:
            color = "yellow"
        else:
            color = "green"

        result.append({
            "work_date": d_str,
            "total_load_min": round(load, 1),
            "capacity_min": round(cap, 1),
            "occupancy_pct": round(pct, 1),
            "status_color": color
        })
        curr += timedelta(days=1)

    return result

app.mount("/static", StaticFiles(directory="static"), name="static")