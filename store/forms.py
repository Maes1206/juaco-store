from django import forms
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm

from .models import Address, Order


User = get_user_model()


class EmailOrUsernameAuthenticationForm(AuthenticationForm):
    username = forms.CharField(label="Usuario o correo electrónico")

    def clean(self):
        identifier = self.cleaned_data.get("username")
        password = self.cleaned_data.get("password")
        if identifier and password:
            username = identifier
            if "@" in identifier:
                user = User.objects.filter(email__iexact=identifier).order_by("id").first()
                if user:
                    username = user.get_username()
            self.user_cache = authenticate(self.request, username=username, password=password)
            if self.user_cache is None:
                raise self.get_invalid_login_error()
            self.confirm_login_allowed(self.user_cache)
        return self.cleaned_data


class RegisterForm(UserCreationForm):
    email = forms.EmailField(label="Correo electrónico", required=True)

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "email")
        labels = {
            "username": "Nombre de usuario",
        }
        widgets = {
            "username": forms.TextInput(attrs={
                "class": "form-control",
                "autocomplete": "username",
                "placeholder": "Ej. usuario_123",
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].help_text = "Sin espacios. Solo letras, números y los caracteres @ . + - _"
        self.fields["email"].widget.attrs.update({"class": "form-control", "autocomplete": "email", "placeholder": "tucorreo@ejemplo.com"})
        self.fields["password1"].label = "Contraseña"
        self.fields["password1"].widget.attrs.update({"class": "form-control", "autocomplete": "new-password"})
        self.fields["password2"].label = "Confirmar contraseña"
        self.fields["password2"].widget.attrs.update({"class": "form-control", "autocomplete": "new-password"})

    def clean_email(self):
        email = self.cleaned_data["email"].lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("Ya existe una cuenta con este correo.")
        return email


class AccountDetailsForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ("first_name", "last_name", "username", "email")
        labels = {
            "first_name": "Nombre",
            "last_name": "Apellido",
            "username": "Nombre a Mostrar",
            "email": "Correo Electrónico",
        }

    def clean_email(self):
        email = self.cleaned_data["email"].lower()
        if User.objects.filter(email__iexact=email).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("Ya existe una cuenta con este correo.")
        return email


class CheckoutForm(forms.Form):
    address = forms.ModelChoiceField(queryset=Address.objects.none(), error_messages={"required": "Selecciona una dirección de envío."})
    payment_method = forms.ChoiceField(choices=Order.PaymentMethod.choices, error_messages={"required": "Selecciona un método de pago."})
    notes = forms.CharField(required=False, widget=forms.Textarea(attrs={"class": "form-control", "rows": 3, "placeholder": "Notas sobre tu pedido, ej. indicaciones para la entrega."}))
    accept_terms = forms.BooleanField(error_messages={"required": "Debes aceptar los términos y condiciones para continuar."})

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["address"].queryset = user.addresses.all() if user else Address.objects.none()


class AddressForm(forms.ModelForm):
    class Meta:
        model = Address
        fields = ("label", "first_name", "last_name", "address_line_1", "address_line_2", "department", "city", "postal_code", "phone", "is_default")
        widgets = {
            "label": forms.TextInput(attrs={"placeholder": "Ej. Casa, trabajo o familiar"}),
            "first_name": forms.TextInput(attrs={"autocomplete": "given-name"}),
            "last_name": forms.TextInput(attrs={"autocomplete": "family-name"}),
            "address_line_1": forms.TextInput(attrs={"placeholder": "Calle, carrera y número", "autocomplete": "address-line1"}),
            "address_line_2": forms.TextInput(attrs={"placeholder": "Apartamento, piso, torre, etc.", "autocomplete": "address-line2"}),
            "department": forms.TextInput(attrs={"placeholder": "Ej. Antioquia", "autocomplete": "address-level1"}),
            "city": forms.TextInput(attrs={"placeholder": "Ej. Medellín", "autocomplete": "address-level2"}),
            "postal_code": forms.TextInput(attrs={"autocomplete": "postal-code"}),
            "phone": forms.TextInput(attrs={"placeholder": "Ej. 300 123 4567", "autocomplete": "tel"}),
            "is_default": forms.CheckboxInput(attrs={"style": "width: 18px; height: 18px; min-height: 0; padding: 0; margin: 0 8px 0 0; vertical-align: middle;"}),
        }
