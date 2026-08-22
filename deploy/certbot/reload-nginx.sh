#!/bin/sh
set -eu

docker exec invoiceplane-nginx nginx -t
docker exec invoiceplane-nginx nginx -s reload
