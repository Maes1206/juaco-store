from datetime import datetime

from django.db import migrations, models
import django.db.models.deletion


CATEGORIES = [
    ("Cultura sneaker", "cultura-sneaker"),
    ("Guías de estilo", "guias-de-estilo"),
    ("Cuidado", "cuidado"),
]

POSTS = [
    ("siluetas-basket-urbanas", "Por qué las siluetas de baloncesto siguen siendo un ícono urbano", "cultura-sneaker", "Las siluetas nacidas en la cancha conservaron su identidad y se volvieron esenciales para el streetwear diario.", "assets/img/blog/juaco-blog-cover-01.png", "Sneaker de caña alta en una cancha urbana nocturna", ["Streetwear", "Baloncesto", "Estilo urbano"], 5, "2026-07-10", "Las zapatillas de baloncesto llegaron a la calle por razones que van más allá de su silueta llamativa. Su estructura transmite historia deportiva, mientras que los materiales resistentes responden bien a una rutina urbana.\n\nPara usarlas a diario, equilibra el volumen del par con prendas de cortes limpios: denim recto, pantalones cargo sobrios o una sudadera sin exceso de gráficos. Así el calzado se mantiene como protagonista sin forzar el look.\n\nAntes de elegir un modelo, revisa el estado de la suela, los materiales y el ajuste del tobillo. Un par que se siente estable desde el primer uso suele acompañarte mejor que uno elegido solo por tendencia."),
    ("cuidado-sneakers-blancos", "Cómo mantener impecables tus sneakers blancos", "cuidado", "Una rutina breve después de cada uso evita manchas permanentes y conserva la forma original de tus pares blancos.", "assets/img/blog/juaco-blog-cover-02.png", "Sneakers blancos junto a elementos de limpieza", ["Cuidado", "Limpieza", "Sneakers blancos"], 4, "2026-07-07", "Los sneakers blancos combinan con casi todo, pero necesitan constancia. Retira el polvo superficial con un cepillo suave al llegar a casa y trata las manchas antes de que se sequen.\n\nUsa un paño de microfibra ligeramente húmedo con jabón neutro. Evita sumergir el par y no uses blanqueadores: pueden alterar el tono del cuero, la malla o las costuras.\n\nDéjalos secar a la sombra, con papel limpio dentro para conservar su forma. Guardarlos en un lugar ventilado prolonga la vida de los materiales."),
    ("combinar-sneakers-color", "Cómo combinar sneakers de colores sin perder tu estilo", "guias-de-estilo", "Los pares con bloques de color pueden elevar un outfit si el resto de las prendas acompaña sin competir.", "assets/img/blog/juaco-blog-cover-03.png", "Sneakers azul marino y crema sobre fondo urbano", ["Color", "Outfits", "Guía de estilo"], 4, "2026-07-03", "Un sneaker de color funciona mejor cuando tiene espacio para destacar. Parte de una base neutra —negro, gris, blanco o denim— y deja que el par marque el punto de atención.\n\nElige uno de sus tonos y repítelo solo una vez: en una gorra, una camiseta o un detalle pequeño. Esto crea coherencia sin convertir el look en un conjunto literal.\n\nSi todavía estás probando combinaciones, empieza con siluetas de dos o tres colores. Son más fáciles de integrar y te dan margen para experimentar."),
    ("sneakers-perfil-bajo", "Qué mirar antes de elegir sneakers de perfil bajo", "guias-de-estilo", "Ajuste, soporte y materiales: tres puntos simples que definen si una silueta baja funcionará para tu día a día.", "assets/img/blog/juaco-blog-cover-04.png", "Sneaker de perfil bajo sobre una cancha interior", ["Comodidad", "Perfil bajo", "Guía de compra"], 3, "2026-06-28", "Las siluetas bajas son versátiles porque se adaptan a distintos estilos y estaciones. Para elegir bien, pruébalas con el tipo de media que usas normalmente y confirma que la puntera tenga espacio.\n\nRevisa el soporte del talón y la flexibilidad de la suela. Un par cómodo no debe necesitar un periodo largo de adaptación para sentirse estable.\n\nLos materiales también importan: el cuero es fácil de limpiar, la gamuza requiere más cuidado y las mallas ayudan en climas cálidos."),
]


def seed_blog(apps, schema_editor):
    Category = apps.get_model("store", "BlogCategory")
    Post = apps.get_model("store", "BlogPost")
    categories = {slug: Category.objects.update_or_create(slug=slug, defaults={"name": name})[0] for name, slug in CATEGORIES}
    for slug, title, category, summary, image, image_alt, tags, reading_time, published_at, content in POSTS:
        Post.objects.update_or_create(slug=slug, defaults={"title": title, "category": categories[category], "summary": summary, "content": content, "image": image, "image_alt": image_alt, "author": "Equipo Juaco Store", "tags": tags, "reading_time": reading_time, "published_at": datetime.fromisoformat(f"{published_at}T09:00:00+00:00"), "is_published": True})


def unseed_blog(apps, schema_editor):
    apps.get_model("store", "BlogPost").objects.filter(slug__in=[post[0] for post in POSTS]).delete()


class Migration(migrations.Migration):
    dependencies = [("store", "0002_seed_products")]

    operations = [
        migrations.CreateModel(
            name="BlogCategory",
            fields=[("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")), ("name", models.CharField(max_length=80, unique=True, verbose_name="nombre")), ("slug", models.SlugField(max_length=100, unique=True))],
            options={"verbose_name": "categoría del blog", "verbose_name_plural": "categorías del blog", "ordering": ["name"]},
        ),
        migrations.CreateModel(
            name="BlogPost",
            fields=[("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")), ("title", models.CharField(max_length=180, verbose_name="título")), ("slug", models.SlugField(max_length=200, unique=True)), ("summary", models.TextField(max_length=360, verbose_name="resumen")), ("content", models.TextField(verbose_name="contenido")), ("image", models.CharField(max_length=255, verbose_name="imagen")), ("image_alt", models.CharField(max_length=180, verbose_name="texto alternativo de la imagen")), ("author", models.CharField(default="Equipo Juaco Store", max_length=100, verbose_name="autor")), ("tags", models.JSONField(blank=True, default=list, verbose_name="etiquetas")), ("reading_time", models.PositiveSmallIntegerField(default=4, verbose_name="minutos de lectura")), ("published_at", models.DateTimeField(verbose_name="fecha de publicación")), ("is_published", models.BooleanField(default=True, verbose_name="publicar")), ("created_at", models.DateTimeField(auto_now_add=True)), ("updated_at", models.DateTimeField(auto_now=True)), ("category", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="posts", to="store.blogcategory", verbose_name="categoría"))],
            options={"verbose_name": "artículo", "verbose_name_plural": "artículos", "ordering": ["-published_at"]},
        ),
        migrations.RunPython(seed_blog, unseed_blog),
    ]
