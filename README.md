# ERP Management System

## Overview

This project is a customized Enterprise Resource Planning (ERP) system built on top of Odoo 18 Community Edition.

The system is designed to manage and automate key business operations including accounting, inventory, purchasing, sales, maintenance, human resources, and reporting.

In addition to the standard Odoo functionality, several customizations have been implemented to support specific business requirements, improve reporting capabilities, and enhance the overall user experience.

---

## Features

### Accounting & Finance

- Chart of Accounts Management
- Journal Entries
- Customer Invoices
- Vendor Bills
- Credit Notes
- Debit Notes
- Bank Reconciliation
- Financial Reporting
- Tax Management
- Multi-Journal Support

### Financial Reports

- Trial Balance
- General Ledger
- Partner Ledger
- Cash Book
- Bank Book
- Aged Partner Balance
- Profit & Loss
- Balance Sheet

### Reporting Enhancements

Custom enhancements include:

- Improved Trial Balance presentation
- Report date range support
- Custom financial report layouts
- Additional totals and summaries
- Period-based reporting support

### Inventory Management

- Product Management
- Stock Transfers
- Warehouses
- Inventory Adjustments
- Lot & Serial Number Tracking
- Reordering Rules

### Purchasing

- Request for Quotation (RFQ)
- Purchase Orders
- Vendor Management
- Vendor Bills

### Sales

- Quotations
- Sales Orders
- Customer Management
- Delivery Orders

### Maintenance

- Equipment Management
- Maintenance Requests
- Preventive Maintenance
- Technician Assignment

### Human Resources

- Employee Management
- Departments
- Job Positions
- Attendance Integration

---

## Technology Stack

### Backend

- Python 3
- Odoo 18 Community

### Database

- PostgreSQL

### Frontend

- XML (QWeb)
- Owl Framework
- Bootstrap

### Reporting

- QWeb PDF Reports
- XLSX Export Support

### Deployment

- Docker
- Linux (Ubuntu)
- Nginx (Optional)

---

## Installation

### Clone Repository

```bash
git clone https://github.com/Walletbirr/ERP_system-Odoo.git
cd ERP_System_Odoo
```

### Install Dependencies

```bash
pip install -r requirements.txt
```

### Configure PostgreSQL

Create a PostgreSQL database:

```bash
createdb erp_db
```

### Run Odoo

```bash
odoo-bin -c odoo.conf
```

### Install Modules

Navigate to:

```text
Apps → Update Apps List
```

Install the required custom modules.

---

## Future Enhancements

Planned improvements include:

- Advanced Dashboard Analytics
- KPI Monitoring
- Multi-Company Reporting
- Mobile Application Integration
- Approval Workflows
- API Integrations

## License

This project is intended for internal business use and customization purposes.

Built using Odoo 18 Community Edition.
