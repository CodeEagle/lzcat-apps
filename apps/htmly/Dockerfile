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
    libonig-dev \
    libpng-dev \
    libwebp-dev \
    libxml2-dev \
    libzip-dev \
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

RUN php <<'PHP'
<?php
$dist = getenv('HTMLY_DIST');

$path = $dist . '/install.php';
$text = file_get_contents($path);
if ($text === false) {
    fwrite(STDERR, "failed to read install.php\n");
    exit(1);
}
$old = <<<'OLD'
        if (!is__writable("./")) {
            $message->error('no permission to write in the Directory.');
        }
OLD;
$new = <<<'NEW'
        foreach (array("./config", "./content", "./cache") as $path) {
            if (!is__writable($path)) {
                $message->error('no permission to write in ' . $path . '.');
            }
        }
NEW;
if (strpos($text, $old) === false) {
    fwrite(STDERR, "install.php writable check block not found\n");
    exit(1);
}
$text = str_replace($old, $new, $text);
$old = <<<'OLD'
        $dir = trim(dirname(substr($_SERVER["SCRIPT_FILENAME"], strlen($_SERVER["DOCUMENT_ROOT"]))), '/');
        if ($dir == '.' || $dir == '..') {
            $dir = '';
        }
        $port = '';
        if ($_SERVER["SERVER_PORT"] != "80" && $_SERVER["SERVER_PORT"] != "443") {
            $port = ':' . $_SERVER["SERVER_PORT"];
        }
        $scheme = isset($_SERVER['HTTPS']) && $_SERVER['HTTPS'] != 'off' ? 'https' : 'http';
        if ($dir === '') {
            $this->siteUrl = $scheme . '://' . trim($_SERVER['SERVER_NAME'], "/") . $port . "/";
            return;
        }
        $this->siteUrl = $scheme . '://' . trim($_SERVER['SERVER_NAME'], "/") . $port . "/" . $dir . '/';
OLD;
$new = <<<'NEW'
        $dir = trim(dirname(substr($_SERVER["SCRIPT_FILENAME"], strlen($_SERVER["DOCUMENT_ROOT"]))), '/');
        if ($dir == '.' || $dir == '..') {
            $dir = '';
        }
        $forwardedProto = isset($_SERVER["HTTP_X_FORWARDED_PROTO"]) ? trim(explode(',', $_SERVER["HTTP_X_FORWARDED_PROTO"])[0]) : '';
        $forwardedHost = isset($_SERVER["HTTP_X_FORWARDED_HOST"]) ? trim(explode(',', $_SERVER["HTTP_X_FORWARDED_HOST"])[0]) : '';
        $forwardedPort = isset($_SERVER["HTTP_X_FORWARDED_PORT"]) ? trim(explode(',', $_SERVER["HTTP_X_FORWARDED_PORT"])[0]) : '';
        $host = $forwardedHost !== '' ? $forwardedHost : (isset($_SERVER["HTTP_HOST"]) ? trim($_SERVER["HTTP_HOST"], "/") : trim($_SERVER["SERVER_NAME"], "/"));
        $scheme = $forwardedProto !== '' ? $forwardedProto : ((isset($_SERVER['HTTPS']) && $_SERVER['HTTPS'] != 'off') ? 'https' : 'http');
        $serverPort = $forwardedPort !== '' ? $forwardedPort : $_SERVER["SERVER_PORT"];
        $port = '';
        if ($serverPort != "80" && $serverPort != "443" && strpos($host, ':') === false) {
            $port = ':' . $serverPort;
        }
        if ($dir === '') {
            $this->siteUrl = $scheme . '://' . $host . $port . "/";
            return;
        }
        $this->siteUrl = $scheme . '://' . $host . $port . "/" . $dir . '/';
NEW;
if (strpos($text, $old) === false) {
    fwrite(STDERR, "install.php generateSiteUrl block not found\n");
    exit(1);
}
$text = str_replace($old, $new, $text);
$text = str_replace('unlink(__FILE__);', '@unlink(__FILE__);', $text, $count);
if ($count !== 1) {
    fwrite(STDERR, "install.php unlink call not patched\n");
    exit(1);
}
file_put_contents($path, $text);

$path = $dist . '/index.php';
$text = file_get_contents($path);
if ($text === false) {
    fwrite(STDERR, "failed to read index.php\n");
    exit(1);
}
$old = <<<'OLD'
$config_file = 'config/config.ini';
require 'system/vendor/autoload.php';
require 'system/htmly.php';
OLD;
$new = <<<'NEW'
$config_file = 'config/config.ini';
if (!file_exists($config_file) && file_exists('install.php')) {
    header('Location: install.php');
    exit();
}
require 'system/vendor/autoload.php';
require 'system/htmly.php';
NEW;
if (strpos($text, $old) === false) {
    fwrite(STDERR, "index.php bootstrap block not found\n");
    exit(1);
}
$text = str_replace($old, $new, $text);
file_put_contents($path, $text);

$path = $dist . '/system/includes/functions.php';
$text = file_get_contents($path);
if ($text === false) {
    fwrite(STDERR, "failed to read functions.php\n");
    exit(1);
}
$old = <<<'OLD'
function safe_html($string)
{
    $string = htmlspecialchars($string, ENT_QUOTES);
OLD;
$new = <<<'NEW'
function safe_html($string)
{
    if ($string === null) {
        $string = '';
    }
    $string = htmlspecialchars($string, ENT_QUOTES);
NEW;
if (strpos($text, $old) === false) {
    fwrite(STDERR, "functions.php safe_html block not found\n");
    exit(1);
}
$text = str_replace($old, $new, $text);

$old = <<<'OLD'
function blog_description()
{
    return config('blog.description');
}
OLD;
$new = <<<'NEW'
function blog_description()
{
    return config('blog.description') ?? '';
}
NEW;
if (strpos($text, $old) === false) {
    fwrite(STDERR, "functions.php blog_description block not found\n");
    exit(1);
}
$text = str_replace($old, $new, $text);
file_put_contents($path, $text);

$path = $dist . '/system/htmly.php';
$text = file_get_contents($path);
if ($text === false) {
    fwrite(STDERR, "failed to read system/htmly.php\n");
    exit(1);
}
$old = <<<'OLD'
// Load theme settings
theme_settings();

// The front page of the blog
get('/index', function () {
OLD;
$new = <<<'NEW'
// Load theme settings
theme_settings();

if (!config('views.root') && file_exists('install.php')) {
    header('Location: ' . site_url() . 'install.php');
    exit();
}

// The front page of the blog
get('/index', function () {
NEW;
if (strpos($text, $old) === false) {
    fwrite(STDERR, "system/htmly.php install guard block not found\n");
    exit(1);
}
$text = str_replace($old, $new, $text);
file_put_contents($path, $text);
PHP

RUN rm -rf /var/www/html/* \
    && cp -a "${HTMLY_DIST}"/. /var/www/html/ \
    && chown -R www-data:www-data /var/www/html

EXPOSE 80

LABEL org.opencontainers.image.title="HTMLy" \
      org.opencontainers.image.description="Databaseless PHP blogging platform and flat-file CMS" \
      org.opencontainers.image.source="https://github.com/danpros/htmly" \
      org.opencontainers.image.version="${BUILD_VERSION}"
