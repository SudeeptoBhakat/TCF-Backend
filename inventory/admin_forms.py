from django import forms
from .models import ProductMedia
from .widgets import MultiFileInput

class ProductMediaMultiUploadForm(forms.ModelForm):
    upload_files = forms.FileField(
        widget=MultiFileInput(attrs={
            'class': 'drag-drop-zone'
        }),
        required=False,
        label="Upload Multiple Images"
    )

    class Meta:
        model = ProductMedia
        fields = ['product', 'sku', 'sort_order', 'media_file', 'media']

