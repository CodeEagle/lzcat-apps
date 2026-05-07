# PressYard

LazyCat migration of [CodeMasters999/PressYard](https://github.com/CodeMasters999/PressYard).

## Description

PressYard creates local WordPress setups with isolated containers, automatic installs, and project-based hostnames for easy development and testing.

## Status: Waiting for Human Review

This migration is blocked pending human operator decision on the following issues:

1. **No LICENSE file** — The upstream repository has no LICENSE file. Legal risk is unquantified. A human must decide whether to proceed.
2. **Source code inaccessible** — Project source is packaged inside ZIP archives in the `pinkweed/` directory (`Press_Yard_1.5-alpha.2.zip`). The repository root contains an unrelated Roblox Lua script (`AftermathCodemasters`), raising questions about repo integrity.
3. **Tool vs. service** — PressYard is described as a local development tool that creates WordPress environments. It may rely on Traefik project-based hostnames and host-level DNS manipulation that won't work in LazyCat's containerized environment. A human must confirm the migration scope.

## Upstream Access

- Upstream repo: https://github.com/CodeMasters999/PressYard
- Latest release: Press_Yard_1.5-alpha.2.zip (in `pinkweed/` directory)
- Topics: Docker, Docker Compose, PHP, WordPress, MariaDB, Traefik, PowerShell

## Services (best-effort scaffold)

| Service | Image | Port | Purpose |
|---------|-------|------|---------|
| wordpress | wordpress:latest (official) | 80 | WordPress application |
| db | mariadb:10.11 (official) | 3306 (internal) | MariaDB database |

## Data Paths

| Container Path | Host Path | Purpose |
|----------------|-----------|---------|
| `/var/www/html/wp-content` | `/lzcapp/var/data/pressyard/wp-content` | WordPress uploads, plugins, themes |
| `/var/lib/mysql` | `/lzcapp/var/db/pressyard/mysql` | MariaDB database files |

## Environment Variables

| Variable | Service | Description |
|----------|---------|-------------|
| `WORDPRESS_DB_HOST` | wordpress | Database host (db:3306) |
| `WORDPRESS_DB_USER` | wordpress | Database username |
| `WORDPRESS_DB_PASSWORD` | wordpress | Database password |
| `WORDPRESS_DB_NAME` | wordpress | Database name |
| `MYSQL_DATABASE` | db | Database to create |
| `MYSQL_USER` | db | Database user |
| `MYSQL_PASSWORD` | db | Database password |
| `MYSQL_ROOT_PASSWORD` | db | MariaDB root password |

## Login

WordPress admin is at `/wp-admin`. First login requires completing the WordPress installation wizard at `/wp-admin/install.php`.

## Notes for Human Reviewer

Before unblocking this migration:
1. Decide on license risk (no LICENSE file)
2. Download and extract the ZIP to inspect actual docker-compose.yml, Dockerfile, and entrypoint scripts
3. Confirm whether PressYard has a web management interface (separate from WordPress itself)
4. Verify ports, data paths, and whether Traefik hostname routing is required
5. Consider whether this is a single-WordPress deployment or a multi-site management tool
6. Update passwords to use `$random(len=20)` deploy params before publishing to store
