from django.template.defaulttags import url
from django.urls import path
from . import views
from django.views.generic import TemplateView

urlpatterns = [
    path('', views.home, name='home'),
    path('owl/<int:owl_id>', views.owl_detail, name='owl_detail'),
    path('owl/data/<int:owl_id>', views.data_detail, name='data_detail'),
    path('owl/<int:owl_id>/edit', views.owl_upload, name='owl_change'),
    path('owl/import/<int:owl_id>', views.data_import, name='data_import'),
    path('owl/<int:owl_id>/delete', views.owl_delete, name='owl_delete'),
    path('owl/<int:owl_id>/real_graph',
         views.owl_live, name='owl_real_time_graph'),
    path('<int:owl_id>',
         views.owl_visualize, name='owl_visualize'),
    path('owl/<int:owl_id>/export',
         views.owl_download, name='owl_export'),
    path('owl/upload', views.owl_upload, name='owl_upload'),
    path('rel/<int:rel_id>/toggle', views.toggle_causality, name="toggle_causality"),
    path('owl/<int:owl_id>/counterfactual',
         views.counterfactual, name='calculate_counterfactual'),
    path('owl/<int:owl_id>/intervention',
         views.intervention, name='intervention'),
    path('owl/<int:owl_id>/conditionalIndependence',
             views.testIndep, name='conditional_independence'),
    path('owl/<int:owl_id>/sparql',
             views.sparql, name='sparql'),
    path('owl/<int:owl_id>/merge',
             views.merge, name='merge'),
]
