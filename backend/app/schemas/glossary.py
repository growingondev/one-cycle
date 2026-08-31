from pydantic import BaseModel, ConfigDict, Field


class GlossaryPublicItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    term: str
    definition: str
    category: str


class GlossaryAdminItem(GlossaryPublicItem):
    is_active: bool


class GlossaryCreateRequest(BaseModel):
    term: str = Field(min_length=1, max_length=200)
    definition: str = Field(min_length=1)
    category: str = Field(min_length=1, max_length=100)
    is_active: bool = True


class GlossaryUpdateRequest(BaseModel):
    term: str = Field(min_length=1, max_length=200)
    definition: str = Field(min_length=1)
    category: str = Field(min_length=1, max_length=100)
    is_active: bool


class GlossaryStatusUpdateRequest(BaseModel):
    is_active: bool


class GlossaryAdminListResponse(BaseModel):
    items: list[GlossaryAdminItem]
    page: int
    size: int
    total: int
    total_pages: int
