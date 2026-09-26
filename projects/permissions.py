"""
Object-level permission checks, used by the mixin in every view
(projects/views_base.py) rather than scattered `if` statements.

Three roles (see docs/architecture.md):
  viewer       — read everything in their projects
  contributor  — create/edit tasks, change state, add dependencies
  manager      — all of the above, plus start/complete sprints, manage members
"""

from projects.models import Member


def member_for(user, project):
    """The user's Member row in this project, or None if they aren't one."""
    if not user.is_authenticated:
        return None
    return Member.objects.filter(user=user, project=project).first()


def can_view(user, project):
    return member_for(user, project) is not None


def can_edit(user, project):
    """Create/edit tasks, change state, add dependencies."""
    member = member_for(user, project)
    return member is not None and member.role in (Member.Role.CONTRIBUTOR, Member.Role.MANAGER)


def can_manage(user, project):
    """Start/complete sprints, manage members."""
    member = member_for(user, project)
    return member is not None and member.role == Member.Role.MANAGER
