"""초기 admin 계정을 생성하는 스크립트.

사용법:
    python -m scripts.create_admin
"""

import asyncio
import sys

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.models.user import User
from app.services.auth_service import hash_password


async def create_admin() -> None:
    engine = create_async_engine(settings.database_url)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as session:
        result = await session.execute(
            select(User).where(User.username == settings.initial_admin_username)
        )
        existing = result.scalar_one_or_none()

        if existing:
            print(f"Admin user '{settings.initial_admin_username}' already exists. Skipping.")
            await engine.dispose()
            return

        admin = User(
            username=settings.initial_admin_username,
            email=settings.initial_admin_email,
            password_hash=hash_password(settings.initial_admin_password),
            display_name="Administrator",
            role="admin",
            is_active=True,
        )
        session.add(admin)
        await session.commit()
        print(f"Admin user '{settings.initial_admin_username}' created successfully.")

    await engine.dispose()


def main() -> None:
    asyncio.run(create_admin())


if __name__ == "__main__":
    main()
