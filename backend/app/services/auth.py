from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password, verify_password
from app.models import User, UserRole


async def authenticate(session: AsyncSession, username: str, password: str) -> User | None:
    result = await session.execute(select(User).where(User.username == username, User.is_active.is_(True)))
    user = result.scalar_one_or_none()
    if not user or not verify_password(password, user.password_hash):
        return None
    return user


async def ensure_dev_users(session: AsyncSession) -> None:
    result = await session.execute(select(User).where(User.username == "admin"))
    if result.scalar_one_or_none():
        return
    session.add_all(
        [
            User(username="admin", password_hash=hash_password("admin123"), role=UserRole.admin),
            User(username="user", password_hash=hash_password("user123"), role=UserRole.user),
            User(username="viewer", password_hash=hash_password("viewer123"), role=UserRole.viewer),
        ]
    )
    await session.commit()
