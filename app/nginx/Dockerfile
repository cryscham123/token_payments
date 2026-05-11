FROM nginx

COPY ./default.conf /etc/nginx/conf.d/default.conf

RUN apt-get update && apt-get install -y netcat-openbsd

COPY docker-entrypoint.sh /usr/bin

ENTRYPOINT [ "docker-entrypoint.sh" ]

CMD ["nginx", "-g", "daemon off;"]
