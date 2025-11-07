from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, Set

import discord

if TYPE_CHECKING:
    from utils.db import Database


def user_has_any_role(member: discord.Member, role_ids: Set[int]) -> bool:
    """Check if member has any of the specified roles."""
    if not role_ids:
        return False
    member_role_ids = {role.id for role in member.roles}
    return bool(member_role_ids & role_ids)


def can_admin_bypass(interaction: discord.Interaction) -> bool:
    """Check if user has Manage Guild permission (admin bypass)."""
    if not interaction.guild or not isinstance(interaction.user, discord.Member):
        return False
    return interaction.user.guild_permissions.manage_guild


async def resolve_completion_policy(
    db: "Database", guild_id: int, board_id: int
) -> Dict[str, Any]:
    """Resolve effective completion policy (board overrides guild)."""
    return await db.get_completion_policy(guild_id, board_id)


async def can_mark_complete(
    interaction: discord.Interaction, task: Dict[str, Any], db: "Database"
) -> bool:
    """
    Check if user can mark a task complete.
    
    Logic:
    1. Admins (Manage Guild) can always complete
    2. If assignee_only is True, user must be in task assignees
    3. Otherwise, user must have one of the allowed roles
    """
    if not interaction.guild or not isinstance(interaction.user, discord.Member):
        return False
    
    # Admin bypass
    if can_admin_bypass(interaction):
        return True
    
    # Get effective policy
    board_id = task.get("board_id")
    if not board_id:
        return False
    
    policy = await resolve_completion_policy(db, interaction.guild.id, board_id)
    assignee_only = policy.get("assignee_only", False)
    allowed_role_ids = set(policy.get("allowed_role_ids", []) or [])
    
    # Check assignee-only rule
    if assignee_only:
        assignee_ids = task.get("assignee_ids", [])
        if not isinstance(assignee_ids, list):
            assignee_ids = []
        if interaction.user.id in assignee_ids:
            return True
        return False
    
    # Check role-based permission
    if allowed_role_ids:
        return user_has_any_role(interaction.user, allowed_role_ids)
    
    # Default: no restrictions (if no policy set)
    return True

