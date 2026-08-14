"""Parsing @mentions out of comment bodies.

Mentions are matched against actual project members, so a stray email address in a
comment does not become a notification and a typo'd handle fails visibly rather than
silently notifying nobody.
"""

import re

from app.domain.entities import Member

#: @ followed by an email local-part or a full address, e.g. @designer or @d@acme.com
MENTION_PATTERN = re.compile(r"@([A-Za-z0-9._%+-]+(?:@[A-Za-z0-9.-]+\.[A-Za-z]{2,})?)")


def extract_handles(body: str) -> list[str]:
    """Every @handle in the text, lower-cased, in order, without duplicates."""
    seen: list[str] = []
    for match in MENTION_PATTERN.findall(body or ""):
        handle = match.lower()
        if handle not in seen:
            seen.append(handle)
    return seen


def resolve_mentions(body: str, members: list[Member]) -> list[str]:
    """User ids of members named in ``body``.

    A member matches on their full email or on its local part, which is what people
    actually type. Unmatched handles are ignored — they are just text.
    """
    handles = set(extract_handles(body))
    if not handles:
        return []

    resolved: list[str] = []
    for member in members:
        email = member.email.lower()
        local_part = email.split("@")[0]
        if (email in handles or local_part in handles) and member.user_id not in resolved:
            resolved.append(member.user_id)
    return resolved
