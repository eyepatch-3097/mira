from django import forms

class WebsiteSourceCreateForm(forms.Form):
    name = forms.CharField(max_length=120)
    domain_url = forms.CharField(max_length=300)

class UrlSelectionForm(forms.Form):
    # used only for “displayed ids” trick
    displayed_ids = forms.CharField(required=False)
    selected_ids = forms.MultipleChoiceField(required=False, choices=[], widget=forms.MultipleHiddenInput)

    def __init__(self, *args, **kwargs):
        page_ids = kwargs.pop("page_ids", [])
        super().__init__(*args, **kwargs)
        self.fields["selected_ids"].choices = [(str(i), str(i)) for i in page_ids]

MAX_FILE_MB = 50
ALLOWED_EXTS = (".pdf", ".docx")

class DocumentSourceCreateForm(forms.Form):
    name = forms.CharField(max_length=120)
    file = forms.FileField()

    def clean_file(self):
        f = self.cleaned_data["file"]
        if f.size > MAX_FILE_MB * 1024 * 1024:
            raise forms.ValidationError(f"File too large. Max {MAX_FILE_MB}MB.")
        name = (f.name or "").lower()
        if not name.endswith(ALLOWED_EXTS):
            raise forms.ValidationError("Only PDF or DOCX files are allowed.")
        return f

class SheetSourceCreateForm(forms.Form):
    name = forms.CharField(max_length=120)
    source_context = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
        help_text="Tell Mira what this sheet represents (1–2 lines)."
    )
    file = forms.FileField()

    def clean_file(self):
        f = self.cleaned_data["file"]
        if f.size > 50 * 1024 * 1024:
            raise forms.ValidationError("File too large (max 50MB).")

        allowed = (".xlsx", ".csv")
        name = (f.name or "").lower()
        if not any(name.endswith(x) for x in allowed):
            raise forms.ValidationError("Only .xlsx and .csv are supported for now.")
        return f