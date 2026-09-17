from django.contrib import admin

from sprints.models import Capacity, Sprint, SprintCommitment, TimeOff, WorkLog

admin.site.register(Sprint)
admin.site.register(SprintCommitment)
admin.site.register(Capacity)
admin.site.register(TimeOff)
admin.site.register(WorkLog)
