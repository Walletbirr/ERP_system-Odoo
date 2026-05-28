FROM odoo:18

USER root

# Install qifparse (required by base_accounting_kit)
# We use --break-system-packages because Odoo 18 Docker image enforces PEP 668
RUN pip install --no-cache-dir qifparse --break-system-packages

USER odoo