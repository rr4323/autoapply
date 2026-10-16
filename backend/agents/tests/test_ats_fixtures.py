"""Local ATS fixture forms are reachable (docs/BACKEND_BUILD_STEPS.md
Step 39). Spins the exact same nginx-serving-a-static-directory setup
docker-compose.yml's ats-fixtures service defines, proving reachability
programmatically rather than only by hand with curl — the same rigor
every other piece of infra in this project gets. Needs Docker, run via
`make test-integration-py`.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from testcontainers.community.nginx import NginxContainer

pytestmark = pytest.mark.integration

FIXTURES_DIR = Path(__file__).resolve().parent.parent.parent.parent / "ats-fixtures"


@pytest.fixture
def ats_fixtures_url():
    with NginxContainer("nginx:alpine").with_volume_mapping(
        str(FIXTURES_DIR), "/usr/share/nginx/html", mode="ro"
    ) as container:
        host_ip = container.get_container_host_ip()
        port = container.get_exposed_port(80)
        yield f"http://{host_ip}:{port}"


def test_clean_fixture_is_reachable(ats_fixtures_url):
    response = httpx.get(f"{ats_fixtures_url}/clean/")

    assert response.status_code == 200
    assert 'id="application_form"' in response.text
    assert "g-recaptcha" not in response.text  # the clean variant has no bot-check signals


def test_captcha_fixture_is_reachable(ats_fixtures_url):
    response = httpx.get(f"{ats_fixtures_url}/captcha/")

    assert response.status_code == 200
    assert 'id="application_form"' in response.text
    assert "g-recaptcha" in response.text
    assert "data-sitekey" in response.text


def test_both_fixtures_expose_the_same_fillable_fields():
    # The Filler Agent (Step 41) needs the same fields present in both
    # variants — only the bot-check signals should differ.
    clean_html = (FIXTURES_DIR / "clean" / "index.html").read_text()
    captcha_html = (FIXTURES_DIR / "captcha" / "index.html").read_text()

    for field_id in ["first_name", "last_name", "email", "phone", "resume", "cover_letter"]:
        assert f'id="{field_id}"' in clean_html
        assert f'id="{field_id}"' in captcha_html
