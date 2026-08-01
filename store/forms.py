import re
from django import forms
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm

from . import bold
from .models import Address, BlogComment, ContactRequest, CustomerProfile, Order, Product, ProductReview


User = get_user_model()


def default_payment_method():
    """Se cobra en línea siempre que la pasarela esté disponible."""
    return Order.PaymentMethod.BOLD if bold.is_configured() else Order.PaymentMethod.BANK_TRANSFER


def available_payment_methods():
    """Métodos ofrecidos en el checkout, con el pago en línea primero."""
    excluded = {Order.PaymentMethod.CASH_ON_DELIVERY}
    if not bold.is_configured():
        excluded.add(Order.PaymentMethod.BOLD)
    choices = [choice for choice in Order.PaymentMethod.choices if choice[0] not in excluded]
    default = default_payment_method()
    return sorted(choices, key=lambda choice: choice[0] != default)

class ProductAdminForm(forms.ModelForm):
    lookup_release_date = forms.BooleanField(
        label="Consultar lanzamiento en StockX al guardar",
        required=False,
        initial=True,
        help_text="Usa la referencia para completar la fecha. La fecha escrita manualmente siempre tiene prioridad.",
    )
    sizes = forms.CharField(
        label="Tallas disponibles",
        required=False,
        help_text="Separa las tallas con comas. Borra una talla para quitarla o deja el campo vacío para ocultar todas.",
        widget=forms.TextInput(attrs={"placeholder": "38, 39, 40, 41, 42"}),
    )
    colors = forms.CharField(
        label="Colores disponibles",
        required=False,
        help_text="Usa una línea por color: Nombre | #HEX. Borra la línea para quitarlo o deja el campo vacío para ocultar todos.",
        widget=forms.Textarea(attrs={"rows": 5, "placeholder": "Gris | #505050\nAzul | #586882"}),
    )
    gallery = forms.CharField(
        label="Galeria adicional",
        required=False,
        help_text="Una imagen por linea: Ruta o URL | texto alternativo.",
        widget=forms.Textarea(attrs={"rows": 5, "placeholder": "Ruta o URL | texto alternativo"}),
    )

    tags = forms.CharField(
        label="Etiquetas",
        required=False,
        help_text="Escribe etiquetas separadas por coma. Ejemplo: Retro, cuero, edicion limitada.",
        widget=forms.TextInput(attrs={"placeholder": "Retro, cuero, edicion limitada"}),
    )
    class Meta:
        model = Product
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields["lookup_release_date"].initial = False
            self.initial["sizes"] = ", ".join(str(size) for size in (self.instance.sizes or []))
            self.initial["colors"] = "\n".join(
                f'{color.get("name", "Color")} | {color.get("hex", "#505050")}'
                for color in (self.instance.colors or [])
                if isinstance(color, dict)
            )
            self.initial["gallery"] = "\n".join(
                f'{item.get("url", "")} | {item.get("alt", "")}'.rstrip(" |")
                for item in (self.instance.gallery or [])
                if isinstance(item, dict) and item.get("url")
            )

            self.initial["tags"] = ", ".join(str(tag) for tag in (self.instance.tags or []))

    def save(self, commit=True):
        product = super().save(commit=False)
        if "release_date" in self.changed_data:
            product.release_date_source = (
                Product.ReleaseDateSource.MANUAL if product.release_date else Product.ReleaseDateSource.UNKNOWN
            )
        if commit:
            product.save()
            self.save_m2m()
        return product

    def clean_sizes(self):
        values = re.split(r"[,;\n]+", self.cleaned_data.get("sizes", ""))
        sizes = []
        for value in values:
            size = value.strip()
            if size and size not in sizes:
                if len(size) > 12:
                    raise forms.ValidationError("Cada talla puede tener maximo 12 caracteres.")
                sizes.append(size)
        return sizes

    def clean_gallery(self):
        raw_lines = re.split(r"[\n;]+", self.cleaned_data.get("gallery", ""))
        gallery = []
        for raw_line in raw_lines:
            line = raw_line.strip()
            if not line:
                continue
            parts = [part.strip() for part in line.split("|", 1)]
            url = parts[0]
            alt = parts[1] if len(parts) > 1 else ""
            if len(url) > 500:
                raise forms.ValidationError("Cada ruta de imagen puede tener maximo 500 caracteres.")
            if len(alt) > 180:
                raise forms.ValidationError("El texto alternativo puede tener maximo 180 caracteres.")
            if not any(item["url"] == url for item in gallery):
                gallery.append({"url": url, "alt": alt})
        return gallery

    def clean_colors(self):
        raw_lines = re.split(r"[\n;]+", self.cleaned_data.get("colors", ""))
        colors = []
        for raw_line in raw_lines:
            line = raw_line.strip()
            if not line:
                continue
            parts = [part.strip() for part in line.split("|", 1)]
            if len(parts) != 2:
                raise forms.ValidationError("Usa el formato Nombre | #HEX, un color por linea.")
            name, hex_value = parts
            if not name or len(name) > 60:
                raise forms.ValidationError("Cada color debe tener un nombre de maximo 60 caracteres.")
            if not re.fullmatch(r"#[0-9a-fA-F]{6}", hex_value):
                raise forms.ValidationError(f'El color "{name}" debe usar un codigo hexadecimal como #505050.')
            if not any(item["name"].casefold() == name.casefold() for item in colors):
                colors.append({"name": name, "hex": hex_value.upper()})
        return colors

    def clean_tags(self):
        raw_value = self.cleaned_data.get("tags", "")
        values = re.split(r"[,;\n]+", raw_value)
        tags = []
        for value in values:
            tag = value.strip()
            if not tag or tag == "[]":
                continue
            if len(tag) > 80:
                raise forms.ValidationError("Cada etiqueta puede tener maximo 80 caracteres.")
            if tag.casefold() not in {item.casefold() for item in tags}:
                tags.append(tag)
        return tags

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
    first_name = forms.CharField(
        label="Nombres",
        max_length=150,
        required=True,
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "autocomplete": "given-name",
            "placeholder": "Tus nombres",
        }),
    )
    last_name = forms.CharField(
        label="Apellidos",
        max_length=150,
        required=True,
        widget=forms.TextInput(attrs={
            "class": "form-control",
            "autocomplete": "family-name",
            "placeholder": "Tus apellidos",
        }),
    )
    email = forms.EmailField(label="Correo electrónico", required=True)

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("first_name", "last_name", "username", "email")
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
    document_number = forms.CharField(
        label="Numero de cedula",
        max_length=30,
        required=False,
        widget=forms.TextInput(attrs={"autocomplete": "off", "placeholder": "Ej. 1.075.000.000"}),
    )
    phone = forms.CharField(
        label="Telefono de contacto",
        max_length=30,
        required=False,
        widget=forms.TextInput(attrs={"autocomplete": "tel", "placeholder": "Ej. 300 123 4567"}),
    )

    class Meta:
        model = User
        fields = ("first_name", "last_name", "username", "email")
        labels = {
            "first_name": "Nombre",
            "last_name": "Apellido",
            "username": "Nombre a Mostrar",
            "email": "Correo Electronico",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        profile = getattr(self.instance, "customer_profile", None) if self.instance.pk else None
        if profile:
            self.fields["document_number"].initial = profile.document_number
            self.fields["phone"].initial = profile.phone

    def clean_email(self):
        email = self.cleaned_data["email"].lower()
        if User.objects.filter(email__iexact=email).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("Ya existe una cuenta con este correo.")
        return email

    def clean_document_number(self):
        document_number = self.cleaned_data["document_number"].strip()
        if document_number and CustomerProfile.objects.filter(document_number=document_number).exclude(user=self.instance).exists():
            raise forms.ValidationError("Ya existe un cliente con este numero de cedula.")
        return document_number

    def save(self, commit=True):
        user = super().save(commit=commit)
        if commit:
            profile, _ = CustomerProfile.objects.get_or_create(user=user)
            profile.document_number = self.cleaned_data["document_number"]
            profile.phone = self.cleaned_data["phone"].strip()
            profile.save(update_fields=("document_number", "phone", "updated_at"))
        return user

class ContactRequestForm(forms.ModelForm):
    class Meta:
        model = ContactRequest
        fields = ("name", "email", "phone", "subject", "message")
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Nombre *"}),
            "email": forms.EmailInput(attrs={"class": "form-control", "placeholder": "Correo electronico *"}),
            "phone": forms.TextInput(attrs={"class": "form-control", "placeholder": "Telefono (opcional)"}),
            "subject": forms.TextInput(attrs={"class": "form-control", "placeholder": "Asunto (opcional)"}),
            "message": forms.Textarea(attrs={"class": "form-control", "placeholder": "Mensaje", "rows": 5}),
        }


