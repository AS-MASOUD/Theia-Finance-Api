from decimal import Decimal
import uuid

from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.core.exceptions import (
    AppException,
    EntityConflictException,
    EntityNotFoundException,
)
from src.app.core.security import hash_password
from src.app.database.models import AuditEntryModel, SystemRole, UserModel
from src.modules.auth.application.dtos import UserResponse
from src.modules.users.application.dtos import (
    RoleDefinitionResponse,
    UserCreateRequest,
    UserListResponse,
    UserUpdateRequest,
)


class UserService:
    def get_system_roles(self) -> list[RoleDefinitionResponse]:
        return [
            RoleDefinitionResponse(
                role=SystemRole.SYSMANAGER.value,
                name_fa="مدیر ارشد سیستم (SysManager)",
                name_en="System Manager",
                description_fa="دسترسی جامع و نامحدود، مدیریت کاربران، تعیین و ارتقاء نقش‌ها، مشاهده گزارش‌های سیستمی و امنیت پایگاه‌داده.",
                description_en="Full administrative control, user & role lifecycle management, audit logs, system configurations.",
                badge_color="#8b5cf6",
                permissions=[
                    "users:create",
                    "users:read",
                    "users:update",
                    "users:delete",
                    "roles:manage",
                    "audit:view",
                    "financial:manage",
                    "system:config",
                ],
            ),
            RoleDefinitionResponse(
                role=SystemRole.ADMIN.value,
                name_fa="مدیر مالی (Admin)",
                name_en="Financial Admin",
                description_fa="مدیریت کامل حساب‌ها، دارایی‌ها، تسهیلات و اسناد مالی با اختیارات ایجاد، ویرایش و حذف گزارش‌های مالی.",
                description_en="Full read/write permissions on accounts, assets, liabilities, and financial operations.",
                badge_color="#0284c7",
                permissions=[
                    "users:read",
                    "financial:manage",
                    "reports:generate",
                    "scenarios:manage",
                ],
            ),
            RoleDefinitionResponse(
                role=SystemRole.USER.value,
                name_fa="کاربر استاندارد (User)",
                name_en="Standard User",
                description_fa="مدیریت و ثبت داده‌های مالی شخصی، تراکنش‌ها، اهداف پس‌انداز و تعامل با دستیار هوشمند مالی.",
                description_en="Manage personal accounts, add transactions, simulate scenarios, AI assistant access.",
                badge_color="#10b981",
                permissions=[
                    "personal_financial:read",
                    "personal_financial:write",
                    "ai:chat",
                ],
            ),
            RoleDefinitionResponse(
                role=SystemRole.VIEWER.value,
                name_fa="ناظر و بازبین (Viewer)",
                name_en="Read-Only Viewer",
                description_fa="دسترسی فقط‌خواندنی به پورتفولیو، تحلیل نسبت‌های مالی، سناریوها و نمودارها بدون امکان ثبت یا حذف.",
                description_en="Read-only access to dashboards, reports, and portfolio analytics.",
                badge_color="#64748b",
                permissions=[
                    "dashboard:view",
                    "analytics:view",
                    "reports:read",
                ],
            ),
        ]

    async def list_users(
        self,
        db: AsyncSession,
        search: str | None = None,
        role: str | None = None,
        is_active: bool | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> UserListResponse:
        query = select(UserModel)

        if search:
            search_term = f"%{search.strip().lower()}%"
            query = query.where(
                or_(
                    func.lower(UserModel.email).like(search_term),
                    func.lower(UserModel.full_name).like(search_term),
                )
            )

        if role:
            query = query.where(UserModel.role == role)

        if is_active is not None:
            query = query.where(UserModel.is_active == is_active)

        # Count total
        count_stmt = select(func.count()).select_from(query.subquery())
        total = (await db.execute(count_stmt)).scalar() or 0

        # Fetch page items
        query = query.order_by(UserModel.created_at.desc()).limit(limit).offset(offset)
        result = await db.execute(query)
        users = result.scalars().all()

        page = (offset // limit) + 1 if limit > 0 else 1

        return UserListResponse(
            total=total,
            page=page,
            limit=limit,
            items=[UserResponse.model_validate(u) for u in users],
        )

    async def get_user_by_id(self, db: AsyncSession, user_id: uuid.UUID) -> UserModel:
        stmt = select(UserModel).where(UserModel.id == user_id)
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()
        if user is None:
            raise EntityNotFoundException("User", user_id)
        return user

    async def create_user(
        self,
        db: AsyncSession,
        admin_user: UserModel,
        request: UserCreateRequest,
    ) -> UserModel:
        # Check email duplicate
        stmt_exist = select(UserModel).where(UserModel.email == request.email)
        res_exist = await db.execute(stmt_exist)
        if res_exist.scalar_one_or_none() is not None:
            raise EntityConflictException("A user with this email address already exists.")

        user = UserModel(
            email=request.email,
            hashed_password=hash_password(request.password),
            full_name=request.full_name,
            role=request.role.value,
            is_active=request.is_active,
            is_verified=True,
            monthly_income=Decimal("0.0000"),
            liquid_assets=Decimal("0.0000"),
            investment_assets=Decimal("0.0000"),
            total_liabilities=Decimal("0.0000"),
            financial_goals=[],
            has_completed_financial_onboarding=False,
            risk_score=0,
            risk_level=None,
            risk_answers=None,
            portfolio_suggestion=None,
            has_completed_risk_onboarding=False,
        )
        db.add(user)
        await db.flush()

        audit = AuditEntryModel(
            action="USER_CREATED_BY_ADMIN",
            entity_type="USER",
            entity_id=str(user.id),
            details={
                "created_by": str(admin_user.id),
                "created_by_email": admin_user.email,
                "target_email": user.email,
                "role": user.role,
            },
        )
        db.add(audit)
        await db.flush()

        return user

    async def update_user_role(
        self,
        db: AsyncSession,
        admin_user: UserModel,
        user_id: uuid.UUID,
        new_role: SystemRole,
    ) -> UserModel:
        user = await self.get_user_by_id(db, user_id)

        # Safeguard: Do not demote the last active sysmanager or last active administrator
        if user.role == SystemRole.SYSMANAGER.value and new_role != SystemRole.SYSMANAGER:
            sysmanager_count = await self._count_active_sysmanagers(db)
            if sysmanager_count <= 1:
                raise AppException(
                    message="Cannot demote the last remaining active System Manager.",
                    code="LAST_SYSMANAGER_PROTECTION",
                    status_code=400,
                )

        if user.role in (SystemRole.SYSMANAGER.value, SystemRole.ADMIN.value) and new_role not in (
            SystemRole.SYSMANAGER,
            SystemRole.ADMIN,
        ):
            admin_count = await self._count_active_administrators(db)
            if admin_count <= 1:
                raise AppException(
                    message="Cannot remove administrative privileges from the last remaining active Administrator.",
                    code="LAST_ADMIN_PROTECTION",
                    status_code=400,
                )

        old_role = user.role
        user.role = new_role.value
        await db.flush()

        audit = AuditEntryModel(
            action="USER_ROLE_CHANGED",
            entity_type="USER",
            entity_id=str(user.id),
            details={
                "changed_by": str(admin_user.id),
                "old_role": old_role,
                "new_role": new_role.value,
                "target_email": user.email,
            },
        )
        db.add(audit)
        await db.flush()

        return user

    async def update_user_status(
        self,
        db: AsyncSession,
        admin_user: UserModel,
        user_id: uuid.UUID,
        is_active: bool,
    ) -> UserModel:
        user = await self.get_user_by_id(db, user_id)

        # Safeguard: cannot deactivate own account
        if admin_user.id == user.id and not is_active:
            raise AppException(
                message="You cannot deactivate your own administrative account.",
                code="SELF_DEACTIVATION_PROHIBITED",
                status_code=400,
            )

        # Safeguard: cannot deactivate last active administrator / sysmanager
        if not is_active and user.role in (SystemRole.SYSMANAGER.value, SystemRole.ADMIN.value):
            if user.role == SystemRole.SYSMANAGER.value:
                sysmanager_count = await self._count_active_sysmanagers(db)
                if sysmanager_count <= 1:
                    raise AppException(
                        message="Cannot deactivate the last remaining active System Manager.",
                        code="LAST_SYSMANAGER_PROTECTION",
                        status_code=400,
                    )
            admin_count = await self._count_active_administrators(db)
            if admin_count <= 1:
                raise AppException(
                    message="Cannot deactivate the last remaining active Administrator.",
                    code="LAST_ADMIN_PROTECTION",
                    status_code=400,
                )

        user.is_active = is_active
        await db.flush()

        audit = AuditEntryModel(
            action="USER_STATUS_CHANGED",
            entity_type="USER",
            entity_id=str(user.id),
            details={
                "changed_by": str(admin_user.id),
                "is_active": is_active,
                "target_email": user.email,
            },
        )
        db.add(audit)
        await db.flush()

        return user

    async def update_user(
        self,
        db: AsyncSession,
        admin_user: UserModel,
        user_id: uuid.UUID,
        request: UserUpdateRequest,
    ) -> UserModel:
        user = await self.get_user_by_id(db, user_id)

        if request.email and request.email != user.email:
            stmt_exist = select(UserModel).where(UserModel.email == request.email)
            res_exist = await db.execute(stmt_exist)
            if res_exist.scalar_one_or_none() is not None:
                raise EntityConflictException("A user with this email address already exists.")
            user.email = request.email

        if request.full_name is not None:
            user.full_name = request.full_name

        if request.role is not None:
            if user.role == SystemRole.SYSMANAGER.value and request.role != SystemRole.SYSMANAGER:
                sysmanager_count = await self._count_active_sysmanagers(db)
                if sysmanager_count <= 1:
                    raise AppException(
                        message="Cannot demote the last remaining active System Manager.",
                        code="LAST_SYSMANAGER_PROTECTION",
                        status_code=400,
                    )
            if user.role in (SystemRole.SYSMANAGER.value, SystemRole.ADMIN.value) and request.role not in (
                SystemRole.SYSMANAGER,
                SystemRole.ADMIN,
            ):
                admin_count = await self._count_active_administrators(db)
                if admin_count <= 1:
                    raise AppException(
                        message="Cannot remove administrative privileges from the last remaining active Administrator.",
                        code="LAST_ADMIN_PROTECTION",
                        status_code=400,
                    )
            user.role = request.role.value

        if request.is_active is not None:
            if admin_user.id == user.id and not request.is_active:
                raise AppException(
                    message="You cannot deactivate your own account.",
                    code="SELF_DEACTIVATION_PROHIBITED",
                    status_code=400,
                )
            if not request.is_active and user.role in (SystemRole.SYSMANAGER.value, SystemRole.ADMIN.value):
                if user.role == SystemRole.SYSMANAGER.value:
                    sysmanager_count = await self._count_active_sysmanagers(db)
                    if sysmanager_count <= 1:
                        raise AppException(
                            message="Cannot deactivate the last active System Manager.",
                            code="LAST_SYSMANAGER_PROTECTION",
                            status_code=400,
                        )
                admin_count = await self._count_active_administrators(db)
                if admin_count <= 1:
                    raise AppException(
                        message="Cannot deactivate the last active Administrator.",
                        code="LAST_ADMIN_PROTECTION",
                        status_code=400,
                    )
            user.is_active = request.is_active

        if request.password:
            user.hashed_password = hash_password(request.password)

        await db.flush()

        audit = AuditEntryModel(
            action="USER_UPDATED_BY_ADMIN",
            entity_type="USER",
            entity_id=str(user.id),
            details={
                "changed_by": str(admin_user.id),
                "target_email": user.email,
                "password_reset": bool(request.password),
            },
        )
        db.add(audit)
        await db.flush()

        return user

    async def delete_user(
        self,
        db: AsyncSession,
        admin_user: UserModel,
        user_id: uuid.UUID,
    ) -> None:
        user = await self.get_user_by_id(db, user_id)

        # Safeguard: cannot delete self
        if admin_user.id == user.id:
            raise AppException(
                message="You cannot delete your own administrative account.",
                code="SELF_DELETION_PROHIBITED",
                status_code=400,
            )

        # Safeguard: cannot delete last sysmanager or last administrator
        if user.role == SystemRole.SYSMANAGER.value:
            sysmanager_count = await self._count_active_sysmanagers(db)
            if sysmanager_count <= 1:
                raise AppException(
                    message="Cannot delete the last remaining active System Manager.",
                    code="LAST_SYSMANAGER_PROTECTION",
                    status_code=400,
                )
        if user.role in (SystemRole.SYSMANAGER.value, SystemRole.ADMIN.value):
            admin_count = await self._count_active_administrators(db)
            if admin_count <= 1:
                raise AppException(
                    message="Cannot delete the last remaining active Administrator.",
                    code="LAST_ADMIN_PROTECTION",
                    status_code=400,
                )

        audit = AuditEntryModel(
            action="USER_DELETED_BY_ADMIN",
            entity_type="USER",
            entity_id=str(user.id),
            details={
                "deleted_by": str(admin_user.id),
                "deleted_email": user.email,
                "role": user.role,
            },
        )
        db.add(audit)

        await db.execute(delete(UserModel).where(UserModel.id == user_id))
        await db.flush()

    async def _count_active_sysmanagers(self, db: AsyncSession) -> int:
        stmt = (
            select(func.count(UserModel.id))
            .where(UserModel.role == SystemRole.SYSMANAGER.value)
            .where(UserModel.is_active == True)  # noqa: E712
        )
        result = await db.execute(stmt)
        return result.scalar() or 0

    async def _count_active_administrators(self, db: AsyncSession) -> int:
        stmt = (
            select(func.count(UserModel.id))
            .where(UserModel.role.in_([SystemRole.SYSMANAGER.value, SystemRole.ADMIN.value]))
            .where(UserModel.is_active == True)  # noqa: E712
        )
        result = await db.execute(stmt)
        return result.scalar() or 0

