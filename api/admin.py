# For admin page registration
from django.contrib import admin
# Importing apps for getting all models
from django.apps import apps
from django.db import models
# For exporting to csv
import csv
from django.http import HttpResponse

edit = []

filter_fields = []


# Class for creating a list of all fields on a model
class AdminList():

    def switch_superuser(modeladmin, request, queryset):
        queryset.update(is_superuser=not queryset[0].is_superuser)

    def export_as_csv(self, request, queryset):
        meta = self.model._meta
        field_names = [field.name for field in meta.fields]
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename={}.csv'.format(
            meta)
        writer = csv.writer(response)
        writer.writerow(field_names)
        for obj in queryset:
            writer.writerow([getattr(obj, field)
                             for field in field_names])
        return response

    def __init__(self, the_model, admin_site):
        self.actions = []
        self.list_display = [field.name for field in the_model._meta.fields]
        self.list_editable = [
            field.name for field in the_model._meta.fields if field.name in edit]
        self.list_display_links = [
            'email', 'id'] if 'email' in self.list_display else ['id'] if 'id' in self.list_display else ['name']
        self.list_filter = [
            field.name for field in the_model._meta.fields if field.name in filter_fields]
        self.search_fields = [field.name for field in the_model._meta.fields if isinstance(
            field, models.CharField)]
        # Only in "User": moves email to front and password to the back
        if the_model._meta.verbose_name.title() == "User":
            self.list_display.remove('password')
            self.list_display.append('password')
            self.list_display.remove('email')
            self.list_display.insert(0, 'email')
            self.actions += ["switch_superuser", "make_state_active",
                             "make_state_inactive", "make_state_on_hold"]
        self.actions += ["export_as_csv"]
        super().__init__(the_model, admin_site)


# Retrieving the models for the current module
app = apps.get_app_config('api')


for model_name, model in app.models.items():
    # Creating an admin site for each and adding all the fields
    admin.site.register(model, type(
        'AdminClass', (AdminList, admin.ModelAdmin), {}))
    # changing the title text
    admin.site.site_header = 'OWL Analyze'
    admin.site.site_title = 'OWL Analyze'
    admin.site.index_title = 'Admin Area'

modules = []

for module in modules:
    for model_name, model in apps.get_app_config(module).models.items():
        admin.site.register(model, type(
            'AdminClass', (AdminList, admin.ModelAdmin), {}))
