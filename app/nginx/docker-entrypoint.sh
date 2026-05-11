#!/bin/sh

set -e

sed -i 's/${HOST}/'"${HOST}"'/g' /etc/nginx/conf.d/default.conf

exec "$@"
