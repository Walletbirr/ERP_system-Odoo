# Binget Stock Dashboard (Odoo 18)

Premium **Stock** dashboard + unified **Products** catalog.

## Install (new database)

1. Copy `binget_stock_dashboard` into your addons path (e.g. `extra-addons/`)
2. Restart Odoo
3. Apps → Update Apps List
4. Search **Binget Stock Dashboard** → **Activate**
5. Hard-refresh the browser (`Ctrl+Shift+R`) or log out/in

**What you get**
- **Inventory → Stock** — warehouse KPI cards, drill-down, serial/lot expand
- **Inventory / Sales / Purchase → Products** — same premium catalog (no duplicate tab)

## Uninstall

Apps → Binget Stock Dashboard → **Uninstall**

Original Products menus are restored automatically. Do not only delete the folder.

## Branding

Edit gold/dark colors at the top of:

- `static/src/scss/stock_dashboard.scss`
- `static/src/scss/products_gallery.scss`

## Requirements

- Odoo 18
- Modules: `stock`, `product`, `web`
- Optional: `sale`, `purchase` (Products menus retargeted when present)
