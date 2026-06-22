# Database Selector Branding

Customizes the name and logo shown on the `/web/database/selector` and
`/web/database/manager` pages — the page shown **before** any database is
selected (e.g. the "list of databases" page you see at `localhost:8069`
when there are multiple databases, or when `list_db` is enabled).

## Why environment variables instead of Settings?

This page is rendered before any specific database is chosen, so there is
no `res.config.settings` / `ir.config_parameter` to read from — those only
exist _inside_ a database. The only thing available at this stage that
isn't tied to one specific database is the server process's environment,
so that's what this module uses.

## Configuration

1. Replace `static/img/my_logo.png` in this module with your own logo
   (keep the same filename, or change `WEB_DB_SELECTOR_BRAND_LOGO` below
   to point at a different static path).

2. Set these environment variables for the Odoo container, e.g. in your
   `docker-compose.yml`:

   ```yaml
   services:
     odoo:
       environment:
         - WEB_DB_SELECTOR_BRAND_NAME=Binget holding PLC
         - WEB_DB_SELECTOR_BRAND_LOGO=/web_database_selector_branding/static/img/my_logo.png
   ```

3. Restart the container:

   ```bash
   docker compose up -d --force-recreate odoo
   ```

   (or `docker restart <container_name>` if you're not using compose env
   changes — note plain `docker restart` will NOT pick up new environment
   variables added to docker-compose.yml; you need to recreate the
   container for env var changes to take effect)

4. Install/upgrade this module from Apps.

If the environment variables are not set, Odoo's default "Odoo" title and
logo are used — nothing breaks.

## Notes

- `WEB_DB_SELECTOR_BRAND_LOGO` can be any URL Odoo can serve: a path into
  this module's `static/` folder (recommended), a path into another
  module's `static/` folder, or an absolute external URL.
- This only affects the database selector/manager pages, not the regular
  Odoo login page or backend — those are separate templates.
