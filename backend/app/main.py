import asyncio
import json
import logging
import threading
import time
from contextlib import asynccontextmanager
from datetime import datetime
from hashlib import sha256
from time import perf_counter
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from fastapi import (
    Depends,
    FastAPI,
    HTTPException,
    Query,
    Request,
    Response,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from openai import OpenAIError
from psycopg import Error as DatabaseError
from psycopg import OperationalError

from .administration import (
    create_machine,
    create_user,
    deactivate_user,
    delete_machine,
    list_audit,
    list_machines,
    list_users,
    update_machine,
    update_user,
)
from .agent_inspection import inspection_snapshot
from .agents import build_graph
from .analytics import dashboard, operational_logs
from .auth import (
    DUMMY_PASSWORD_HASH,
    create_access_token,
    create_customer_token,
    current_user,
    decode_customer_token,
    hash_password,
    login_key,
    login_limiter,
    require_role,
    user_from_token,
    validate_new_password,
    verify_password,
)
from .bootstrap import ensure_rag_seed
from .config import settings
from .conversation_policy import language_for, policy_message
from .customers_admin import (
    create_customer,
    customer_detail,
    link_terminal,
    list_customers,
    reset_customer_password,
    unlink_terminal,
    update_customer,
)
from .db import connection
from .guardrails import (
    InputDecision,
    ToolPolicyError,
    inspect_input,
    inspect_output,
    list_events,
    record_event,
)
from .guardrails.scope import EXCHANGE_DOMAINS, is_exchange_query
from .handoff.service import (
    CLOSED_MESSAGE,
    HandoffConflict,
    active_handoff_for_conversation,
    add_internal_note,
    claim,
    close_customer_conversation,
    close_handoff,
    pull,
    reassign_stale_offline,
    service_center_counts,
    set_technician_status,
    transfer,
)
from .migrations import migrate
from .persistence import (
    conversation_memory,
    get_or_create_conversation,
    persist_message,
    persist_run,
    update_conversation_summary,
)
from .privacy import anonymize_customer, apply_retention, export_customer_data
from .provider import BudgetExceeded, Provider, ProviderUnavailable
from .rag_admin import (
    create_document,
    delete_document,
    get_reindex_status,
    ingest_url,
    list_documents,
    review_document,
    start_reindex,
    update_document,
)
from .rate_limit import request_limiter
from .realtime import hub
from .schemas import (
    AdminUserCreate,
    AdminUserUpdate,
    AuthUser,
    ChangePasswordRequest,
    ChatRequest,
    ChatResponse,
    CloseHandoffRequest,
    CustomerCreate,
    CustomerTerminalRequest,
    CustomerUpdate,
    InternalNoteRequest,
    LoginRequest,
    MachineCreate,
    MachineUpdate,
    PullHandoffRequest,
    RagDocumentCreate,
    RagDocumentUpdate,
    RagReviewRequest,
    RagUrlRequest,
    TechnicianMessageRequest,
    TechnicianStatusRequest,
    TransferHandoffRequest,
)
from .security import (
    annotate_openapi,
    client_ip,
    enforce_csrf,
    safe_log_value,
    security_headers,
    websocket_origin_allowed,
)
from .setup_db import setup
from .technician import (
    conversation_belongs_to_customer,
    conversation_detail,
    list_conversations,
    technician_owns_conversation,
)
from .tools import customer_exists, list_customer_terminals

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("getnet")
logging.getLogger("httpx").setLevel(logging.WARNING)
capacity = threading.BoundedSemaphore(2)


@asynccontextmanager
async def lifespan(app):
    settings().validate_production()
    migrate()
    setup()
    ensure_rag_seed()
    hub.bind()

    async def sweep_offline_technicians():
        interval = max(1, min(30, settings().handoff_offline_timeout_seconds))
        while True:
            await asyncio.sleep(interval)
            try:
                await asyncio.to_thread(reassign_stale_offline)
            except Exception as exc:
                logger.error(json.dumps({"event": "handoff_sweep_failed", "error_type": type(exc).__name__}))

    async def retention_worker():
        while True:
            await asyncio.sleep(max(3600, settings().retention_interval_hours * 3600))
            try:
                await asyncio.to_thread(
                    apply_retention, settings().retention_days, settings().retention_action
                )
            except Exception as exc:
                logger.error(
                    json.dumps(
                        {"event": "retention_failed", "error_type": safe_log_value(type(exc).__name__)}
                    )
                )

    task = asyncio.create_task(sweep_offline_technicians())
    retention_task = asyncio.create_task(retention_worker())
    try:
        yield
    finally:
        task.cancel()
        retention_task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        try:
            await retention_task
        except asyncio.CancelledError:
            pass


cfg_at_import = settings()
app = FastAPI(
    title="Getnet · Multi-Agent Support",
    version="0.1.0",
    lifespan=lifespan,
    docs_url=None if cfg_at_import.production else "/docs",
    redoc_url=None if cfg_at_import.production else "/redoc",
    openapi_url=None if cfg_at_import.production else "/openapi.json",
)


def set_session_cookie(response: Response, name: str, token: str) -> None:
    cfg = settings()
    response.set_cookie(
        key=name,
        value=token,
        max_age=cfg.auth_session_minutes * 60,
        httponly=True,
        secure=cfg.auth_cookie_secure or cfg.production,
        samesite="lax",
        path="/",
    )


app.add_middleware(
    CORSMiddleware,
    allow_origins=list(cfg_at_import.allowed_origins),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-Request-ID"],
)


@app.middleware("http")
async def request_context(request: Request, call_next):
    request.state.request_id = request.headers.get("X-Request-ID") or str(uuid4())
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > settings().max_request_body_bytes:
        return JSONResponse(
            status_code=413,
            content=error_body(request, "body_too_large", "Corpo da requisição excede o limite permitido."),
        )
    try:
        enforce_csrf(request)
    except HTTPException as exc:
        return JSONResponse(
            status_code=exc.status_code, content=error_body(request, "csrf_rejected", str(exc.detail))
        )
    response = await call_next(request)
    response.headers["X-Request-ID"] = request.state.request_id
    security_headers(response)
    return response


def error_body(request: Request, code: str, message: str) -> dict:
    return {"code": code, "message": message, "request_id": request.state.request_id}


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    details = "; ".join(
        f"{'.'.join(str(part) for part in item['loc'] if part != 'body')}: {item['msg']}".strip(": ")
        for item in exc.errors()
    )
    return JSONResponse(
        status_code=422, content=error_body(request, "validation_error", details or "Dados inválidos.")
    )


@app.exception_handler(HTTPException)
async def http_error(request: Request, exc: HTTPException):
    codes = {
        401: "unauthorized",
        403: "forbidden",
        404: "not_found",
        409: "conflict",
        422: "validation_error",
        429: "rate_limited",
        503: "service_unavailable",
    }
    return JSONResponse(
        status_code=exc.status_code,
        content=error_body(request, codes.get(exc.status_code, "request_error"), str(exc.detail)),
        headers=exc.headers,
    )


def _notify_assignment(handoff_id):
    if not handoff_id:
        return
    with connection() as conn:
        row = conn.execute(
            "SELECT h.conversation_id,h.technician_id,u.display_name FROM handoffs h "
            "JOIN users u ON u.id=h.technician_id WHERE h.id=%s",
            (handoff_id,),
        ).fetchone()
    if row:
        hub.publish_customer(
            str(row["conversation_id"]),
            {
                "event_id": f"technician:{handoff_id}:{row['technician_id']}",
                "type": "technician.joined",
                "technician_name": row["display_name"],
            },
        )
        hub.publish_technician(row["technician_id"], {"type": "handoff.assigned"})


def _broadcast_queue_positions():
    with connection() as conn:
        rows = conn.execute(
            "SELECT id,conversation_id FROM handoffs WHERE status='waiting' ORDER BY created_at,id"
        ).fetchall()
    for position, row in enumerate(rows, 1):
        conversation_id = str(row["conversation_id"])
        if hub.queue_positions.get(conversation_id) == position:
            continue
        hub.queue_positions[conversation_id] = position
        hub.publish_customer(
            conversation_id,
            {"event_id": f"queue:{row['id']}:{position}", "type": "queue.position", "position": position},
        )
    active = {str(row["conversation_id"]) for row in rows}
    for conversation_id in set(hub.queue_positions) - active:
        hub.queue_positions.pop(conversation_id, None)


@app.post("/api/auth/login", response_model=AuthUser)
def login(payload: LoginRequest, request: Request, response: Response):
    key = login_key(request, payload.username)
    ip_key = f"ip:{client_ip(request)}"
    account_key = f"account:{payload.username.casefold()}"
    now = time.monotonic()
    remaining = max(
        login_limiter.check(key, now), login_limiter.check(ip_key, now), login_limiter.check(account_key, now)
    )
    if remaining:
        logger.warning(
            json.dumps(
                {
                    "event": "login_rate_limited",
                    "account_hash": sha256(account_key.encode()).hexdigest()[:12],
                    "retry_after": remaining,
                }
            )
        )
        raise HTTPException(
            429, "Muitas tentativas. Tente novamente mais tarde.", headers={"Retry-After": str(remaining)}
        )
    with connection() as conn:
        user = conn.execute(
            "SELECT id,username,password_hash,role,display_name,is_active,customer_id,must_change_password,token_version "
            "FROM users WHERE lower(username)=lower(%s)",
            (payload.username,),
        ).fetchone()
        valid_password = verify_password(
            payload.password, user["password_hash"] if user else DUMMY_PASSWORD_HASH
        )
        if not user or not user["is_active"] or not valid_password:
            locked = max(
                login_limiter.failure(key, now),
                login_limiter.failure(ip_key, now),
                login_limiter.failure(account_key, now),
            )
            if locked:
                logger.warning(
                    json.dumps(
                        {
                            "event": "login_lockout",
                            "account_hash": sha256(account_key.encode()).hexdigest()[:12],
                            "retry_after": locked,
                        }
                    )
                )
            headers = {"Retry-After": str(locked)} if locked else None
            raise HTTPException(429 if locked else 401, "Usuário ou senha inválidos.", headers=headers)
        login_limiter.success(key)
        login_limiter.success(ip_key)
        login_limiter.success(account_key)
        conn.execute(
            "INSERT INTO audit_logs(actor_id,action,entity,entity_id,diff) VALUES (%s,'auth.login','user',%s,'{}')",
            (user["id"], str(user["id"])),
        )
    if user["role"] == "tecnico":
        presence = set_technician_status(user["id"], "online")
        _notify_assignment(presence.get("assigned_handoff_id"))
        _broadcast_queue_positions()
    set_session_cookie(response, settings().auth_cookie_name, create_access_token(user))
    return user


@app.post("/api/auth/change-password", response_model=AuthUser)
def change_password(payload: ChangePasswordRequest, response: Response, user: dict = Depends(current_user)):
    with connection() as conn:
        current = conn.execute(
            "SELECT id,username,password_hash FROM users WHERE id=%s FOR UPDATE", (user["id"],)
        ).fetchone()
        if not current or not verify_password(payload.current_password, current["password_hash"]):
            raise HTTPException(401, "Senha atual inválida.")
        try:
            validate_new_password(current["username"], payload.new_password)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        updated = conn.execute(
            "UPDATE users SET password_hash=%s,must_change_password=false,password_changed_at=now(),"
            "token_version=token_version+1,updated_at=now() WHERE id=%s "
            "RETURNING id,username,role,display_name,customer_id,must_change_password,token_version",
            (hash_password(payload.new_password), user["id"]),
        ).fetchone()
        conn.execute(
            "INSERT INTO audit_logs(actor_id,action,entity,entity_id,diff) "
            "VALUES (%s,'auth.password_changed','user',%s,'{\"credentials\":\"changed\"}')",
            (user["id"], str(user["id"])),
        )
    set_session_cookie(response, settings().auth_cookie_name, create_access_token(updated))
    return updated


@app.post("/api/auth/logout", status_code=204)
def logout(response: Response, user: dict = Depends(current_user)):
    with connection() as conn:
        conn.execute(
            "UPDATE users SET token_version=token_version+1,updated_at=now() WHERE id=%s", (user["id"],)
        )
        conn.execute(
            "INSERT INTO audit_logs(actor_id,action,entity,entity_id,diff) VALUES (%s,'auth.logout','user',%s,'{}')",
            (user["id"], str(user["id"])),
        )
    if user["role"] == "tecnico":
        set_technician_status(user["id"], "offline")
    response.delete_cookie(
        settings().auth_cookie_name, path="/", secure=settings().auth_cookie_secure or settings().production
    )
    response.delete_cookie(
        settings().customer_cookie_name,
        path="/",
        secure=settings().auth_cookie_secure or settings().production,
    )


@app.get("/api/auth/me", response_model=AuthUser)
def me(response: Response, user: dict = Depends(current_user)):
    set_session_cookie(response, settings().auth_cookie_name, create_access_token(user))
    return user


@app.get("/api/customer/profile")
def customer_profile(user: dict = Depends(require_role("cliente"))):
    with connection() as conn:
        return conn.execute(
            "SELECT external_id,nome,email,telefone FROM customers WHERE id=%s AND is_active=true",
            (user["customer_id"],),
        ).fetchone()


@app.get("/api/customer/terminals")
def customer_terminals(user: dict = Depends(require_role("cliente"))):
    return list_customer_terminals(user["customer_id"])


@app.get("/api/admin")
def admin_placeholder(user: dict = Depends(require_role("admin"))):
    return {"message": "Área administrativa preparada para a próxima fase.", "user": user["display_name"]}


def _admin_error(exc: Exception):
    if isinstance(exc, LookupError):
        raise HTTPException(404, str(exc)) from exc
    if isinstance(exc, PermissionError):
        raise HTTPException(403, str(exc)) from exc
    raise HTTPException(409, str(exc)) from exc


@app.get("/api/admin/users")
def admin_users(user: dict = Depends(require_role("admin"))):
    return list_users()


@app.post("/api/admin/users", status_code=201)
def admin_create_user(payload: AdminUserCreate, user: dict = Depends(require_role("admin"))):
    try:
        return create_user(user["id"], payload.model_dump())
    except (ValueError, LookupError, PermissionError) as exc:
        _admin_error(exc)


@app.patch("/api/admin/users/{user_id}")
def admin_update_user(user_id: int, payload: AdminUserUpdate, user: dict = Depends(require_role("admin"))):
    try:
        return update_user(user["id"], user_id, payload.model_dump(exclude_none=True))
    except (ValueError, LookupError, PermissionError) as exc:
        _admin_error(exc)


@app.delete("/api/admin/users/{user_id}")
def admin_deactivate_user(user_id: int, user: dict = Depends(require_role("admin"))):
    try:
        return deactivate_user(user["id"], user_id)
    except (ValueError, LookupError, PermissionError) as exc:
        _admin_error(exc)


@app.get("/api/admin/customers")
def admin_customers(
    search: str = "", page: int = 1, page_size: int = 20, user: dict = Depends(require_role("admin"))
):
    return list_customers(search, page, page_size)


@app.get("/api/admin/customers/{customer_id}")
def admin_customer(customer_id: str, user: dict = Depends(require_role("admin"))):
    try:
        return customer_detail(customer_id)
    except LookupError as exc:
        _admin_error(exc)


@app.post("/api/admin/customers", status_code=201)
def admin_create_customer(payload: CustomerCreate, user: dict = Depends(require_role("admin"))):
    try:
        return create_customer(user["id"], payload.model_dump())
    except (ValueError, LookupError) as exc:
        _admin_error(exc)


@app.patch("/api/admin/customers/{customer_id}")
def admin_update_customer(
    customer_id: str, payload: CustomerUpdate, user: dict = Depends(require_role("admin"))
):
    try:
        return update_customer(user["id"], customer_id, payload.model_dump(exclude_none=True))
    except (ValueError, LookupError) as exc:
        _admin_error(exc)


@app.delete("/api/admin/customers/{customer_id}")
def admin_deactivate_customer(customer_id: str, user: dict = Depends(require_role("admin"))):
    try:
        return update_customer(user["id"], customer_id, {"is_active": False})
    except (ValueError, LookupError) as exc:
        _admin_error(exc)


@app.post("/api/admin/customers/{customer_id}/reset-password")
def admin_reset_customer_password(customer_id: str, user: dict = Depends(require_role("admin"))):
    try:
        return reset_customer_password(user["id"], customer_id)
    except LookupError as exc:
        _admin_error(exc)


@app.get("/api/admin/customers/{customer_id}/export")
def admin_export_customer(customer_id: str, user: dict = Depends(require_role("admin"))):
    try:
        return export_customer_data(customer_id)
    except LookupError as exc:
        _admin_error(exc)


@app.post("/api/admin/customers/{customer_id}/anonymize")
def admin_anonymize_customer(customer_id: str, user: dict = Depends(require_role("admin"))):
    try:
        return anonymize_customer(user["id"], customer_id)
    except LookupError as exc:
        _admin_error(exc)


@app.post("/api/admin/customers/{customer_id}/terminals")
def admin_link_customer_terminal(
    customer_id: str, payload: CustomerTerminalRequest, user: dict = Depends(require_role("admin"))
):
    try:
        return link_terminal(user["id"], customer_id, payload.model_dump(exclude_none=True))
    except (ValueError, LookupError, DatabaseError) as exc:
        _admin_error(ValueError("Número de série já cadastrado.") if isinstance(exc, DatabaseError) else exc)


@app.delete("/api/admin/customers/{customer_id}/terminals/{terminal_id}")
def admin_unlink_customer_terminal(
    customer_id: str, terminal_id: str, user: dict = Depends(require_role("admin"))
):
    try:
        return unlink_terminal(user["id"], customer_id, terminal_id)
    except LookupError as exc:
        _admin_error(exc)


@app.get("/api/admin/machines")
def admin_machines(
    kind: str = Query("terminal", pattern="^(model|terminal)$"),
    search: str = Query("", max_length=100),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: dict = Depends(require_role("admin")),
):
    return list_machines(kind, search, page, page_size)


@app.post("/api/admin/machines", status_code=201)
def admin_create_machine(payload: MachineCreate, user: dict = Depends(require_role("admin"))):
    try:
        return create_machine(user["id"], payload.model_dump())
    except (ValueError, LookupError) as exc:
        _admin_error(exc)


@app.patch("/api/admin/machines/{kind}/{entity_id}")
def admin_update_machine(
    kind: str,
    entity_id: str,
    payload: MachineUpdate,
    user: dict = Depends(require_role("admin")),
):
    if kind not in {"model", "terminal"}:
        raise HTTPException(422, "Tipo de máquina inválido.")
    try:
        return update_machine(user["id"], kind, entity_id, payload.model_dump(exclude_none=True))
    except (ValueError, LookupError) as exc:
        _admin_error(exc)


@app.delete("/api/admin/machines/{kind}/{entity_id}")
def admin_delete_machine(kind: str, entity_id: str, user: dict = Depends(require_role("admin"))):
    if kind not in {"model", "terminal"}:
        raise HTTPException(422, "Tipo de máquina inválido.")
    try:
        return delete_machine(user["id"], kind, entity_id)
    except (ValueError, LookupError) as exc:
        _admin_error(exc)


@app.get("/api/admin/audit")
def admin_audit(
    entity: str = Query("", max_length=100),
    action: str = Query("", max_length=100),
    actor_id: int | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: dict = Depends(require_role("admin")),
):
    return list_audit(entity, action, actor_id, page, page_size)


@app.get("/api/admin/logs")
def admin_operational_logs(
    start: str | None = Query(None, max_length=50),
    end: str | None = Query(None, max_length=50),
    route: str | None = Query(None, max_length=100),
    tool: str | None = Query(None, max_length=150),
    status: str | None = Query(None, max_length=100),
    customer: str | None = Query(None, max_length=100),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: dict = Depends(require_role("admin")),
):
    return operational_logs(
        _parse_filter_datetime(start),
        _parse_filter_datetime(end),
        route or "",
        tool or "",
        status or "",
        customer or "",
        page,
        page_size,
    )


@app.get("/api/admin/guardrails")
def admin_guardrails(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: dict = Depends(require_role("admin")),
):
    return list_events(page, page_size)


@app.get("/api/admin/agents")
def admin_agents(user: dict = Depends(require_role("admin"))):
    return inspection_snapshot()


def _parse_filter_datetime(value: str | None) -> datetime | None:
    if not value or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HTTPException(422, "Data inválida. Use o formato ISO 8601.") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=ZoneInfo("America/Sao_Paulo"))
    return parsed


