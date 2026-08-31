# BH Management Dashboard — Odoo 18 Community

## Overview
Executive reporting dashboard for **BINGET HOLDING PLC** — restricted to CEO/GM level users.

## Sections
| Tab | KPIs Covered |
|-----|-------------|
| 💰 Sales | Revenue, Orders, Trend, Top Customers |
| 📦 Inventory | Stock Value, Qty, Location breakdown, Low stock alerts |
| 🏦 Finance | Invoiced, Receivables, Payables, Monthly trend, Customer Credit, Customer Deposits |
| 🛒 Purchase | PO spend, Top vendors, RFQs |
| 🏭 Manufacturing | MO status, Qty produced, Top products |
| 👥 HR | Headcount, Departments, Gender distribution |

## Installation

### Step 1 — Copy the module
```bash
cp -r bh_management_dashboard /path/to/odoo/custom_addons/
```

### Step 2 — Update addons path
Make sure your `odoo.conf` includes your custom_addons path:
```
addons_path = /usr/lib/python3/dist-packages/odoo/addons,/path/to/custom_addons
```

### Step 3 — Restart Odoo and update apps list
```bash
sudo systemctl restart odoo
```
Then in Odoo: **Settings → Apps → Update Apps List**

### Step 4 — Install the module
Search for **"BH Management Dashboard"** and click Install.

### Step 5 — Assign users
Go to **Settings → Users** → open the CEO/GM user → under **Other** tab, tick **BH Executive / CEO / GM** group.

## Dependencies
- sale_management, stock, account, purchase, mrp, hr

### Optional (soft) dependencies
The Finance tab's **Customer Credit** and **Customer Deposits** sections read
extra `res.partner` fields added by two standalone companion modules. They
are *not* listed in `depends`, so this dashboard installs fine without them —
each section simply shows an "Install the ... module" hint instead of data
until the matching module is installed:

| Section | Needs module |
|---|---|
| Customer Credit | `customer_credit_report` |
| Customer Deposits | `customer_deposit_credit` |

## Chart.js
This module uses Odoo's bundled Chart.js. If charts do not render, ensure Chart.js is loaded
by your Odoo version (it is included by default in Odoo 16+).
