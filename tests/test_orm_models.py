from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.models import (
    FamilyContact,
    MedicalArchive,
    QaRecommendation,
    QaSession,
    User,
    UserPreference,
)
import app.db.models  # noqa: F401


@pytest.fixture
async def session() -> AsyncSession:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as sess:
        yield sess
    await engine.dispose()


@pytest.mark.asyncio
async def test_user_relationships(session: AsyncSession) -> None:
    user = User(phone="13800138001", preferred_lang="zh", status="active")
    user.preferences = UserPreference(preferred_lang="zh")
    user.family_contacts.append(
        FamilyContact(name="女儿", phone="13900000001", relation="daughter")
    )
    session.add(user)
    await session.commit()

    loaded = (
        await session.execute(select(User).where(User.phone == "13800138001"))
    ).scalar_one()
    assert loaded.preferences is not None
    assert loaded.preferences.preferred_lang == "zh"
    assert len(loaded.family_contacts) == 1
    assert loaded.family_contacts[0].name == "女儿"


@pytest.mark.asyncio
async def test_qa_and_archive_graph(session: AsyncSession) -> None:
    user = User(phone="13800138002")
    qa = QaSession(
        user=user,
        lang="zh",
        input_mode="text",
        question_text="今天天气怎么样",
        answer_text="晴，18～26℃",
    )
    qa.recommendation = QaRecommendation(
        user=user,
        title="就医建议",
        body="建议社区医院就诊",
        risk_level="low",
        disclaimer="不能替代医生诊断",
    )
    archive = MedicalArchive(
        user=user,
        diagnosis="支气管炎倾向",
        medicine="止咳药",
        visit_date=date(2026, 7, 27),
        source="album",
    )
    session.add_all([user, qa, archive])
    await session.commit()

    loaded_qa = (await session.execute(select(QaSession))).scalar_one()
    assert loaded_qa.recommendation is not None
    assert loaded_qa.recommendation.risk_level == "low"
    assert loaded_qa.user.phone == "13800138002"

    loaded_arc = (await session.execute(select(MedicalArchive))).scalar_one()
    assert loaded_arc.user_id == loaded_qa.user_id
