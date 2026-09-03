#!/bin/sh

set -eu

if [ "$#" -gt 0 ]; then
    exec "$@"
fi

process="${FLUIDP_PROCESS:-web}"

case "$process" in
    migrate)
        echo "Aplicando migrations..."
        python manage.py migrate --noinput

        echo "Garantindo a tabela de cache..."
        python manage.py createcachetable

        echo "Preparando Tailwind CSS..."
        python manage.py tailwind install
        python manage.py tailwind build

        echo "Coletando arquivos estáticos..."
        python manage.py collectstatic --noinput --clear
        ;;
    web)
        echo "Iniciando Gunicorn..."
        exec gunicorn sistemadp.wsgi:application \
            --bind 0.0.0.0:8000 \
            --workers "${GUNICORN_WORKERS:-3}" \
            --timeout "${GUNICORN_TIMEOUT:-120}" \
            --access-logfile - \
            --error-logfile -
        ;;
    worker)
        echo "Iniciando worker do Django Q..."
        exec python manage.py qcluster
        ;;
    *)
        echo "FLUIDP_PROCESS inválido: $process" >&2
        exit 2
        ;;
esac
