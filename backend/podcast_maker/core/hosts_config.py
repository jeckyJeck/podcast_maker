"""
Host profiles for podcast generation.
Loads host configurations from hosts.json file.
"""

import json
from typing import Dict, List, Optional
from dataclasses import dataclass
from pathlib import Path

from podcast_maker.core.paths import BACKEND_ROOT


@dataclass
class HostProfile:
    """Represents a podcast host with personality and voice characteristics"""
    id: str  # unique identifier
    name: str  # display name
    personality: str  # personality description for the LLM
    voice_id: str  # Google Cloud TTS voice ID
    gender: str  # "male", "female", or other
    tone: str  # general tone/style
    role: str  # "primary" or "secondary" - describes their role in the conversation


def _load_hosts_config() -> Dict:
    """Load hosts configuration from JSON file"""
    hosts_file = BACKEND_ROOT / "podcast_maker" / "core" / "hosts.json"
    
    if not hosts_file.exists():
        raise FileNotFoundError(f"Hosts configuration file not found: {hosts_file}")
    
    with open(hosts_file, 'r', encoding='utf-8') as f:
        return json.load(f)


def _build_host_profiles() -> Dict[str, HostProfile]:
    """Build host profiles from configuration"""
    config = _load_hosts_config()
    profiles = {}
    
    for host_id, host_data in config["hosts"].items():
        profiles[host_id] = HostProfile(
            id=host_data["id"],
            name=host_data["name"],
            personality=host_data["personality"],
            voice_id=host_data["voice_id"],
            gender=host_data["gender"],
            tone=host_data["tone"],
            role=host_data["role"]
        )
    
    return profiles


# Load profiles once at module import time
AVAILABLE_HOSTS = _build_host_profiles()


def get_host_profile(host_id: str) -> HostProfile:
    """Get a host profile by ID"""
    if host_id not in AVAILABLE_HOSTS:
        raise ValueError(f"Unknown host ID: {host_id}")
    return AVAILABLE_HOSTS[host_id]


def get_host_names() -> Dict[str, str]:
    """Get mapping of host IDs to display names"""
    return {host_id: host.name for host_id, host in AVAILABLE_HOSTS.items()}


def validate_host_selection(host_ids: list) -> bool:
    """Validate that selected hosts exist and have the right combination"""
    if not isinstance(host_ids, list) or len(host_ids) < 2:
        raise ValueError("At least 2 hosts are required")
    
    for host_id in host_ids:
        if host_id not in AVAILABLE_HOSTS:
            raise ValueError(f"Unknown host ID: {host_id}")
    
    return True


def format_hosts_for_prompt(host_ids: list) -> str:
    """Format host information for inclusion in the prompt"""
    profiles = [get_host_profile(host_id) for host_id in host_ids]
    
    formatted = "## HOST PROFILES\n\n"
    for i, profile in enumerate(profiles, 1):
        formatted += f"**HOST_{i} ({profile.name})**\n"
        formatted += f"- Role: {profile.role} host\n"
        formatted += f"- Tone: {profile.tone}\n"
        formatted += f"- Personality:\n{profile.personality}\n\n"
    
    formatted += "\n**CRITICAL**: Maintain these personality profiles throughout the entire episode. "
    formatted += "Use the names and personality traits consistently. The hosts should sound distinct and authentic.\n"
    
    return formatted
