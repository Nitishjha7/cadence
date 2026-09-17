from django.contrib import admin

from projects.models import Member, Project

admin.site.register(Project)
admin.site.register(Member)