class BlogCommentForm(forms.ModelForm):
    class Meta:
        model = BlogComment
        fields = ("name", "email", "body")
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Nombre *"}),
            "email": forms.EmailInput(attrs={"class": "form-control", "placeholder": "Correo electronico *"}),
            "body": forms.Textarea(attrs={"class": "form-control", "placeholder": "Comentario", "rows": 5}),
        }


class ProductReviewForm(forms.ModelForm):
    recommends = forms.BooleanField(label="Recomiendo este producto", required=False, initial=True)

    class Meta:
        model = ProductReview
        fields = ("name", "email", "rating", "recommends", "title", "body")
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Ingresa tu nombre"}),
            "email": forms.EmailInput(attrs={"class": "form-control", "placeholder": "correo@ejemplo.com"}),
            "rating": forms.Select(attrs={"class": "form-control"}, choices=((5, "5 - Excelente"), (4, "4 - Muy buena"), (3, "3 - Buena"), (2, "2 - Regular"), (1, "1 - Mala"))),
            "title": forms.TextInput(attrs={"class": "form-control", "placeholder": "Titulo de la resena"}),
            "body": forms.Textarea(attrs={"class": "form-control", "placeholder": "Escribe tu comentario aqui", "rows": 5}),
        }

class CheckoutForm(forms.Form):
    DELIVERY_CHOICES = (
        ("courier", "Enviar a mi dirección"),
        ("pickup", "Recoger en Neiva, Huila"),
    )

    delivery_method = forms.ChoiceField(choices=DELIVERY_CHOICES, initial="courier", required=False)
    address = forms.ModelChoiceField(
        queryset=Address.objects.none(),
        required=False,
        error_messages={"required": "Selecciona una dirección de envío."},
    )
    payment_method = forms.ChoiceField(choices=Order.PaymentMethod.choices, error_messages={"required": "Selecciona un método de pago."})
    notes = forms.CharField(required=False, widget=forms.Textarea(attrs={"class": "form-control", "rows": 3, "placeholder": "Notas sobre tu pedido, ej. indicaciones para la entrega."}))
    accept_terms = forms.BooleanField(error_messages={"required": "Debes aceptar los términos y condiciones para continuar."})

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["address"].queryset = user.addresses.all() if user else Address.objects.none()
        self.fields["payment_method"].choices = available_payment_methods()

    def clean(self):
        cleaned_data = super().clean()
        delivery_method = cleaned_data.get("delivery_method") or "courier"
        cleaned_data["delivery_method"] = delivery_method
        if delivery_method != "pickup" and not cleaned_data.get("address"):
            self.add_error("address", "Selecciona una dirección de envío.")
        return cleaned_data


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

class NewsletterSubscriptionForm(forms.Form):
    email = forms.EmailField()

    def clean_email(self):
        return self.cleaned_data["email"].strip().lower()
