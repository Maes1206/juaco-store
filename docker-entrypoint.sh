#!/bin/sh
set -e

# Los volumenes Docker nuevos se montan como root:root. Preparamos el volumen
# persistente y luego reiniciamos el entrypoint como el usuario sin privilegios.
if [ "$(id -u)" = "0" ]; then
    mkdir -p /app/media
    chown -R django:django /app/media
    exec setpriv --reuid=django --regid=django --init-groups "$0" "$@"
fi

python manage.py migrate --noinput

if [ "${DJANGO_COLLECTSTATIC:-1}" = "1" ]; then
    python manage.py collectstatic --noinput
fi

exec "$@"
