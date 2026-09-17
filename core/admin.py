from django.contrib import admin

from core.models import (
    Capacity,
    Member,
    Project,
    Sprint,
    SprintCommitment,
    Task,
    TaskDependency,
    TimeOff,
    WorkLog,
)

admin.site.register(Project)
admin.site.register(Member)
admin.site.register(Sprint)
admin.site.register(Task)
admin.site.register(TaskDependency)
admin.site.register(SprintCommitment)
admin.site.register(Capacity)
admin.site.register(TimeOff)
admin.site.register(WorkLog)
