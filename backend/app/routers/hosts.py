"""Routes: public host catalogue (no auth required)."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/available-hosts/")
async def get_available_hosts():
    """Return the list of available podcast hosts."""
    from podcast_maker.core.hosts_config import AVAILABLE_HOSTS

    hosts_list = []
    for _host_id, profile in AVAILABLE_HOSTS.items():
        hosts_list.append(
            {
                "id": profile.id,
                "name": profile.name,
                "tone": profile.tone,
                "role": profile.role,
                "gender": profile.gender,
                "personality": profile.personality,
            }
        )
    return {"hosts": hosts_list}
