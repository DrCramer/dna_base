from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import current_user, db_session
from app.core.config import get_settings
from app.core.security import create_access_token
from app.schemas import LoginRequest, LoginResponse, UserOut
from app.services.auth import authenticate


router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
async def login(payload: LoginRequest, response: Response, session: AsyncSession = Depends(db_session)):
    user = await authenticate(session, payload.username, payload.password)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Неверный логин или пароль")
    settings = get_settings()
    token = create_access_token(str(user.id), {"role": user.role.value})
    response.set_cookie(
        settings.cookie_name,
        token,
        httponly=True,
        secure=False,
        samesite="lax",
        max_age=settings.access_token_expire_minutes * 60,
        path="/",
    )
    return LoginResponse(user=UserOut.model_validate(user))


@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie(get_settings().cookie_name, path="/")
    return {"ok": True}


@router.get("/me", response_model=UserOut)
async def me(user=Depends(current_user)):
    return user
