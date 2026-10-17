"""PostgreSQL business facts. All writes go through transactional services."""

from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Customer(Base):
    __tablename__ = "customers"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String)


class Policy(Base):
    __tablename__ = "policies"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    rules: Mapped[dict] = mapped_column(JSON)
    content_hash: Mapped[str] = mapped_column(String)
    current: Mapped[bool] = mapped_column(Boolean, default=False)
    __table_args__ = (
        Index(
            "one_current_policy", "current", unique=True, postgresql_where=text('"current" = true')
        ),
    )


class Variant(Base):
    __tablename__ = "variants"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    product_id: Mapped[str] = mapped_column(String)
    title: Mapped[str] = mapped_column(String)
    color: Mapped[str] = mapped_column(String)
    size: Mapped[str] = mapped_column(String)
    price_fen: Mapped[int] = mapped_column(Integer)
    returnable: Mapped[bool] = mapped_column(Boolean, default=True)
    exchangeable: Mapped[bool] = mapped_column(Boolean, default=True)
    category: Mapped[str] = mapped_column(String, default="ordinary")
    __table_args__ = (CheckConstraint("price_fen >= 0"),)


class Inventory(Base):
    __tablename__ = "inventory"
    variant_id: Mapped[str] = mapped_column(ForeignKey("variants.id"), primary_key=True)
    available: Mapped[int] = mapped_column(Integer)
    reserved: Mapped[int] = mapped_column(Integer, default=0)
    version: Mapped[int] = mapped_column(Integer, default=1)
    __table_args__ = (CheckConstraint("available >= 0 AND reserved >= 0"),)


class Order(Base):
    __tablename__ = "orders"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id"), index=True)
    status: Mapped[str] = mapped_column(String)
    paid_fen: Mapped[int] = mapped_column(Integer)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(Integer, default=1)
    policy_version: Mapped[str] = mapped_column(ForeignKey("policies.id"))
    __table_args__ = (CheckConstraint("paid_fen >= 0"),)


class OrderLine(Base):
    __tablename__ = "order_lines"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id"), index=True)
    variant_id: Mapped[str] = mapped_column(ForeignKey("variants.id"))
    quantity: Mapped[int] = mapped_column(Integer)
    occupied: Mapped[int] = mapped_column(Integer, default=0)
    unused: Mapped[bool] = mapped_column(Boolean, default=True)
    __table_args__ = (CheckConstraint("quantity > 0 AND occupied >= 0 AND occupied <= quantity"),)


class Conversation(Base):
    __tablename__ = "conversations"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id"), index=True)
    revision: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String, default="IDLE")
    case: Mapped[dict] = mapped_column(JSON, default=dict)


class Message(Base):
    __tablename__ = "messages"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"), index=True)
    client_message_id: Mapped[str] = mapped_column(String)
    role: Mapped[str] = mapped_column(String, default="user")
    text: Mapped[str] = mapped_column(Text)
    revision: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    __table_args__ = (UniqueConstraint("conversation_id", "client_message_id"),)


class Preview(Base):
    __tablename__ = "action_previews"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"), index=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id"))
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id"))
    payload: Mapped[dict] = mapped_column(JSON)
    parameter_hash: Mapped[str] = mapped_column(String)
    revision: Mapped[int] = mapped_column(Integer)
    order_version: Mapped[int] = mapped_column(Integer)
    eligibility_policy: Mapped[str] = mapped_column(String)
    flow_policy: Mapped[str] = mapped_column(String)
    policy_hash: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, default="PENDING")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        Index(
            "unique_active_preview",
            "conversation_id",
            "revision",
            "parameter_hash",
            unique=True,
            postgresql_where=text("status IN ('PENDING', 'CONFIRMED')"),
        ),
    )


