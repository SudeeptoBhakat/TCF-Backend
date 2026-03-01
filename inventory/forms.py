from django import forms
from django.forms.widgets import ClearableFileInput
from .models import ProductMedia, Product, ProductSKU

class MultipleFileInput(ClearableFileInput):
    allow_multiple_selected = True

class ProductMediaMultiUploadForm(forms.ModelForm):
    # This is NOT saved to the model; it's used only to upload multiple files at once
    upload_files = forms.FileField(
        widget=MultipleFileInput(attrs={'multiple': True}),
        required=False,
        label="Upload images (you can choose multiple)"
    )

    class Meta:
        model = ProductMedia
        fields = ['product', 'sku', 'sort_order', 'media_file', 'upload_files']
        widgets = {
            # keep native media_file field but we will hide it with JS if desired
            'media_file': forms.ClearableFileInput()
        }

    def clean(self):
        cleaned = super().clean()
        # If no media_file but upload_files present, that's OK
        return cleaned
