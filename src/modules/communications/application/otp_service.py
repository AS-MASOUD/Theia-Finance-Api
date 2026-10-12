import random
import re
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.core.exceptions import AppException, AuthenticationException
from src.app.core.security import hash_password, verify_password
from src.app.core.settings import get_settings
from src.app.database.models import OTPRequestModel
from src.app.observability.logging import get_logger
from src.modules.communications.infrastructure.bale.factory import get_bale_provider
from src.modules.communications.infrastructure.email.factory import get_email_provider
from src.modules.communications.infrastructure.sms.factory import get_sms_provider

logger = get_logger("communications.otp")
settings = get_settings()

IRAN_PHONE_REGEX = re.compile(r"^09\d{9}$")
EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")


def normalize_identifier(identifier: str) -> tuple[str, str]:
    """Parse identifier and return (normalized_identifier, channel).

    channel is 'email' or 'sms'.
    """
    cleaned = identifier.strip()
    if "@" in cleaned:
        email = cleaned.lower()
        if not EMAIL_REGEX.match(email):
            raise AppException("قالب آدرس ایمیل نامعتبر است.", code="INVALID_EMAIL", status_code=400)
        return email, "email"

    # Normalize Iranian mobile number
    digits = re.sub(r"[^\d]", "", cleaned)
    if digits.startswith("0098"):
        digits = "0" + digits[4:]
    elif digits.startswith("98"):
        digits = "0" + digits[2:]
    elif len(digits) == 10 and digits.startswith("9"):
        digits = "0" + digits

    if not IRAN_PHONE_REGEX.match(digits):
        raise AppException(
            "شماره موبایل وارد شده نامعتبر است. نمونه صحیح: 09123456789",
            code="INVALID_PHONE",
            status_code=400,
        )

    return digits, "sms"


