# Import forms for form datafields
from django.forms import ModelForm
# Import models for ModelChoiceFields
from .models import OWLFile
from django import forms


class OWLFileForm(ModelForm):
    class Meta:
        model = OWLFile
        fields = ['name', 'file']

class InterventionForm (forms.Form):
    name = forms.CharField()