class Approval(Base):
    __tablename__ = "approvals"
    preview_id: Mapped[str] = mapped_column(ForeignKey("action_previews.id"), primary_key=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id"))
    parameter_hash: Mapped[str] = mapped_column(String)
    revision: Mapped[int] = mapped_column(Integer)
    confirmed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    method: Mapped[str] = mapped_column(String, default="trusted-api")


class Operation(Base):
    __tablename__ = "operations"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    preview_id: Mapped[str] = mapped_column(ForeignKey("action_previews.id"), unique=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id"))
    idempotency_key: Mapped[str] = mapped_column(String)
    request_hash: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, default="COMMITTED")
    receipt: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    __table_args__ = (UniqueConstraint("customer_id", "idempotency_key"),)


class Application(Base):
    __tablename__ = "aftercare_requests"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    operation_id: Mapped[str] = mapped_column(ForeignKey("operations.id"), unique=True)
    line_id: Mapped[str] = mapped_column(ForeignKey("order_lines.id"), index=True)
    action: Mapped[str] = mapped_column(String)
    quantity: Mapped[int] = mapped_column(Integer)
    target_variant: Mapped[str | None] = mapped_column(ForeignKey("variants.id"))
    status: Mapped[str] = mapped_column(String)
    __table_args__ = (CheckConstraint("quantity > 0"),)


class Reservation(Base):
    __tablename__ = "inventory_reservations"
    application_id: Mapped[str] = mapped_column(
        ForeignKey("aftercare_requests.id"), primary_key=True
    )
    variant_id: Mapped[str] = mapped_column(ForeignKey("inventory.variant_id"))
    quantity: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String, default="RESERVED")
    __table_args__ = (CheckConstraint("quantity > 0"),)


class Refund(Base):
    __tablename__ = "refund_requests"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    operation_id: Mapped[str] = mapped_column(ForeignKey("operations.id"), unique=True)
    amount_fen: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String, default="SIMULATED_REQUESTED")


class Handoff(Base):
    __tablename__ = "handoff_tickets"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"))
    revision: Mapped[int] = mapped_column(Integer)
    reason_code: Mapped[str] = mapped_column(String)
    summary: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String, default="HANDOFF_PENDING")
    __table_args__ = (UniqueConstraint("conversation_id", "revision", "reason_code"),)


class Event(Base):
    __tablename__ = "events"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"), index=True)
    event_type: Mapped[str] = mapped_column(String)
    payload: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class IdempotencyBinding(Base):
    __tablename__ = "idempotency_bindings"
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id"), primary_key=True)
    key: Mapped[str] = mapped_column(String, primary_key=True)
    request_hash: Mapped[str] = mapped_column(String)
    operation_id: Mapped[str] = mapped_column(ForeignKey("operations.id"))


class PolicyChunk(Base):
    __tablename__ = "policy_chunks"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    corpus_hash: Mapped[str] = mapped_column(String)
    model_revision: Mapped[str] = mapped_column(String)
    metadata_json: Mapped[dict] = mapped_column(JSON)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(512))


class Budget(Base):
    __tablename__ = "budgets"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    cap: Mapped[int] = mapped_column(BigInteger)
    settled: Mapped[int] = mapped_column(BigInteger, default=0)
    reserved: Mapped[int] = mapped_column(BigInteger, default=0)
    paused: Mapped[bool] = mapped_column(Boolean, default=False)
    __table_args__ = (CheckConstraint("cap >= 0 AND settled >= 0 AND reserved >= 0"),)


class ModelCall(Base):
    __tablename__ = "model_calls"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    budget_id: Mapped[str] = mapped_column(ForeignKey("budgets.id"), index=True)
    provider: Mapped[str] = mapped_column(String)
    exact_model: Mapped[str] = mapped_column(String)
    batch_id: Mapped[str] = mapped_column(String)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"), index=True)
    run_id: Mapped[str] = mapped_column(String, index=True)
    reserved: Mapped[int] = mapped_column(Integer)
    usage: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String)
    request_id: Mapped[str | None] = mapped_column(String)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class DemoSession(Base):
    __tablename__ = "demo_sessions"
    token_hash: Mapped[str] = mapped_column(String, primary_key=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id"))
    csrf_token: Mapped[str] = mapped_column(String)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"), index=True)
    message_id: Mapped[str | None] = mapped_column(ForeignKey("messages.id"))
    dedup_key: Mapped[str] = mapped_column(String, unique=True)
    kind: Mapped[str] = mapped_column(String)
    revision: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String, default="PENDING")
    lease_owner: Mapped[str | None] = mapped_column(String)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempt: Mapped[int] = mapped_column(Integer, default=0)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
