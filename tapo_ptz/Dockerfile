ARG BUILD_FROM
FROM ${BUILD_FROM}

ENV PIP_NO_CACHE_DIR=1
RUN apk add --no-cache tzdata \
 && PKGS="pytapo==3.4.27 flask==3.0.3 waitress==3.0.0 requests" \
 && (pip install --only-binary=:all: $PKGS \
     || (apk add --no-cache --virtual .build-deps build-base libffi-dev openssl-dev cargo \
         && pip install $PKGS && apk del .build-deps))

COPY app /app
COPY run.sh /run.sh
RUN chmod a+x /run.sh

CMD [ "/run.sh" ]
