import io
import pytest
from httpx import AsyncClient, ASGITransport
from src.main import app


@pytest.mark.asyncio
async def test_secure_file_upload_validation():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Unauthenticated request rejected
        unauth_res = await client.post(
            "/api/v1/uploads",
            files={"file": ("test.png", b"fake image content", "image/png")},
        )
        assert unauth_res.status_code == 401

        # 2. Login as regular user or admin
        login_res = await client.post(
            "/api/v1/auth/login",
            json={"email": "sysmanager@personal-fc.local", "password": "AdminPassword123!"},
        )
        assert login_res.status_code == 200
        token = login_res.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # 3. Disallowed dangerous executable / script files rejected
        dangerous_files = [
            ("malicious.exe", b"MZ...", "application/x-msdownload"),
            ("exploit.php", b"<?php echo 1; ?>", "application/x-php"),
            ("payload.sh", b"#!/bin/sh", "text/x-shellscript"),
            ("attack.html", b"<script>alert(1)</script>", "text/html"),
            ("graphic.svg", b"<svg onload=alert(1)></svg>", "image/svg+xml"),
        ]

        for filename, content, content_type in dangerous_files:
            bad_res = await client.post(
                "/api/v1/uploads",
                headers=headers,
                files={"file": (filename, content, content_type)},
            )
            assert bad_res.status_code == 400
            assert bad_res.json()["code"] in ("DANGEROUS_FILE_EXTENSION", "DISALLOWED_FILE_EXTENSION")

        # 4. Valid file upload succeeds and returns sanitized GUID filename
        valid_res = await client.post(
            "/api/v1/uploads",
            headers=headers,
            files={"file": ("receipt_screenshot.png", b"\x89PNG\r\n\x1a\nfakeimagebytes", "image/png")},
        )
        assert valid_res.status_code == 201
        data = valid_res.json()
        assert data["original_filename"] == "receipt_screenshot.png"
        assert data["stored_filename"].endswith(".png")
        assert data["stored_filename"] != "receipt_screenshot.png"
        assert data["size_bytes"] > 0
        assert data["url"].startswith("/uploads/")
