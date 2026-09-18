from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(50), nullable=False, default="user")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    google_id: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True, index=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    can_create_gateway_key: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    api_keys: Mapped[list["ApiKey"]] = relationship("ApiKey", back_populates="owner", lazy="selectin")
    gateway_key: Mapped["GatewayKey | None"] = relationship("GatewayKey", back_populates="owner", uselist=False, lazy="selectin")


class KiroUserMapping(Base):
    __tablename__ = "kiro_user_mappings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kiro_user_id: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    imported_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class ApiKey(Base):
    __tablename__ = "api_keys"
    __table_args__ = (
        Index("ix_api_keys_active_id", "is_active", "id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    kiro_user_id: Mapped[str | None] = mapped_column(String(255), ForeignKey("kiro_user_mappings.kiro_user_id"), nullable=True)
    key_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    key_encrypted: Mapped[str] = mapped_column(String(512), nullable=False)
    key_prefix: Mapped[str] = mapped_column(String(20), nullable=False)
    key_suffix: Mapped[str] = mapped_column(String(10), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    use_proxy: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

    owner: Mapped["User | None"] = relationship("User", back_populates="api_keys")
    usages: Mapped[list["KeyUsage"]] = relationship("KeyUsage", back_populates="api_key", lazy="selectin")


class KeyUsage(Base):
    __tablename__ = "key_usage"
    __table_args__ = (
        UniqueConstraint("key_id", "month", name="uq_key_usage_key_month"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key_id: Mapped[int] = mapped_column(Integer, ForeignKey("api_keys.id"), nullable=False)
    month: Mapped[str] = mapped_column(String(7), nullable=False)
    current_usage: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    usage_limit: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    api_key: Mapped["ApiKey"] = relationship("ApiKey", back_populates="usages")


class DailyUsage(Base):
    __tablename__ = "daily_usage"
    __table_args__ = (
        UniqueConstraint("key_id", "date", "model", name="uq_daily_usage_key_date_model"),
        Index("ix_daily_usage_date", "date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key_id: Mapped[int] = mapped_column(Integer, ForeignKey("api_keys.id"), nullable=False)
    date: Mapped[str] = mapped_column(String(10), nullable=False)  # "YYYY-MM-DD"
    model: Mapped[str] = mapped_column(String(100), nullable=False, default="unknown")
    input_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)


class FallbackUsage(Base):
    __tablename__ = "fallback_usage"
    __table_args__ = (
        UniqueConstraint("original_key_id", "fallback_key_id", "month", "model", name="uq_fallback_usage_orig_fb_month_model"),
        Index("ix_fallback_usage_month", "month"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    original_key_id: Mapped[int] = mapped_column(Integer, ForeignKey("api_keys.id"), nullable=False)
    fallback_key_id: Mapped[int] = mapped_column(Integer, ForeignKey("api_keys.id"), nullable=False)
    month: Mapped[str] = mapped_column(String(7), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False, default="unknown")
    input_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)


class GatewayKey(Base):
    __tablename__ = "gateway_keys"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    key_hash: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    key_prefix: Mapped[str] = mapped_column(String(20), nullable=False)
    key_suffix: Mapped[str] = mapped_column(String(10), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

    owner: Mapped["User"] = relationship("User", back_populates="gateway_key")
    usages: Mapped[list["GatewayKeyUsage"]] = relationship("GatewayKeyUsage", back_populates="gateway_key", lazy="selectin", cascade="all, delete-orphan")
    daily_usages: Mapped[list["GatewayKeyDailyUsage"]] = relationship("GatewayKeyDailyUsage", back_populates="gateway_key", lazy="selectin", cascade="all, delete-orphan")


class GatewayKeyUsage(Base):
    __tablename__ = "gateway_key_usage"
    __table_args__ = (
        UniqueConstraint("gateway_key_id", "month", "key_id", name="uq_gw_key_usage_gwkey_month_poolkey"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    gateway_key_id: Mapped[int] = mapped_column(Integer, ForeignKey("gateway_keys.id"), nullable=False)
    month: Mapped[str] = mapped_column(String(7), nullable=False)
    current_usage: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    key_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("api_keys.id"), nullable=True)

    gateway_key: Mapped["GatewayKey"] = relationship("GatewayKey", back_populates="usages")


class GatewayKeyDailyUsage(Base):
    __tablename__ = "gateway_key_daily_usage"
    __table_args__ = (
        UniqueConstraint("gateway_key_id", "date", "key_id", "model", name="uq_gw_daily_usage_gwkey_date_poolkey_model"),
        Index("ix_gw_daily_usage_date", "date"),
        Index("ix_gw_daily_usage_key_id", "key_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    gateway_key_id: Mapped[int] = mapped_column(Integer, ForeignKey("gateway_keys.id"), nullable=False)
    date: Mapped[str] = mapped_column(String(10), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False, default="unknown")
    input_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    key_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("api_keys.id"), nullable=True)

    gateway_key: Mapped["GatewayKey"] = relationship("GatewayKey", back_populates="daily_usages")


class ServiceAccount(Base):
    """A non-human identity (CI bot, app, team) that is NOT tied to a User.

    Service accounts always route straight to 9router (never the Kiro pool)
    and are restricted to an admin-configured allowlist of models.
    """

    __tablename__ = "service_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # JSON-encoded list[str] of allowed model ids. Fail-closed: an empty list
    # ("[]") means the account may use NO model. See
    # kiro.db.repositories.encode_allowed_models / decode_allowed_models.
    allowed_models: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    # Audit only — which admin created this account. NOT a relationship that
    # implies ownership (unlike GatewayKey.user_id, which does).
    created_by_user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

    keys: Mapped[list["ServiceAccountKey"]] = relationship(
        "ServiceAccountKey", back_populates="service_account", lazy="selectin", cascade="all, delete-orphan"
    )
    usages: Mapped[list["ServiceAccountUsage"]] = relationship(
        "ServiceAccountUsage", back_populates="service_account", lazy="selectin", cascade="all, delete-orphan"
    )
    daily_usages: Mapped[list["ServiceAccountDailyUsage"]] = relationship(
        "ServiceAccountDailyUsage", back_populates="service_account", lazy="selectin", cascade="all, delete-orphan"
    )


class ServiceAccountKey(Base):
    """An API key (prefix ``izisa_``) issued to a ServiceAccount.

    A service account can hold many active keys at once, so keys can be
    rotated without downtime. Only the salted hash is stored — like
    GatewayKey, the raw key is only ever verified, never replayed upstream.
    """

    __tablename__ = "service_account_keys"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    service_account_id: Mapped[int] = mapped_column(Integer, ForeignKey("service_accounts.id"), index=True, nullable=False)
    key_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    key_prefix: Mapped[str] = mapped_column(String(20), nullable=False)
    key_suffix: Mapped[str] = mapped_column(String(10), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

    service_account: Mapped["ServiceAccount"] = relationship("ServiceAccount", back_populates="keys")


class ServiceAccountUsage(Base):
    """Monthly request-count rollup for a service account. Mirrors GatewayKeyUsage."""

    __tablename__ = "service_account_usage"
    __table_args__ = (
        UniqueConstraint("service_account_id", "month", name="uq_sa_usage_sa_month"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    service_account_id: Mapped[int] = mapped_column(Integer, ForeignKey("service_accounts.id"), nullable=False)
    month: Mapped[str] = mapped_column(String(7), nullable=False)
    current_usage: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    service_account: Mapped["ServiceAccount"] = relationship("ServiceAccount", back_populates="usages")


class ServiceAccountDailyUsage(Base):
    """Daily per-model token usage for a service account. Mirrors GatewayKeyDailyUsage."""

    __tablename__ = "service_account_daily_usage"
    __table_args__ = (
        UniqueConstraint("service_account_id", "date", "model", name="uq_sa_daily_usage_sa_date_model"),
        Index("ix_sa_daily_usage_date", "date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    service_account_id: Mapped[int] = mapped_column(Integer, ForeignKey("service_accounts.id"), nullable=False)
    date: Mapped[str] = mapped_column(String(10), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False, default="unknown")
    input_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)

    service_account: Mapped["ServiceAccount"] = relationship("ServiceAccount", back_populates="daily_usages")


class SystemConfig(Base):
    __tablename__ = "system_config"

    key: Mapped[str] = mapped_column(String(255), primary_key=True)
    value: Mapped[str] = mapped_column(String(1024), nullable=False, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
