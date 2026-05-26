#!/bin/sh

set -e

HOST="${HOST:-localhost}"
sed -i 's/${HOST}/'"${HOST}"'/g' /etc/nginx/conf.d/default.conf

exec "$@"
