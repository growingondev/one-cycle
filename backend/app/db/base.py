from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """모든 SQLAlchemy ORM 모델이 상속하는 기본 클래스."""

    pass