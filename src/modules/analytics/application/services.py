import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_HALF_EVEN, Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.app.core.exceptions import AuthenticationException
from src.app.database.models import (
    AccountModel,
    AssetModel,
    AssetPositionModel,
    CashflowEntryModel,
    HistoricalSnapshotModel,
    LiabilityModel,
    TransactionModel,
    UserModel,
)
from src.modules.analytics.application.dtos import (
    AttentionItem,
    HistoricalSnapshotResponse,
    IncomeTrajectoryItem,
    InvestmentTrajectoryItem,
    LoanTrajectoryItem,
    OverviewDashboardResponse,
    TrajectoryTimelinePoint,
    WealthTrajectoryResponse,
)


class AnalyticsService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_overview(
        self, current_user: UserModel | None = None
    ) -> OverviewDashboardResponse:
        if current_user is None:
            raise AuthenticationException("Authentication required. Please log in.")

        # Check if user has personal onboarding state (0 baseline for all new users until entered)
        if not current_user.has_completed_financial_onboarding:
            # Newly registered user: All cards and charts start at 0 baseline
            return OverviewDashboardResponse(
                net_worth=Decimal("0.0000"),
                total_assets=Decimal("0.0000"),
                total_liabilities=Decimal("0.0000"),
                liquid_cash=Decimal("0.0000"),
                invested_capital=Decimal("0.0000"),
                currency="TOMAN",
                monthly_income=Decimal("0.0000"),
                monthly_expenses=Decimal("0.0000"),
                monthly_debt_service=Decimal("0.0000"),
                monthly_free_cashflow=Decimal("0.0000"),
                asset_allocation=[],
                liability_breakdown=[],
                attention_items=[
                    AttentionItem(
                        id="welcome-onboarding",
                        severity="info",
                        title="تکمیل پروفایل مالی",
                        message="برای مشاهده شاخص‌ها و پیشنهادهای شخصی‌سازی شده سرمایه‌گذاری، اطلاعات مالی و آزمون سنجش ریسک خود را تکمیل نمایید.",
                        category="onboarding",
                        action_link="/profile",
                    )
                ],
                recent_transactions=[],
                upcoming_obligations=[],
            )
        else:
            # User completed onboarding: personalize overview from user's financial profile
            u_income = (current_user.monthly_income or Decimal("0.0000")).quantize(
                Decimal("0.0001"), rounding=ROUND_HALF_EVEN
            )
            u_liquid = (current_user.liquid_assets or Decimal("0.0000")).quantize(
                Decimal("0.0001"), rounding=ROUND_HALF_EVEN
            )
            u_invested = (current_user.investment_assets or Decimal("0.0000")).quantize(
                Decimal("0.0001"), rounding=ROUND_HALF_EVEN
            )
            # Query obligations specifically for this user
            liab_stmt = select(LiabilityModel).where(LiabilityModel.user_id == current_user.id)
            liab_res = await self.db.execute(liab_stmt)
            user_liabs = liab_res.scalars().all()
            user_obligations = [
                {
                    "id": str(liab.id),
                    "name": liab.name,
                    "monthly_payment": float(liab.monthly_payment),
                    "remaining_balance": float(liab.current_balance),
                    "due_day": liab.start_date.day,
                }
                for liab in user_liabs
            ]

            if user_liabs:
                u_liabilities = sum((l.current_balance for l in user_liabs), Decimal("0.0000")).quantize(
                    Decimal("0.0001"), rounding=ROUND_HALF_EVEN
                )
                u_debt_service = sum((l.monthly_payment for l in user_liabs), Decimal("0.0000")).quantize(
                    Decimal("0.0001"), rounding=ROUND_HALF_EVEN
                )
            else:
                u_liabilities = (current_user.total_liabilities or Decimal("0.0000")).quantize(
                    Decimal("0.0001"), rounding=ROUND_HALF_EVEN
                )
                u_debt_service = Decimal("0.0000")

            u_total_assets = u_liquid + u_invested
            u_net_worth = u_total_assets - u_liabilities
            u_free_cashflow = u_income - u_debt_service

            u_allocation = []
            if u_total_assets > Decimal("0"):
                liq_pct = ((u_liquid / u_total_assets) * Decimal("100")).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_EVEN
                )
                inv_pct = ((u_invested / u_total_assets) * Decimal("100")).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_EVEN
                )
                if u_liquid > 0:
                    u_allocation.append(
                        {
                            "category": "نقدینگی و پس‌انداز",
                            "amount": float(u_liquid),
                            "percentage": float(liq_pct),
                        }
                    )
                if u_invested > 0:
                    u_allocation.append(
                        {
                            "category": "دارایی‌های سرمایه‌گذاری",
                            "amount": float(u_invested),
                            "percentage": float(inv_pct),
                        }
                    )

            u_liability_breakdown = []
            if u_liabilities > Decimal("0"):
                u_liability_breakdown.append(
                    {
                        "category": "تعهدات و بدهی‌ها",
                        "amount": float(u_liabilities),
                        "percentage": 100.0,
                    }
                )

            u_attention = []
            if current_user.risk_level:
                u_attention.append(
                    AttentionItem(
                        id="risk-profile-status",
                        severity="info",
                        title=f"پروفایل ریسک: {current_user.risk_level}",
                        message=f"بر اساس نتایج آزمون روانشناسی مالی، استراتژی سبد شما تنظیم گردیده است (امتیاز: {current_user.risk_score or 0}/100).",
                        category="risk",
                        action_link="/profile",
                    )
                )

            # Query recent transactions specifically for this user
            tx_stmt = (
                select(TransactionModel)
                .join(AccountModel, TransactionModel.account_id == AccountModel.id)
                .options(selectinload(TransactionModel.account))
                .where(AccountModel.user_id == current_user.id)
                .order_by(TransactionModel.transaction_date.desc())
                .limit(5)
            )
            tx_res = await self.db.execute(tx_stmt)
            user_txs = [
                {
                    "id": str(t.id),
                    "account_name": t.account.name if t.account else "حساب",
                    "type": t.transaction_type,
                    "amount": float(t.total_amount),
                    "date": t.transaction_date.isoformat(),
                    "currency": t.currency,
                    "notes": t.notes,
                }
                for t in tx_res.scalars().all()
            ]

            return OverviewDashboardResponse(
                net_worth=u_net_worth,
                total_assets=u_total_assets,
                total_liabilities=u_liabilities,
                liquid_cash=u_liquid,
                invested_capital=u_invested,
                currency="TOMAN",
                monthly_income=u_income,
                monthly_expenses=Decimal("0.0000"),
                monthly_debt_service=u_debt_service,
                monthly_free_cashflow=u_free_cashflow,
                asset_allocation=u_allocation,
                liability_breakdown=u_liability_breakdown,
                attention_items=u_attention,
                recent_transactions=user_txs,
                upcoming_obligations=user_obligations,
            )

        # Default system/sysmanager calculation (seeded accounts, positions, liabilities)
        # 1. Accounts & Liquid Cash
        acc_stmt = select(AccountModel).where(AccountModel.is_active == True)  # noqa: E712
        acc_result = await self.db.execute(acc_stmt)
        accounts = acc_result.scalars().all()

        liquid_cash = Decimal("0.0000")
        total_account_cash = Decimal("0.0000")
        for acc in accounts:
            total_account_cash += acc.current_balance
            if acc.account_type.lower() in ("checking", "savings", "cash"):
                liquid_cash += acc.current_balance

        # 2. Asset Positions & Valuation
        pos_stmt = select(AssetPositionModel).options(selectinload(AssetPositionModel.asset))
        pos_result = await self.db.execute(pos_stmt)
        positions = pos_result.scalars().all()

        invested_value = Decimal("0.0000")
        allocation_map: dict[str, Decimal] = {"Cash": liquid_cash}

        for pos in positions:
            val = (pos.quantity * pos.asset.current_price).quantize(
                Decimal("0.0001"), rounding=ROUND_HALF_EVEN
            )
            invested_value += val
            cls_name = pos.asset.asset_class.title()
            allocation_map[cls_name] = allocation_map.get(cls_name, Decimal("0.0000")) + val

        total_assets = total_account_cash + invested_value

        # 3. Liabilities
        liab_stmt = select(LiabilityModel)
        liab_result = await self.db.execute(liab_stmt)
        liabilities = liab_result.scalars().all()

        total_liabilities = Decimal("0.0000")
        monthly_debt_service = Decimal("0.0000")
        liab_breakdown_map: dict[str, Decimal] = {}

        for liab in liabilities:
            total_liabilities += liab.current_balance
            monthly_debt_service += liab.monthly_payment
            l_type = liab.liability_type.replace("_", " ").title()
            liab_breakdown_map[l_type] = (
                liab_breakdown_map.get(l_type, Decimal("0.0000")) + liab.current_balance
            )

        net_worth = total_assets - total_liabilities

        # 4. Monthly Cashflow (Last 30 days)
        thirty_days_ago = date.today() - timedelta(days=30)
        cf_stmt = select(CashflowEntryModel).where(CashflowEntryModel.entry_date >= thirty_days_ago)
        cf_result = await self.db.execute(cf_stmt)
        cf_entries = cf_result.scalars().all()

        monthly_income = Decimal("0.0000")
        monthly_expenses = Decimal("0.0000")
        for cf in cf_entries:
            if cf.flow_type == "income":
                monthly_income += cf.amount
            else:
                monthly_expenses += cf.amount

        monthly_free_cashflow = monthly_income - monthly_expenses - monthly_debt_service

        # 5. Asset Allocation Format
        asset_allocation = []
        for k, v in allocation_map.items():
            pct = Decimal("0.00")
            if total_assets > Decimal("0"):
                pct = ((v / total_assets) * Decimal("100")).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_EVEN
                )
            asset_allocation.append({"category": k, "amount": float(v), "percentage": float(pct)})

        # 6. Liability Breakdown Format
        liability_breakdown = []
        for k, v in liab_breakdown_map.items():
            pct = Decimal("0.00")
            if total_liabilities > Decimal("0"):
                pct = ((v / total_liabilities) * Decimal("100")).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_EVEN
                )
            liability_breakdown.append(
                {"category": k, "amount": float(v), "percentage": float(pct)}
            )

        # 7. Attention Items (Anomalies / Rule-based insights)
        attention_items: list[AttentionItem] = []

        # Check emergency fund buffer (3x monthly expenses)
        emergency_target = (monthly_expenses + monthly_debt_service) * Decimal("3")
        if emergency_target > Decimal("0") and liquid_cash < emergency_target:
            attention_items.append(
                AttentionItem(
                    id="low-liquid-buffer",
                    severity="warning",
                    title="Liquidity Buffer Notice",
                    message=f"Liquid cash (${float(liquid_cash):,.2f}) is below the recommended 3-month expense buffer (${float(emergency_target):,.2f}).",
                    category="liquidity",
                    action_link="/cashflow",
                )
            )

        # Check high interest liabilities
        for liab in liabilities:
            if liab.interest_rate_percent >= Decimal("10.0"):
                attention_items.append(
                    AttentionItem(
                        id=f"high-rate-{liab.id}",
                        severity="critical"
                        if liab.interest_rate_percent > Decimal("18.0")
                        else "warning",
                        title=f"High Interest Obligation: {liab.name}",
                        message=f"{liab.name} carries a {liab.interest_rate_percent}% APR. Consider accelerated repayment.",
                        category="liability",
                        action_link="/liabilities",
                    )
                )

        # Check asset concentration (>35% in single holding)
        for pos in positions:
            pos_val = pos.quantity * pos.asset.current_price
            if total_assets > Decimal("0"):
                concentration = (pos_val / total_assets) * Decimal("100")
                if concentration > Decimal("35.0"):
                    attention_items.append(
                        AttentionItem(
                            id=f"concentration-{pos.asset.symbol}",
                            severity="info",
                            title=f"High Concentration: {pos.asset.symbol}",
                            message=f"{pos.asset.name} ({pos.asset.symbol}) accounts for {float(concentration):.1f}% of total assets.",
                            category="portfolio",
                            action_link="/portfolio",
                        )
                    )

        # 8. Recent Transactions
        tx_stmt = (
            select(TransactionModel)
            .options(selectinload(TransactionModel.account))
            .order_by(TransactionModel.transaction_date.desc())
            .limit(5)
        )
        tx_result = await self.db.execute(tx_stmt)
        recent_txs = [
            {
                "id": str(t.id),
                "account_name": t.account.name if t.account else "حساب",
                "type": t.transaction_type,
                "amount": float(t.total_amount),
                "date": t.transaction_date.isoformat(),
                "currency": t.currency,
                "notes": t.notes,
            }
            for t in tx_result.scalars().all()
        ]

        # 9. Upcoming Obligations
        upcoming_obligations = [
            {
                "id": str(liab.id),
                "name": liab.name,
                "monthly_payment": float(liab.monthly_payment),
                "remaining_balance": float(liab.current_balance),
                "due_day": liab.start_date.day,
            }
            for liab in liabilities
        ]

        return OverviewDashboardResponse(
            net_worth=net_worth.quantize(Decimal("0.0001"), rounding=ROUND_HALF_EVEN),
            total_assets=total_assets.quantize(Decimal("0.0001"), rounding=ROUND_HALF_EVEN),
            total_liabilities=total_liabilities.quantize(
                Decimal("0.0001"), rounding=ROUND_HALF_EVEN
            ),
            liquid_cash=liquid_cash.quantize(Decimal("0.0001"), rounding=ROUND_HALF_EVEN),
            invested_capital=invested_value.quantize(Decimal("0.0001"), rounding=ROUND_HALF_EVEN),
            currency="USD",
            monthly_income=monthly_income.quantize(Decimal("0.0001"), rounding=ROUND_HALF_EVEN),
            monthly_expenses=monthly_expenses.quantize(Decimal("0.0001"), rounding=ROUND_HALF_EVEN),
            monthly_debt_service=monthly_debt_service.quantize(
                Decimal("0.0001"), rounding=ROUND_HALF_EVEN
            ),
            monthly_free_cashflow=monthly_free_cashflow.quantize(
                Decimal("0.0001"), rounding=ROUND_HALF_EVEN
            ),
            asset_allocation=asset_allocation,
            liability_breakdown=liability_breakdown,
            attention_items=attention_items,
            recent_transactions=recent_txs,
            upcoming_obligations=upcoming_obligations,
        )

    async def get_historical_snapshots(
        self, limit: int = 90, current_user: UserModel | None = None
    ) -> list[HistoricalSnapshotResponse]:
        if current_user is None:
            raise AuthenticationException("Authentication required. Please log in.")

        now = datetime.now(UTC)
        today = date.today()
        days = min(limit, 30)

        if not current_user.has_completed_financial_onboarding:
            # Return empty list so charts show proper empty state for new user
            return []
        else:
            stmt = (
                select(HistoricalSnapshotModel)
                .order_by(HistoricalSnapshotModel.snapshot_date.asc())
                .limit(limit)
            )
            res = await self.db.execute(stmt)
            db_snapshots = res.scalars().all()
            if db_snapshots:
                return [
                    HistoricalSnapshotResponse.model_validate(s)
                    for s in db_snapshots
                ]

            # Snapshots reflecting user's financial profile
            u_liquid = current_user.liquid_assets or Decimal("0.0000")
            u_invested = current_user.investment_assets or Decimal("0.0000")

            liab_stmt = select(LiabilityModel).where(LiabilityModel.user_id == current_user.id)
            liab_res = await self.db.execute(liab_stmt)
            user_liabs = liab_res.scalars().all()
            if user_liabs:
                u_liab = sum((l.current_balance for l in user_liabs), Decimal("0.0000"))
            else:
                u_liab = current_user.total_liabilities or Decimal("0.0000")

            u_assets = u_liquid + u_invested
            u_net = u_assets - u_liab
            return [
                HistoricalSnapshotResponse(
                    id=uuid.uuid4(),
                    snapshot_date=today - timedelta(days=i),
                    total_assets=u_assets,
                    total_liabilities=u_liab,
                    net_worth=u_net,
                    liquid_assets=u_liquid,
                    currency="TOMAN",
                    created_at=now,
                )
                for i in reversed(range(days))
            ]

    async def record_snapshot(
        self, snapshot_date: date | None = None, current_user: UserModel | None = None
    ) -> HistoricalSnapshotModel:
        target_date = snapshot_date or date.today()
        overview = await self.get_overview(current_user=current_user)

        # Check existing snapshot for date
        stmt = select(HistoricalSnapshotModel).where(
            HistoricalSnapshotModel.snapshot_date == target_date
        )
        result = await self.db.execute(stmt)
        snapshot = result.scalar_one_or_none()

        if snapshot:
            snapshot.total_assets = overview.total_assets
            snapshot.total_liabilities = overview.total_liabilities
            snapshot.net_worth = overview.net_worth
            snapshot.liquid_assets = overview.liquid_cash
            snapshot.currency = "TOMAN"
        else:
            snapshot = HistoricalSnapshotModel(
                snapshot_date=target_date,
                total_assets=overview.total_assets,
                total_liabilities=overview.total_liabilities,
                net_worth=overview.net_worth,
                liquid_assets=overview.liquid_cash,
                currency="TOMAN",
            )
            self.db.add(snapshot)

        await self.db.flush()
        await self.db.refresh(snapshot)
        return snapshot

    async def get_wealth_trajectory(
        self,
        history_days: int = 180,
        forecast_months: int = 24,
        annual_growth_override: Decimal | None = None,
        current_user: UserModel | None = None,
    ) -> WealthTrajectoryResponse:
        if current_user is None:
            raise AuthenticationException("Authentication required. Please log in.")

        overview = await self.get_overview(current_user=current_user)
        baseline_invested = overview.invested_capital
        baseline_liabilities = overview.total_liabilities
        baseline_liquid = overview.liquid_cash
        baseline_salary = overview.monthly_income
        baseline_free_cf = overview.monthly_free_cashflow

        today = date.today()

        # 1. Fetch user liabilities
        if current_user.role != "sysmanager":
            liab_stmt = (
                select(LiabilityModel)
                .options(selectinload(LiabilityModel.type_config))
                .where(LiabilityModel.user_id == current_user.id)
                .order_by(LiabilityModel.current_balance.desc())
            )
        else:
            liab_stmt = (
                select(LiabilityModel)
                .options(selectinload(LiabilityModel.type_config))
                .order_by(LiabilityModel.current_balance.desc())
            )
        liab_res = await self.db.execute(liab_stmt)
        raw_liabs = list(liab_res.scalars().all())

        loans_list: list[LoanTrajectoryItem] = []
        sim_loans: list[dict[str, Any]] = []

        if raw_liabs:
            for l in raw_liabs:
                repaid = max(Decimal("0.00"), l.original_principal - l.current_balance)
                repaid_pct = (
                    ((repaid / l.original_principal) * Decimal("100")).quantize(
                        Decimal("0.01"), rounding=ROUND_HALF_EVEN
                    )
                    if l.original_principal > Decimal("0")
                    else Decimal("0.00")
                )

                # Estimate months to payoff
                rem_months = 0
                balance_tracker = l.current_balance
                m_rate = (l.interest_rate_percent / Decimal("100")) / Decimal("12")
                while balance_tracker > Decimal("0.01") and rem_months < 120:
                    rem_months += 1
                    interest = balance_tracker * m_rate
                    principal_paid = max(Decimal("0.00"), l.monthly_payment - interest)
                    if principal_paid <= Decimal("0.00"):
                        principal_paid = balance_tracker / Decimal(max(1, 36 - rem_months))
                    balance_tracker = max(Decimal("0.00"), balance_tracker - principal_paid)

                payoff_dt = today + timedelta(days=int(rem_months * 30.5))
                payoff_str = payoff_dt.strftime("%Y-%m-%d")

                loans_list.append(
                    LoanTrajectoryItem(
                        id=str(l.id),
                        name=l.name,
                        liability_type=l.liability_type,
                        lender=l.lender,
                        original_principal=l.original_principal,
                        current_balance=l.current_balance,
                        interest_rate_percent=l.interest_rate_percent,
                        monthly_payment=l.monthly_payment,
                        start_date=l.start_date.isoformat(),
                        maturity_date=l.maturity_date.isoformat() if l.maturity_date else None,
                        estimated_payoff_date=payoff_str,
                        remaining_months=rem_months,
                        repaid_percent=repaid_pct,
                    )
                )
                sim_loans.append({
                    "id": str(l.id),
                    "name": l.name,
                    "balance": l.current_balance,
                    "monthly_payment": l.monthly_payment,
                    "rate": l.interest_rate_percent,
                    "orig_principal": l.original_principal,
                })
        elif baseline_liabilities > Decimal("0"):
            synth_id = "synth-profile-loan"
            synth_orig = (baseline_liabilities * Decimal("1.25")).quantize(Decimal("0.01"))
            synth_rate = Decimal("18.0")
            synth_pmt = max(Decimal("1000000.00"), (baseline_liabilities * Decimal("0.045")).quantize(Decimal("0.01")))
            rem_months = max(6, int(baseline_liabilities / synth_pmt))
            payoff_dt = today + timedelta(days=int(rem_months * 30.5))
            loans_list.append(
                LoanTrajectoryItem(
                    id=synth_id,
                    name="تسهیلات بانکی و اقساط مصوب",
                    liability_type="bank_loan",
                    lender="بانک عامل",
                    original_principal=synth_orig,
                    current_balance=baseline_liabilities,
                    interest_rate_percent=synth_rate,
                    monthly_payment=synth_pmt,
                    start_date=(today - timedelta(days=180)).isoformat(),
                    maturity_date=payoff_dt.isoformat(),
                    estimated_payoff_date=payoff_dt.strftime("%Y-%m-%d"),
                    remaining_months=rem_months,
                    repaid_percent=Decimal("20.00"),
                )
            )
            sim_loans.append({
                "id": synth_id,
                "name": "تسهیلات بانکی و اقساط مصوب",
                "balance": baseline_liabilities,
                "monthly_payment": synth_pmt,
                "rate": synth_rate,
                "orig_principal": synth_orig,
            })

        # 2. Fetch user asset positions
        pos_stmt = (
            select(AssetPositionModel)
            .join(AccountModel, AssetPositionModel.account_id == AccountModel.id)
            .options(selectinload(AssetPositionModel.asset))
        )
        if current_user.role != "sysmanager":
            pos_stmt = pos_stmt.where(AccountModel.user_id == current_user.id)
        pos_res = await self.db.execute(pos_stmt)
        raw_positions = list(pos_res.scalars().all())

        CLASS_GROWTH_RATES = {
            "equity": Decimal("26.0"),
            "commodity": Decimal("28.0"),
            "crypto": Decimal("32.0"),
            "fixed_income": Decimal("22.0"),
            "real_estate": Decimal("24.0"),
            "cash": Decimal("18.0"),
            "other": Decimal("20.0"),
        }

        investments_list: list[InvestmentTrajectoryItem] = []
        sim_investments: list[dict[str, Any]] = []

        if raw_positions:
            for p in raw_positions:
                val = (p.quantity * p.asset.current_price).quantize(Decimal("0.0001"))
                cost = (p.quantity * p.average_cost_basis).quantize(Decimal("0.0001"))
                pnl = val - cost
                c_key = p.asset.asset_class.lower()
                expected_rate = annual_growth_override or CLASS_GROWTH_RATES.get(c_key, Decimal("24.0"))

                rate_1 = Decimal("1") + (expected_rate / Decimal("100"))
                rate_2 = (Decimal("1") + (expected_rate / Decimal("100"))) ** 2
                val_1y = (val * rate_1).quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)
                val_2y = (val * rate_2).quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)

                investments_list.append(
                    InvestmentTrajectoryItem(
                        id=str(p.id),
                        name=p.asset.name,
                        symbol=p.asset.symbol,
                        asset_class=p.asset.asset_class,
                        current_value=val.quantize(Decimal("0.01")),
                        quantity=p.quantity,
                        current_price=p.asset.current_price,
                        unrealized_pnl=pnl.quantize(Decimal("0.01")),
                        projected_annual_growth_rate=expected_rate,
                        projected_value_1y=val_1y,
                        projected_value_2y=val_2y,
                    )
                )
                sim_investments.append({
                    "id": str(p.id),
                    "name": p.asset.name,
                    "symbol": p.asset.symbol,
                    "value": val,
                    "growth_rate": expected_rate,
                })
        elif baseline_invested > Decimal("0"):
            synth_specs = [
                ("synth-inv-gold", "طلا و سکه بهار آزادی", "GOLD", "commodity", Decimal("0.35"), Decimal("28.0")),
                ("synth-inv-equity", "صندوق‌های شاخصی و سهامی", "ETF", "equity", Decimal("0.40"), Decimal("26.0")),
                ("synth-inv-fixed", "صندوق اوراق با درآمد ثابت", "FIXED", "fixed_income", Decimal("0.25"), Decimal("22.0")),
            ]
            for s_id, s_name, s_sym, s_cls, s_share, s_rate in synth_specs:
                s_val = (baseline_invested * s_share).quantize(Decimal("0.01"))
                s_rate_use = annual_growth_override or s_rate
                rate_1 = Decimal("1") + (s_rate_use / Decimal("100"))
                rate_2 = (Decimal("1") + (s_rate_use / Decimal("100"))) ** 2
                investments_list.append(
                    InvestmentTrajectoryItem(
                        id=s_id,
                        name=s_name,
                        symbol=s_sym,
                        asset_class=s_cls,
                        current_value=s_val,
                        quantity=Decimal("1.00"),
                        current_price=s_val,
                        unrealized_pnl=(s_val * Decimal("0.12")).quantize(Decimal("0.01")),
                        projected_annual_growth_rate=s_rate_use,
                        projected_value_1y=(s_val * rate_1).quantize(Decimal("0.01")),
                        projected_value_2y=(s_val * rate_2).quantize(Decimal("0.01")),
                    )
                )
                sim_investments.append({
                    "id": s_id,
                    "name": s_name,
                    "symbol": s_sym,
                    "value": s_val,
                    "growth_rate": s_rate_use,
                })

        # 3. Income Streams
        incomes_list: list[IncomeTrajectoryItem] = []
        if baseline_salary > Decimal("0"):
            incomes_list.append(
                IncomeTrajectoryItem(
                    id="primary-salary",
                    name="حقوق و دریافتی ماهانه",
                    flow_type="salary",
                    monthly_amount=baseline_salary,
                    annual_amount=baseline_salary * Decimal("12"),
                    is_recurring=True,
                )
            )

        # 4. Construct Timeline
        timeline: list[TrajectoryTimelinePoint] = []

        history_steps = max(1, min(12, max(1, history_days // 30)))
        for step in range(history_steps, 0, -1):
            past_date = today - timedelta(days=step * 30)
            date_str = past_date.strftime("%Y-%m-%d")
            display_str = past_date.strftime("%m/%d")

            item_vals: dict[str, Decimal] = {}
            hist_liab_sum = Decimal("0.00")
            for sl in sim_loans:
                added_back = sl["monthly_payment"] * Decimal("0.75") * Decimal(step)
                past_l_val = min(sl["orig_principal"], sl["balance"] + added_back).quantize(Decimal("0.01"))
                item_vals[sl["id"]] = past_l_val
                hist_liab_sum += past_l_val

            hist_inv_sum = Decimal("0.00")
            for si in sim_investments:
                monthly_factor = (Decimal("1") + ((si["growth_rate"] / Decimal("100")) / Decimal("12"))) ** step
                past_inv_val = (si["value"] / monthly_factor).quantize(Decimal("0.01"))
                item_vals[si["id"]] = past_inv_val
                hist_inv_sum += past_inv_val

            hist_nw = (hist_inv_sum + baseline_liquid - hist_liab_sum).quantize(Decimal("0.01"))
            timeline.append(
                TrajectoryTimelinePoint(
                    date=date_str,
                    display_date=display_str,
                    is_forecast=False,
                    total_liabilities=hist_liab_sum.quantize(Decimal("0.01")),
                    total_investments=hist_inv_sum.quantize(Decimal("0.01")),
                    salary_income=baseline_salary,
                    net_worth=hist_nw,
                    liquid_cash=baseline_liquid,
                    forecast_confidence_upper=None,
                    forecast_confidence_lower=None,
                    item_values=item_vals,
                )
            )

        # Present Day point
        today_str = today.strftime("%Y-%m-%d")
        today_display = "امروز"
        today_item_vals: dict[str, Decimal] = {}
        for sl in sim_loans:
            today_item_vals[sl["id"]] = sl["balance"].quantize(Decimal("0.01"))
        for si in sim_investments:
            today_item_vals[si["id"]] = si["value"].quantize(Decimal("0.01"))

        today_nw = (baseline_invested + baseline_liquid - baseline_liabilities).quantize(Decimal("0.01"))
        timeline.append(
            TrajectoryTimelinePoint(
                date=today_str,
                display_date=today_display,
                is_forecast=False,
                total_liabilities=baseline_liabilities,
                total_investments=baseline_invested,
                salary_income=baseline_salary,
                net_worth=today_nw,
                liquid_cash=baseline_liquid,
                forecast_confidence_upper=baseline_invested,
                forecast_confidence_lower=baseline_invested,
                item_values=today_item_vals,
            )
        )

        # Future AI Forecast points
        curr_sim_loans = [{**sl, "curr": sl["balance"]} for sl in sim_loans]
        curr_sim_invs = [{**si, "curr": si["value"]} for si in sim_investments]
        debt_free_date: str | None = None
        crossover_date: str | None = None

        for m in range(1, forecast_months + 1):
            f_date = today + timedelta(days=int(m * 30.4375))
            f_date_str = f_date.strftime("%Y-%m-%d")
            f_display = f"+{m} ماه"

            f_item_vals: dict[str, Decimal] = {}
            f_liab_sum = Decimal("0.00")

            for sl in curr_sim_loans:
                if sl["curr"] > Decimal("0.00"):
                    m_rate = (sl["rate"] / Decimal("100")) / Decimal("12")
                    interest = sl["curr"] * m_rate
                    principal = max(Decimal("0.00"), sl["monthly_payment"] - interest)
                    if principal <= Decimal("0.00") or principal > sl["curr"]:
                        principal = sl["curr"]
                    sl["curr"] = max(Decimal("0.00"), sl["curr"] - principal)
                f_item_vals[sl["id"]] = sl["curr"].quantize(Decimal("0.01"))
                f_liab_sum += sl["curr"]

            if f_liab_sum == Decimal("0.00") and debt_free_date is None and baseline_liabilities > Decimal("0"):
                debt_free_date = f_date_str

            f_inv_sum = Decimal("0.00")
            extra_freed_debt_pmt = max(Decimal("0.00"), overview.monthly_debt_service - sum(sl["monthly_payment"] for sl in curr_sim_loans if sl["curr"] > Decimal("0.00")))
            monthly_invest_infusion = max(Decimal("0.00"), (baseline_free_cf + extra_freed_debt_pmt) * Decimal("0.40"))

            total_inv_weight = sum(si["curr"] for si in curr_sim_invs) or Decimal("1.00")

            for si in curr_sim_invs:
                m_rate = (si["growth_rate"] / Decimal("100")) / Decimal("12")
                growth = si["curr"] * m_rate
                portion_infusion = (si["curr"] / total_inv_weight) * monthly_invest_infusion if total_inv_weight > Decimal("0") else Decimal("0.00")
                si["curr"] = (si["curr"] + growth + portion_infusion).quantize(Decimal("0.01"))
                f_item_vals[si["id"]] = si["curr"]
                f_inv_sum += si["curr"]

            if f_inv_sum >= f_liab_sum and crossover_date is None:
                crossover_date = f_date_str

            variance_pct = Decimal("0.05") + (Decimal("0.004") * Decimal(m))
            conf_upper = (f_inv_sum * (Decimal("1") + variance_pct)).quantize(Decimal("0.01"))
            conf_lower = (f_inv_sum * (Decimal("1") - variance_pct)).quantize(Decimal("0.01"))

            f_salary = (baseline_salary * ((Decimal("1") + Decimal("0.003")) ** m)).quantize(Decimal("0.01"))
            f_nw = (f_inv_sum + baseline_liquid - f_liab_sum).quantize(Decimal("0.01"))

            timeline.append(
                TrajectoryTimelinePoint(
                    date=f_date_str,
                    display_date=f_display,
                    is_forecast=True,
                    total_liabilities=f_liab_sum.quantize(Decimal("0.01")),
                    total_investments=f_inv_sum.quantize(Decimal("0.01")),
                    salary_income=f_salary,
                    net_worth=f_nw,
                    liquid_cash=baseline_liquid,
                    forecast_confidence_upper=conf_upper,
                    forecast_confidence_lower=conf_lower,
                    item_values=f_item_vals,
                )
            )

        projected_investments_end = timeline[-1].total_investments if timeline else baseline_invested
        projected_liabilities_end = timeline[-1].total_liabilities if timeline else Decimal("0.00")
        projected_total_profit = max(Decimal("0.00"), projected_investments_end - baseline_invested)
        total_interest_saved = (baseline_liabilities * Decimal("0.18") * Decimal("0.5")).quantize(Decimal("0.01"))

        debt_status_fa = f"تا تاریخ {debt_free_date} بدهی‌های شما به صفر خواهد رسید" if debt_free_date else "بدهی‌ها در مسیر کاهشی منظم قرار دارند"
        profit_ratio = (
            ((projected_total_profit / baseline_invested) * Decimal("100")).quantize(Decimal("0.1"))
            if baseline_invested > Decimal("0")
            else Decimal("0.0")
        )
        ai_narrative = (
            f"بر اساس شبیه‌سازی مالی هوش مصنوعی، {debt_status_fa} و ارزش پورتفولیوی سرمایه‌گذاری شما با سود مرکب و تزریق مستمر پس‌انداز مازاد حقوق، رشد تخمینی {profit_ratio}٪ را تجربه خواهد کرد. استهلاک موفق اقساط وام ظرفیت نقدینگی آزاد ماهانه شما را به میزان قابل توجهی ارتقا می‌دهد."
        )

        return WealthTrajectoryResponse(
            timeline=timeline,
            historical_points_count=history_steps + 1,
            forecast_points_count=forecast_months,
            baseline_investments=baseline_invested,
            baseline_liabilities=baseline_liabilities,
            baseline_salary=baseline_salary,
            debt_free_date=debt_free_date,
            crossover_date=crossover_date,
            projected_investments_end=projected_investments_end,
            projected_liabilities_end=projected_liabilities_end,
            projected_total_profit=projected_total_profit,
            total_debt_interest_saved=total_interest_saved,
            ai_narrative=ai_narrative,
            loans=loans_list,
            investments=investments_list,
            incomes=incomes_list,
        )
