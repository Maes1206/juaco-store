import re

from django.conf import settings
from django.contrib import admin
from django.urls import include, path, re_path
from django.views.static import serve as serve_static


urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("store.urls")),
]

# Sin almacenamiento en la nube ni bloque nginx para /media/, Django debe
# servir los archivos subidos (product.image_file, etc.) tambien en produccion.
# static() de Django se ignora a si mismo si DEBUG=False, por eso se usa la
# vista de servicio directamente en lugar de ese helper.
urlpatterns += [
    re_path(r"^%s(?P<path>.*)$" % re.escape(settings.MEDIA_URL.lstrip("/")), serve_static, {"document_root": settings.MEDIA_ROOT}),
]