@app.get("/api/admin/dashboard")
def admin_dashboard(
    period: str = Query("today", pattern="^(today|7d|30d)$"),
    user: dict = Depends(require_role("admin")),
):
    return dashboard(period)


def _rag_error(exc: Exception):
    if isinstance(exc, LookupError):
        raise HTTPException(404, str(exc)) from exc
    if isinstance(exc, ValueError):
        raise HTTPException(409, str(exc)) from exc
    if isinstance(exc, RuntimeError):
        raise HTTPException(503, "Falha temporária ao gerar embeddings.") from exc
    raise exc


@app.get("/api/admin/rag/documents")
def admin_rag_documents(
    search: str = Query("", max_length=200),
    origin: str = Query("", pattern="^(|crawler|manual)$"),
    status: str = Query("", pattern="^(|pending|indexing|indexed|failed)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: dict = Depends(require_role("admin")),
):
    return list_documents(search, origin, status, page, page_size)


@app.post("/api/admin/rag/documents", status_code=201)
def admin_create_rag_document(payload: RagDocumentCreate, user: dict = Depends(require_role("admin"))):
    try:
        return create_document(user["id"], payload.title, payload.content)
    except Exception as exc:
        _rag_error(exc)


@app.put("/api/admin/rag/documents/{document_id}")
def admin_update_rag_document(
    document_id: int,
    payload: RagDocumentUpdate,
    user: dict = Depends(require_role("admin")),
):
    try:
        return update_document(user["id"], document_id, payload.title, payload.content)
    except Exception as exc:
        _rag_error(exc)


@app.delete("/api/admin/rag/documents/{document_id}")
def admin_delete_rag_document(document_id: int, user: dict = Depends(require_role("admin"))):
    try:
        return delete_document(user["id"], document_id)
    except Exception as exc:
        _rag_error(exc)


@app.post("/api/admin/rag/ingest-url", status_code=201)
def admin_ingest_rag_url(payload: RagUrlRequest, user: dict = Depends(require_role("admin"))):
    try:
        return ingest_url(user["id"], payload.url)
    except Exception as exc:
        _rag_error(exc)


@app.post("/api/admin/rag/documents/{document_id}/review")
def admin_review_rag_document(
    document_id: int,
    payload: RagReviewRequest,
    user: dict = Depends(require_role("admin")),
):
    try:
        return review_document(user["id"], document_id, payload.decision, payload.reason)
    except Exception as exc:
        _rag_error(exc)


@app.post("/api/admin/rag/reindex", status_code=202)
def admin_reindex_rag(user: dict = Depends(require_role("admin"))):
    try:
        return start_reindex(user["id"])
    except Exception as exc:
        _rag_error(exc)


@app.get("/api/admin/rag/reindex")
def admin_reindex_status(user: dict = Depends(require_role("admin"))):
    return get_reindex_status()


@app.get("/api/tecnico")
def technician_placeholder(user: dict = Depends(require_role("tecnico", "admin"))):
    return {"message": "Área técnica preparada para a próxima fase.", "user": user["display_name"]}


@app.patch("/api/tech/status")
def technician_status(payload: TechnicianStatusRequest, user: dict = Depends(require_role("tecnico"))):
    try:
        result = set_technician_status(user["id"], payload.status)
        hub.publish_all_technicians({"type": "conversations.refresh"})
        _notify_assignment(result.get("assigned_handoff_id"))
        _broadcast_queue_positions()
        return result
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.exception_handler(OperationalError)
async def database_connection_error(request: Request, exc: OperationalError):
    logger.error(
        json.dumps(
            {
                "event": "database_connection_failed",
                "request_id": request.state.request_id,
                "error_type": type(exc).__name__,
            }
        )
    )
    return JSONResponse(
        status_code=503,
        content=error_body(request, "database_unavailable", "Banco de dados temporariamente indisponível."),
    )


@app.exception_handler(DatabaseError)
async def database_query_error(request: Request, exc: DatabaseError):
    logger.exception(
        json.dumps(
            {
                "event": "database_query_failed",
                "request_id": request.state.request_id,
                "error_type": type(exc).__name__,
            }
        )
    )
    return JSONResponse(
        status_code=500,
        content=error_body(request, "database_query_failed", "Falha interna ao consultar os dados."),
    )


@app.exception_handler(Exception)
async def unexpected_error(request: Request, exc: Exception):
    logger.exception(
        json.dumps(
            {
                "event": "unexpected_error",
                "request_id": request.state.request_id,
                "error_type": type(exc).__name__,
            }
        )
    )
    return JSONResponse(
        status_code=500, content=error_body(request, "internal_error", "Erro interno inesperado.")
    )


@app.get("/api/health/live")
def live():
    return {"status": "alive"}


@app.get("/api/health/ready")
def ready():
    with connection() as conn:
        chunks = conn.execute("SELECT count(*) AS count FROM chunks").fetchone()["count"]
        state = conn.execute("SELECT value FROM app_runtime_state WHERE key='rag_bootstrap'").fetchone()
    configured = bool(settings().openai_api_key.get_secret_value())
    degraded = not bool(chunks) or bool((state or {}).get("value", {}).get("degraded", False))
    return {
        "status": "degraded" if degraded else "ready",
        "database": True,
        "api_key_configured": configured,
        "rag_chunks": chunks,
        "degraded": degraded,
        "rag_action": "Reindexar a base de conhecimento" if degraded else None,
        "demo": True,
    }


@app.get("/api/demo/customers")
def customers():
    with connection() as conn:
        return conn.execute("SELECT id,display_name FROM customers WHERE demo=true ORDER BY id").fetchall()


@app.get("/api/metrics")
def metrics():
    with connection() as conn:
        usage = conn.execute("SELECT * FROM usage_daily ORDER BY day DESC,kind LIMIT 30").fetchall()
        requests = conn.execute(
            "SELECT count(*) AS total, "
            "percentile_cont(0.5) WITHIN GROUP (ORDER BY latency_ms) AS p50_ms, "
            "percentile_cont(0.95) WITHIN GROUP (ORDER BY latency_ms) AS p95_ms FROM requests"
        ).fetchone()
        docs = conn.execute("SELECT count(*) AS total FROM documents").fetchone()["total"]
    return {
        "usage": usage,
        "requests": requests,
        "documents": docs,
        "model": settings().openai_model,
        "limits": {"model": settings().daily_model_call_limit, "web": settings().daily_web_call_limit},
        "scope": "Somente esta aplicação; não é o saldo OpenAI.",
    }


@app.get("/metrics", response_class=PlainTextResponse)
def prometheus_metrics(request: Request):
    token = settings().metrics_token.get_secret_value()
    if token and request.headers.get("X-Metrics-Token") != token:
        raise HTTPException(401, "Autenticação de métricas necessária.")
    if not token and client_ip(request) not in {"127.0.0.1", "::1", "testclient"}:
        raise HTTPException(403, "Métricas restritas à rede interna.")
    with connection() as conn:
        requests = conn.execute("SELECT count(*) AS n FROM requests").fetchone()["n"]
        blocked = conn.execute("SELECT count(*) AS n FROM guardrail_events WHERE action='block'").fetchone()[
            "n"
        ]
    return f"# TYPE getnet_requests_total counter\ngetnet_requests_total {requests}\n# TYPE getnet_guardrail_blocks_total counter\ngetnet_guardrail_blocks_total {blocked}\n"


def _customer_from_request(request: Request) -> str:
    authenticated = user_from_token(request.cookies.get(settings().auth_cookie_name))
    if authenticated:
        if authenticated["role"] != "cliente":
            raise HTTPException(403, "Apenas clientes acessam suas conversas.")
        if authenticated["must_change_password"]:
            raise HTTPException(403, "Troque a senha antes de acessar o atendimento.")
        return authenticated["customer_id"]
    customer_id = decode_customer_token(request.cookies.get(settings().customer_cookie_name))
    if not customer_id:
        raise HTTPException(401, "Sessão do cliente necessária.")
    return customer_id


@app.get("/api/chat/current")
def customer_current(request: Request):
    """Restore an unresolved handoff; a new AI visit starts with a clean chat."""
    customer_id = _customer_from_request(request)
    with connection() as conn:
        row = conn.execute(
            "SELECT c.id FROM conversations c JOIN customers u ON u.id=c.customer_id "
            "WHERE u.external_id=%s AND c.status IN ('waiting','with_technician') "
            "ORDER BY c.started_at DESC LIMIT 1",
            (customer_id,),
        ).fetchone()
    return customer_messages(row["id"], request) if row else None


@app.post("/api/chat/conversations/{conversation_id}/close")
def customer_close(conversation_id: UUID, request: Request):
    customer_id = _customer_from_request(request)
    user = user_from_token(request.cookies.get(settings().auth_cookie_name))
    if not user or user["role"] != "cliente" or user["customer_id"] != customer_id:
        raise HTTPException(403, "Sessão do cliente necessária para encerrar.")
    try:
        result = close_customer_conversation(conversation_id, customer_id, user["id"])
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc
    if result["handoff_id"]:
        hub.publish_all_technicians({"type": "handoff.closed", "handoff_id": str(result["handoff_id"])})
        _broadcast_queue_positions()
    if result.get("message_id"):
        hub.publish_customer(
            str(conversation_id),
            hub.event(
                "handoff.closed",
                message="Você encerrou este atendimento.",
                message_id=str(result["message_id"]),
                status="closed",
            ),
        )
    return result


@app.get("/api/chat/conversations/{conversation_id}/messages")
def customer_messages(conversation_id: UUID, request: Request):
    customer_id = _customer_from_request(request)
    if not conversation_belongs_to_customer(conversation_id, customer_id):
        raise HTTPException(403, "Conversa não pertence à sessão do cliente.")
    with connection() as conn:
        conversation = conn.execute(
            "SELECT status FROM conversations WHERE id=%s", (conversation_id,)
        ).fetchone()
        messages = conn.execute(
            "SELECT id,sender_type,sender_id,content,created_at FROM messages "
            "WHERE conversation_id=%s AND visibility='public' ORDER BY created_at,id",
            (conversation_id,),
        ).fetchall()
    return {"conversation_id": conversation_id, "status": conversation["status"], "messages": messages}


@app.get("/api/tech/conversations")
def technician_conversations(user: dict = Depends(require_role("tecnico"))):
    return list_conversations(user["id"])


def _center_rows(where: str, params: tuple = (), *, closed_first: bool = False):
    order = (
        "h.closed_at DESC,h.id DESC"
        if closed_first
        else "COALESCE(h.waiting_since,h.assigned_at,h.closed_at),h.id"
    )
    with connection() as conn:
        return conn.execute(
            "SELECT h.id,h.conversation_id,h.reason,h.summary,h.status,h.waiting_since,h.assigned_at,h.closed_at,"
            "h.technician_id,h.close_category,h.resolution_note,tu.display_name AS technician_name,c.selected_terminal_id,"
            "COALESCE(t.apelido,t.model,'Máquina não selecionada') AS terminal_name,u.nome AS customer_name "
            "FROM handoffs h JOIN conversations c ON c.id=h.conversation_id JOIN customers u ON u.id=c.customer_id "
            "LEFT JOIN users tu ON tu.id=h.technician_id "
            "LEFT JOIN terminals t ON t.id=c.selected_terminal_id "
            f"WHERE {where} ORDER BY {order}",
            params,
        ).fetchall()


@app.get("/api/tech/service-center/summary")
def service_center_summary(user: dict = Depends(require_role("tecnico"))):
    with connection() as conn:
        counts = service_center_counts(user["id"], conn=conn)
        closed = conn.execute(
            "SELECT count(*) AS total FROM handoffs h WHERE h.status='closed' AND "
            "(h.closed_by_id=%s OR h.technician_id=%s OR "
            "(h.technician_id IS NULL AND EXISTS (SELECT 1 FROM handoff_events e WHERE e.handoff_id=h.id AND e.type='customer_closed')))",
            (user["id"], user["id"]),
        ).fetchone()["total"]
    return {**counts, "closed": closed}


@app.get("/api/tech/queue")
def service_center_queue(user: dict = Depends(require_role("tecnico"))):
    rows = _center_rows("h.status='waiting'")
    for pos, row in enumerate(rows, 1):
        row["position"] = pos
    return rows


@app.get("/api/tech/handoffs/mine")
def service_center_mine(user: dict = Depends(require_role("tecnico"))):
    return _center_rows("h.status='assigned' AND h.technician_id=%s", (user["id"],))


@app.get("/api/tech/handoffs/others")
def service_center_others(user: dict = Depends(require_role("tecnico"))):
    return _center_rows("h.status='assigned' AND h.technician_id<>%s", (user["id"],))


@app.get("/api/tech/handoffs/closed")
def service_center_closed(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    category: str = "",
    search: str = "",
    user: dict = Depends(require_role("tecnico")),
):
    where, params = (
        "h.status='closed' AND (h.closed_by_id=%s OR h.technician_id=%s OR "
        "(h.technician_id IS NULL AND EXISTS (SELECT 1 FROM handoff_events e WHERE e.handoff_id=h.id AND e.type='customer_closed')))",
        [user["id"], user["id"]],
    )
    if category:
        where += " AND h.close_category=%s"
        params.append(category)
    if search:
        where += " AND (u.nome ILIKE %s OR h.resolution_note ILIKE %s)"
        params.extend([f"%{search}%", f"%{search}%"])
    rows = _center_rows(where, tuple(params), closed_first=True)
    return {
        "items": rows[(page - 1) * page_size : page * page_size],
        "total": len(rows),
        "page": page,
        "page_size": page_size,
    }


@app.get("/api/tech/technicians")
def service_center_technicians(user: dict = Depends(require_role("tecnico"))):
    with connection() as conn:
        return conn.execute(
            "SELECT u.id,u.display_name,p.status,count(h.id) FILTER (WHERE h.status='assigned') AS active_chats FROM users u JOIN technician_presence p ON p.user_id=u.id LEFT JOIN handoffs h ON h.technician_id=u.id WHERE u.role='tecnico' AND u.is_active=true GROUP BY u.id,u.display_name,p.status ORDER BY u.id"
        ).fetchall()


def _public_handoff_event(result: dict, event_type: str):
    with connection() as conn:
        name = (
            conn.execute("SELECT display_name FROM users WHERE id=%s", (result["technician_id"],)).fetchone()
            if result.get("technician_id")
            else None
        )
    if result["status"] == "waiting":
        text = "Estamos direcionando você para o próximo técnico disponível."
    elif event_type in {"handoff.pulled", "handoff.transferred"}:
        text = f"Seu atendimento agora está com {name['display_name']}."
    else:
        text = f"{name['display_name']} assumiu seu atendimento."
    message_id = persist_message(result["conversation_id"], "system", "system", text)
    hub.publish_customer(
        str(result["conversation_id"]),
        hub.event(event_type, message=text, message_id=str(message_id), status=result["status"]),
    )
    hub.publish_all_technicians({"type": "queue.updated"})


@app.post("/api/tech/handoffs/{handoff_id}/claim")
def service_center_claim(handoff_id: UUID, user: dict = Depends(require_role("tecnico"))):
    try:
        result = claim(handoff_id, user["id"])
    except HandoffConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(409, str(exc)) from exc
    _public_handoff_event(result, "handoff.claimed")
    return result


@app.post("/api/tech/handoffs/{handoff_id}/pull")
def service_center_pull(
    handoff_id: UUID, payload: PullHandoffRequest, user: dict = Depends(require_role("tecnico"))
):
    try:
        result = pull(handoff_id, user["id"], payload.reason)
    except HandoffConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc
    _public_handoff_event(result, "handoff.pulled")
    hub.publish_technician(
        result["previous_technician_id"], {"type": "handoff.pulled_from_you", "handoff_id": str(handoff_id)}
    )
    return result


@app.post("/api/tech/handoffs/{handoff_id}/transfer")
def service_center_transfer(
    handoff_id: UUID, payload: TransferHandoffRequest, user: dict = Depends(require_role("tecnico"))
):
    if payload.to_queue == (payload.to_technician_id is not None):
        raise HTTPException(422, "Informe um técnico de destino ou devolva à fila.")
    try:
        result = transfer(
            handoff_id, user["id"], None if payload.to_queue else payload.to_technician_id, payload.note
        )
    except HandoffConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc
    _public_handoff_event(result, "handoff.transferred")
    if result.get("technician_id"):
        hub.publish_technician(
            result["technician_id"], {"type": "handoff.transferred_to_you", "handoff_id": str(handoff_id)}
        )
    return result


@app.post("/api/tech/handoffs/{handoff_id}/close")
def service_center_close(
    handoff_id: UUID, payload: CloseHandoffRequest, user: dict = Depends(require_role("tecnico"))
):
    try:
        result = close_handoff(handoff_id, payload.resolution_note, user["id"], payload.close_category)
    except HandoffConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    text = CLOSED_MESSAGE
    message_id = result["message_id"]
    hub.publish_customer(
        str(result["conversation_id"]),
        hub.event("handoff.closed", message=text, message_id=str(message_id), status="closed"),
    )
    hub.publish_technician(user["id"], {"type": "handoff.closed", "handoff_id": str(handoff_id)})
    return result


@app.post("/api/tech/handoffs/{handoff_id}/notes")
def service_center_note(
    handoff_id: UUID, payload: InternalNoteRequest, user: dict = Depends(require_role("tecnico"))
):
    return add_internal_note(handoff_id, user["id"], payload.text)


@app.get("/api/tech/handoffs/{handoff_id}/events")
def service_center_events(handoff_id: UUID, user: dict = Depends(require_role("tecnico"))):
    with connection() as conn:
        owner = conn.execute(
            "SELECT 1 FROM handoffs h WHERE h.id=%s AND (h.technician_id=%s OR h.closed_by_id=%s OR "
            "(h.status='closed' AND h.technician_id IS NULL AND EXISTS (SELECT 1 FROM handoff_events e WHERE e.handoff_id=h.id AND e.type='customer_closed')))",
            (handoff_id, user["id"], user["id"]),
        ).fetchone()
        if not owner:
            raise HTTPException(403, "Eventos disponíveis apenas ao técnico responsável.")
        return conn.execute(
            "SELECT e.id,e.type,e.note,e.created_at,ua.display_name AS actor_name FROM handoff_events e LEFT JOIN users ua ON ua.id=e.actor_id WHERE e.handoff_id=%s ORDER BY e.created_at,e.id",
            (handoff_id,),
        ).fetchall()


@app.get("/api/tech/handoffs/{handoff_id}/preview")
def service_center_queue_preview(handoff_id: UUID, user: dict = Depends(require_role("tecnico"))):
    """Read-only public context to decide whether to assume a waiting handoff."""
    with connection() as conn:
        handoff = conn.execute(
            "SELECT h.id,h.conversation_id,h.reason,h.summary,u.nome AS customer_name,"
            "COALESCE(t.apelido,t.model,'Máquina não selecionada') AS terminal_name "
            "FROM handoffs h JOIN conversations c ON c.id=h.conversation_id "
            "JOIN customers u ON u.id=c.customer_id LEFT JOIN terminals t ON t.id=c.selected_terminal_id "
            "WHERE h.id=%s AND h.status='waiting'",
            (handoff_id,),
        ).fetchone()
        if not handoff:
            raise HTTPException(404, "Atendimento não está disponível na fila.")
        handoff["messages"] = conn.execute(
            "SELECT id,sender_type,content,created_at FROM messages "
            "WHERE conversation_id=%s AND visibility='public' "
            "ORDER BY created_at DESC,id DESC LIMIT 8",
            (handoff["conversation_id"],),
        ).fetchall()[::-1]
        return handoff


@app.get("/api/tech/conversations/{conversation_id}")
def technician_conversation(
    conversation_id: UUID, handoff_id: UUID | None = None, user: dict = Depends(require_role("tecnico"))
):
    detail = conversation_detail(conversation_id, user["id"], handoff_id)
    if not detail:
        raise HTTPException(403, "Conversa não atribuída a este técnico.")
    return detail


@app.post("/api/tech/conversations/{conversation_id}/messages")
async def technician_message(
    conversation_id: UUID,
    payload: TechnicianMessageRequest,
    user: dict = Depends(require_role("tecnico")),
):
    if not technician_owns_conversation(conversation_id, user["id"]):
        raise HTTPException(403, "Conversa não atribuída a este técnico.")
    detail = conversation_detail(conversation_id, user["id"])
    if not detail or detail["handoff_status"] != "assigned":
        raise HTTPException(409, "Este atendimento não está ativo.")
    with connection() as conn:
        handoff = conn.execute(
            "SELECT status,technician_id FROM handoffs WHERE id=%s FOR UPDATE", (detail["handoff_id"],)
        ).fetchone()
        conversation = conn.execute(
            "SELECT status FROM conversations WHERE id=%s FOR UPDATE", (conversation_id,)
        ).fetchone()
        if (
            not conversation
            or conversation["status"] != "with_technician"
            or not handoff
            or handoff["status"] != "assigned"
            or handoff["technician_id"] != user["id"]
        ):
            raise HTTPException(409, "Este atendimento foi encerrado ou transferido.")
        message_id = uuid4()
        conn.execute(
            "INSERT INTO messages(id,conversation_id,sender_type,sender_id,content) VALUES (%s,%s,'technician',%s,%s)",
            (message_id, conversation_id, str(user["id"]), payload.content),
        )
        conn.execute(
            "UPDATE handoffs SET first_response_at=COALESCE(first_response_at,now()),version=version+1 WHERE id=%s",
            (detail["handoff_id"],),
        )
    event = {
        "type": "message",
        "message": {
            "id": str(message_id),
            "sender_type": "technician",
            "sender_id": str(user["id"]),
            "sender_name": user["display_name"],
            "content": payload.content,
        },
    }
    await hub.customer(str(conversation_id), event)
    await hub.technician(user["id"], {"type": "message.sent", "conversation_id": str(conversation_id)})
    return event["message"]


@app.post("/api/tech/conversations/{conversation_id}/close")
async def technician_close(
    conversation_id: UUID,
    payload: CloseHandoffRequest,
    user: dict = Depends(require_role("tecnico")),
):
    detail = conversation_detail(conversation_id, user["id"])
    if not detail:
        raise HTTPException(403, "Conversa não atribuída a este técnico.")
    try:
        result = close_handoff(detail["handoff_id"], payload.resolution_note, user["id"])
    except HandoffConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    text = CLOSED_MESSAGE
    message_id = result["message_id"]
    await hub.customer(
        str(conversation_id),
        hub.event("handoff.closed", message=text, message_id=str(message_id), status="closed"),
    )
    await hub.all_technicians({"type": "conversations.refresh"})
    _notify_assignment(result.get("assigned_handoff_id"))
    _broadcast_queue_positions()
    return result


@app.websocket("/ws/chat/{conversation_id}")
async def customer_websocket(websocket: WebSocket, conversation_id: UUID):
    if not websocket_origin_allowed(websocket):
        await websocket.close(code=4403)
        return
    authenticated = user_from_token(websocket.cookies.get(settings().auth_cookie_name))
    customer_id = (
        authenticated["customer_id"]
        if authenticated and authenticated["role"] == "cliente" and not authenticated["must_change_password"]
        else decode_customer_token(websocket.cookies.get(settings().customer_cookie_name))
        if not authenticated
        else None
    )
    if not customer_id or not conversation_belongs_to_customer(conversation_id, customer_id):
        await websocket.close(code=4403)
        return
    await hub.add_customer(str(conversation_id), websocket)
    try:
        handoff = active_handoff_for_conversation(conversation_id)
        detail = None
        if handoff and handoff.get("technician_id"):
            with connection() as conn:
                detail = conn.execute(
                    "SELECT display_name FROM users WHERE id=%s", (handoff["technician_id"],)
                ).fetchone()
        await websocket.send_json(
            {
                "event_id": f"queue:{handoff['id']}:{handoff.get('queue_position')}"
                if handoff and handoff["status"] == "waiting"
                else f"technician:{handoff['id']}:{handoff.get('technician_id')}"
                if handoff
                else "connection:ai",
                "type": "connection.ready",
                "status": handoff["status"] if handoff else "ai",
                "queue_position": handoff.get("queue_position") if handoff else None,
                "technician_name": detail["display_name"] if detail else None,
            }
        )
        while True:
            frame = await asyncio.wait_for(
                websocket.receive_text(), timeout=settings().websocket_idle_timeout_seconds
            )
            if len(frame.encode("utf-8")) > settings().websocket_max_message_bytes:
                await websocket.close(code=1009)
                break
            allowed, _ = request_limiter.allow(
                f"ws:customer:{customer_id}", settings().websocket_messages_per_minute, 60
            )
            if not allowed:
                await websocket.close(code=4429)
                break
    except (WebSocketDisconnect, asyncio.TimeoutError):
        hub.remove_customer(str(conversation_id), websocket)


async def _offline_after_disconnect(user_id: int):
    await asyncio.sleep(settings().handoff_offline_timeout_seconds)
    if not hub.technicians[user_id]:
        await asyncio.to_thread(set_technician_status, user_id, "offline")


@app.websocket("/ws/tech")
async def technician_websocket(websocket: WebSocket):
    if not websocket_origin_allowed(websocket):
        await websocket.close(code=4403)
        return
    user = user_from_token(websocket.cookies.get(settings().auth_cookie_name))
    if not user or user["role"] != "tecnico":
        await websocket.close(code=4401)
        return
    await hub.add_technician(user["id"], websocket)
    result = await asyncio.to_thread(set_technician_status, user["id"], "online")
    await websocket.send_json({"type": "connection.ready", "user_id": user["id"]})
    if result.get("assigned_handoff_id"):
        await websocket.send_json({"type": "handoff.assigned"})
    try:
        while True:
            frame = await asyncio.wait_for(
                websocket.receive_text(), timeout=settings().websocket_idle_timeout_seconds
            )
            if len(frame.encode("utf-8")) > settings().websocket_max_message_bytes:
                await websocket.close(code=1009)
                break
            allowed, _ = request_limiter.allow(
                f"ws:tech:{user['id']}", settings().websocket_messages_per_minute, 60
            )
            if not allowed:
                await websocket.close(code=4429)
                break
    except (WebSocketDisconnect, asyncio.TimeoutError):
        if hub.remove_technician(user["id"], websocket):
            asyncio.create_task(_offline_after_disconnect(user["id"]))


@app.post("/api/chat", response_model=ChatResponse)
def chat(payload: ChatRequest, response: Response, request: Request):
    cfg = settings()
    ip = client_ip(request)
    auth_cookie = request.cookies.get(cfg.auth_cookie_name)
    authenticated = user_from_token(auth_cookie)
    if auth_cookie and not authenticated:
        raise HTTPException(401, "Sessão expirada. Entre novamente.")
    if not authenticated and not cfg.anonymous_chat_enabled:
        raise HTTPException(401, "Entre na sua conta para iniciar o atendimento.")
    if authenticated and authenticated["role"] != "cliente":
        raise HTTPException(403, "Use uma conta de cliente para acessar o atendimento.")
    if authenticated and authenticated["must_change_password"]:
        raise HTTPException(403, "Troque a senha antes de acessar o atendimento.")
    if authenticated:
        customer_id = authenticated["customer_id"]
        if payload.user_id is not None and customer_id != payload.user_id:
            raise HTTPException(403, "Cliente não autorizado para este cadastro.")
    else:
        customer_id = payload.user_id
        if not customer_id:
            raise HTTPException(422, "Informe user_id para usar o chat anônimo de demonstração.")
    if not customer_exists(customer_id):
        raise HTTPException(404, "Cliente não localizado no cadastro. Confira o identificador informado.")
    rate_keys = (
        (
            f"chat:session:{authenticated['id'] if authenticated else customer_id}",
            cfg.chat_requests_per_minute,
        ),
        (f"chat:ip:{ip}", cfg.chat_requests_per_minute * 5),
    )
    for rate_key, rate_limit in rate_keys:
        allowed, retry_after = request_limiter.allow(rate_key, rate_limit, 60)
        if not allowed:
            logger.warning(
                json.dumps(
                    {
                        "event": "chat_rate_limited",
                        "key_hash": sha256(rate_key.encode()).hexdigest()[:12],
                        "retry_after": retry_after,
                    }
                )
            )
            raise HTTPException(
                429,
                "Limite de mensagens atingido. Aguarde antes de tentar novamente.",
                headers={"Retry-After": str(retry_after)},
            )
    with connection() as conn:
        used = conn.execute(
            "SELECT tokens FROM customer_token_usage_daily WHERE customer_id=%s AND day=CURRENT_DATE",
            (customer_id,),
        ).fetchone()
        if used and used["tokens"] >= cfg.customer_daily_token_budget:
            raise HTTPException(
                429,
                "Orçamento diário de atendimento atingido. Tente novamente amanhã ou fale com um técnico.",
            )
    start = perf_counter()
    request_uuid = uuid4()
    request_id = str(request_uuid)
    try:
        conversation = (
            get_or_create_conversation(
                customer_id,
                UUID(payload.conversation_id) if payload.conversation_id else None,
                fresh=bool(authenticated and not payload.conversation_id),
            )
            if authenticated or payload.conversation_id
            else get_or_create_conversation(customer_id)
        )
    except (ValueError, PermissionError) as exc:
        raise HTTPException(409, str(exc)) from exc
    conversation_id = conversation["id"]
    try:
        decision = inspect_input(
            payload.message,
            customer_id,
            cfg.effective_off_topic_policy,
            not conversation.get("is_new", False),
        )
    except Exception as exc:
        decision = InputDecision("", "prompt_injection", True, "input_layer_failure", "block", "critical")
        logger.error(
            json.dumps(
                {
                    "event": "guardrail_failure",
                    "layer": "input",
                    "error_type": type(exc).__name__,
                    "request_id": request_id,
                }
            )
        )
    payload.message = decision.text
    if decision.action != "allow":
        record_event(
            request_uuid,
            conversation_id,
            "input",
            decision.rule,
            decision.action,
            decision.severity,
            decision.text,
        )
    if decision.block:
        persist_message(conversation_id, "customer", customer_id, decision.text)
        answers = {
            "cross_customer_request": "Não posso acessar nem mostrar dados de outro cliente. Posso ajudar com o seu próprio cadastro Getnet.",
            "prompt_injection": "Não posso seguir instruções para revelar ou alterar minhas regras. Posso ajudar com produtos, máquinas e atendimento Getnet.",
            "sensitive_data": "Por segurança, mascarei os dados enviados. Não compartilhe CPF, cartão, telefone ou e-mail no chat. Posso continuar sem esses dados.",
            "abusive": "Quero ajudar, mas vamos manter a conversa respeitosa. Posso orientar sobre a Getnet ou chamar um técnico.",
            "off_topic": policy_message("scope", language_for(payload.message)),
        }
        answer = answers.get(
            decision.safety_label,
            "Não posso processar essa solicitação com segurança. Posso chamar um técnico.",
        )
        if decision.rule == "command_execution_request":
            answer = (
                "Não executo comandos, códigos ou scripts enviados pelo chat. "
                "Posso ajudar com produtos, máquinas e atendimento Getnet."
            )
        blocked = ChatResponse(
            request_id=request_id,
            conversation_id=str(conversation_id),
            answer=answer,
            route="blocked",
            agents_used=["Guardrail"],
            status="blocked",
            latency_ms=int((perf_counter() - start) * 1000),
        )
        persist_run(
            request_id=request_uuid,
            conversation_id=conversation_id,
            user_id=customer_id,
            route="blocked",
            agents_used=blocked.agents_used,
            status="blocked",
            latency_ms=blocked.latency_ms,
            tokens={},
            tool_calls=[],
            answer=answer,
        )
        return blocked
    terminals = list_customer_terminals(customer_id)
    terminal_id = payload.terminal_id or conversation.get("selected_terminal_id")
    if terminal_id and not any(item["id"] == terminal_id for item in terminals):
        raise HTTPException(403, "Terminal não pertence ao cliente autenticado.")
    normalized = payload.message.casefold()
    machine_intent = any(
        word in normalized
        for word in ("máquina", "maquina", "maquininha", "terminal", "offline", "conecta", "erro", "falha")
    )
    if conversation.get("pending_terminal_selection") and not terminal_id:
        matches = [
            item
            for item in terminals
            if item["id"].casefold() in normalized
            or (item.get("apelido") and item["apelido"].casefold() in normalized)
            or (item.get("model") and item["model"].casefold() in normalized)
        ]
        if len(matches) == 1:
            terminal_id = matches[0]["id"]
    if not terminal_id and machine_intent and len(terminals) == 1:
        terminal_id = terminals[0]["id"]
    if terminal_id:
        with connection() as conn:
            conn.execute(
                "UPDATE conversations SET selected_terminal_id=%s,pending_terminal_selection=false WHERE id=%s",
                (terminal_id, conversation_id),
            )
    customer_message_id = persist_message(conversation_id, "customer", customer_id, payload.message)
    memory = conversation_memory(conversation_id)
    set_session_cookie(response, cfg.customer_cookie_name, create_customer_token(customer_id))
    if not capacity.acquire(blocking=False):
        raise HTTPException(429, "Há dois atendimentos em execução. Aguarde e tente novamente.")
    provider = None
    result = None

    def record_failure(exc):
        steps = result.get("steps", []) if result else []
        persist_run(
            request_id=request_uuid,
            conversation_id=conversation_id,
            user_id=customer_id,
            route=result["route"].route if result and result.get("route") else "clarify",
            agents_used=list(dict.fromkeys(item["agent"] for item in steps)),
            status="unavailable",
            latency_ms=int((perf_counter() - start) * 1000),
            tokens=getattr(provider, "usage", {}) if provider else {},
            tool_calls=result.get("tool_calls", []) if result else [],
            error=f"{type(exc).__name__}: {exc}",
        )

    try:
        if (
            machine_intent
            and len(terminals) > 1
            and not terminal_id
            and conversation["status"] not in {"waiting", "with_technician"}
        ):
            with connection() as conn:
                conn.execute(
                    "UPDATE conversations SET pending_terminal_selection=true WHERE id=%s", (conversation_id,)
                )
            options = [
                item.get("apelido") or f"{item['model']} ••••{item['serial_number'][-4:]}"
                for item in terminals
            ]
            answer = policy_message("terminal", language_for(payload.message)) + " " + " | ".join(options)
            clarification = ChatResponse(
                request_id=request_id,
                conversation_id=str(conversation_id),
                answer=answer,
                route="clarify",
                agents_used=["Router"],
                status="needs_clarification",
                latency_ms=int((perf_counter() - start) * 1000),
                quick_replies=options,
            )
            persist_run(
                request_id=request_uuid,
                conversation_id=conversation_id,
                user_id=customer_id,
                route="clarify",
                agents_used=["Router"],
                status=clarification.status,
                latency_ms=clarification.latency_ms,
                tokens={},
                tool_calls=[],
                answer=answer,
            )
            return clarification
        if conversation["status"] in {"waiting", "with_technician"}:
            handoff = active_handoff_for_conversation(conversation_id)
            status = conversation["status"]
            response = ChatResponse(
                request_id=request_id,
                conversation_id=str(conversation_id),
                answer="",
                route="escalation",
                agents_used=[],
                status=status,
                latency_ms=int((perf_counter() - start) * 1000),
            )
            persist_run(
                request_id=request_uuid,
                conversation_id=conversation_id,
                user_id=customer_id,
                route=response.route,
                agents_used=[],
                status=response.status,
                latency_ms=response.latency_ms,
                tokens={},
                tool_calls=[],
                answer=None,
            )
            if status == "with_technician" and handoff and handoff.get("technician_id"):
                hub.publish_technician(
                    handoff["technician_id"],
                    {
                        "type": "message",
                        "conversation_id": str(conversation_id),
                        "message": {
                            "id": str(customer_message_id),
                            "sender_type": "customer",
                            "sender_id": customer_id,
                            "content": payload.message,
                        },
                    },
                )
            return response
        if payload.message.casefold().strip(" .,!?") in {
            "ok",
            "obrigado",
            "obrigada",
            "valeu",
            "thanks",
            "thank you",
            "gracias",
        }:
            answer = policy_message("thanks", language_for(payload.message))
            response = ChatResponse(
                request_id=request_id,
                conversation_id=str(conversation_id),
                answer=answer,
                route="knowledge",
                agents_used=["Router"],
                status="ok",
                latency_ms=int((perf_counter() - start) * 1000),
            )
            persist_run(
                request_id=request_uuid,
                conversation_id=conversation_id,
                user_id=customer_id,
                route=response.route,
                agents_used=response.agents_used,
                status=response.status,
                latency_ms=response.latency_ms,
                tokens={},
                tool_calls=[],
                answer=response.answer,
            )
            return response
        provider = Provider()
        graph = build_graph(provider)
        result = graph.invoke(
            {
                "message": payload.message,
                "user_id": customer_id,
                "conversation_id": str(conversation_id),
                "failure_count": conversation["failure_count"],
                "terminal_id": terminal_id,
                "customer_context": {
                    "name": authenticated["display_name"] if authenticated else customer_id,
                    "terminals": terminals,
                    "selected_terminal_id": terminal_id,
                },
                "conversation_memory": memory,
                "steps": [],
                "tool_calls": [],
            },
            config={"recursion_limit": 8},
        )
        response = ChatResponse(
            request_id=request_id,
            conversation_id=str(conversation_id),
            answer=result["answer"],
            route=result["route"].route,
            agents_used=list(dict.fromkeys(s["agent"] for s in result["steps"])),
            sources=result.get("sources", []),
            steps=result["steps"],
            status=result["status"],
            handoff_token=result.get("handoff_token"),
            quick_replies=result.get("quick_replies", []),
            latency_ms=int((perf_counter() - start) * 1000),
        )
        route_safety = result["route"].safety_label
        if route_safety != "ok":
            record_event(
                request_uuid,
                conversation_id,
                "classification",
                route_safety,
                "block",
                "high",
                payload.message,
            )
            response.answer = (
                policy_message("scope", result["route"].language)
                if route_safety == "off_topic"
                else "Não posso atender esse pedido com segurança. Posso ajudar com sua conta, produtos e máquinas Getnet."
            )
            response.route = "blocked"
            response.status = "blocked"
            response.sources = []
        output_domains = cfg.allowed_web_domains
        if result["route"].knowledge_source == "web" and is_exchange_query(payload.message):
            output_domains = (*output_domains, *EXCHANGE_DOMAINS)
        try:
            output_ok, output_rule, safe_answer = inspect_output(response.answer, output_domains)
        except Exception as exc:
            logger.error(
                json.dumps(
                    {
                        "event": "guardrail_failure",
                        "layer": "output",
                        "error_type": type(exc).__name__,
                        "request_id": request_id,
                    }
                )
            )
            output_ok, output_rule, safe_answer = (
                False,
                "output_layer_failure",
                "Não consegui validar essa resposta com segurança. Posso encaminhar para um técnico.",
            )
        if not output_ok:
            record_event(
                request_uuid, conversation_id, "output", output_rule, "block", "high", response.answer
            )
            response.answer = safe_answer
            response.route = "blocked"
            response.status = "blocked"
            response.sources = []
        elif decision.notices:
            response.answer = " ".join(decision.notices) + "\n\n" + response.answer
        if response.status == "waiting":
            current_handoff = active_handoff_for_conversation(conversation_id)
            if current_handoff:
                response.event_id = f"queue:{current_handoff['id']}:{current_handoff.get('queue_position')}"
        elif response.status == "with_technician":
            current_handoff = active_handoff_for_conversation(conversation_id)
            if current_handoff:
                response.event_id = (
                    f"technician:{current_handoff['id']}:{current_handoff.get('technician_id')}"
                )
        persist_run(
            request_id=request_uuid,
            conversation_id=conversation_id,
            user_id=customer_id,
            route=response.route,
            agents_used=response.agents_used,
            status=response.status,
            latency_ms=response.latency_ms,
            tokens=getattr(provider, "usage", {}),
            tool_calls=result.get("tool_calls", []),
            answer=response.answer,
        )
        update_conversation_summary(conversation_id)
        provider_usage = getattr(provider, "usage", {})
        token_total = int(provider_usage.get("input_tokens", 0)) + int(provider_usage.get("output_tokens", 0))
        if token_total:
            with connection() as conn:
                conn.execute(
                    "INSERT INTO customer_token_usage_daily(customer_id,day,tokens) VALUES (%s,CURRENT_DATE,%s) "
                    "ON CONFLICT(customer_id,day) DO UPDATE SET tokens=customer_token_usage_daily.tokens+EXCLUDED.tokens",
                    (customer_id, token_total),
                )
        if response.status in {"waiting", "with_technician"}:
            handoff = active_handoff_for_conversation(conversation_id)
            hub.publish_all_technicians({"type": "conversations.refresh"})
            if handoff and handoff.get("technician_id"):
                hub.publish_technician(handoff["technician_id"], {"type": "handoff.assigned"})
            _broadcast_queue_positions()
        logger.info(
            json.dumps(
                {
                    "event": "chat_completed",
                    "request_id": request_id,
                    "route": response.route,
                    "status": response.status,
                    "latency_ms": response.latency_ms,
                    "agents": response.agents_used,
                    "source_count": len(response.sources),
                },
                ensure_ascii=False,
            )
        )
        return response
    except ToolPolicyError as exc:
        record_event(
            request_uuid, conversation_id, "tools", "tool_policy_failure", "block", "high", type(exc).__name__
        )
        answer = "Uma verificação de segurança impediu a consulta. Nenhum dado foi alterado; posso encaminhar para um técnico."
        safe = ChatResponse(
            request_id=request_id,
            conversation_id=str(conversation_id),
            answer=answer,
            route="blocked",
            agents_used=["Guardrail"],
            status="blocked",
            latency_ms=int((perf_counter() - start) * 1000),
        )
        persist_run(
            request_id=request_uuid,
            conversation_id=conversation_id,
            user_id=customer_id,
            route="blocked",
            agents_used=safe.agents_used,
            status="blocked",
            latency_ms=safe.latency_ms,
            tokens=getattr(provider, "usage", {}) if provider else {},
            tool_calls=[],
            answer=answer,
        )
        return safe
    except BudgetExceeded as exc:
        record_failure(exc)
        raise HTTPException(429, str(exc)) from exc
    except ProviderUnavailable as exc:
        record_failure(exc)
        raise HTTPException(503, str(exc)) from exc
    except OpenAIError as exc:
        record_failure(exc)
        logger.warning(
            json.dumps(
                {"event": "provider_failed", "request_id": request_id, "error_type": type(exc).__name__}
            )
        )
        if getattr(exc, "code", None) in ("credit_balance_exhausted", "insufficient_quota"):
            raise HTTPException(
                503,
                "O projeto OpenAI desta chave está sem crédito disponível. "
                "Confira o faturamento na plataforma OpenAI e tente novamente.",
            ) from exc
        raise HTTPException(
            503,
            "A OpenAI não concluiu a chamada. Verifique chave, crédito e conectividade. "
            "Identificador: " + request_id,
        ) from exc
    finally:
        capacity.release()


_generated_openapi = app.openapi


def _security_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    schema = annotate_openapi(_generated_openapi())
    app.openapi_schema = schema
    return schema


app.openapi = _security_openapi
