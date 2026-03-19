from django.forms.widgets import FileInput


class MultipleFileInput(FileInput):
    """
    A file input widget that supports selecting multiple files at once.
    Overrides value_from_datadict to return a LIST of uploaded files
    (instead of a single file, which is the default Django behaviour).
    """
    allow_multiple_selected = True

    def __init__(self, attrs=None):
        default_attrs = {'multiple': True}
        if attrs:
            default_attrs.update(attrs)
        super().__init__(default_attrs)

    def value_from_datadict(self, data, files, name):
        # files is a MultiValueDict — getlist returns all files for the key
        return files.getlist(name)

    def value_omitted_from_data(self, data, files, name):
        # If the key is absent entirely (not just empty), treat as omitted
        return name not in files