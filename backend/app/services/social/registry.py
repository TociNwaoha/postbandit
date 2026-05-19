from app.models.connected_account import SocialPlatform
from app.services.social.base import SocialProviderAdapter
from app.services.social.facebook import FacebookAdapter
from app.services.social.instagram import InstagramAdapter
from app.services.social.linkedin import LinkedInAdapter
from app.services.social.threads import ThreadsAdapter
from app.services.social.tiktok import TikTokAdapter
from app.services.social.x import XAdapter
from app.services.social.youtube import YouTubeAdapter

_ADAPTERS: dict[SocialPlatform, SocialProviderAdapter] = {
    SocialPlatform.instagram: InstagramAdapter(),
    SocialPlatform.threads: ThreadsAdapter(),
    SocialPlatform.tiktok: TikTokAdapter(),
    SocialPlatform.facebook: FacebookAdapter(),
    SocialPlatform.youtube: YouTubeAdapter(),
    SocialPlatform.x: XAdapter(),
    SocialPlatform.linkedin: LinkedInAdapter(),
}


def get_adapter(platform: SocialPlatform | str) -> SocialProviderAdapter:
    if isinstance(platform, str):
        platform = SocialPlatform(platform)
    return _ADAPTERS[platform]


def all_adapters() -> list[SocialProviderAdapter]:
    return list(_ADAPTERS.values())
