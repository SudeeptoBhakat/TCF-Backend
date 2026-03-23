import io
from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from .models import ProductMedia, Product, ProductSKU
from .widgets import MultipleFileInput

# Max individual file size: 5 MB
MAX_FILE_SIZE_BYTES = 5 * 1024 * 1024

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

    Validation per file:
    - Size  ≤ MAX_FILE_SIZE_BYTES (10 MB)
    - MIME  in ALLOWED_IMAGE_TYPES
    - Deep  Pillow Image.verify() — catches corrupt/spoofed files
    """

    def __init__(self, *args, **kwargs):
        kwargs.setdefault('required', False)
        kwargs.setdefault('label', _('Upload Images'))
        kwargs.setdefault('help_text', _(
            'Select one or more image files (JPG, PNG, WEBP, GIF). Max 5 MB each.'
        ))
        # Pass widget as keyword arg to forms.Field.__init__
        super().__init__(
            *args,
            widget=MultipleFileInput(attrs={'class': 'multi-image-simple-input'}),
            **kwargs
        )

    def to_python(self, data):
        """
        data arrives as a list from MultipleFileInput.value_from_datadict().
        Returns cleaned list, or [] if nothing was posted.
        """
        if not data:
            return []
        if not isinstance(data, (list, tuple)):
            data = [data]
        return [f for f in data if f]  # drop Falsy entries

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
            # ── Size guard ──────────────────────────────────────────────────
            if f.size > MAX_FILE_SIZE_BYTES:
                errors.append(ValidationError(
                    _('%(name)s is too large (%(size)s). Max allowed is 5 MB.'),
                    params={'name': f.name, 'size': f'{f.size / 1024 / 1024:.1f} MB'},
                    code='file_too_large',
                ))
                continue

            # ── MIME guard (fast path) ───────────────────────────────────────
            content_type = getattr(f, 'content_type', '')
            if content_type and content_type not in ALLOWED_IMAGE_TYPES:
                errors.append(ValidationError(
                    _('%(name)s is not a supported image type (JPG, PNG, WEBP, GIF).'),
                    params={'name': f.name},
                    code='invalid_image_type',
                ))
                continue

            # ── Pillow deep verify ──────────────────────────────────────────
            try:
                from PIL import Image
                f.seek(0)
                img = Image.open(io.BytesIO(f.read()))
                img.verify()   # raises on corrupt / truncated data
                f.seek(0)      # reset pointer so storage backend can stream it
            except Exception:
                errors.append(ValidationError(
                    _('%(name)s could not be read as a valid image. '
                      'The file may be corrupt or in an unsupported format.'),
                    params={'name': f.name},
                    code='invalid_image',
                ))
                continue

            cleaned.append(f)

        if errors:
            raise ValidationError(errors)

        return cleaned


class ProductMediaMultiUploadForm(forms.ModelForm):
    """
    Admin form for ProductMedia with multi-image upload support.

    ── Fields ──────────────────────────────────────────────────────────────
    product         ForeignKey  (required)
    sku             ForeignKey  (optional)
    sort_order      Integer     (default 0)
    upload_images   Custom      Multi-file picker — creates N rows on save
    media_file      ImageField  Hidden — used for direct single-file edits

    ── Upload flow ──────────────────────────────────────────────────────────
    When upload_images has files → ProductMediaAdmin.save_model() creates
    one ProductMedia row per file (ignores the model-level media_file).

    When upload_images is empty → normal ModelForm save (edit mode, preserves
    the existing media_file on the record being changed).
    """

    upload_images = MultipleImageField()

    class Meta:
        model = ProductMedia
        # Include media_file so existing records can be edited without re-upload
        fields = ['product', 'sku', 'media_file']
        widgets = {
            # Hide the single-file picker — it is only used as a fallback when
            # editing an existing record. Users upload via upload_images instead.
            'media_file': forms.FileInput(attrs={
                'style': 'display:none',
                'id': 'id_media_file_hidden',
            }),
        }
        labels = {
            'media_file': _('Replace existing image (optional)'),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Product — required, only active products
        self.fields['product'].required = True
        self.fields['product'].queryset = (
            Product.objects.filter(is_active=True).order_by('name')
        )

        # SKU — optional
        self.fields['sku'].required = False
        self.fields['sku'].queryset = (
            ProductSKU.objects
            .select_related('product')
            .order_by('product__name', 'sku_code')
        )
        self.fields['sku'].empty_label = '— No SKU (product-level image) —'

        # media_file — only show if editing an existing object that has one
        obj = kwargs.get('instance')
        if obj and obj.pk and obj.media_file:
            self.fields['media_file'].widget = forms.ClearableFileInput()
            self.fields['media_file'].required = False
            self.fields['media_file'].label = _('Replace existing image (optional)')
        else:
            # Hide entirely when adding — upload_images handles it
            self.fields['media_file'].required = False
            self.fields['media_file'].widget.attrs['style'] = 'display:none'
