from django.contrib import admin

from core.models import Member, Project, Sprint, Task

admin.site.register(Project)
admin.site.register(Member)
admin.site.register(Sprint)
admin.site.register(Task)
