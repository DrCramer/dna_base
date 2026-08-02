import asyncio
import getpass
import sys

from sqlalchemy import select

from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models import User, UserRole


async def main() -> None:
    username = sys.argv[1] if len(sys.argv) > 1 else input("Username: ")
    password = sys.argv[2] if len(sys.argv) > 2 else getpass.getpass("Password: ")
    async with SessionLocal() as session:
        result = await session.execute(select(User).where(User.username == username))
        user = result.scalar_one_or_none()
        if user:
            user.password_hash = hash_password(password)
            user.role = UserRole.admin
            user.is_active = True
            print(f"Updated admin user {username}")
        else:
            session.add(User(username=username, password_hash=hash_password(password), role=UserRole.admin))
            print(f"Created admin user {username}")
        await session.commit()


if __name__ == "__main__":
    asyncio.run(main())
