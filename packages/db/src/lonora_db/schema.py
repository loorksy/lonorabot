from datetime import datetime
from typing import Any

from lonora_contracts.domain import new_id, utcnow
from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    def __init__(self, **kwargs: Any) -> None:
        for name, value in kwargs.items():
            if not hasattr(type(self), name):
                raise TypeError("invalid_model_field")
            setattr(self, name, value)


class OwnerRow(Base):
    __tablename__ = "ln_owners"
    __table_args__ = (CheckConstraint("singleton = 1", name="one_owner"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    singleton: Mapped[int] = mapped_column(Integer, default=1, unique=True)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    password_hash: Mapped[str] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SessionRow(Base):
    __tablename__ = "ln_sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("ln_owners.id", ondelete="CASCADE"))
    csrf_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked: Mapped[bool] = mapped_column(default=False)


class AgentRow(Base):
    __tablename__ = "ln_agents"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(
        ForeignKey("ln_owners.id", ondelete="CASCADE"), index=True
    )
    parent_id: Mapped[str | None] = mapped_column(ForeignKey("ln_agents.id", ondelete="SET NULL"))
    name: Mapped[str] = mapped_column(String(80))
    title: Mapped[str] = mapped_column(String(160), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    avatar: Mapped[str] = mapped_column(String(24), default="orb")
    color: Mapped[str] = mapped_column(String(7), default="#7c83fd")
    instructions: Mapped[str] = mapped_column(Text, default="")
    paused: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ThreadRow(Base):
    context_summary: Mapped[str] = mapped_column(Text, default="")
    summary_seq: Mapped[int] = mapped_column(Integer, default=0)
    __tablename__ = "ln_threads"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(
        ForeignKey("ln_owners.id", ondelete="CASCADE"), index=True
    )
    agent_id: Mapped[str | None] = mapped_column(ForeignKey("ln_agents.id", ondelete="CASCADE"))
    group_id: Mapped[str | None] = mapped_column(String(36), index=True)
    title: Mapped[str] = mapped_column(String(160), default="")
    next_seq: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class MessageRow(Base):
    __tablename__ = "ln_messages"
    __table_args__ = (
        UniqueConstraint("thread_id", "seq"),
        UniqueConstraint("thread_id", "client_nonce"),
        Index("ln_message_sequence_page", "thread_id", "seq"),
        CheckConstraint("role IN ('user','assistant','system','tool')"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    thread_id: Mapped[str] = mapped_column(
        ForeignKey("ln_threads.id", ondelete="CASCADE"), index=True
    )
    agent_id: Mapped[str | None] = mapped_column(ForeignKey("ln_agents.id", ondelete="SET NULL"))
    seq: Mapped[int] = mapped_column(Integer)
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text)
    client_nonce: Mapped[str | None] = mapped_column(String(100))
    reply_to: Mapped[str | None] = mapped_column(String(36))
    attachment_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class RunRow(Base):
    __tablename__ = "ln_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued','leased','running','waiting_input','waiting_takeover','completed','failed','cancelled')"
        ),
        Index("ln_run_claim", "status", "lease_expires_at", "created_at"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    thread_id: Mapped[str] = mapped_column(
        ForeignKey("ln_threads.id", ondelete="CASCADE"), index=True
    )
    agent_id: Mapped[str] = mapped_column(ForeignKey("ln_agents.id", ondelete="CASCADE"))
    parent_run_id: Mapped[str | None] = mapped_column(String(36), index=True)
    trigger: Mapped[str] = mapped_column(String(32), default="user")
    prompt: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(24), default="queued")
    input_seq: Mapped[int] = mapped_column(Integer, default=0)
    lease_owner: Mapped[str | None] = mapped_column(String(120))
    lease_fence: Mapped[int] = mapped_column(Integer, default=0)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    execution_state: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    model_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    error_code: Mapped[str | None] = mapped_column(String(80))
    result: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SteeringRow(Base):
    __tablename__ = "ln_steering"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    run_id: Mapped[str] = mapped_column(ForeignKey("ln_runs.id", ondelete="CASCADE"), index=True)
    message_id: Mapped[str] = mapped_column(
        ForeignKey("ln_messages.id", ondelete="CASCADE"), unique=True
    )
    consumed: Mapped[bool] = mapped_column(default=False)


class EventRow(Base):
    __tablename__ = "ln_events"
    cursor: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner_id: Mapped[str] = mapped_column(
        ForeignKey("ln_owners.id", ondelete="CASCADE"), index=True
    )
    thread_id: Mapped[str | None] = mapped_column(String(36), index=True)
    agent_id: Mapped[str | None] = mapped_column(String(36))
    run_id: Mapped[str | None] = mapped_column(String(36))
    kind: Mapped[str] = mapped_column(String(80))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class MemoryRow(Base):
    __tablename__ = "ln_memory"
    agent_id: Mapped[str] = mapped_column(
        ForeignKey("ln_agents.id", ondelete="CASCADE"), primary_key=True
    )
    content: Mapped[str] = mapped_column(Text, default="")
    version: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class RoutineRow(Base):
    goal_id: Mapped[str | None] = mapped_column(
        ForeignKey("ln_trading_goals.id", ondelete="CASCADE")
    )
    step_id: Mapped[str | None] = mapped_column(String(64))
    __tablename__ = "ln_routines"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(ForeignKey("ln_owners.id", ondelete="CASCADE"))
    agent_id: Mapped[str] = mapped_column(ForeignKey("ln_agents.id", ondelete="CASCADE"))
    thread_id: Mapped[str] = mapped_column(ForeignKey("ln_threads.id", ondelete="CASCADE"))
    prompt: Mapped[str] = mapped_column(Text)
    interval_seconds: Mapped[int | None] = mapped_column(Integer)
    cron: Mapped[str | None] = mapped_column(String(100))
    timezone: Mapped[str] = mapped_column(String(80), default="UTC")
    enabled: Mapped[bool] = mapped_column(default=True)
    next_run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SettingRow(Base):
    __tablename__ = "ln_settings"
    key: Mapped[str] = mapped_column(String(120), primary_key=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SecretRow(Base):
    __tablename__ = "ln_secrets"
    __table_args__ = (UniqueConstraint("scope", "name"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(ForeignKey("ln_owners.id", ondelete="CASCADE"))
    scope: Mapped[str] = mapped_column(String(120))
    name: Mapped[str] = mapped_column(String(80))
    ciphertext: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class GatewayRow(Base):
    __tablename__ = "ln_gateways"
    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    state: Mapped[str] = mapped_column(String(24))
    heartbeat_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class EffectReceiptRow(Base):
    __tablename__ = "ln_effect_receipts"
    key: Mapped[str] = mapped_column(String(160), primary_key=True)
    result: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ResourceRow(Base):
    __abstract__ = True
    state: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(
        ForeignKey("ln_owners.id", ondelete="CASCADE"), index=True
    )
    agent_id: Mapped[str | None] = mapped_column(ForeignKey("ln_agents.id", ondelete="CASCADE"))
    thread_id: Mapped[str | None] = mapped_column(ForeignKey("ln_threads.id", ondelete="CASCADE"))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class TradingJournalRow(Base):
    __tablename__ = "ln_trading_journal"
    __table_args__ = (Index("ln_journal_reconcile_due", "status", "submitted_at"),)
    operation_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("ln_owners.id", ondelete="CASCADE"))
    account_id: Mapped[str] = mapped_column(String(120), index=True)
    request_hash: Mapped[str] = mapped_column(String(64))
    request: Mapped[dict[str, Any]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(24), default="created", index=True)
    result: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ScratchpadRow(ResourceRow):
    __tablename__ = "ln_scratchpad"


class SkillRow(ResourceRow):
    __tablename__ = "ln_skills"


class GroupRow(ResourceRow):
    __tablename__ = "ln_groups"


class PeerMessageRow(ResourceRow):
    __tablename__ = "ln_peer_messages"


class ArtifactRow(ResourceRow):
    __tablename__ = "ln_artifacts"


class BoardRow(ResourceRow):
    __tablename__ = "ln_boards"


class TicketRow(ResourceRow):
    __tablename__ = "ln_tickets"


class ModelBackupRow(ResourceRow):
    __tablename__ = "ln_model_backups"


class UsageRow(ResourceRow):
    __tablename__ = "ln_usage"


class VoiceSessionRow(ResourceRow):
    __tablename__ = "ln_voice"


class BrokerSessionRow(ResourceRow):
    __tablename__ = "ln_broker_sessions"


class BrokerSubscriptionRow(ResourceRow):
    __tablename__ = "ln_broker_subscriptions"


class MarketWatchRow(ResourceRow):
    __tablename__ = "ln_market_watches"


class MarketWakeReceiptRow(ResourceRow):
    __tablename__ = "ln_market_wake_receipts"


class CloudChartRow(ResourceRow):
    __tablename__ = "ln_cloud_charts"


class ChartIndicatorRow(ResourceRow):
    __tablename__ = "ln_chart_indicators"


class TradingAccountRow(ResourceRow):
    __tablename__ = "ln_trading_accounts"


class FinancialReceiptRow(ResourceRow):
    __tablename__ = "ln_financial_receipts"


class EconomicCalendarRow(ResourceRow):
    __tablename__ = "ln_economic_calendar"


class McpConnectionRow(ResourceRow):
    __tablename__ = "ln_mcp_connections"


class IntegrationRow(ResourceRow):
    __tablename__ = "ln_integrations"


class SemanticMemoryRow(ResourceRow):
    __tablename__ = "ln_semantic_memory"


class MarketSnapshotRow(Base):
    __tablename__ = "ln_market_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "owner_id", "connection_id", "symbol", "timeframe", name="market_snapshot_identity"
        ),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(
        ForeignKey("ln_owners.id", ondelete="CASCADE"), index=True
    )
    connection_id: Mapped[str] = mapped_column(
        ForeignKey("ln_broker_sessions.id", ondelete="CASCADE")
    )
    symbol: Mapped[str] = mapped_column(String(80))
    timeframe: Mapped[str] = mapped_column(String(12))
    connection_version: Mapped[int] = mapped_column(Integer)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class TradingGoalRow(ResourceRow):
    __tablename__ = "ln_trading_goals"


class GoalDecisionRow(Base):
    __tablename__ = "ln_goal_decisions"
    __table_args__ = (UniqueConstraint("goal_id", "step_id", "attempt", name="goal_step_attempt"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    goal_id: Mapped[str] = mapped_column(
        ForeignKey("ln_trading_goals.id", ondelete="CASCADE"), index=True
    )
    owner_id: Mapped[str] = mapped_column(ForeignKey("ln_owners.id", ondelete="CASCADE"))
    step_id: Mapped[str] = mapped_column(String(64))
    attempt: Mapped[int] = mapped_column(Integer, default=1)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("ln_runs.id", ondelete="SET NULL"))
    operation_id: Mapped[str] = mapped_column(String(80), unique=True)
    status: Mapped[str] = mapped_column(String(24), default="planned")
    request: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    evidence: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    result: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
