import io
from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from .models import ProductMedia, Product, ProductSKU
from .widgets import MultipleFileInput

# Max individual file size: 10 MB
MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024

# Accepted MIME types
ALLOWED_IMAGE_TYPES = {
    'image/jpeg',
    'image/png',
    'image/webp',
    'image/gif',
}


class MultipleImageField(forms.Field):
    """
    A form field that accepts multiple image files via a single <input type="file" multiple>.

    Validation:
    - Each file must be a valid image (checked via Pillow).
    - Each file must be <= MAX_FILE_SIZE_BYTES.
    - Empty list is allowed (field is optional) unless required=True.
    """

    def __init__(self, *args, **kwargs):
        kwargs.setdefault('required', False)
        kwargs.setdefault('label', _('Upload Images'))
        kwargs.setdefault('help_text', _(
            'Select one or multiple image files (JPG, PNG, WEBP, GIF). '
            'Max 10 MB each.'
        ))
        super().__init__(*args, widget=MultipleFileInput(attrs={'class': 'multi-image-upload-input'}), **kwargs)

    def to_python(self, data):
        """
        data is a list of InMemoryUploadedFile (or similar) objects.
        Returns the same list, or [] if nothing was uploaded.
        """
        if not data:
            return []
        if not isinstance(data, (list, tuple)):
            data = [data]
        return [f for f in data if f]

    def validate(self, value):
        super().validate(value)
        if not value and self.required:
            raise ValidationError(_('Please select at least one image file.'))

    def clean(self, value):
        value = self.to_python(value)
        self.validate(value)

        cleaned = []
        errors = []

        for f in value:
            # ── Size check ──────────────────────────────────────────────────
            if f.size > MAX_FILE_SIZE_BYTES:
                errors.append(
                    ValidationError(
                        _('%(name)s is too large (%(size)s). Max allowed size is 10 MB.'),
                        params={'name': f.name, 'size': f'{f.size / 1024 / 1024:.1f} MB'},
                        code='file_too_large',
                    )
                )
                continue

            # ── MIME type check (fast) ───────────────────────────────────────
            content_type = getattr(f, 'content_type', '')
            if content_type and content_type not in ALLOWED_IMAGE_TYPES:
                errors.append(
                    ValidationError(
                        _('%(name)s is not a supported image format. Allowed: JPG, PNG, WEBP, GIF.'),
                        params={'name': f.name},
                        code='invalid_image_type',
                    )
                )
                continue

            # ── Pillow deep validation ──────────────────────────────────────
            try:
                from PIL import Image
                # Read without consuming the file pointer
                f.seek(0)
                img = Image.open(io.BytesIO(f.read()))
                img.verify()   # raises if file is corrupt
                f.seek(0)      # reset so Django can stream it to storage
            except Exception:
                errors.append(
                    ValidationError(
                        _('%(name)s could not be identified as a valid image. '
                          'The file may be corrupt or in an unsupported format.'),
                        params={'name': f.name},
                        code='invalid_image',
                    )
                )
                continue

            cleaned.append(f)

        if errors:
            raise ValidationError(errors)

        return cleaned


class ProductMediaMultiUploadForm(forms.ModelForm):
    """
    Admin form for ProductMedia.
    Supports uploading multiple images in a single request.
    The `upload_images` field is the multi-file picker.
    The underlying `media_file` ImageField is hidden — it is populated
    programmatically by ProductMediaAdmin.save_model() for each file.
    """

    upload_images = MultipleImageField()

    class Meta:
        model = ProductMedia
        fields = ['product', 'sku', 'sort_order']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Make product required
        self.fields['product'].required = True
        self.fields['product'].queryset = Product.objects.filter(is_active=True).order_by('name')

        # SKU is optional — filter to skus of selected product if possible
        self.fields['sku'].required = False
        self.fields['sku'].queryset = ProductSKU.objects.select_related('product').order_by('product__name', 'sku_code')
        self.fields['sku'].empty_label = '— No SKU (product-level image) —'

        self.fields['sort_order'].initial = 0
        self.fields['sort_order'].help_text = _(
            'Images are ordered ascending. Multiple uploads start at this value and increment by 1.'
        )
