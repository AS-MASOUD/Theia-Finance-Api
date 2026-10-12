import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Optional

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class AssetClassModel(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "asset_classes"

    code: Mapped[str] = mapped_column(String(50), nullable=False, unique=True, index=True)
    label: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    icon: Mapped[str] = mapped_column(String(50), nullable=False, default="Layers")
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    assets: Mapped[list["AssetModel"]] = relationship(
        "AssetModel", back_populates="class_config"
    )


class AccountModel(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "accounts"

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    account_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # checking, savings, brokerage, crypto, cash
    institution: Mapped[str | None] = mapped_column(String(100), nullable=True)
    currency: Mapped[str] = mapped_column(String(10), nullable=False, default="TOMAN")
    current_balance: Mapped[Decimal] = mapped_column(
        Numeric(20, 4), nullable=False, default=Decimal("0.0000")
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    account_number_mask: Mapped[str | None] = mapped_column(String(20), nullable=True)

    positions: Mapped[list["AssetPositionModel"]] = relationship(
        "AssetPositionModel", back_populates="account", cascade="all, delete-orphan"
    )
    transactions: Mapped[list["TransactionModel"]] = relationship(
        "TransactionModel", back_populates="account", cascade="all, delete-orphan"
    )


class AssetModel(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "assets"

    symbol: Mapped[str] = mapped_column(String(30), nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    asset_class: Mapped[str] = mapped_column(
        String(50),
        ForeignKey("asset_classes.code", onupdate="CASCADE", ondelete="RESTRICT"),
        nullable=False,
    )
    currency: Mapped[str] = mapped_column(String(10), nullable=False, default="TOMAN")
    current_price: Mapped[Decimal] = mapped_column(
        Numeric(20, 4), nullable=False, default=Decimal("0.0000")
    )
    price_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    class_config: Mapped[Optional["AssetClassModel"]] = relationship(
        "AssetClassModel", back_populates="assets"
    )
    positions: Mapped[list["AssetPositionModel"]] = relationship(
        "AssetPositionModel", back_populates="asset", cascade="all, delete-orphan"
    )


class AssetPositionModel(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "asset_positions"

    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    quantity: Mapped[Decimal] = mapped_column(Numeric(28, 8), nullable=False, default=Decimal("0"))
    average_cost_basis: Mapped[Decimal] = mapped_column(
        Numeric(20, 4), nullable=False, default=Decimal("0.0000")
    )

    account: Mapped["AccountModel"] = relationship("AccountModel", back_populates="positions")
    asset: Mapped["AssetModel"] = relationship("AssetModel", back_populates="positions")


class TransactionModel(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "transactions"

    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    asset_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assets.id", ondelete="SET NULL"), nullable=True, index=True
    )
    transaction_type: Mapped[str] = mapped_column(
        String(30), nullable=False
    )  # BUY, SELL, DEPOSIT, WITHDRAWAL, DIVIDEND, INTEREST, FEE, TRANSFER
    transaction_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(28, 8), nullable=True)
    unit_price: Mapped[Decimal | None] = mapped_column(Numeric(20, 4), nullable=True)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    fee: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False, default=Decimal("0.0000"))
    currency: Mapped[str] = mapped_column(String(10), nullable=False, default="TOMAN")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_reconciled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    account: Mapped["AccountModel"] = relationship("AccountModel", back_populates="transactions")
    asset: Mapped[Optional["AssetModel"]] = relationship("AssetModel")


class LiabilityTypeModel(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "liability_types"

    code: Mapped[str] = mapped_column(String(50), nullable=False, unique=True, index=True)
    label: Mapped[str] = mapped_column(String(100), nullable=False)
    short_label: Mapped[str | None] = mapped_column(String(100), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    icon: Mapped[str] = mapped_column(String(50), nullable=False, default="Building")
    default_rate: Mapped[Decimal] = mapped_column(
        Numeric(6, 3), nullable=False, default=Decimal("0.000")
    )
    default_term_months: Mapped[int] = mapped_column(Integer, nullable=False, default=12)
    is_friend: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    direction: Mapped[str] = mapped_column(
        String(20), nullable=False, default="debt"
    )  # debt, claim
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    liabilities: Mapped[list["LiabilityModel"]] = relationship(
        "LiabilityModel", back_populates="type_config"
    )


class LiabilityModel(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "liabilities"

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    liability_type: Mapped[str] = mapped_column(
        String(50),
        ForeignKey("liability_types.code", onupdate="CASCADE", ondelete="RESTRICT"),
        nullable=False,
    )  # mortgage, auto_loan, student_loan, personal_loan, credit_card, etc.
    lender: Mapped[str | None] = mapped_column(String(100), nullable=True)
    original_principal: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    current_balance: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    interest_rate_percent: Mapped[Decimal] = mapped_column(Numeric(6, 3), nullable=False)
    monthly_payment: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    maturity_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    currency: Mapped[str] = mapped_column(String(10), nullable=False, default="TOMAN")

    type_config: Mapped[Optional["LiabilityTypeModel"]] = relationship(
        "LiabilityTypeModel", back_populates="liabilities"
    )
    payments: Mapped[list["LiabilityPaymentModel"]] = relationship(
        "LiabilityPaymentModel", back_populates="liability", cascade="all, delete-orphan"
    )
    user: Mapped[Optional["UserModel"]] = relationship("UserModel")


class LiabilityPaymentModel(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "liability_payments"

    liability_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("liabilities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    payment_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    principal_amount: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    interest_amount: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    extra_principal: Mapped[Decimal] = mapped_column(
        Numeric(20, 4), nullable=False, default=Decimal("0.0000")
    )
    total_payment: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    liability: Mapped["LiabilityModel"] = relationship("LiabilityModel", back_populates="payments")


class CashflowCategoryModel(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "cashflow_categories"

    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    flow_type: Mapped[str] = mapped_column(String(20), nullable=False)  # income, expense
    color_hex: Mapped[str] = mapped_column(String(10), nullable=False, default="#6366f1")
    icon: Mapped[str] = mapped_column(String(50), nullable=False, default="circle")
    monthly_budget: Mapped[Decimal | None] = mapped_column(Numeric(20, 4), nullable=True)

    entries: Mapped[list["CashflowEntryModel"]] = relationship(
        "CashflowEntryModel", back_populates="category"
    )


class CashflowEntryModel(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "cashflow_entries"

    account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("accounts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    category_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("cashflow_categories.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    flow_type: Mapped[str] = mapped_column(String(20), nullable=False)  # income, expense
    amount: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    currency: Mapped[str] = mapped_column(String(10), nullable=False, default="TOMAN")
    entry_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    is_recurring: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    category: Mapped["CashflowCategoryModel"] = relationship(
        "CashflowCategoryModel", back_populates="entries"
    )


class GoalCategoryModel(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "goal_categories"

    code: Mapped[str] = mapped_column(String(50), nullable=False, unique=True, index=True)
    label: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    icon: Mapped[str] = mapped_column(String(50), nullable=False, default="Target")
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    goals: Mapped[list["FinancialGoalModel"]] = relationship(
        "FinancialGoalModel", back_populates="category_config"
    )


class FinancialGoalModel(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "financial_goals"

    name: Mapped[str] = mapped_column(String(150), nullable=False)
    category: Mapped[str] = mapped_column(
        String(50),
        ForeignKey("goal_categories.code", onupdate="CASCADE", ondelete="RESTRICT"),
        nullable=False,
    )
    target_amount: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    current_amount: Mapped[Decimal] = mapped_column(
        Numeric(20, 4), nullable=False, default=Decimal("0.0000")
    )
    currency: Mapped[str] = mapped_column(String(10), nullable=False, default="TOMAN")
    target_date: Mapped[date] = mapped_column(Date, nullable=False)
    monthly_contribution: Mapped[Decimal] = mapped_column(
        Numeric(20, 4), nullable=False, default=Decimal("0.0000")
    )
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="in_progress"
    )  # in_progress, achieved, paused
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    category_config: Mapped[Optional["GoalCategoryModel"]] = relationship(
        "GoalCategoryModel", back_populates="goals"
    )


class HistoricalSnapshotModel(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "historical_snapshots"

    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False, unique=True, index=True)
    total_assets: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    total_liabilities: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    net_worth: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    liquid_assets: Mapped[Decimal] = mapped_column(Numeric(20, 4), nullable=False)
    currency: Mapped[str] = mapped_column(String(10), nullable=False, default="TOMAN")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )


class AIConversationModel(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "ai_conversations"

    title: Mapped[str] = mapped_column(String(200), nullable=False)

    messages: Mapped[list["AIMessageModel"]] = relationship(
        "AIMessageModel",
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="AIMessageModel.created_at",
    )


class AIMessageModel(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "ai_messages"

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ai_conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[str] = mapped_column(String(30), nullable=False)  # user, assistant, system, tool
    content: Mapped[str] = mapped_column(Text, nullable=False)
    tool_calls: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    tool_results: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    conversation: Mapped["AIConversationModel"] = relationship(
        "AIConversationModel", back_populates="messages"
    )


class AuditEntryModel(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "audit_entries"

    action: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(100), nullable=False)
    details: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False, index=True
    )


class SystemRole(StrEnum):
    SYSMANAGER = "sysmanager"
    ADMIN = "admin"
    USER = "user"
    VIEWER = "viewer"


class UserModel(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "users"

    email: Mapped[str | None] = mapped_column(String(255), unique=True, index=True, nullable=True)
    phone_number: Mapped[str | None] = mapped_column(
        String(30), unique=True, index=True, nullable=True
    )
    hashed_password: Mapped[str | None] = mapped_column(String(255), nullable=True)
    full_name: Mapped[str] = mapped_column(String(150), nullable=False)
    role: Mapped[str] = mapped_column(
        String(50), nullable=False, default=SystemRole.USER.value, index=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    failed_login_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    lockout_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    age: Mapped[int | None] = mapped_column(Integer, nullable=True)
    job: Mapped[str | None] = mapped_column(String(100), nullable=True)
    bio: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Financial Onboarding & Salary Benchmark Profile
    monthly_income: Mapped[Decimal | None] = mapped_column(Numeric(20, 4), nullable=True)
    liquid_assets: Mapped[Decimal | None] = mapped_column(Numeric(20, 4), nullable=True)
    investment_assets: Mapped[Decimal | None] = mapped_column(Numeric(20, 4), nullable=True)
    total_liabilities: Mapped[Decimal | None] = mapped_column(Numeric(20, 4), nullable=True)
    financial_goals: Mapped[list | None] = mapped_column(JSON, nullable=True)
    has_completed_financial_onboarding: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )

    # Psychological Risk Profile & Portfolio Suggestion
    risk_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    risk_level: Mapped[str | None] = mapped_column(String(50), nullable=True)
    risk_answers: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    portfolio_suggestion: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    has_completed_risk_onboarding: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )

    notifications: Mapped[list["NotificationModel"]] = relationship(
        "NotificationModel", back_populates="user", cascade="all, delete-orphan"
    )


class OTPRequestModel(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "otp_requests"

    identifier: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    channel: Mapped[str] = mapped_column(String(20), nullable=False)  # sms, email
    otp_code_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    purpose: Mapped[str] = mapped_column(String(50), nullable=False, default="login")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_used: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False, index=True
    )


class NotificationModel(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "notifications"

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    notification_type: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True
    )  # GOAL_REACHED, ASSET_VOLATILITY, PRICE_ALERT, SYSTEM
    severity: Mapped[str] = mapped_column(
        String(20), nullable=False, default="info"
    )  # info, warning, success, critical
    data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    is_read: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False, index=True
    )

    user: Mapped[Optional["UserModel"]] = relationship("UserModel", back_populates="notifications")


