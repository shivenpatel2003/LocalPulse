"""Instagram data normalizer transformers.

Provides functions to transform Instagram-specific data from Apify
to the unified CollectedContent schema.
"""

from datetime import datetime

from src.collectors.normalization.schema import CollectedContent, ContentType


def transform_instagram_post(raw: dict) -> CollectedContent:
    """Transform Instagram post data to unified CollectedContent schema.

    Args:
        raw: Raw post dictionary from Apify

    Returns:
        Normalized CollectedContent instance
    """
    # Parse timestamp
    created_at = None
    if raw.get("timestamp"):
        try:
            created_at = datetime.fromtimestamp(raw["timestamp"])
        except (ValueError, TypeError, OSError):
            pass

    # Extract media URLs
    media_urls = []
    if raw.get("displayUrl"):
        if isinstance(raw["displayUrl"], list):
            media_urls.extend(raw["displayUrl"])
        else:
            media_urls.append(raw["displayUrl"])

    # Also check for video URL
    if raw.get("videoUrl"):
        media_urls.append(raw["videoUrl"])

    return CollectedContent(
        id=str(raw.get("id", "")),
        source="instagram",
        source_url=raw.get("url"),
        content_type=ContentType.POST,
        text=raw.get("caption"),
        media_urls=media_urls,
        likes=raw.get("likesCount"),
        comments_count=raw.get("commentsCount"),
        views=raw.get("videoViewCount"),
        author_id=str(raw.get("ownerId", "")) if raw.get("ownerId") else None,
        author_name=raw.get("ownerFullName"),
        author_handle=raw.get("ownerUsername"),
        created_at=created_at,
        confidence=0.90,  # Apify is reliable but third-party
        raw_data=raw,
    )


def transform_instagram_profile(raw: dict) -> CollectedContent:
    """Transform Instagram profile data to unified CollectedContent schema.

    Args:
        raw: Raw profile dictionary from Apify

    Returns:
        Normalized CollectedContent instance
    """
    # Profile picture as media
    media_urls = []
    if raw.get("profilePicUrl") or raw.get("profilePicUrlHD"):
        media_urls.append(raw.get("profilePicUrlHD") or raw.get("profilePicUrl"))

    # Combine bio and metadata into text
    text_parts = []
    if raw.get("biography"):
        text_parts.append(raw["biography"])

    # Include follower/following counts in profile text for searchability
    if raw.get("followersCount") is not None:
        text_parts.append(f"Followers: {raw['followersCount']}")
    if raw.get("followingCount") is not None:
        text_parts.append(f"Following: {raw['followingCount']}")
    if raw.get("postsCount") is not None:
        text_parts.append(f"Posts: {raw['postsCount']}")

    return CollectedContent(
        id=str(raw.get("id", "")),
        source="instagram",
        source_url=f"https://instagram.com/{raw.get('username')}"
        if raw.get("username")
        else None,
        content_type=ContentType.PROFILE,
        title=raw.get("fullName"),
        text="\n".join(text_parts) if text_parts else None,
        media_urls=media_urls,
        author_id=str(raw.get("id", "")) if raw.get("id") else None,
        author_name=raw.get("fullName"),
        author_handle=raw.get("username"),
        created_at=None,  # Profile creation date not typically available
        confidence=0.90,
        raw_data=raw,
    )
