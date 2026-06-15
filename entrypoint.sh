#!/bin/bash

set -e

echo "Instalando dependências do Tailwind..."
python manage.py tailwind install --no-input

echo "Fazendo o build do Tailwind CSS..."
python manage.py tailwind build --no-input

echo "Aplicando migrações do banco de dados..."
python manage.py migrate --noinput

echo "Coletando arquivos estáticos para a pasta compartilhada..."
python manage.py collectstatic --noinput

echo "Iniciando o servidor Gunicorn..."
exec gunicorn sistemadp.wsgi:application --bind 0.0.0.0:8000 --workers 3
