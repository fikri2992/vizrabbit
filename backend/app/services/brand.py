"""The brand profile's life: proposed by extraction, confirmed by the Owner.

The two halves are deliberately hard to confuse. ``propose`` can be called by
anything — a PDF reading, a form, a script — and changes nothing the pipeline
sees. ``confirm`` is Owner-only and is the single moment a palette starts
producing defects (domain-model.md decision 16).
"""

from app.domain.brand import PALETTE_RULE
from app.domain.color import BadHex, normalise_hex
from app.domain.entities import BrandProfile, PaletteEntry, Project, User, now
from app.domain.permissions import Permission, require
from app.infra import repository as repo
from app.infra.store import Store


#: One profile per project, so its id is derivable rather than looked up.
def profile_id(project_id: str) -> str:
    return f"brand-{project_id}"


async def load(store: Store, project_id: str) -> BrandProfile | None:
    return await repo.load(store, BrandProfile, profile_id(project_id))


async def load_active(store: Store, project_id: str) -> BrandProfile | None:
    """What the pipeline asks for: a profile only if it is confirmed and non-empty."""
    profile = await load(store, project_id)
    return profile if profile and profile.is_active else None


async def get_or_create(store: Store, project_id: str) -> BrandProfile:
    profile = await load(store, project_id)
    if profile is None:
        profile = BrandProfile(id=profile_id(project_id), project_id=project_id)
        await repo.save(store, profile)
    return profile


def clean_entries(entries: list[PaletteEntry]) -> list[PaletteEntry]:
    """Normalise hexes, drop unparseable ones, and de-duplicate by colour.

    Extraction reads the same swatch twice more often than it invents one, and a
    duplicate entry would silently double a colour's weight in "nearest".
    """
    seen: set[str] = set()
    cleaned: list[PaletteEntry] = []
    for entry in entries:
        try:
            hex_value = normalise_hex(entry.hex)
        except BadHex:
            continue
        if hex_value in seen:
            continue
        seen.add(hex_value)
        cleaned.append(
            PaletteEntry(
                hex=hex_value,
                role=entry.role.strip(),
                tolerance=max(0.0, float(entry.tolerance)),
            )
        )
    return cleaned


async def propose(
    store: Store, project_id: str, entries: list[PaletteEntry], source: str = ""
) -> BrandProfile:
    """Record a proposed palette. Inert until the Owner confirms it."""
    profile = await get_or_create(store, project_id)
    profile.proposed = clean_entries(entries)
    profile.source = source
    profile.updated_at = now()
    await repo.save(store, profile)
    return profile


async def confirm(
    store: Store, project: Project, user: User, entries: list[PaletteEntry]
) -> BrandProfile:
    """The Owner signs off a palette; from here the pipeline measures against it."""
    require(project, user.id, Permission.CONFIRM_BRAND_PROFILE)

    cleaned = clean_entries(entries)
    if not cleaned:
        raise ValueError("a brand profile needs at least one valid colour")

    profile = await get_or_create(store, project.id)
    profile.entries = cleaned
    profile.confirmed_by = user.id
    profile.confirmed_at = now()
    profile.updated_at = now()
    await repo.save(store, profile)
    return profile


async def withdraw(store: Store, project: Project, user: User) -> BrandProfile:
    """Stop enforcing the palette without forgetting it.

    Clearing the confirmation rather than the colours: the Owner who switches the
    checker off usually wants the same palette back on afterwards, and existing
    BRAND-* defects keep meaning something because the colours still exist.
    """
    require(project, user.id, Permission.CONFIRM_BRAND_PROFILE)

    profile = await get_or_create(store, project.id)
    profile.proposed = profile.proposed or profile.entries
    profile.entries = []
    profile.confirmed_by = ""
    profile.confirmed_at = None
    profile.updated_at = now()
    await repo.save(store, profile)
    return profile


__all__ = [
    "PALETTE_RULE",
    "clean_entries",
    "confirm",
    "get_or_create",
    "load",
    "load_active",
    "profile_id",
    "propose",
    "withdraw",
]
