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
