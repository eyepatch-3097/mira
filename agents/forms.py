# agents/forms.py
from django import forms
from .models import Agent

class AgentCreateForm(forms.ModelForm):
    class Meta:
        model = Agent
        fields = [
            "name",
            "description",
            "icon",
            "greeting_message",
            "title_bar_color",
            "window_bg_color",
            "bot_bubble_color",
            "user_bubble_color",
            "text_color",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
            "greeting_message": forms.TextInput(attrs={"maxlength": 280}),
            "title_bar_color": forms.TextInput(attrs={"type": "color"}),
            "window_bg_color": forms.TextInput(attrs={"type": "color"}),
            "bot_bubble_color": forms.TextInput(attrs={"type": "color"}),
            "user_bubble_color": forms.TextInput(attrs={"type": "color"}),
            "text_color": forms.TextInput(attrs={"type": "color"}),
        }
