from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.db.session import get_session
from src.app.schemas.auth import UserProfile
from src.app.security.jwt import get_current_subject
from src.app.services.auth_service import AuthService

router = APIRouter(tags=["me"])


@router.get("/me", response_model=UserProfile)
async def get_me(
    session: Annotated[AsyncSession, Depends(get_session)],
    user_id: Annotated[str, Depends(get_current_subject)],
) -> UserProfile:
    return await AuthService(session).get_me(user_id)
