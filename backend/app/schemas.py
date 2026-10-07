from typing import Literal
from uuid import UUID

from pydantic import BaseModel as PydanticBaseModel
from pydantic import ConfigDict, Field, field_validator


class BaseModel(PydanticBaseModel):
    pass


class StrictWriteModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PresenceRequest(StrictWriteModel):
    session_id: UUID
    active: bool = True


class ChatRequest(StrictWriteModel):
    message: str = Field(min_length=1, max_length=10000)
    # Optional for signed-in portal users; chat() always derives their identity
    # from the session. Kept for backwards-compatible anonymous demo requests.
    user_id: str | None = Field(default=None, min_length=1, max_length=120)
    terminal_id: str | None = Field(default=None, min_length=2, max_length=120)
    conversation_id: str | None = None

    @field_validator("message")
    @classmethod
    def not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("A mensagem não pode estar vazia.")
        return value.strip()


class Route(BaseModel):
    route: Literal["knowledge", "support", "knowledge_support", "escalation", "clarify", "blocked"]
    knowledge_source: Literal["rag", "web"] = "rag"
    support_tools: list[
        Literal["get_receivables", "get_terminal_status", "get_customer_profile", "list_customer_terminals"]
    ]
    search_query: str
    clarification: str
    language: str = Field(default="pt", pattern=r"^[a-z]{2,3}(?:-[A-Za-z]{2,4})?$")
    customer_dissatisfied: bool = False
    accepts_human_offer: bool = False
    currency_base: str = Field(default="", pattern=r"^(?:[A-Z]{3})?$")
    currency_quote: str = Field(default="", pattern=r"^(?:[A-Z]{3})?$")
    safety_label: Literal[
        "ok", "off_topic", "prompt_injection", "sensitive_data", "abusive", "cross_customer_request"
    ] = "ok"


class Draft(BaseModel):
    answer: str
    source_ids: list[int]
    insufficient_evidence: bool


class EscalationSummary(BaseModel):
    problem: str
    customer_context: str
    terminal_context: str
    attempts: list[str]
    reason: Literal["cliente_pediu", "baixa_confianca", "falha_nao_resolvida"]


class Source(BaseModel):
    id: int
    title: str
    url: str | None = None
    retrieved_at: str
    kind: Literal["rag", "manual", "web", "customer"]


class Step(BaseModel):
    agent: str
    action: str
    duration_ms: int = 0


class ChatResponse(BaseModel):
    request_id: str
    conversation_id: str
    answer: str
    route: str
    agents_used: list[str]
    sources: list[Source] = Field(default_factory=list)
    steps: list[Step] = Field(default_factory=list)
    status: Literal[
        "ok", "needs_clarification", "needs_handoff", "blocked", "unavailable", "waiting", "with_technician"
    ]
    handoff_token: str | None = None
    demo: bool = True
    latency_ms: int = 0
    event_id: str | None = None
    quick_replies: list[str] = Field(default_factory=list)


class LoginRequest(StrictWriteModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=200)


class AuthUser(BaseModel):
    id: int
    username: str
    role: Literal["admin", "tecnico", "cliente"]
    display_name: str
    customer_id: str | None = None
    must_change_password: bool = False


class ChangePasswordRequest(StrictWriteModel):
    current_password: str = Field(min_length=1, max_length=200)
    new_password: str = Field(min_length=8, max_length=200)


class CustomerCreate(StrictWriteModel):
    username: str = Field(min_length=3, max_length=100)
    nome: str = Field(min_length=2, max_length=150)
    email: str | None = Field(default=None, max_length=254)
    telefone: str | None = Field(default=None, max_length=40)


class CustomerUpdate(StrictWriteModel):
    nome: str | None = Field(default=None, min_length=2, max_length=150)
    email: str | None = Field(default=None, max_length=254)
    telefone: str | None = Field(default=None, max_length=40)
    is_active: bool | None = None


class CustomerTerminalRequest(StrictWriteModel):
    terminal_id: str | None = Field(default=None, min_length=2, max_length=120)
    model_id: int | None = None
    serial_number: str | None = Field(default=None, min_length=2, max_length=120, pattern=r"^[A-Za-z0-9-]+$")
    apelido: str | None = Field(default=None, max_length=120)
    status: str | None = Field(default=None, max_length=50)


class TechnicianStatusRequest(StrictWriteModel):
    status: Literal["online", "pausa", "offline"]


class TechnicianMessageRequest(StrictWriteModel):
    content: str = Field(min_length=1, max_length=3000)

    @field_validator("content")
    @classmethod
    def message_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("A mensagem não pode estar vazia.")
        return value.strip()


class CloseHandoffRequest(StrictWriteModel):
    resolution_note: str = Field(default="", max_length=4000)

    close_category: Literal["resolvido", "nao_resolvido", "cliente_ausente", "outro"] = "resolvido"


class PullHandoffRequest(StrictWriteModel):
    reason: str = Field(min_length=10, max_length=1000)


class TransferHandoffRequest(StrictWriteModel):
    to_technician_id: int | None = None
    to_queue: bool = False
    note: str = Field(default="", max_length=2000)


class InternalNoteRequest(StrictWriteModel):
    text: str = Field(min_length=1, max_length=3000)


class AdminUserCreate(StrictWriteModel):
    username: str = Field(min_length=3, max_length=100)
    password: str = Field(min_length=8, max_length=200)
    role: Literal["admin", "tecnico"]
    display_name: str = Field(min_length=2, max_length=150)


class AdminUserUpdate(StrictWriteModel):
    username: str | None = Field(default=None, min_length=3, max_length=100)
    password: str | None = Field(default=None, min_length=8, max_length=200)
    role: Literal["admin", "tecnico"] | None = None
    display_name: str | None = Field(default=None, min_length=2, max_length=150)
    is_active: bool | None = None


class MachineCreate(StrictWriteModel):
    kind: Literal["model", "terminal"]
    name: str | None = Field(default=None, min_length=2, max_length=120)
    id: str | None = Field(default=None, min_length=2, max_length=120)
    customer_id: str | None = None
    model_id: int | None = None
    status: str | None = Field(default=None, min_length=2, max_length=50)
    last_error: str | None = Field(default=None, max_length=500)
    serial_number: str | None = Field(default=None, min_length=2, max_length=120, pattern=r"^[A-Za-z0-9-]+$")
    apelido: str | None = Field(default=None, max_length=120)


class MachineUpdate(StrictWriteModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    is_active: bool | None = None
    customer_id: str | None = None
    model_id: int | None = None
    status: str | None = Field(default=None, min_length=2, max_length=50)
    last_error: str | None = Field(default=None, max_length=500)
    serial_number: str | None = Field(default=None, min_length=2, max_length=120, pattern=r"^[A-Za-z0-9-]+$")
    apelido: str | None = Field(default=None, max_length=120)


class RagDocumentCreate(StrictWriteModel):
    title: str = Field(min_length=2, max_length=300)
    content: str = Field(min_length=20, max_length=500_000)


class RagDocumentUpdate(StrictWriteModel):
    title: str = Field(min_length=2, max_length=300)
    content: str = Field(min_length=20, max_length=500_000)


class RagUrlRequest(StrictWriteModel):
    url: str = Field(min_length=10, max_length=2000)


class RagReviewRequest(StrictWriteModel):
    decision: Literal["approved", "rejected"]
    reason: str = Field(min_length=10, max_length=1000)
