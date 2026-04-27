import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import AsyncClient, ASGITransport
from fastapi import FastAPI
from kiro.dashboard.routes_auth import router
from kiro.db.engine import get_session

app = FastAPI()
app.include_router(router)
app.dependency_overrides[get_session] = lambda: AsyncMock()

VALID_PAYLOAD = {
    "sub": "google-uid-123",
    "email": "user@example.com",
    "hd": "example.com",
}


@pytest.mark.asyncio
async def test_google_login_creates_new_user():
    mock_session = AsyncMock()
    app.dependency_overrides[get_session] = lambda: mock_session

    with patch("kiro.dashboard.routes_auth.GOOGLE_CLIENT_ID", "test-client-id"), \
         patch("kiro.dashboard.routes_auth.GOOGLE_ALLOWED_DOMAIN", ""), \
         patch("kiro.dashboard.routes_auth.id_token.verify_oauth2_token", return_value=VALID_PAYLOAD), \
         patch("kiro.dashboard.routes_auth.get_user_by_google_id", new_callable=AsyncMock, return_value=None), \
         patch("kiro.dashboard.routes_auth.create_user", new_callable=AsyncMock) as mock_create, \
         patch("kiro.dashboard.routes_auth.create_access_token", return_value="access-tok"), \
         patch("kiro.dashboard.routes_auth.create_refresh_token", return_value="refresh-tok"):
        mock_create.return_value = MagicMock(id=1, role="user", username="user@example.com")
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/auth/google", json={"credential": "fake-token"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["access_token"] == "access-tok"
    assert data["refresh_token"] == "refresh-tok"
    mock_create.assert_called_once()


@pytest.mark.asyncio
async def test_google_login_existing_user():
    mock_session = AsyncMock()
    app.dependency_overrides[get_session] = lambda: mock_session
    existing_user = MagicMock(id=5, role="admin", username="user@example.com", is_active=True)

    with patch("kiro.dashboard.routes_auth.GOOGLE_CLIENT_ID", "test-client-id"), \
         patch("kiro.dashboard.routes_auth.GOOGLE_ALLOWED_DOMAIN", ""), \
         patch("kiro.dashboard.routes_auth.id_token.verify_oauth2_token", return_value=VALID_PAYLOAD), \
         patch("kiro.dashboard.routes_auth.get_user_by_google_id", new_callable=AsyncMock, return_value=existing_user), \
         patch("kiro.dashboard.routes_auth.create_access_token", return_value="access-tok"), \
         patch("kiro.dashboard.routes_auth.create_refresh_token", return_value="refresh-tok"):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/auth/google", json={"credential": "fake-token"})
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_google_login_domain_blocked():
    mock_session = AsyncMock()
    app.dependency_overrides[get_session] = lambda: mock_session
    payload_wrong_domain = {**VALID_PAYLOAD, "hd": "other.com"}

    with patch("kiro.dashboard.routes_auth.GOOGLE_CLIENT_ID", "test-client-id"), \
         patch("kiro.dashboard.routes_auth.GOOGLE_ALLOWED_DOMAIN", "example.com"), \
         patch("kiro.dashboard.routes_auth.id_token.verify_oauth2_token", return_value=payload_wrong_domain):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/auth/google", json={"credential": "fake-token"})
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_google_login_inactive_user():
    mock_session = AsyncMock()
    app.dependency_overrides[get_session] = lambda: mock_session
    inactive_user = MagicMock(id=2, role="user", username="user@example.com", is_active=False)

    with patch("kiro.dashboard.routes_auth.GOOGLE_CLIENT_ID", "test-client-id"), \
         patch("kiro.dashboard.routes_auth.GOOGLE_ALLOWED_DOMAIN", ""), \
         patch("kiro.dashboard.routes_auth.id_token.verify_oauth2_token", return_value=VALID_PAYLOAD), \
         patch("kiro.dashboard.routes_auth.get_user_by_google_id", new_callable=AsyncMock, return_value=inactive_user):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/auth/google", json={"credential": "fake-token"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_google_login_not_configured():
    with patch("kiro.dashboard.routes_auth.GOOGLE_CLIENT_ID", ""):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/auth/google", json={"credential": "fake-token"})
    assert resp.status_code == 500


@pytest.mark.asyncio
async def test_google_login_invalid_token():
    from google.auth.exceptions import GoogleAuthError
    with patch("kiro.dashboard.routes_auth.GOOGLE_CLIENT_ID", "test-client-id"), \
         patch("kiro.dashboard.routes_auth.GOOGLE_ALLOWED_DOMAIN", ""), \
         patch("kiro.dashboard.routes_auth.id_token.verify_oauth2_token", side_effect=GoogleAuthError("bad")):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/auth/google", json={"credential": "fake-token"})
    assert resp.status_code == 401
