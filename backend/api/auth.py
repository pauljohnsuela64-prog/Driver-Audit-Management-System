from fastapi import APIRouter, Request, Response

from backend.api.dependencies import Auth, Identity
from backend.schemas.auth import LoginRequest, TokenResponse, UserResponse

router = APIRouter(prefix="/auth", tags=["authentication"])


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, request: Request, auth: Auth):
    request.app.state.login_limiter.check(request.client.host if request.client else "unknown")
    token, expires = auth.login(payload.username, payload.password.get_secret_value())
    return TokenResponse(access_token=token, expires_at=expires)


@router.post("/logout", status_code=204)
def logout(identity: Identity, auth: Auth):
    auth.logout(identity[0])
    return Response(status_code=204)


@router.get("/me", response_model=UserResponse)
def me(identity: Identity):
    return UserResponse.model_validate(identity[1])
