"""Sets Bella's WhatsApp profile picture and display name.

Run once after deploy, from inside the Bella container (`python -m
bella.scripts.set_presentation`) — see docs/deploy.md.

Evolution GO fetches the profile picture itself via a plain HTTP GET (its
/user/profilePicture call takes a URL, not image bytes — see
pkg/user/service/user_service.go: SetProfilePicture does `http.Get(data.
Image)`, no auth header support). That GET must reach Bella's own
/assets/whatsapp-profile-picture.jpg route (bella/app.py), so
BELLA_INTERNAL_URL has to already be correct and reachable from the
Evolution GO container when this runs — i.e. after the network wiring in
docs/deploy.md, not before.
"""

from bella.config import Settings
from bella.scripts._client import post


def main() -> None:
    settings = Settings.from_env()
    picture_url = f"{settings.bella_internal_url.rstrip('/')}/assets/whatsapp-profile-picture.jpg"

    print(f"Setting profile picture from: {picture_url}")
    post(settings, "/user/profilePicture", {"image": picture_url})

    print(f"Setting display name: {settings.bella_display_name}")
    post(settings, "/user/profileName", {"name": settings.bella_display_name})

    print("Done.")


if __name__ == "__main__":
    main()
