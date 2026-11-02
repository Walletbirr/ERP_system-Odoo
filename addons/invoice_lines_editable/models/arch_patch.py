"""Pure-lxml helper (no Odoo import) so it can be tested on its own."""
from lxml import etree

LINE_LOCK = "display_type in ('line_section', 'line_note')"


def patch_move_form_arch(arch):
    """Patch the merged account.move form arch.

    1. Debit / Credit of the Journal Items list are editable on every line
       except sections and notes (standard Odoo locks 'product' lines on
       invoices, and every line added with "Add a line" is a product line).
    2. A "Manual Journal Items" switch is added on
       top of the Journal Items tab.

    Nothing fails if a node is missing (other modules may have changed the
    form): that part is simply skipped. Returns the number of nodes touched.
    """
    touched = 0
    for node in arch.xpath(
        "//field[@name='line_ids']/list/field[@name='debit' or @name='credit']"
    ):
        node.set('readonly', LINE_LOCK)
        touched += 1

    pages = arch.xpath("//page[@name='aml_tab']")
    if pages and not pages[0].xpath(".//field[@name='manual_journal_items']"):
        group = etree.Element('group')
        etree.SubElement(
            group, 'field',
            name='manual_journal_items',
            readonly="state != 'draft'",
            invisible="move_type == 'entry'",
        )
        pages[0].insert(0, group)
        touched += 1
    return touched
