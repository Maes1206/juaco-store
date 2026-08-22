from datetime import datetime

from django.db import migrations


POSTS = [
    {
        "slug": "siluetas-retro-para-uso-diario",
        "title": "Siluetas retro que siguen funcionando todos los días",
        "category": "guias-de-estilo",
        "summary": "Los perfiles clásicos ganan vigencia cuando se combinan con prendas actuales y materiales bien cuidados.",
        "content": "Las siluetas retro no necesitan un outfit temático para verse bien. Su mejor versión aparece al mezclarlas con básicos actuales: denim recto, pantalones de pinzas relajados o una camiseta de buen gramaje.\n\nBusca pares con materiales que envejezcan bien, como cuero liso, gamuza o nylon resistente. Los tonos crema, blanco roto, verde oscuro y azul marino suelen ser fáciles de integrar a un armario diario.\n\nSi es tu primer par retro, prioriza comodidad y versatilidad sobre una edición limitada. Un modelo que puedas usar varias veces por semana termina siendo una compra más acertada.",
        "image": "assets/img/blog/juaco-blog-cover-05.png",
        "image_alt": "Sneakers retro verde y crema en una calle urbana",
        "tags": ["Retro", "Estilo diario", "Streetwear"],
        "reading_time": 4,
        "published_at": "2026-06-24T09:00:00+00:00",
    },
    {
        "slug": "colaboraciones-que-definen-cultura-sneaker",
        "title": "Colaboraciones que ayudaron a definir la cultura sneaker",
        "category": "cultura-sneaker",
        "summary": "Las mejores colaboraciones suman una historia, materiales especiales y una visión clara, no solo un logo distinto.",
        "content": "Una colaboración memorable conecta dos universos de forma natural: deporte, música, diseño, skate o arte. Por eso algunos lanzamientos siguen siendo relevantes años después de su salida.\n\nAntes de decidirte por un par colaborativo, investiga qué cambió realmente frente a la versión regular. Los detalles en materiales, paleta de color, empaque y narrativa suelen contar más que la escasez.\n\nTambién vale la pena preguntarse si el par encaja con tu estilo personal. La mejor compra no es necesariamente la más comentada, sino la que vas a querer usar y cuidar con el tiempo.",
        "image": "assets/img/blog/juaco-blog-cover-06.png",
        "image_alt": "Flat lay editorial de sneakers y bocetos de diseño",
        "tags": ["Colaboraciones", "Diseño", "Cultura sneaker"],
        "reading_time": 5,
        "published_at": "2026-06-19T09:00:00+00:00",
    },
]


def add_posts(apps, schema_editor):
    Category = apps.get_model("store", "BlogCategory")
    Post = apps.get_model("store", "BlogPost")
    for article in POSTS:
        category = Category.objects.get(slug=article["category"])
        Post.objects.update_or_create(
            slug=article["slug"],
            defaults={
                "title": article["title"],
                "category": category,
                "summary": article["summary"],
                "content": article["content"],
                "image": article["image"],
                "image_alt": article["image_alt"],
                "author": "Equipo Juaco Store",
                "tags": article["tags"],
                "reading_time": article["reading_time"],
                "published_at": datetime.fromisoformat(article["published_at"]),
                "is_published": True,
            },
        )


def remove_posts(apps, schema_editor):
    apps.get_model("store", "BlogPost").objects.filter(slug__in=[article["slug"] for article in POSTS]).delete()


class Migration(migrations.Migration):
    dependencies = [("store", "0003_blog_models")]

    operations = [migrations.RunPython(add_posts, remove_posts)]
