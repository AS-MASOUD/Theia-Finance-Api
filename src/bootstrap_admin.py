import asyncio
import os
import sys

from sqlalchemy import select

from src.app.core.security import hash_password
from src.app.database.models import SystemRole, UserModel
from src.app.database.session import AsyncSessionFactory


async def bootstrap_admin() -> None:
    admin_email = os.getenv("BOOTSTRAP_ADMIN_EMAIL", "admin@thiea-finance.ir")
    admin_password = os.getenv("BOOTSTRAP_ADMIN_PASSWORD")

    if not admin_password:
        print("[Bootstrap] No BOOTSTRAP_ADMIN_PASSWORD provided; skipping admin bootstrap.")
        return

    async with AsyncSessionFactory() as db:
        query = select(UserModel).where(UserModel.email == admin_email)
        result = await db.execute(query)
        existing_user = result.scalar_one_or_none()

        hashed_pwd = hash_password(admin_password)

        if existing_user:
            print(f"[Bootstrap] User '{admin_email}' already exists. Updating credentials and active status.")
            existing_user.hashed_password = hashed_pwd
            existing_user.role = SystemRole.SYSMANAGER.value
            existing_user.is_active = True
            existing_user.is_verified = True
            existing_user.failed_login_attempts = 0
            existing_user.lockout_until = None
        else:
            print(f"[Bootstrap] Creating new administrator '{admin_email}'...")
            new_admin = UserModel(
                email=admin_email,
                phone_number=os.getenv("BOOTSTRAP_ADMIN_PHONE", "09121111111"),
                hashed_password=hashed_pwd,
                full_name="سیستم ادمین (System Administrator)",
                role=SystemRole.SYSMANAGER.value,
                is_active=True,
                is_verified=True,
                failed_login_attempts=0,
                lockout_until=None,
            )
            db.add(new_admin)

        await db.commit()
        print(f"[Bootstrap] Administrator '{admin_email}' bootstrapped successfully.")


if __name__ == "__main__":
    try:
        asyncio.run(bootstrap_admin())
    except Exception as e:
        print(f"[Bootstrap ERROR] Failed to bootstrap administrator: {e}", file=sys.stderr)
