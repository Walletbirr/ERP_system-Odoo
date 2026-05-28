## Files
- docker-compose.yml: Odoo + Postgres services
- .env: version, port, database credentials
- start-odoo.ps1: helper to start containers
- config/odoo.conf: base Odoo config
- addons/: place custom community modules here

## Start
Run in this folder:

powershell
./start-odoo.ps1

Then open:
http://localhost:8069

## Stop
powershell
docker compose down

## Stop and remove data
powershell
docker compose down -v

## Update Odoo image
1. Set ODOO_VERSION in .env (for example 18.0)
2. Run:

powershell
docker compose pull
docker compose up -d

## Notes
- Change POSTGRES_PASSWORD in .env for real use.
- Change admin_passwd in config/odoo.conf.
- If docker command is not found in a new terminal, reopen VS Code terminal after Docker Desktop install.
