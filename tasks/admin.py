from django.contrib import admin

from tasks.models import Task, TaskDependency

admin.site.register(Task)
admin.site.register(TaskDependency)