class OTPService:
    def __init__(self):
        self.bale_provider = get_bale_provider()
        self.sms_provider = get_sms_provider()
        self.email_provider = get_email_provider()

    async def request_otp(
        self,
        db: AsyncSession,
        identifier: str,
        purpose: str = "login",
        preferred_channel: str | None = None,
    ) -> dict[str, str | int | None]:
        clean_id, channel = normalize_identifier(identifier)
        now = datetime.now(UTC)

        if not settings.ENABLE_OTP:
            raise AppException(
                "سرویس کد یکبار مصرف (OTP) موقتاً غیرفعال است. لطفاً با استفاده از رمز عبور وارد شوید یا ثبت‌نام فرمایید.",
                code="OTP_DISABLED",
                status_code=400,
            )

        # Check rate-limit / cooldown
        stmt_last = (
            select(OTPRequestModel)
            .where(
                OTPRequestModel.identifier == clean_id,
                OTPRequestModel.purpose == purpose,
            )
            .order_by(desc(OTPRequestModel.created_at))
            .limit(1)
        )
        res_last = await db.execute(stmt_last)
        last_otp = res_last.scalar_one_or_none()

        if last_otp and not last_otp.is_used:
            elapsed = (now - last_otp.created_at).total_seconds()
            if elapsed < settings.OTP_COOLDOWN_SECONDS:
                wait_seconds = int(settings.OTP_COOLDOWN_SECONDS - elapsed)
                raise AppException(
                    f"لطفاً {wait_seconds} ثانیه تا درخواست مجدد کد شکیبا باشید.",
                    code="OTP_COOLDOWN",
                    status_code=429,
                    details={"retry_after_seconds": wait_seconds},
                )

        # Generate cryptographically secure OTP code
        min_val = 10 ** (settings.OTP_DIGITS - 1)
        max_val = (10**settings.OTP_DIGITS) - 1
        code_int = random.SystemRandom().randint(min_val, max_val)
        code_str = str(code_int)
        code_hash = hash_password(code_str)

        expires_at = now + timedelta(seconds=settings.OTP_EXPIRE_SECONDS)

        # Dispatch via Bale Messenger, SMS, or Email
        actual_channel = channel
        if channel == "sms":
            strategy = settings.OTP_DELIVERY_STRATEGY.lower().strip()
            pref = (preferred_channel or "").lower().strip()

            should_attempt_bale = pref == "bale" or (
                pref not in ("sms", "email") and strategy in ("bale_first", "bale_only")
            )

            if should_attempt_bale:
                bale_req_id = uuid.uuid4().hex
                bale_result = await self.bale_provider.send_otp(clean_id, code_str, request_id=bale_req_id)
                if bale_result.success:
                    actual_channel = "bale"
                    logger.info(
                        "[OTP-SERVICE] Dispatched OTP via Bale Safir to %s (message_id=%s)",
                        clean_id,
                        bale_result.message_id,
                    )
                elif strategy == "bale_only" or pref == "bale_only":
                    if bale_result.is_not_bale_user:
                        raise AppException(
                            "این شماره موبایل در پیام‌رسان بله ثبت‌نام نکرده است.",
                            code="BALE_NOT_USER",
                            status_code=400,
                        )
                    raise AppException(
                        f"خطا در ارسال پیام بله: {bale_result.error_description}",
                        code="BALE_SEND_FAILED",
                        status_code=502,
                    )
                else:
                    # Strategy is bale_first: Fallback to Iranian SMS gateway
                    logger.warning(
                        "[OTP-SERVICE] Bale delivery not available for %s (code=%s: %s). Falling back to SMS gateway...",
                        clean_id,
                        bale_result.error_code,
                        bale_result.error_description,
                    )
                    await self.sms_provider.send_otp_pattern(clean_id, code_str)
                    actual_channel = "sms"
            else:
                # Direct SMS delivery
                await self.sms_provider.send_otp_pattern(clean_id, code_str)
                actual_channel = "sms"
        else:
            actual_channel = "email"
            subject = "کد تایید سامانه فرماندهی مالی"
            html_body = f"""
            <div dir="rtl" style="font-family: Tahoma, sans-serif; padding: 20px; color: #1e293b;">
                <h2 style="color: #4f46e5;">سامانه مدیریت مالی و سرمایه‌گذاری شخصی</h2>
                <p>کد یکبار مصرف ورود شما به سامانه:</p>
                <div style="font-size: 28px; font-weight: bold; letter-spacing: 5px; color: #0284c7; padding: 10px 0;">
                    {code_str}
                </div>
                <p style="font-size: 12px; color: #64748b;">این کد تا {settings.OTP_EXPIRE_SECONDS // 60} دقیقه معتبر است.</p>
            </div>
            """
            await self.email_provider.send_email(clean_id, subject, html_body)

        otp_record = OTPRequestModel(
            identifier=clean_id,
            channel=actual_channel,
            otp_code_hash=code_hash,
            purpose=purpose,
            attempts=0,
            is_used=False,
            expires_at=expires_at,
            created_at=now,
        )
        db.add(otp_record)
        await db.flush()

        logger.info(
            "[OTP-SERVICE] Generated OTP code for %s [%s] (expires in %ds, code redacted)",
            clean_id,
            actual_channel,
            settings.OTP_EXPIRE_SECONDS,
        )

        return {
            "identifier": clean_id,
            "channel": actual_channel,
            "expires_in": settings.OTP_EXPIRE_SECONDS,
            "cooldown_seconds": settings.OTP_COOLDOWN_SECONDS,
        }

    async def verify_otp(
        self,
        db: AsyncSession,
        identifier: str,
        code: str,
        purpose: str = "login",
    ) -> bool:
        clean_id, channel = normalize_identifier(identifier)
        now = datetime.now(UTC)

        stmt = (
            select(OTPRequestModel)
            .where(
                OTPRequestModel.identifier == clean_id,
                OTPRequestModel.purpose == purpose,
                OTPRequestModel.is_used == False,  # noqa: E712
                OTPRequestModel.expires_at > now,
            )
            .order_by(desc(OTPRequestModel.created_at))
            .limit(1)
        )
        result = await db.execute(stmt)
        record = result.scalar_one_or_none()

        if record is None:
            raise AuthenticationException(
                "کد یکبار مصرف منقضی شده است یا درخواستی یافت نشد. لطفاً کد جدید دریافت نمایید."
            )

        if record.attempts >= 5:
            record.is_used = True
            await db.flush()
            raise AuthenticationException(
                "تعداد دفعات تلاش ناموفق بیش از حد مجاز است. لطفاً مجدداً کد درخواست دهید."
            )

        if not verify_password(code.strip(), record.otp_code_hash):
            record.attempts += 1
            await db.flush()
            remaining = 5 - record.attempts
            raise AuthenticationException(
                f"کد وارد شده صحیح نمی‌باشد. {remaining} تلاش دیگر باقی مانده است."
            )

        record.is_used = True
        await db.flush()
        return True
