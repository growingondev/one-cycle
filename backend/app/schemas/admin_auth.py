from pydantic import BaseModel, Field


class AdminLoginRequest(BaseModel):
    admin_id: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=200)


class AdminLoginResponse(BaseModel):
    authenticated: bool
    admin_id: str
    role: str


class AdminMeResponse(BaseModel):
    authenticated: bool
    admin_id: str
    role: str


class AdminLogoutResponse(BaseModel):
    success: bool
