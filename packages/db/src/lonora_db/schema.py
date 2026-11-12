from datetime import datetime
from typing import Any

from lonora_contracts.domain import new_id, utcnow
from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    text,
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


class PushDeviceRow(Base):
    """One phone registered for push, bound to the sign-in session that registered it:
    signing out deletes it."""

    __tablename__ = "ln_push_devices"
    __table_args__ = (UniqueConstraint("owner_id", "device_id", name="uq_push_device"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(
        ForeignKey("ln_owners.id", ondelete="CASCADE"), index=True
    )
    device_id: Mapped[str] = mapped_column(String(64))
    session_hash: Mapped[str] = mapped_column(
        ForeignKey("ln_sessions.token_hash", ondelete="CASCADE"), index=True
    )
    platform: Mapped[str] = mapped_column(String(16))
    # The token is encrypted at rest; its SHA-256 keeps one row per token.
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    token_ciphertext: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class DeviceCredentialRow(Base):
    __tablename__ = "ln_device_credentials"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(
        ForeignKey("ln_owners.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(80))
    credential_id: Mapped[str] = mapped_column(String(2048), unique=True)
    public_key: Mapped[str] = mapped_column(Text)
    sign_count: Mapped[int] = mapped_column(BigInteger, default=0)
    revoked: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class DeviceChallengeRow(Base):
    __tablename__ = "ln_device_challenges"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(
        ForeignKey("ln_owners.id", ondelete="CASCADE"), index=True
    )
    session_hash: Mapped[str] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(16))
    request_id: Mapped[str | None] = mapped_column(String(36))
    challenge: Mapped[str] = mapped_column(Text)
    binding_hash: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(80), default="")
    status: Mapped[str] = mapped_column(String(16), default="pending")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SuperBotRequestRow(Base):
    """Retired goal-autonomy requests, kept only as audit history.

    Nothing reads them for authority: a signed AccountAuthority is the only grant. Rows
    that were pending or activated when the feature was retired have status 'retired'.
    """

    __tablename__ = "ln_super_bot_requests"
    __table_args__ = (
        CheckConstraint("mode IN ('advisory','supervised','autonomous')", name="ln_super_bot_mode"),
        CheckConstraint(
            "status IN ('pending','activated','rejected','expired','cancelled','paused',"
            "'disabled','retired')",
            name="ln_super_bot_status",
        ),
        Index(
            "ln_super_bot_active_goal",
            "goal_id",
            unique=True,
            postgresql_where=text("status = 'activated'"),
            sqlite_where=text("status = 'activated'"),
        ),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(
        ForeignKey("ln_owners.id", ondelete="CASCADE"), index=True
    )
    # Durable record: the agent and goal ids are kept as values, never cascaded away.
    agent_id: Mapped[str] = mapped_column(String(36), index=True)
    thread_id: Mapped[str | None] = mapped_column(ForeignKey("ln_threads.id", ondelete="SET NULL"))
    goal_id: Mapped[str] = mapped_column(String(36), index=True)
    mode: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16), default="pending")
    envelope: Mapped[dict[str, Any]] = mapped_column(JSON)
    envelope_hash: Mapped[str] = mapped_column(String(64))
    device_id: Mapped[str | None] = mapped_column(
        ForeignKey("ln_device_credentials.id", ondelete="SET NULL")
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AccountAuthorityRow(Base):
    """Immutable signed account scope."""

    __tablename__ = "ln_account_authorities"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','active','revoked','expired')", name="ln_account_authority_status"
        ),
        Index(
            "ln_account_authority_active",
            "agent_id",
            "account_id",
            unique=True,
            postgresql_where=text("status = 'active'"),
            sqlite_where=text("status = 'active'"),
        ),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(
        ForeignKey("ln_owners.id", ondelete="CASCADE"), index=True
    )
    # Durable record: the agent and account ids are kept as values, never cascaded away.
    agent_id: Mapped[str] = mapped_column(String(36), index=True)
    thread_id: Mapped[str | None] = mapped_column(ForeignKey("ln_threads.id", ondelete="SET NULL"))
    account_id: Mapped[str] = mapped_column(String(36), index=True)
    status: Mapped[str] = mapped_column(String(16), default="pending", server_default="pending")
    envelope: Mapped[dict[str, Any]] = mapped_column(JSON)
    envelope_hash: Mapped[str] = mapped_column(String(64))
    device_id: Mapped[str | None] = mapped_column(
        ForeignKey("ln_device_credentials.id", ondelete="SET NULL")
    )
    activation_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AgentRow(Base):
    scope_mode: Mapped[str] = mapped_column(
        String(16), default="fixed_market", server_default="fixed_market"
    )
    scope_revision: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    __tablename__ = "ln_agents"
    __table_args__ = (
        CheckConstraint(
            "role IN ('personal','general','specialist','delegated','legacy')", name="ln_agent_role"
        ),
        CheckConstraint("scope_mode IN ('fixed_market','flexible')", name="ln_agent_scope_mode"),
        CheckConstraint(
            "template IS NULL OR template IN ('trading','general','research','supervisor')",
            name="ln_agent_template",
        ),
        CheckConstraint(
            "scope_mode != 'flexible' OR (parent_id IS NULL AND role IN ('general','specialist'))",
            name="ln_agent_flexible_root",
        ),
        CheckConstraint(
            "role != 'general' OR (scope_mode = 'flexible' AND trading_account_id IS NULL AND trading_symbol IS NULL)",
            name="ln_agent_general_scope",
        ),
        CheckConstraint(
            "role != 'personal' OR (parent_id IS NULL AND trading_account_id IS NULL AND trading_symbol IS NULL)",
            name="ln_personal_scope",
        ),
        CheckConstraint(
            "role != 'delegated' OR (trading_account_id IS NULL AND trading_symbol IS NULL)",
            name="ln_delegated_scope",
        ),
        Index(
            "ln_one_personal_agent",
            "owner_id",
            unique=True,
            postgresql_where=text("role = 'personal'"),
            sqlite_where=text("role = 'personal'"),
        ),
    )
    role: Mapped[str] = mapped_column(String(16), default="legacy", server_default="legacy")
    # The creation template (trading, general, research, supervisor). None for the
    # personal agent and delegated helpers, whose role is their type.
    template: Mapped[str | None] = mapped_column(String(16))
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(
        ForeignKey("ln_owners.id", ondelete="CASCADE"), index=True
    )
    parent_id: Mapped[str | None] = mapped_column(ForeignKey("ln_agents.id", ondelete="SET NULL"))
    trading_account_id: Mapped[str | None] = mapped_column(String(36))
    trading_symbol: Mapped[str | None] = mapped_column(String(80))
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
    __table_args__ = (
        CheckConstraint("purpose IN ('conversation','work')", name="ln_thread_purpose"),
    )
    purpose: Mapped[str] = mapped_column(
        String(16), default="conversation", server_default="conversation"
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(
        ForeignKey("ln_owners.id", ondelete="CASCADE"), index=True
    )
    agent_id: Mapped[str | None] = mapped_column(ForeignKey("ln_agents.id", ondelete="CASCADE"))
    group_id: Mapped[str | None] = mapped_column(String(36), index=True)
    title: Mapped[str] = mapped_column(String(160), default="")
    next_seq: Mapped[int] = mapped_column(Integer, default=1)
    # Per-chat options the agent reads ({"web_search": bool}).
    options: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, server_default=text("'{}'"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class MessageRow(Base):
    __tablename__ = "ln_messages"
    mentions: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    __table_args__ = (
        UniqueConstraint("thread_id", "seq"),
        UniqueConstraint("thread_id", "client_nonce"),
        Index("ln_message_sequence_page", "thread_id", "seq"),
        CheckConstraint("role IN ('user','assistant','system','tool')"),
        CheckConstraint("origin IN ('owner','ui_submit','ui_follow_up')", name="ln_message_origin"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    thread_id: Mapped[str] = mapped_column(
        ForeignKey("ln_threads.id", ondelete="CASCADE"), index=True
    )
    agent_id: Mapped[str | None] = mapped_column(ForeignKey("ln_agents.id", ondelete="SET NULL"))
    seq: Mapped[int] = mapped_column(Integer)
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text)
    rich_content: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    client_nonce: Mapped[str | None] = mapped_column(String(100))
    reply_to: Mapped[str | None] = mapped_column(String(36))
    attachment_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    # The agent's optional next-reply suggestion on a conversational answer (Q23).
    suggested_reply: Mapped[str | None] = mapped_column(String(60))
    # Edit and resend (Q21): the original owner message this one replaces; both stay.
    edited_from: Mapped[str | None] = mapped_column(String(36), index=True, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    # Who wrote it (GENUI_PLAN §8.4): ``owner``, ``ui_submit`` (a card's send, text composed
    # by the server) or ``ui_follow_up`` (a v1 follow-up tap). Only ``owner`` is the owner's
    # own words for any owner-words check.
    origin: Mapped[str] = mapped_column(String(16), default="owner", server_default="owner")
    ui_submit: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    ui_state: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class MessageReactionRow(Base):
    """One quick reaction per reactor ("owner" or an agent id) and message (Q26, Q28)."""

    __tablename__ = "ln_message_reactions"
    __table_args__ = (
        UniqueConstraint("message_id", "reactor", name="ln_message_reaction_reactor"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    message_id: Mapped[str] = mapped_column(ForeignKey("ln_messages.id", ondelete="CASCADE"))
    thread_id: Mapped[str] = mapped_column(String(36))
    reactor: Mapped[str] = mapped_column(String(36))
    emoji: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ThreadPrefsRow(Base):
    """The owner's state of one conversation: read cursor, marks and the history cursor.

    ``last_read_seq`` only grows (max-wins). ``hidden_before_seq`` is «مسح»: messages at
    or before it are hidden from the owner's history, inbox and search; the thread, its
    grants and the agent stay. ``pinned_order`` is 1..3 per owner.
    """

    __tablename__ = "ln_thread_prefs"
    __table_args__ = (
        CheckConstraint(
            "pinned_order IS NULL OR (pinned_order >= 1 AND pinned_order <= 3)",
            name="ln_thread_prefs_pinned_order",
        ),
    )
    owner_id: Mapped[str] = mapped_column(
        ForeignKey("ln_owners.id", ondelete="CASCADE"), primary_key=True
    )
    thread_id: Mapped[str] = mapped_column(
        ForeignKey("ln_threads.id", ondelete="CASCADE"), primary_key=True
    )
    last_read_seq: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    marked_unread: Mapped[bool] = mapped_column(default=False, server_default=text("false"))
    muted: Mapped[bool] = mapped_column(default=False, server_default=text("false"))
    archived: Mapped[bool] = mapped_column(default=False, server_default=text("false"))
    favourite: Mapped[bool] = mapped_column(default=False, server_default=text("false"))
    pinned_order: Mapped[int | None] = mapped_column(Integer)
    hidden_before_seq: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ChatListRow(Base):
    """An owner-defined list of conversations (a filter chip), unique by name per owner."""

    __tablename__ = "ln_chat_lists"
    __table_args__ = (UniqueConstraint("owner_id", "name", name="ln_chat_list_name"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(
        ForeignKey("ln_owners.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(30))
    position: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AgentDeliveryRulesRow(Base):
    """Per-agent delivery rules (Q47): in-app alerts, calls and a daily alert limit.

    No row = the owner-wide policy alone. The rules only narrow delivery; urgent items
    always show and nothing here grants authority."""

    __tablename__ = "ln_agent_delivery_rules"
    __table_args__ = (
        CheckConstraint(
            "daily_limit IS NULL OR (daily_limit >= 1 AND daily_limit <= 100)",
            name="ln_agent_delivery_rules_daily_limit",
        ),
    )
    owner_id: Mapped[str] = mapped_column(
        ForeignKey("ln_owners.id", ondelete="CASCADE"), primary_key=True
    )
    agent_id: Mapped[str] = mapped_column(
        ForeignKey("ln_agents.id", ondelete="CASCADE"), primary_key=True
    )
    in_app: Mapped[bool] = mapped_column(default=True, server_default=text("true"))
    calls: Mapped[bool] = mapped_column(default=True, server_default=text("true"))
    daily_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ChatListMemberRow(Base):
    __tablename__ = "ln_chat_list_members"
    list_id: Mapped[str] = mapped_column(
        ForeignKey("ln_chat_lists.id", ondelete="CASCADE"), primary_key=True
    )
    thread_id: Mapped[str] = mapped_column(
        ForeignKey("ln_threads.id", ondelete="CASCADE"), primary_key=True
    )


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
    # Crash recoveries since the last clean claim; the watchdog quarantines a run past the cap.
    recovery_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    execution_state: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    model_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    error_code: Mapped[str | None] = mapped_column(String(80))
    result: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SteeringRow(Base):
    __tablename__ = "ln_steering"
    __table_args__ = (UniqueConstraint("run_id", "message_id", name="ln_run_message_steering"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    run_id: Mapped[str] = mapped_column(ForeignKey("ln_runs.id", ondelete="CASCADE"), index=True)
    message_id: Mapped[str] = mapped_column(ForeignKey("ln_messages.id", ondelete="CASCADE"))
    consumed: Mapped[bool] = mapped_column(default=False)


class EventRow(Base):
    __tablename__ = "ln_events"
    __table_args__ = (
        Index(
            "ln_events_owner_public_cursor",
            "owner_id",
            text("CAST(payload ->> '_ln_public_cursor' AS INTEGER)"),
        ).ddl_if(dialect="postgresql"),
        Index(
            "ln_events_unpublished_cursor",
            "cursor",
            postgresql_where=text("CAST(payload ->> '_ln_public_cursor' AS INTEGER) IS NULL"),
        ).ddl_if(dialect="postgresql"),
        Index("ln_events_run_cursor", "run_id", "cursor"),
        Index("ln_events_owner_agent_kind_cursor", "owner_id", "agent_id", "kind", "cursor"),
    )
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


class AgentToolUsageRow(Base):
    """Bounded per-agent recency of long-tail tools; presentation only, never authority."""

    __tablename__ = "ln_agent_tool_usage"
    agent_id: Mapped[str] = mapped_column(
        ForeignKey("ln_agents.id", ondelete="CASCADE"), primary_key=True
    )
    tool_name: Mapped[str] = mapped_column(String(100), primary_key=True)
    owner_id: Mapped[str] = mapped_column(
        ForeignKey("ln_owners.id", ondelete="CASCADE"), index=True
    )
    uses: Mapped[int] = mapped_column(Integer, default=1)
    last_used_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class MemoryRow(Base):
    __tablename__ = "ln_memory"
    agent_id: Mapped[str] = mapped_column(
        ForeignKey("ln_agents.id", ondelete="CASCADE"), primary_key=True
    )
    content: Mapped[str] = mapped_column(Text, default="")
    version: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class OwnerProfileRow(Base):
    """The one owner profile (USER.md) every agent reads; owner-attributed, never authority."""

    __tablename__ = "ln_owner_profile"
    __table_args__ = (
        CheckConstraint(
            "reply_language IS NULL OR reply_language IN ('ar','en')",
            name="ln_owner_profile_reply_language",
        ),
    )
    owner_id: Mapped[str] = mapped_column(
        ForeignKey("ln_owners.id", ondelete="CASCADE"), primary_key=True
    )
    content: Mapped[str] = mapped_column(Text, default="")
    version: Mapped[int] = mapped_column(Integer, default=1)
    # None follows the language of the owner's latest message.
    reply_language: Mapped[str | None] = mapped_column(String(8))
    # «الاسم» and «طريقة المخاطبة» of the owner form (WP-H); None until the owner sets them.
    name: Mapped[str | None] = mapped_column(String(80))
    address: Mapped[str | None] = mapped_column(String(80))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class MemoryRevisionRow(Base):
    """One commit's prior and resulting text and its author; revert restores the prior text."""

    __tablename__ = "ln_memory_revisions"
    __table_args__ = (
        CheckConstraint(
            "document IN ('owner_profile','owner_preferences','agent_memory')",
            name="ln_memory_revision_document",
        ),
        CheckConstraint(
            "(document = 'agent_memory') = (agent_id IS NOT NULL)",
            name="ln_memory_revision_agent",
        ),
        CheckConstraint("author IN ('owner','agent','system')", name="ln_memory_revision_author"),
        Index("ix_ln_memory_revisions_document", "owner_id", "document", "agent_id", "created_at"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(ForeignKey("ln_owners.id", ondelete="CASCADE"))
    document: Mapped[str] = mapped_column(String(24))
    agent_id: Mapped[str | None] = mapped_column(ForeignKey("ln_agents.id", ondelete="CASCADE"))
    version: Mapped[int] = mapped_column(Integer)
    previous_content: Mapped[str] = mapped_column(Text, default="")
    content: Mapped[str] = mapped_column(Text, default="")
    author: Mapped[str] = mapped_column(String(8))
    author_agent_id: Mapped[str | None] = mapped_column(
        ForeignKey("ln_agents.id", ondelete="SET NULL")
    )
    source_message_id: Mapped[str | None] = mapped_column(
        ForeignKey("ln_messages.id", ondelete="SET NULL")
    )
    source_run_id: Mapped[str | None] = mapped_column(String(36))
    # operations | document | revert | merge | preferences
    change: Mapped[str] = mapped_column(String(16))
    reverted_revision_id: Mapped[str | None] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class RoutineRow(Base):
    __tablename__ = "ln_routines"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(ForeignKey("ln_owners.id", ondelete="CASCADE"))
    agent_id: Mapped[str] = mapped_column(ForeignKey("ln_agents.id", ondelete="CASCADE"))
    thread_id: Mapped[str] = mapped_column(ForeignKey("ln_threads.id", ondelete="CASCADE"))
    prompt: Mapped[str] = mapped_column(Text)
    title: Mapped[str | None] = mapped_column(String(160))
    run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
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


class AttentionRow(Base):
    __tablename__ = "ln_attention"
    __table_args__ = (
        UniqueConstraint("owner_id", "logical_key", name="ln_attention_logical_key"),
        CheckConstraint(
            "status IN ('pending','ready','seen','suppressed')", name="ln_attention_status"
        ),
        Index("ln_attention_due", "status", "due_at"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(
        ForeignKey("ln_owners.id", ondelete="CASCADE"), index=True
    )
    agent_id: Mapped[str] = mapped_column(ForeignKey("ln_agents.id", ondelete="CASCADE"))
    thread_id: Mapped[str] = mapped_column(ForeignKey("ln_threads.id", ondelete="CASCADE"))
    logical_key: Mapped[str] = mapped_column(String(64))
    coalesce_key: Mapped[str] = mapped_column(String(64), index=True)
    importance: Mapped[str] = mapped_column(String(24))
    code: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(16), default="pending")
    parameters: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    source_events: Mapped[list[int]] = mapped_column(JSON, default=list)
    source_count: Mapped[int] = mapped_column(Integer, default=1)
    version: Mapped[int] = mapped_column(Integer, default=1)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
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
    # Per-step liveness written by the heartbeat step; readiness needs every critical step live.
    liveness: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, server_default="{}")


class ItemFailureRow(Base):
    """One maintenance item that failed: it backs off, then is quarantined; others keep running."""

    __tablename__ = "ln_item_failures"
    __table_args__ = (Index("ln_item_failure_due", "kind", "next_attempt_at"),)
    kind: Mapped[str] = mapped_column(String(40), primary_key=True)
    item_id: Mapped[str] = mapped_column(String(160), primary_key=True)
    owner_id: Mapped[str | None] = mapped_column(ForeignKey("ln_owners.id", ondelete="CASCADE"))
    failures: Mapped[int] = mapped_column(Integer, default=1)
    code: Mapped[str] = mapped_column(String(120))
    first_failed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_failed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    quarantined_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class EffectReceiptRow(Base):
    __tablename__ = "ln_effect_receipts"
    key: Mapped[str] = mapped_column(String(160), primary_key=True)
    result: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AnalyticalWorkspaceRow(Base):
    __tablename__ = "ln_analytical_workspaces"
    __table_args__ = (CheckConstraint("revision >= 0", name="ln_workspace_revision"),)
    agent_id: Mapped[str] = mapped_column(
        ForeignKey("ln_agents.id", ondelete="CASCADE"), primary_key=True
    )
    revision: Mapped[int] = mapped_column(Integer, default=0)
    snapshot: Mapped[bytes] = mapped_column(LargeBinary, default=b"{}")
    active_operation_id: Mapped[str | None] = mapped_column(String(36))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class WorkspaceOperationRow(Base):
    __tablename__ = "ln_workspace_operations"
    __table_args__ = (
        CheckConstraint(
            "status IN ('running','completed','failed','abandoned')",
            name="ln_workspace_operation_status",
        ),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    agent_id: Mapped[str] = mapped_column(
        ForeignKey("ln_agents.id", ondelete="CASCADE"), index=True
    )
    run_id: Mapped[str] = mapped_column(ForeignKey("ln_runs.id", ondelete="CASCADE"), index=True)
    lease_fence: Mapped[int] = mapped_column(Integer)
    request_hash: Mapped[str] = mapped_column(String(64))
    base_revision: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16))
    result: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


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
    __table_args__ = (
        Index("ln_journal_reconcile_due", "status", "submitted_at"),
        Index("ln_trading_journal_thread", "thread_id", "updated_at"),
    )
    operation_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("ln_owners.id", ondelete="CASCADE"))
    account_id: Mapped[str] = mapped_column(String(120), index=True)
    request_hash: Mapped[str] = mapped_column(String(64))
    request: Mapped[dict[str, Any]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(24), default="created", index=True)
    result: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    # Presentation anchor only (never read by execution or authority): the conversation
    # and its next message seq when an agent Run of that conversation requested it.
    thread_id: Mapped[str | None] = mapped_column(ForeignKey("ln_threads.id", ondelete="SET NULL"))
    timeline_seq: Mapped[int | None] = mapped_column(Integer)


class ScratchpadRow(ResourceRow):
    __tablename__ = "ln_scratchpad"


class SkillRow(ResourceRow):
    __tablename__ = "ln_skills"


class SkillVersionRow(Base):
    """One saved version of a skill's validated payload (its «سجل الإصدارات»)."""

    __tablename__ = "ln_skill_versions"
    skill_id: Mapped[str] = mapped_column(
        ForeignKey("ln_skills.id", ondelete="CASCADE"), primary_key=True
    )
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("ln_owners.id", ondelete="CASCADE"))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AgentGoalRow(ResourceRow):
    """A light goal of a non-trading agent: a note with no schedule and no authority."""

    __tablename__ = "ln_agent_goals"


class KnowledgeLinkRow(ResourceRow):
    """A «رابط» knowledge entry of one agent."""

    __tablename__ = "ln_knowledge_links"


class GroupRow(ResourceRow):
    __tablename__ = "ln_groups"


class PeerMessageRow(ResourceRow):
    __tablename__ = "ln_peer_messages"


class CollaborationSessionRow(ResourceRow):
    __tablename__ = "ln_collaboration_sessions"


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
    __table_args__ = (Index("ln_usage_owner_created", "owner_id", "created_at"),)


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


class TradeApprovalRow(Base):
    __tablename__ = "ln_trade_approvals"
    broker_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    timeline_seq: Mapped[int | None] = mapped_column(Integer)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_id: Mapped[str] = mapped_column(
        ForeignKey("ln_owners.id", ondelete="CASCADE"), index=True
    )
    # Durable record: the owner's decision and broker snapshot survive the Run, the
    # conversation and the agent; the agent id is kept as a value.
    run_id: Mapped[str | None] = mapped_column(
        ForeignKey("ln_runs.id", ondelete="SET NULL"), index=True
    )
    thread_id: Mapped[str | None] = mapped_column(
        ForeignKey("ln_threads.id", ondelete="SET NULL"), index=True
    )
    agent_id: Mapped[str] = mapped_column(String(36))
    call_id: Mapped[str] = mapped_column(String(120))
    requests: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(24), default="pending")
    results: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    # Past it a pending approval can no longer be approved (Q32); NULL on older rows.
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class TradingOpportunityRow(ResourceRow):
    __tablename__ = "ln_trading_opportunities"
    __table_args__ = (
        UniqueConstraint(
            "owner_id",
            "agent_id",
            "account_id",
            "symbol",
            "timeframe",
            "setup_key",
            name="ln_opportunity_identity",
        ),
        CheckConstraint(
            "status IN ('forming','confirmed','degraded','invalidated','expired','acted_on','completed')",
            name="ln_opportunity_status",
        ),
    )
    account_id: Mapped[str] = mapped_column(String(120), index=True)
    symbol: Mapped[str] = mapped_column(String(80))
    timeframe: Mapped[str] = mapped_column(String(12))
    setup_key: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(24), default="forming", index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    last_validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TradingRestrictionRow(Base):
    """Owner restriction narrowing financial admission; enforced at the send boundary."""

    __tablename__ = "ln_trading_restrictions"
    __table_args__ = (
        CheckConstraint(
            "action_class IN ('no_new_entries','no_risk_increase','all_mutations')",
            name="ln_trading_restriction_action_class",
        ),
        CheckConstraint(
            "source IN ('owner_ui','owner_message','agent')", name="ln_trading_restriction_source"
        ),
        CheckConstraint("created_by IN ('owner','agent')", name="ln_trading_restriction_creator"),
        CheckConstraint(
            "valid_until IS NULL OR valid_until > valid_from",
            name="ln_trading_restriction_window",
        ),
        Index("ln_trading_restriction_scope", "owner_id", "account_id", "revoked_at"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(
        ForeignKey("ln_owners.id", ondelete="CASCADE"), index=True
    )
    # Durable brake record: ids are kept as values. NULL agent means "every agent", so a
    # deleted agent must never turn its restriction into an account-wide one.
    account_id: Mapped[str] = mapped_column(String(36))
    agent_id: Mapped[str | None] = mapped_column(String(36))
    symbol: Mapped[str | None] = mapped_column(String(80))
    # False when the broker catalog could not be read and the symbol was kept as given.
    symbol_verified: Mapped[bool] = mapped_column(default=True)
    action_class: Mapped[str] = mapped_column(String(24))
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source: Mapped[str] = mapped_column(String(16))
    source_message_id: Mapped[str | None] = mapped_column(
        ForeignKey("ln_messages.id", ondelete="SET NULL")
    )
    source_run_id: Mapped[str | None] = mapped_column(String(36))
    reason: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[str] = mapped_column(String(8))
    created_by_agent_id: Mapped[str | None] = mapped_column(
        ForeignKey("ln_agents.id", ondelete="SET NULL")
    )
    applies_to_owner_manual: Mapped[bool] = mapped_column(default=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class OwnerActionRow(Base):
    """One owner-only action offered as a card in the conversation; single use, expiring.

    The payload is the exact, server-validated effect the card performs and is hashed:
    a confirmation runs it through the existing owner function, never anything else, and
    a card cannot be replayed once it is no longer pending. Title and facts shown to the
    owner are derived from the records it names, never from model text.
    """

    __tablename__ = "ln_owner_actions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','confirmed','cancelled','expired','superseded')",
            name="ln_owner_action_status",
        ),
        CheckConstraint("source IN ('agent','system','owner')", name="ln_owner_action_source"),
        Index("ln_owner_action_owner_status", "owner_id", "status"),
        Index("ln_owner_action_thread", "thread_id", "created_at"),
        Index("ln_owner_action_subject", "owner_id", "kind", "subject"),
        # One live card per agent and exact effect: a repeated proposal returns it.
        Index(
            "ln_owner_action_pending_effect",
            "agent_id",
            "kind",
            "payload_hash",
            unique=True,
            postgresql_where=text("status = 'pending'"),
            sqlite_where=text("status = 'pending'"),
        ),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(ForeignKey("ln_owners.id", ondelete="CASCADE"))
    # Durable record: the agent and run ids are kept as values, never cascaded away.
    agent_id: Mapped[str] = mapped_column(String(36))
    thread_id: Mapped[str | None] = mapped_column(ForeignKey("ln_threads.id", ondelete="SET NULL"))
    run_id: Mapped[str | None] = mapped_column(String(36))
    # agent: proposed by an agent's tool call; system: raised from a runtime event;
    # owner: drafted by the owner (a grant card from the mandate sheet).
    source: Mapped[str] = mapped_column(String(8))
    kind: Mapped[str] = mapped_column(String(32))
    # The record the card acts on ("trading", "restriction:<id>", "operation:<id>", ...).
    subject: Mapped[str] = mapped_column(String(160))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    payload_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default="pending")
    status_reason: Mapped[str | None] = mapped_column(String(64))
    # The newer card that replaced this one (same subject), for «عرض الأحدث».
    superseded_by: Mapped[str | None] = mapped_column(String(36))
    result: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    timeline_seq: Mapped[int | None] = mapped_column(Integer)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # tap (one owner tap), passkey (owner tap plus a verified device assertion).
    decided_via: Mapped[str | None] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SupervisionGrantRow(Base):
    """One agent may read and steer another's work: visible, revocable, never money.

    The Personal Agent holds a ``default`` grant over every agent; the owner revokes any
    grant with one tap. A grant lets the supervisor read the supervised agent's threads,
    runs, memory and records, message it, pause or resume its work and add narrowing
    pauses. It never trades for it, never uses its grant and never lifts a brake.
    """

    __tablename__ = "ln_supervision_grants"
    __table_args__ = (
        CheckConstraint(
            "created_via IN ('default','owner_ui','owner_message','owner_card')",
            name="ln_supervision_grant_created_via",
        ),
        CheckConstraint(
            "revoked_via IS NULL OR revoked_via IN ('owner_ui','owner_card','owner_message')",
            name="ln_supervision_grant_revoked_via",
        ),
        CheckConstraint(
            "supervisor_agent_id <> supervised_agent_id", name="ln_supervision_grant_distinct"
        ),
        Index("ln_supervision_grant_supervisor", "owner_id", "supervisor_agent_id", "revoked_at"),
        Index("ln_supervision_grant_supervised", "owner_id", "supervised_agent_id", "revoked_at"),
        # One active grant per pair; a revoked one stays as the record of what was allowed.
        Index(
            "ln_supervision_grant_active_pair",
            "supervisor_agent_id",
            "supervised_agent_id",
            unique=True,
            postgresql_where=text("revoked_at IS NULL"),
            sqlite_where=text("revoked_at IS NULL"),
        ),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(ForeignKey("ln_owners.id", ondelete="CASCADE"))
    supervisor_agent_id: Mapped[str] = mapped_column(ForeignKey("ln_agents.id", ondelete="CASCADE"))
    supervised_agent_id: Mapped[str] = mapped_column(ForeignKey("ln_agents.id", ondelete="CASCADE"))
    created_via: Mapped[str] = mapped_column(String(16))
    source_message_id: Mapped[str | None] = mapped_column(
        ForeignKey("ln_messages.id", ondelete="SET NULL")
    )
    # The agent whose tool call or card recorded it; a value, never cascaded away.
    created_by_agent_id: Mapped[str | None] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_via: Mapped[str | None] = mapped_column(String(16))


class SupervisionHoldRow(Base):
    """A pause on an agent's work (the agent itself, one of its Tasks, routines or
    watches), put there by a supervising agent or by the owner. On its own initiative
    only the agent that set it (still supervising) lifts it; a run that answers the
    owner's message lifts it too. The owner pausing the same work makes it the owner's
    (``source='owner'``, the holder kept for attribution), lifted only by the owner; the
    owner resuming the work releases it. The owner's own pause with no supervisor is a
    hold with no holder, and a deleted supervisor's hold stays as the owner's."""

    __tablename__ = "ln_supervision_holds"
    __table_args__ = (
        CheckConstraint(
            "target_kind IN ('agent','task','routine','watch')",
            name="ln_supervision_hold_target_kind",
        ),
        CheckConstraint(
            "source IN ('agent','owner_message','owner')", name="ln_supervision_hold_source"
        ),
        CheckConstraint(
            "released_by IS NULL OR released_by IN ('holder','owner','stale')",
            name="ln_supervision_hold_released_by",
        ),
        Index("ln_supervision_hold_agent", "owner_id", "agent_id", "released_at"),
        Index("ln_supervision_hold_holder", "owner_id", "holder_agent_id", "released_at"),
        # At most one live hold per paused item.
        Index(
            "ln_supervision_hold_live_target",
            "target_kind",
            "target_id",
            unique=True,
            postgresql_where=text("released_at IS NULL"),
            sqlite_where=text("released_at IS NULL"),
        ),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(ForeignKey("ln_owners.id", ondelete="CASCADE"))
    # The supervising agent that set it; None for the owner's own pause, or once that
    # supervisor is deleted (its hold is then the owner's).
    holder_agent_id: Mapped[str | None] = mapped_column(
        ForeignKey("ln_agents.id", ondelete="SET NULL")
    )
    # The agent whose work is paused.
    agent_id: Mapped[str] = mapped_column(ForeignKey("ln_agents.id", ondelete="CASCADE"))
    target_kind: Mapped[str] = mapped_column(String(8))
    target_id: Mapped[str] = mapped_column(String(36))
    source: Mapped[str] = mapped_column(String(16))
    source_message_id: Mapped[str | None] = mapped_column(
        ForeignKey("ln_messages.id", ondelete="SET NULL")
    )
    source_run_id: Mapped[str | None] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    released_by: Mapped[str | None] = mapped_column(String(8))


class TrustedSourceRow(Base):
    """One source the owner trusts: inside the list, agents install and use capabilities
    without asking; outside it, one owner card. Visible and removable in Capabilities.

    ``github`` (github.com, every public repository; the default, trusted as before),
    ``github_owner`` and ``github_repo`` admit Skill imports; ``mcp_server`` pins one saved
    connection's endpoint and the exact input schema of each tool the owner reviewed;
    ``feed_domain`` admits news feed subscriptions. A trusted source never carries money
    authority: no tool that can trade or move money is ever pinned.
    """

    __tablename__ = "ln_trusted_sources"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('github','github_owner','github_repo','mcp_server','feed_domain')",
            name="ln_trusted_source_kind",
        ),
        CheckConstraint(
            "effect_tier IN ('read','write_nonfinancial')", name="ln_trusted_source_tier"
        ),
        CheckConstraint(
            "added_via IN ('default','operator','owner_ui','owner_card')",
            name="ln_trusted_source_added_via",
        ),
        CheckConstraint(
            "revoked_via IS NULL OR revoked_via IN ('owner_ui','owner_card')",
            name="ln_trusted_source_revoked_via",
        ),
        Index("ln_trusted_source_owner_kind", "owner_id", "kind", "revoked_at"),
        # One active entry per source; a removed one stays as the record and can be restored.
        Index(
            "ln_trusted_source_active",
            "owner_id",
            "kind",
            "identifier",
            unique=True,
            postgresql_where=text("revoked_at IS NULL"),
            sqlite_where=text("revoked_at IS NULL"),
        ),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    owner_id: Mapped[str] = mapped_column(ForeignKey("ln_owners.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(16))
    # github.com, an owner name, owner/repository (case-folded), a connection id or a host.
    identifier: Mapped[str] = mapped_column(String(300))
    effect_tier: Mapped[str] = mapped_column(String(24), default="read")
    # mcp_server: the reviewed endpoint and {tool name: input schema sha256}.
    endpoint_sha256: Mapped[str | None] = mapped_column(String(64))
    tool_hashes: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    # The pinned tools the server marked read-only at review: the only ones the read tier
    # runs (a later hint can narrow this, never widen it).
    read_only_tools: Mapped[list[Any]] = mapped_column(JSON, default=list)
    # Tools seen at review that can trade or move money; never pinned, shown as blocked.
    blocked_tools: Mapped[list[Any]] = mapped_column(JSON, default=list)
    # operator: copied from LONORA_MCP_DECLARATIONS; it authorizes nothing by itself (only
    # while that declaration stands) until the owner reviews it.
    added_via: Mapped[str] = mapped_column(String(16))
    # The agent whose card the owner confirmed; a value, never cascaded away.
    added_by_agent_id: Mapped[str | None] = mapped_column(String(36))
    card_id: Mapped[str | None] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_via: Mapped[str | None] = mapped_column(String(16))
