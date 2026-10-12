from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.core.exceptions import (
    AccountLockedException,
    AppException,
    AuthenticationException,
    EntityConflictException,
)
from src.app.core.security import create_access_token, hash_password, verify_password
from src.app.core.settings import get_settings
from src.app.database.models import AuditEntryModel, SystemRole, UserModel
from src.modules.auth.application.dtos import (
    ChangePasswordRequest,
    FinancialOnboardingRequest,
    FinancialOnboardingResponse,
    JobBenchmarkResponse,
    LoginWithOTPRequest,
    LoginWithPasswordRequest,
    OTPResponse,
    ProfileUpdateRequest,
    RegisterRequestOTP,
    RegisterVerifyOTPRequest,
    RequestOTPRequest,
    RiskAssessmentRequest,
    RiskAssessmentResultResponse,
    RiskOnboardingResponse,
    TokenResponse,
    UserLoginRequest,
    UserRegisterRequest,
    UserResponse,
)
from src.modules.communications.application.otp_service import OTPService, normalize_identifier

settings = get_settings()


class AuthService:
    def __init__(self):
        self.otp_service = OTPService()

    async def request_register_otp(
        self, db: AsyncSession, request: RegisterRequestOTP
    ) -> OTPResponse:
        clean_phone, _ = normalize_identifier(request.phone_number)
        clean_email = request.email.strip().lower() if request.email else None

        # Check existing user
        conditions = [UserModel.phone_number == clean_phone]
        if clean_email:
            conditions.append(UserModel.email == clean_email)

        stmt = select(UserModel).where(or_(*conditions))
        res = await db.execute(stmt)
        existing = res.scalar_one_or_none()
        if existing is not None:
            if existing.phone_number == clean_phone:
                raise EntityConflictException(
                    "کاربری با این شماره موبایل قبلاً در سامانه ثبت‌نام کرده است. لطفاً وارد شوید."
                )
            if clean_email and existing.email == clean_email:
                raise EntityConflictException(
                    "کاربری با این ایمیل قبلاً در سامانه ثبت‌نام کرده است. لطفاً وارد شوید."
                )

        data = await self.otp_service.request_otp(
            db=db,
            identifier=clean_phone,
            purpose="register",
        )
        return OTPResponse(
            identifier=str(data["identifier"]),
            channel=str(data["channel"]),
            expires_in=int(data["expires_in"] or 180),
            cooldown_seconds=int(data["cooldown_seconds"] or 120),
            message="کد یکبار مصرف با موفقیت به شماره موبایل شما ارسال شد.",
        )

    async def register_with_otp(
        self, db: AsyncSession, request: RegisterVerifyOTPRequest
    ) -> TokenResponse:
        clean_id, channel = normalize_identifier(request.phone_number)
        clean_phone = clean_id if channel == "sms" else None
        clean_email = request.email.strip().lower() if request.email else (clean_id if channel == "email" else None)
        # Check conflict first before verifying OTP
        conditions = []
        if clean_phone:
            conditions.append(UserModel.phone_number == clean_phone)
        if clean_email:
            conditions.append(UserModel.email == clean_email)

        if conditions:
            stmt_exist = select(UserModel).where(or_(*conditions))
            res_exist = await db.execute(stmt_exist)
            if res_exist.scalar_one_or_none() is not None:
                raise EntityConflictException("کاربری با این مشخصات قبلاً در سامانه ثبت شده است.")

        # Verify OTP
        await self.otp_service.verify_otp(
            db=db,
            identifier=clean_id,
            code=request.code,
            purpose="register",
        )

        stmt_count = select(func.count(UserModel.id))
        user_count = (await db.execute(stmt_count)).scalar() or 0
        role = SystemRole.SYSMANAGER.value if user_count == 0 else SystemRole.USER.value

        hashed = hash_password(request.password) if request.password else None
        now = datetime.now(UTC)

        user = UserModel(
            email=clean_email,
            phone_number=clean_phone,
            hashed_password=hashed,
            full_name=request.full_name,
            role=role,
            is_active=True,
            is_verified=True,
            failed_login_attempts=0,
            lockout_until=None,
            last_login_at=now,
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
            action="USER_REGISTER_OTP",
            entity_type="USER",
            entity_id=str(user.id),
            details={
                "email": user.email,
                "phone_number": user.phone_number,
                "role": user.role,
                "is_first_user": user_count == 0,
            },
        )
        db.add(audit)
        await db.flush()

        token_data = {
            "sub": str(user.id),
            "email": user.email or "",
            "phone_number": user.phone_number or "",
            "role": user.role,
        }
        access_token = create_access_token(token_data)

        return TokenResponse(
            access_token=access_token,
            token_type="bearer",
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            user=UserResponse.model_validate(user),
        )

    async def register(self, db: AsyncSession, request: UserRegisterRequest) -> TokenResponse:
        # Mandatory OTP verification
        if not request.code:
            raise AppException(
                "کد یکبار مصرف جهت اعتبارسنجی ثبت‌نام الزامی است.",
                code="OTP_REQUIRED",
                status_code=400,
            )

        clean_phone = request.phone_number
        if clean_phone:
            clean_phone, _ = normalize_identifier(clean_phone)
        clean_email = request.email.strip().lower() if request.email else None

        if not clean_phone and not clean_email:
            raise AppException("لطفاً شماره موبایل یا ایمیل را وارد نمایید.", code="MISSING_CONTACT", status_code=400)

        return await self.register_with_otp(
            db=db,
            request=RegisterVerifyOTPRequest(
                full_name=request.full_name,
                phone_number=clean_phone or clean_email or "",
                email=clean_email,
                password=request.password,
                code=request.code,
            ),
        )

    async def login_with_password(
        self, db: AsyncSession, request: LoginWithPasswordRequest
    ) -> TokenResponse:
        clean_id, channel = normalize_identifier(request.identifier)

        if channel == "email":
            stmt = select(UserModel).where(UserModel.email == clean_id)
        else:
            stmt = select(UserModel).where(UserModel.phone_number == clean_id)

        res = await db.execute(stmt)
        user = res.scalar_one_or_none()

        if user is None:
            raise AppException(
                "حساب کاربری با این مشخصات یافت نشد. لطفاً ابتدا ثبت‌نام فرمایید.",
                code="USER_NOT_FOUND",
                status_code=404,
            )

        now = datetime.now(UTC)

        # Check account lockout against brute-force
        if user.lockout_until and user.lockout_until > now:
            remaining_mins = max(1, int((user.lockout_until - now).total_seconds() // 60) + 1)
            raise AccountLockedException(
                f"حساب کاربری به دلیل تلاش‌های ناموفق مکرر موقتاً مسدود است. لطفاً پس از {remaining_mins} دقیقه مجدداً تلاش فرمایید.",
                details={"locked_until": user.lockout_until.isoformat(), "retry_after_minutes": remaining_mins},
            )

        if not user.hashed_password:
            raise AuthenticationException(
                "این حساب فاقد رمز عبور ثابت است. لطفاً از طریق ورود با کد یکبار مصرف (OTP) وارد شوید."
            )

        if not verify_password(request.password, user.hashed_password):
            user.failed_login_attempts = (user.failed_login_attempts or 0) + 1
            if user.failed_login_attempts >= settings.MAX_FAILED_ACCESS_ATTEMPTS:
                from datetime import timedelta
                user.lockout_until = now + timedelta(minutes=settings.LOCKOUT_DURATION_MINUTES)
                audit = AuditEntryModel(
                    action="USER_ACCOUNT_LOCKED",
                    entity_type="USER",
                    entity_id=str(user.id),
                    details={"identifier": clean_id, "failed_attempts": user.failed_login_attempts},
                )
                db.add(audit)
                await db.commit()
                raise AccountLockedException(
                    f"رمز عبور وارد شده نادرست است. حساب کاربری شما به دلیل ۵ بار تلاش ناموفق، به مدت {settings.LOCKOUT_DURATION_MINUTES} دقیقه قفل شد."
                )

            await db.commit()
            remaining_attempts = settings.MAX_FAILED_ACCESS_ATTEMPTS - user.failed_login_attempts
            raise AuthenticationException(
                f"رمز عبور وارد شده نادرست است. {remaining_attempts} تلاش دیگر تا قفل شدن حساب باقی مانده است."
            )

        if not user.is_active:
            raise AuthenticationException(
                "حساب کاربری شما غیرفعال شده است. لطفاً با مدیر سیستم تماس بگیرید."
            )

        # Reset failed attempts on success
        user.failed_login_attempts = 0
        user.lockout_until = None
        user.last_login_at = now
        await db.flush()

        audit = AuditEntryModel(
            action="USER_LOGIN_PASSWORD",
            entity_type="USER",
            entity_id=str(user.id),
            details={"identifier": clean_id, "channel": channel},
        )
        db.add(audit)
        await db.flush()

        token_data = {
            "sub": str(user.id),
            "email": user.email or "",
            "phone_number": user.phone_number or "",
            "role": user.role,
        }
        access_token = create_access_token(token_data)

        return TokenResponse(
            access_token=access_token,
            token_type="bearer",
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            user=UserResponse.model_validate(user),
        )

    async def login(self, db: AsyncSession, request: UserLoginRequest) -> TokenResponse:
        """Legacy and universal login method."""
        identifier = request.identifier or request.email
        if not identifier:
            raise AppException("لطفاً ایمیل یا شماره موبایل را وارد نمایید.", code="MISSING_IDENTIFIER", status_code=400)
        return await self.login_with_password(
            db=db,
            request=LoginWithPasswordRequest(identifier=identifier, password=request.password),
        )

    async def request_login_otp(
        self, db: AsyncSession, request: RequestOTPRequest
    ) -> OTPResponse:
        clean_id, channel = normalize_identifier(request.identifier)

        # Ensure user exists for login OTP
        if channel == "email":
            stmt = select(UserModel).where(UserModel.email == clean_id)
        else:
            stmt = select(UserModel).where(UserModel.phone_number == clean_id)

        res = await db.execute(stmt)
        user = res.scalar_one_or_none()

        if user is None:
            raise AppException(
                "حساب کاربری با این مشخصات یافت نشد. لطفاً ابتدا ثبت‌نام فرمایید.",
                code="USER_NOT_FOUND",
                status_code=404,
            )

        if not user.is_active:
            raise AuthenticationException(
                "حساب کاربری شما غیرفعال شده است. لطفاً با مدیر سیستم تماس بگیرید."
            )

        data = await self.otp_service.request_otp(
            db=db,
            identifier=request.identifier,
            purpose="login",
        )
        return OTPResponse(
            identifier=str(data["identifier"]),
            channel=str(data["channel"]),
            expires_in=int(data["expires_in"] or 180),
            cooldown_seconds=int(data["cooldown_seconds"] or 120),
            message="کد یکبار مصرف با موفقیت ارسال شد.",
        )

    async def login_with_otp(
        self, db: AsyncSession, request: LoginWithOTPRequest
    ) -> TokenResponse:
        # Verify OTP code first
        await self.otp_service.verify_otp(
            db=db,
            identifier=request.identifier,
            code=request.code,
            purpose="login",
        )

        clean_id, channel = normalize_identifier(request.identifier)

        if channel == "email":
            stmt = select(UserModel).where(UserModel.email == clean_id)
        else:
            stmt = select(UserModel).where(UserModel.phone_number == clean_id)

        res = await db.execute(stmt)
        user = res.scalar_one_or_none()

        if user is None:
            raise AppException(
                "حساب کاربری با این مشخصات یافت نشد. لطفاً ابتدا ثبت‌نام فرمایید.",
                code="USER_NOT_FOUND",
                status_code=404,
            )

        if not user.is_active:
            raise AuthenticationException("حساب کاربری شما غیرفعال شده است. لطفاً با مدیر سیستم تماس بگیرید.")

        now = datetime.now(UTC)
        user.failed_login_attempts = 0
        user.lockout_until = None
        user.last_login_at = now
        audit = AuditEntryModel(
            action="USER_LOGIN_OTP",
            entity_type="USER",
            entity_id=str(user.id),
            details={"identifier": clean_id, "channel": channel},
        )
        db.add(audit)
        await db.flush()

        token_data = {
            "sub": str(user.id),
            "email": user.email or "",
            "phone_number": user.phone_number or "",
            "role": user.role,
        }
        access_token = create_access_token(token_data)

        return TokenResponse(
            access_token=access_token,
            token_type="bearer",
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            user=UserResponse.model_validate(user),
        )

    async def change_password(
        self, db: AsyncSession, user: UserModel, request: ChangePasswordRequest
    ) -> None:
        if user.hashed_password and not verify_password(request.old_password, user.hashed_password):
            raise AuthenticationException("Current password is incorrect.")

        user.hashed_password = hash_password(request.new_password)
        await db.flush()

        audit = AuditEntryModel(
            action="USER_PASSWORD_CHANGE",
            entity_type="USER",
            entity_id=str(user.id),
            details={"email": user.email, "phone_number": user.phone_number},
        )
        db.add(audit)
        await db.flush()

    async def update_profile(
        self, db: AsyncSession, user: UserModel, request: ProfileUpdateRequest
    ) -> UserResponse:
        # Check email uniqueness if changing email
        if request.email is not None:
            clean_email = request.email.strip().lower() if request.email.strip() else None
            if clean_email and clean_email != user.email:
                stmt = select(UserModel).where(UserModel.email == clean_email, UserModel.id != user.id)
                res = await db.execute(stmt)
                if res.scalar_one_or_none() is not None:
                    raise EntityConflictException("این آدرس ایمیل قبلاً توسط کاربر دیگری ثبت شده است.")
            user.email = clean_email

        # Check phone number uniqueness if changing phone
        if request.phone_number is not None:
            clean_phone = None
            if request.phone_number.strip():
                clean_phone, _ = normalize_identifier(request.phone_number)
            if clean_phone and clean_phone != user.phone_number:
                stmt = select(UserModel).where(UserModel.phone_number == clean_phone, UserModel.id != user.id)
                res = await db.execute(stmt)
                if res.scalar_one_or_none() is not None:
                    raise EntityConflictException("این شماره موبایل قبلاً توسط کاربر دیگری ثبت شده است.")
            user.phone_number = clean_phone

        if request.full_name is not None and request.full_name.strip():
            user.full_name = request.full_name.strip()

        if request.age is not None:
            user.age = request.age

        if request.job is not None:
            user.job = request.job.strip() if request.job.strip() else None

        if request.bio is not None:
            user.bio = request.bio.strip() if request.bio.strip() else None

        if request.portfolio_suggestion is not None:
            user.portfolio_suggestion = request.portfolio_suggestion

        await db.flush()

        audit = AuditEntryModel(
            action="USER_PROFILE_UPDATE",
            entity_type="USER",
            entity_id=str(user.id),
            details={
                "email": user.email,
                "phone_number": user.phone_number,
                "full_name": user.full_name,
                "age": user.age,
                "job": user.job,
            },
        )
        db.add(audit)
        await db.flush()

        return UserResponse.model_validate(user)

    @staticmethod
    def calculate_job_benchmark(job: str, user_salary: Decimal) -> JobBenchmarkResponse:
        job_lower = (job or "").lower().strip()

        benchmarks = {
            "it_software": {
                "title": "فناوری اطلاعات و مهندسی نرم‌افزار",
                "keywords": ["نرم‌افزار", "برنامه‌نویس", "توسعه‌دهنده", "it", "web", "developer", "دولوپر", "پایتون", "react", "فرانت", "بک"],
                "avg_toman": Decimal("65000000"),
                "min_toman": Decimal("35000000"),
                "max_toman": Decimal("110000000"),
            },
            "finance_accounting": {
                "title": "امور مالی، حسابداری و تحلیل سرمایه‌گذاری",
                "keywords": ["مالی", "حسابدار", "تحلیل‌گر", "سرمایه‌گذاری", "بورس", "بانک", "حسابرسی", "اقتصاد"],
                "avg_toman": Decimal("48000000"),
                "min_toman": Decimal("25000000"),
                "max_toman": Decimal("85000000"),
            },
            "healthcare": {
                "title": "پزشکی، داروسازی و سلامت",
                "keywords": ["پزشک", "داروساز", "دندانپزشک", "درمان", "پرستار", "مطب", "کلینیک", "پزشکی"],
                "avg_toman": Decimal("80000000"),
                "min_toman": Decimal("40000000"),
                "max_toman": Decimal("160000000"),
            },
            "engineering": {
                "title": "مهندسی (عمران، برق، مکانیک، صنایع)",
                "keywords": ["مهندس", "عمران", "مکانیک", "صنایع", "معمار", "کارخانه", "تولید", "پروژه"],
                "avg_toman": Decimal("42000000"),
                "min_toman": Decimal("25000000"),
                "max_toman": Decimal("75000000"),
            },
            "marketing_sales": {
                "title": "مارکتینگ، بازاریابی و فروش",
                "keywords": ["مارکتینگ", "فروش", "بازاریاب", "دیجیتال مارکتینگ", "سئو", "ادمین", "تبلیغات", "تجارت الکترونیک"],
                "avg_toman": Decimal("40000000"),
                "min_toman": Decimal("22000000"),
                "max_toman": Decimal("70000000"),
            },
            "business_retail": {
                "title": "کسب‌وکار آزاد، اصناف و فروشگاه",
                "keywords": ["آزاد", "کسب‌وکار", "فروشگاه", "مغازه", "تجارت", "بازرگان", "صاحب کار", "توزیع"],
                "avg_toman": Decimal("55000000"),
                "min_toman": Decimal("30000000"),
                "max_toman": Decimal("120000000"),
            },
            "education_academic": {
                "title": "آموزش، تدریس و پژوهش",
                "keywords": ["معلم", "استاد", "مدرس", "آموزش", "دانشگاه", "پژوهشگر"],
                "avg_toman": Decimal("30000000"),
                "min_toman": Decimal("18000000"),
                "max_toman": Decimal("55000000"),
            },
            "administrative_civil": {
                "title": "اداری، دفتری و خدمات عمومی",
                "keywords": ["کارمند", "اداری", "منشی", "دفتر", "دولتی", "پشتیبانی"],
                "avg_toman": Decimal("26000000"),
                "min_toman": Decimal("16000000"),
                "max_toman": Decimal("40000000"),
            },
        }

        matched_info = {
            "title": "مشاغل تخصصی و آزاد",
            "avg_toman": Decimal("45000000"),
            "min_toman": Decimal("25000000"),
            "max_toman": Decimal("85000000"),
        }

        for _, data in benchmarks.items():
            if any(kw in job_lower for kw in data["keywords"]):
                matched_info = data
                break

        avg_val = matched_info["avg_toman"]
        min_val = matched_info["min_toman"]
        max_val = matched_info["max_toman"]

        if avg_val > Decimal("0"):
            ratio = round(float((user_salary / avg_val) * Decimal("100")), 1)
        else:
            ratio = 100.0

        if ratio > 120.0:
            status_fa = "بالاتر از میانگین صنفی"
            diff_pct = int(ratio - 100)
            suggestion_fa = f"درآمد شما حدود {diff_pct}٪ بالاتر از میانگین این رده شغلی است. پیشنهاد می‌شود حداقل ۴۰ تا ۵۰ درصد از مازاد ماهانه را مستقیماً به سبد سرمایه‌گذاری مولد (سهام، طلا و رمزارز) هدایت فرمایید."
        elif ratio >= 85.0:
            status_fa = "در محدوده استاندارد صنفی"
            suggestion_fa = "حقوق ماهانه شما در بازه نرمال این صنف قرار دارد. رعایت فرمول استاندارد ۵۰٪ نیازهای اساسی، ۳۰٪ خواسته‌ها و ۲۰٪ پس‌انداز منظم، امنیت مالی آینده شما را تامین می‌کند."
        else:
            status_fa = "پایین‌تر از میانگین صنفی"
            diff_pct = int(100 - ratio)
            suggestion_fa = f"حقوق فعلی شما حدود {diff_pct}٪ پایین‌تر از میانگین کشوری برای این تخصص است. ارتقاء مهارت‌های جانبی، پروژه‌های فریلنسری و مذاکره برای ارتقای شغلی توصیه می‌شود."

        return JobBenchmarkResponse(
            job_category=matched_info["title"],
            average_salary_toman=avg_val,
            min_salary_toman=min_val,
            max_salary_toman=max_val,
            user_salary_toman=user_salary,
            comparison_ratio_percent=ratio,
            status_fa=status_fa,
            suggestion_fa=suggestion_fa,
        )

    @staticmethod
    def calculate_risk_assessment(answers: dict[str, int]) -> RiskAssessmentResultResponse:
        total_score = sum(int(v) for v in answers.values())

        if total_score <= 45:
            risk_level = "conservative"
            risk_title = "محافظه‌کار (پوشش تورم و حفظ اصل سرمایه)"
            desc = "اولویت اصلی شما حفظ ارزش دارایی‌ها و پرهیز از افت‌های شدید و استرس‌زای بازار است. خواب راحت شبانه برای شما مهم‌تر از بازدهی‌های هیجانی است."
            allocation = {
                "equities": 15.0,
                "gold": 25.0,
                "gold_commodity": 25.0,
                "fixed_income": 45.0,
                "crypto": 0.0,
                "cash": 15.0,
            }
        elif total_score <= 75:
            risk_level = "moderate"
            risk_title = "متعادل (رشد متوازن با مهار نوسان)"
            desc = "شما خواهان ترکیبی هوشمندانه از رشد ثروت و مهار ریسک هستید و نوسانات طبیعی بازار را به عنوان بخشی از مسیر سرمایه‌گذاری می‌پذیرید."
            allocation = {
                "equities": 35.0,
                "gold": 20.0,
                "gold_commodity": 20.0,
                "fixed_income": 25.0,
                "crypto": 5.0,
                "cash": 15.0,
            }
        else:
            risk_level = "aggressive"
            risk_title = "جسور و ریسک‌پذیر (حداکثر رشد و ثروت‌آفرینی)"
            desc = "شما با افق بلندمدت، افت‌های شدید بازار را فرصت طلایی خرید ارزان‌تر دانسته و به دنبال بازدهی‌های حداکثری و ثروت‌آفرینی شتابان هستید."
            allocation = {
                "equities": 50.0,
                "gold": 15.0,
                "gold_commodity": 15.0,
                "fixed_income": 10.0,
                "crypto": 15.0,
                "cash": 10.0,
            }

        return RiskAssessmentResultResponse(
            total_score=total_score,
            risk_level=risk_level,
            risk_title_fa=risk_title,
            description_fa=desc,
            portfolio_suggestion=allocation,
        )

    async def submit_financial_onboarding(
        self, db: AsyncSession, user: UserModel, request: FinancialOnboardingRequest
    ) -> FinancialOnboardingResponse:
        user.job = request.job.strip()
        user.monthly_income = request.monthly_income
        user.liquid_assets = request.liquid_assets
        user.investment_assets = request.investment_assets
        user.total_liabilities = request.total_liabilities
        user.financial_goals = request.financial_goals
        user.has_completed_financial_onboarding = True

        await db.flush()

        benchmark = self.calculate_job_benchmark(request.job, request.monthly_income)

        audit = AuditEntryModel(
            action="USER_FINANCIAL_ONBOARDING",
            entity_type="USER",
            entity_id=str(user.id),
            details={
                "job": user.job,
                "monthly_income": float(user.monthly_income),
                "liquid_assets": float(user.liquid_assets),
                "investment_assets": float(user.investment_assets),
                "total_liabilities": float(user.total_liabilities),
                "benchmark_category": benchmark.job_category,
            },
        )
        db.add(audit)
        await db.flush()

        return FinancialOnboardingResponse(
            user=UserResponse.model_validate(user),
            benchmark=benchmark,
            message="پرونده مالی و ارزیابی حقوق شغلی شما با موفقیت ثبت شد.",
        )

    async def submit_risk_onboarding(
        self, db: AsyncSession, user: UserModel, request: RiskAssessmentRequest
    ) -> RiskOnboardingResponse:
        result = self.calculate_risk_assessment(request.answers)

        user.risk_score = result.total_score
        user.risk_level = result.risk_level
        user.risk_answers = request.answers
        if request.custom_portfolio_allocation:
            user.portfolio_suggestion = request.custom_portfolio_allocation
            result.portfolio_suggestion = request.custom_portfolio_allocation
        else:
            user.portfolio_suggestion = result.portfolio_suggestion
        user.has_completed_risk_onboarding = True

        await db.flush()

        audit = AuditEntryModel(
            action="USER_RISK_ONBOARDING",
            entity_type="USER",
            entity_id=str(user.id),
            details={
                "risk_score": user.risk_score,
                "risk_level": user.risk_level,
                "portfolio_suggestion": user.portfolio_suggestion,
            },
        )
        db.add(audit)
        await db.flush()

        return RiskOnboardingResponse(
            user=UserResponse.model_validate(user),
            risk_result=result,
            message="سنجش روانشناسی ریسک‌پذیری و سبد پیشنهادی با موفقیت در پروفایل شما ثبت شد.",
        )
