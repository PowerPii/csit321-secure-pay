"""Public customer APIs refuse anything but JSON on unsafe requests (security self-test,
Nov 2026): a cross-site HTML form cannot reach even the views that never read a body."""
import pytest

SESSION = "cs_" + "A" * 24


@pytest.mark.django_db
@pytest.mark.parametrize("path", [
    f"/checkout/{SESSION}/submit",
    f"/checkout/{SESSION}/verify/resend",
    "/customer/sign-out",
    "/customer/sign-out-everywhere",
    "/guest/status/sign-out",
])
@pytest.mark.parametrize("content_type", [
    "application/x-www-form-urlencoded", "multipart/form-data; boundary=x", "text/plain",
])
def test_form_and_text_posts_are_refused_before_the_view_runs(client, path, content_type):
    response = client.post(path, data="a=1", content_type=content_type)
    assert response.status_code == 415
    assert response.json()["error"]["code"] == "unsupported_media_type"


@pytest.mark.django_db
def test_json_posts_still_reach_the_view(client):
    # An unknown session is a 404 from the view itself, not a 415.
    response = client.post(f"/checkout/{SESSION}/submit", data="{}",
                           content_type="application/json")
    assert response.status_code == 404
