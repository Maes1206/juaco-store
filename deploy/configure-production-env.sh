#!/bin/sh
set -eu

cd /var/www/nexus-sneakers
umask 077

database_password="$(openssl rand -hex 32)"
django_secret_key="$(openssl rand -hex 48)"

{
    printf 'POSTGRES_DB=nexus_sneakers\n'
    printf 'POSTGRES_USER=nexus\n'
    printf 'POSTGRES_PASSWORD=%s\n' "$database_password"
    printf 'DJANGO_SECRET_KEY=%s\n' "$django_secret_key"
    grep -E '^(BOLD_IDENTITY_KEY|BOLD_SECRET_KEY|BOLD_TEST_MODE|DJANGO_EMAIL_BACKEND|EMAIL_HOST|EMAIL_PORT|EMAIL_HOST_USER|EMAIL_HOST_PASSWORD|EMAIL_USE_TLS|EMAIL_USE_SSL|EMAIL_TIMEOUT|DEFAULT_FROM_EMAIL|PASSWORD_RESET_TIMEOUT_SECONDS)=' .env.source
    printf 'BOLD_ALLOW_UNSIGNED_WEBHOOKS=0\n'
    printf 'BOLD_PUBLIC_BASE_URL=https://nexusneaker.store\n'
    printf 'PUBLIC_SITE_URL=https://nexusneaker.store\n'
    printf 'DJANGO_ALLOWED_HOSTS=nexusneaker.store,www.nexusneaker.store,nexus_sneakers_web,localhost,127.0.0.1\n'
    printf 'DJANGO_CSRF_TRUSTED_ORIGINS=https://nexusneaker.store,https://www.nexusneaker.store\n'
    printf 'ADMIN_REGISTRATION_EMAILS=emersonmanquillo@gmail.com,U20242226877@usco.edu.co\n'
    printf 'DJANGO_LOG_LEVEL=INFO\n'
    printf 'AXES_FAILURE_LIMIT=5\n'
    printf 'AXES_COOLOFF_MINUTES=15\n'
} > .env.production

chmod 600 .env.production
rm .env.source
printf 'Environment configured\n'
sed -E 's/=.*/=<configured>/' .env.production
