ARG SOURCE_VERSION=v3.1.1
ARG BUILD_VERSION=3.1.1

FROM php:8.2-apache-bookworm

ARG SOURCE_VERSION
ARG BUILD_VERSION

ENV HTMLY_DIST=/opt/htmly-dist

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    libfreetype6-dev \
    libicu-dev \
    libjpeg62-turbo-dev \
    libpng-dev \
    libwebp-dev \
    libxml2-dev \
    libzip-dev \
    patch \
    unzip \
    && docker-php-ext-configure gd --with-freetype --with-jpeg --with-webp \
    && docker-php-ext-install -j"$(nproc)" gd intl mbstring xml zip \
    && a2enmod rewrite expires headers deflate \
    && sed -ri '/<Directory \/var\/www\/>/,/<\/Directory>/ s/AllowOverride None/AllowOverride All/' /etc/apache2/apache2.conf \
    && printf 'ServerName localhost\n' > /etc/apache2/conf-available/server-name.conf \
    && a2enconf server-name \
    && rm -rf /var/lib/apt/lists/*

WORKDIR ${HTMLY_DIST}

RUN curl -fsSL "https://codeload.github.com/danpros/htmly/tar.gz/refs/tags/${SOURCE_VERSION}" \
    | tar -xz --strip-components=1 -C "${HTMLY_DIST}"

COPY install.php.patch /tmp/install.php.patch

RUN patch -d "${HTMLY_DIST}" -p0 < /tmp/install.php.patch \
    && rm -rf /var/www/html/* \
    && cp -a "${HTMLY_DIST}"/. /var/www/html/ \
    && chown -R www-data:www-data /var/www/html

EXPOSE 80

LABEL org.opencontainers.image.title="HTMLy" \
      org.opencontainers.image.description="Databaseless PHP blogging platform and flat-file CMS" \
      org.opencontainers.image.source="https://github.com/danpros/htmly" \
      org.opencontainers.image.version="${BUILD_VERSION}"
