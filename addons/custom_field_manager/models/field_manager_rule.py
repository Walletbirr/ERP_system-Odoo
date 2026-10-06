# -*- coding: utf-8 -*-
import logging

from lxml import etree

from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# Values Odoo accepts as "true" for a modifier attribute.
TRUE_VALUES = ("1", "True", "true")


class FieldManagerRule(models.Model):
    _name = "field.manager.rule"
    _description = "UI Element Visibility & Label Rule"
    _inherit = ["mail.thread"]
    _order = "target_type, model_id, field_id, menu_id, action_id, id"

    name = fields.Char(compute="_compute_name", store=True)

    target_type = fields.Selection(
        [
            ("field", "Field"),
            ("tab", "Notebook Tab"),
            ("button", "Button"),
            ("menu", "Menu Item (Apps & sub-menus)"),
            ("action", "Window Action / Page Title"),
            ("selection_option", "Selection / Radio Option"),
        ],
        required=True,
        default="field",
        tracking=True,
        help="What kind of UI element to control:\n"
             "• Field — any field on a model\n"
             "• Notebook Tab — a whole page/tab inside a form\n"
             "• Button — header or smart/stat button\n"
             "• Menu Item — any sidebar or Apps-switcher entry, including nested sub-menus\n"
             "• Window Action / Page Title — the title shown at the top of list & form views\n"
             "• Selection / Radio Option — individual values of a selection field "
             "(e.g. Send / Receive on Customer Payments)",
    )

    model_id = fields.Many2one(
        "ir.model",
        string="Model",
        ondelete="cascade",
        tracking=True,
        help="The model whose form/list you want to control. "
             "Required for Field / Tab / Button / Selection Option. "
             "Optional for Action (helps filtering).",
    )
    model_name = fields.Char(
        string="Technical Model Name", related="model_id.model", store=True, readonly=True,
    )

    # --- Field target ---
    field_id = fields.Many2one(
        "ir.model.fields",
        string="Field",
        domain="[('model_id', '=', model_id)]",
        ondelete="cascade",
        tracking=True,
        help="The field to hide / restrict / rename on that model.",
    )

    # --- Tab target ---
    tab_label = fields.Char(
        string="Tab Label (as shown on screen)",
        tracking=True,
        help="Type the tab's current visible label EXACTLY as it appears on the form, "
             "e.g. 'Settings' or 'Private Information'. Case-sensitive.",
    )

    # --- Button target ---
    button_label = fields.Char(
        string="Button Label (as shown on screen)",
        tracking=True,
        help="Type the button's current visible text EXACTLY as it appears. "
             "Case-sensitive. Leave empty if you filled Technical Name instead.",
    )
    button_name = fields.Char(
        string="Technical Name (optional, more precise)",
        tracking=True,
        help="The button's technical 'name' attribute (method or action). "
             "More reliable when several buttons share the same visible text.",
    )

    # --- Menu target (any depth: Apps → sub → sub-sub → deeper) ---
    menu_id = fields.Many2one(
        "ir.ui.menu",
        string="Menu Item",
        ondelete="cascade",
        tracking=True,
        context={"active_test": False},
        help="Select ANY menu at any depth: top-level Apps, sub-menus, sub-sub-menus "
             "and deeper (e.g. Accounting → Accounting → Journal Entries). "
             "Search by short name or part of the full path. "
             "Already-hidden menus are listed too so you can restore them.",
    )
    menu_complete_name = fields.Char(
        related="menu_id.complete_name",
        string="Full Menu Path",
        readonly=True,
        help="Full hierarchical path: Parent / Child / Sub-child / …",
    )
    menu_parent_id = fields.Many2one(
        related="menu_id.parent_id",
        string="Parent Menu",
        readonly=True,
    )
    menu_depth = fields.Integer(
        string="Menu Depth",
        compute="_compute_menu_depth",
        help="0 = top-level App, 1 = sub-menu, 2 = sub-sub-menu, 3+ = deeper.",
    )
    menu_original_name = fields.Char(
        string="Original Menu Name",
        readonly=True,
        copy=False,
    )
    menu_original_active = fields.Boolean(
        string="Original Menu Active",
        readonly=True,
        copy=False,
    )

    # --- Action / Page Title target ---
    action_id = fields.Many2one(
        "ir.actions.act_window",
        string="Window Action",
        ondelete="cascade",
        tracking=True,
        help="Select the window action whose title appears at the top of the page "
             "(e.g. 'Journal Entries', 'Customer Payments', 'Customers').",
    )
    action_original_name = fields.Char(
        string="Original Action Name",
        readonly=True,
        copy=False,
    )

    # --- Selection / Radio Option target ---
    selection_field_id = fields.Many2one(
        "ir.model.fields",
        string="Selection Field",
        domain="[('model_id', '=', model_id), ('ttype', 'in', ('selection', 'reference'))]",
        ondelete="cascade",
        tracking=True,
        help="Pick a Selection or Radio field (e.g. Payment Type that shows Send / Receive).",
    )
    selection_id = fields.Many2one(
        "ir.model.fields.selection",
        string="Option (value)",
        domain="[('field_id', '=', selection_field_id)]",
        ondelete="cascade",
        tracking=True,
        help="The concrete option to rename or hide (e.g. 'Send' or 'Receive').",
    )
    selection_original_name = fields.Char(
        string="Original Option Label",
        readonly=True,
        copy=False,
    )
    selection_original_sequence = fields.Integer(
        string="Original Sequence",
        readonly=True,
        copy=False,
    )

    # --- Common action & label ---
    action = fields.Selection(
        [
            ("hide", "Hide"),
            ("readonly", "Make Read-only"),
            ("required", "Make Required"),
            ("rename", "Rename"),
        ],
        required=True,
        default="hide",
        tracking=True,
        help="Fields support Hide / Read-only / Required / Rename.\n"
             "Tabs, Buttons, Menus and Selection Options support Hide / Rename.\n"
             "Window Actions (page titles) support Rename only.",
    )
    new_label = fields.Char(
        string="New Label",
        tracking=True,
        help="The new text to display when Action = Rename.",
    )

    view_type = fields.Selection(
        [
            ("form", "Form"),
            ("list", "List / Tree (table columns)"),
            ("kanban", "Kanban"),
        ],
        default="form",
        tracking=True,
        help="Which view type to apply this rule to.\n"
             "• Form — hide/rename fields, tabs, buttons on the form\n"
             "• List / Tree — manage table columns (hide or rename column headers)\n"
             "• Kanban — kanban card fields\n"
             "Tabs only exist on Form views. Not used for Menu / Action / Selection Option.",
    )

    reason = fields.Char(
        string="Business Reason",
        tracking=True,
        help="Why is this being changed? Visible in the audit trail.",
    )

    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("applied", "Applied"),
            ("reverted", "Reverted"),
        ],
        default="draft",
        tracking=True,
        readonly=True,
    )

    generated_view_id = fields.Many2one(
        "ir.ui.view",
        readonly=True,
        string="Generated View",
        help="The view record created to enforce Field / Tab / Button rules. "
             "Managed automatically.",
    )

    result_info = fields.Text(
        string="Last Apply Report",
        readonly=True,
        copy=False,
        help="What the last Apply actually did: how many elements were matched, "
             "in which views, and whether the final merged view was verified.",
    )

    applied_by = fields.Many2one("res.users", readonly=True)
    applied_on = fields.Datetime(readonly=True)
    active = fields.Boolean(default=True)

    # ------------------------------------------------------------------
    # Compute / Onchange / Constraints
    # ------------------------------------------------------------------
    @api.depends(
        "model_id", "field_id", "tab_label", "button_label", "button_name",
        "menu_id", "action_id", "selection_field_id", "selection_id",
        "target_type", "action", "view_type", "new_label",
    )
    def _compute_name(self):
        for rec in self:
            action_label = dict(rec._fields["action"].selection).get(rec.action, "")
            view_label = dict(rec._fields["view_type"].selection).get(rec.view_type, "")
            if rec.target_type == "field" and rec.model_id and rec.field_id:
                rec.name = "%s / %s → %s (%s)" % (
                    rec.model_id.name,
                    rec.field_id.field_description or rec.field_id.name,
                    action_label,
                    view_label,
                )
            elif rec.target_type == "tab" and rec.model_id and rec.tab_label:
                rec.name = "%s / Tab \"%s\" → %s" % (
                    rec.model_id.name, rec.tab_label, action_label,
                )
            elif rec.target_type == "button" and rec.model_id and (
                rec.button_label or rec.button_name
            ):
                rec.name = "%s / Button \"%s\" → %s (%s)" % (
                    rec.model_id.name,
                    rec.button_label or rec.button_name,
                    action_label,
                    view_label,
                )
            elif rec.target_type == "menu" and rec.menu_id:
                rec.name = "Menu \"%s\" → %s" % (rec.menu_id.complete_name or rec.menu_id.name, action_label)
            elif rec.target_type == "action" and rec.action_id:
                rec.name = "Action \"%s\" → %s" % (rec.action_id.name, action_label)
            elif rec.target_type == "selection_option" and rec.selection_id:
                fld = rec.selection_field_id.field_description or (
                    rec.selection_field_id.name if rec.selection_field_id else ""
                )
                rec.name = "%s / Option \"%s\" on %s → %s" % (
                    rec.model_id.name if rec.model_id else "",
                    rec.selection_id.name,
                    fld,
                    action_label,
                )
            else:
                rec.name = _("New Rule")

    @api.depends("menu_id", "menu_id.parent_id")
    def _compute_menu_depth(self):
        """0 = top-level App, 1 = first submenu, 2 = sub-sub-menu, etc."""
        for rec in self:
            depth = 0
            menu = rec.menu_id
            # Walk up the parent chain (safety limit avoids cycles)
            seen = set()
            while menu and menu.parent_id and menu.id not in seen:
                seen.add(menu.id)
                depth += 1
                menu = menu.parent_id
            rec.menu_depth = depth

    @api.onchange("model_id")
    def _onchange_model_id(self):
        self.field_id = False
        self.selection_field_id = False
        self.selection_id = False
        if self.target_type == "action" and self.model_id:
            return {
                "domain": {
                    "action_id": [("res_model", "=", self.model_id.model)],
                }
            }

    @api.onchange("selection_field_id")
    def _onchange_selection_field_id(self):
        self.selection_id = False

    @api.onchange("target_type")
    def _onchange_target_type(self):
        self.field_id = False
        self.tab_label = False
        self.button_label = False
        self.button_name = False
        self.menu_id = False
        self.action_id = False
        self.selection_field_id = False
        self.selection_id = False
        if self.target_type == "tab":
            self.view_type = "form"
        if self.target_type in ("tab", "button", "menu", "action", "selection_option"):
            if self.action in ("readonly", "required"):
                self.action = "hide"
        if self.target_type == "action":
            # A page title cannot be "hidden" (the action name is mandatory).
            self.action = "rename"
        if self.target_type in ("menu", "action", "selection_option"):
            self.view_type = False
            if self.target_type in ("menu", "action"):
                self.model_id = False

    @api.constrains(
        "target_type", "action", "field_id", "tab_label", "button_label",
        "button_name", "menu_id", "action_id", "view_type", "new_label",
        "model_id", "selection_field_id", "selection_id",
    )
    def _check_consistency(self):
        for rec in self:
            if rec.target_type == "field":
                if not rec.model_id:
                    raise UserError(_("Please select a Model."))
                if not rec.field_id:
                    raise UserError(_("Please select a Field."))
                if not rec.view_type:
                    raise UserError(_("Please select a View Type."))
            elif rec.target_type == "tab":
                if not rec.model_id:
                    raise UserError(_("Please select a Model."))
                if not rec.tab_label:
                    raise UserError(_("Please type the Tab Label."))
                if rec.action in ("readonly", "required"):
                    raise UserError(_(
                        "Tabs only support 'Hide' or 'Rename'."
                    ))
                if rec.view_type != "form":
                    raise UserError(_("Tabs only exist on Form views."))
            elif rec.target_type == "button":
                if not rec.model_id:
                    raise UserError(_("Please select a Model."))
                if not rec.button_label and not rec.button_name:
                    raise UserError(_(
                        "Please type the Button Label or the Technical Name."
                    ))
                if rec.action in ("readonly", "required"):
                    raise UserError(_(
                        "Buttons only support 'Hide' or 'Rename'."
                    ))
                if not rec.view_type:
                    raise UserError(_("Please select a View Type."))
            elif rec.target_type == "menu":
                if not rec.menu_id:
                    raise UserError(_("Please select a Menu Item."))
                if rec.action in ("readonly", "required"):
                    raise UserError(_(
                        "Menu Items only support 'Hide' or 'Rename'."
                    ))
            elif rec.target_type == "action":
                if not rec.action_id:
                    raise UserError(_("Please select a Window Action."))
                if rec.action != "rename":
                    raise UserError(_(
                        "Window Actions / Page Titles only support 'Rename'. "
                        "A page title cannot be hidden; to remove a screen from the "
                        "UI, hide its Menu Item instead."
                    ))
            elif rec.target_type == "selection_option":
                if not rec.model_id:
                    raise UserError(_("Please select a Model."))
                if not rec.selection_field_id:
                    raise UserError(_("Please select a Selection Field."))
                if not rec.selection_id:
                    raise UserError(_("Please select the Option to manage."))
                if rec.action in ("readonly", "required"):
                    raise UserError(_(
                        "Selection Options only support 'Hide' or 'Rename'."
                    ))
            if rec.action == "rename" and not rec.new_label:
                raise UserError(_("Please enter the New Label to rename to."))

    # ------------------------------------------------------------------
    # Core engine
    # ------------------------------------------------------------------
    def action_apply(self):
        for rule in self:
            if rule.state == "applied":
                continue
            rule._apply_one()
        return True

    def action_reapply(self):
        """Revert then apply again (e.g. after a module upgrade or after
        installing a module that adds new copies of the same element)."""
        for rule in self:
            if rule.state != "applied":
                continue
            rule.action_revert()
            rule.action_apply()
        return True

    def _apply_one(self):
        self.ensure_one()
        if self.target_type == "menu":
            return self._apply_menu()
        if self.target_type == "action":
            return self._apply_action()
        if self.target_type == "selection_option":
            return self._apply_selection_option()
        return self._apply_view_rule()

    # ------------------------------------------------------------------
    # XPath helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _xpath_literal(value):
        """Safe XPath 1.0 string literal even when value contains both quote types."""
        if value is None:
            value = ""
        if "'" not in value:
            return "'%s'" % value
        if '"' not in value:
            return '"%s"' % value
        parts = value.split("'")
        return "concat('" + "', \"'\", '".join(parts) + "')"

    def _identity_predicate(self, node):
        """XPath predicate built from the most identifying attribute, or ''."""
        for attr in ("id", "name", "for"):
            val = node.get(attr)
            if val:
                return "@%s=%s" % (attr, self._xpath_literal(val))
        return ""

    def _stable_xpath(self, tree, node):
        """Return an XPath that selects exactly ``node`` inside ``tree``.

        Odoo's view inheritance only ever modifies the FIRST node an xpath
        matches, so when an element appears several times (e.g. two tabs
        with the same ``name``, or a field repeated in a form) every copy
        needs its own, unambiguous locator. The locator is anchored on the
        closest ancestor that is uniquely identifiable by ``id`` / ``name``
        / ``for`` and falls back to positional steps, so it keeps working
        when unrelated modules add elements elsewhere in the view.
        """
        steps = []
        cur = node
        while cur is not None:
            pred = self._identity_predicate(cur)
            if pred:
                anchor = "//%s[%s]" % (cur.tag, pred)
                found = tree.xpath(anchor)
                if len(found) == 1 and found[0] is cur:
                    return anchor + "".join(reversed(steps))
            parent = cur.getparent()
            if parent is None:  # reached the root element
                return "/" + cur.tag + "".join(reversed(steps))
            siblings = [c for c in parent if isinstance(c.tag, str) and c.tag == cur.tag]
            if pred:
                same = [c for c in siblings if self._identity_predicate(c) == pred]
                step = "/%s[%s]" % (cur.tag, pred)
                if len(same) > 1:
                    step += "[%d]" % (same.index(cur) + 1)
            else:
                step = "/%s" % cur.tag
                if len(siblings) > 1:
                    step += "[%d]" % (siblings.index(cur) + 1)
            steps.append(step)
            cur = parent
        return None  # pragma: no cover

    # ------------------------------------------------------------------
    # View discovery
    # ------------------------------------------------------------------
    def _get_base_views(self, view_type=None, model_name=None):
        """Return the *primary* views of the model that may actually be displayed.

        Includes:
        - all primary views of that type
        - the default view returned by get_view()
        - views linked from window actions (so action-specific forms are covered)
        """
        view_type = view_type or self.view_type
        model_name = model_name or self.model_id.model
        View = self.env["ir.ui.view"]
        bases = View.browse()

        # 1) Primary views
        bases |= View.search([
            ("model", "=", model_name),
            ("type", "=", view_type),
            ("mode", "=", "primary"),
        ], order="priority, id")

        # 2) Default view from get_view (what the UI uses when no view_id is forced)
        try:
            info = self.env[model_name].get_view(view_type=view_type)
            if info.get("id"):
                bases |= View.browse(info["id"])
        except Exception:
            pass

        # 3) Views referenced by window actions for this model
        actions = self.env["ir.actions.act_window"].sudo().search([
            ("res_model", "=", model_name),
        ])
        wanted_modes = (view_type, "tree") if view_type == "list" else (view_type,)
        for act in actions:
            if act.view_id and act.view_id.type == view_type:
                bases |= act.view_id
            for av in act.view_ids:
                if av.view_id and av.view_mode in wanted_modes:
                    bases |= av.view_id

        # 4) Fallback: any view of that type
        if not bases:
            bases = View.search([
                ("model", "=", model_name),
                ("type", "=", view_type),
            ], order="priority, id", limit=20)

        # Extensions can only be attached to a primary root: map every
        # view to its primary ancestor and de-duplicate, keeping order.
        result = View.browse()
        for view in bases:
            root = view
            while root.mode != "primary" and root.inherit_id:
                root = root.inherit_id
            if root.mode == "primary":
                result |= root
        return result

    def _combined_tree(self, view):
        """Raw, fully merged arch of a primary view as an lxml element.

        Unlike ``get_view()`` this does NOT drop nodes the current user
        has no group for, so every copy of an element is visible to us.

        ``load_all_views`` makes the merge include views created at run time
        (like the ones this module generates) even while Odoo is in the
        middle of a module upgrade, when it would otherwise ignore every
        view that has no XML id.
        """
        return view.sudo().with_context(load_all_views=True)._get_combined_arch()

    # ------------------------------------------------------------------
    # Target collectors: (node, [(attribute, value), ...]) for EVERY match
    # ------------------------------------------------------------------
    def _field_attrs(self):
        is_list = self.view_type in ("list", "tree")
        if self.action == "hide":
            if is_list:
                return [("column_invisible", "1"), ("optional", "hide"), ("invisible", "1")]
            attrs = [("invisible", "1")]
            if self.view_type == "form" and self.field_id.required:
                attrs.append(("force_save", "1"))
            return attrs
        if self.action == "readonly":
            return [("readonly", "1")]
        if self.action == "required":
            return [("required", "1")]
        return [("string", self.new_label)]  # rename

    def _collect_field_targets(self, tree):
        fname = self.field_id.name
        attrs = self._field_attrs()
        # Only fields of THIS model: skip fields nested inside another field
        # (inline sub-lists/forms of one2many/many2many belong to other models).
        targets = [
            (node, attrs)
            for node in tree.xpath("//field[@name=$n][not(ancestor::field)]", n=fname)
        ]
        # Forms often print the caption through a separate <label for="...">.
        if self.view_type == "form" and self.action in ("hide", "rename"):
            label_attrs = (
                [("invisible", "1")] if self.action == "hide"
                else [("string", self.new_label)]
            )
            for lbl in tree.xpath("//label[@for=$n][not(ancestor::field)]", n=fname):
                targets.append((lbl, label_attrs))
        return targets

    def _collect_tab_targets(self, tree):
        wanted = (self.tab_label or "").strip()
        attrs = (
            [("invisible", "1")] if self.action == "hide"
            else [("string", self.new_label)]
        )
        return [
            (page, attrs)
            for page in tree.xpath("//page[not(ancestor::field)]")
            if (page.get("string") or "").strip() == wanted
        ]

    @staticmethod
    def _button_visible_label(btn):
        """Return (visible_label, nested_field_node_or_None)."""
        if btn.get("string"):
            return btn.get("string"), None
        for fld in btn.iter("field"):
            if fld.get("string"):
                return fld.get("string"), fld
        return " ".join("".join(btn.itertext()).split()), None

    def _collect_button_targets(self, tree):
        targets = []
        wanted_label = (self.button_label or "").strip()
        for btn in tree.xpath("//button[not(ancestor::field)]"):
            nested = None
            if self.button_name:
                is_match = btn.get("name") == self.button_name
            else:
                label, nested = self._button_visible_label(btn)
                is_match = label.strip() == wanted_label
            if not is_match:
                continue
            if self.action == "hide":
                targets.append((btn, [("invisible", "1")]))
            else:
                if nested is None:
                    _label, nested = self._button_visible_label(btn)
                targets.append((nested if nested is not None else btn,
                                [("string", self.new_label)]))
        return targets

    def _collect_targets(self, tree):
        if self.target_type == "field":
            return self._collect_field_targets(tree)
        if self.target_type == "tab":
            return self._collect_tab_targets(tree)
        return self._collect_button_targets(tree)

    def _build_specs(self, tree, targets):
        """[(xpath, attrs)] with one unambiguous locator per target (de-duplicated)."""
        specs, seen = [], set()
        for node, attrs in targets:
            expr = self._stable_xpath(tree, node)
            if expr and expr not in seen:
                seen.add(expr)
                specs.append((expr, attrs))
        return specs

    @staticmethod
    def _specs_to_arch(specs):
        root = etree.Element("data")
        for expr, attrs in specs:
            xpath_el = etree.SubElement(root, "xpath")
            xpath_el.set("expr", expr)
            xpath_el.set("position", "attributes")
            for name, value in attrs:
                attr_el = etree.SubElement(xpath_el, "attribute")
                attr_el.set("name", name)
                attr_el.text = value
        return etree.tostring(root, encoding="unicode")

    @staticmethod
    def _verify_specs(tree, specs):
        """Count specs whose attributes are really present in the merged ``tree``."""
        ok = 0
        for expr, attrs in specs:
            try:
                found = tree.xpath(expr)
            except etree.XPathError:
                continue
            if len(found) == 1 and all(found[0].get(a) == v for a, v in attrs):
                ok += 1
        return ok

    # ------------------------------------------------------------------
    # Planning: which views get patched and with which specs
    # ------------------------------------------------------------------
    def _plan_view_changes(self):
        """Return (plans, info). Each plan is (model, base_view, view_type, specs, suffix)."""
        plans = []
        info = {"tab_labels": set()}
        model_name = self.model_id.model
        for base in self._get_base_views():
            tree = self._combined_tree(base)
            if self.target_type == "tab":
                info["tab_labels"].update(
                    (p.get("string") or "").strip()
                    for p in tree.xpath("//page[not(ancestor::field)]") if p.get("string")
                )
            specs = self._build_specs(tree, self._collect_targets(tree))
            if specs:
                plans.append((model_name, base, self.view_type, specs, ""))
        if self.target_type == "field" and self.view_type in ("list", "tree"):
            plans.extend(self._plan_embedded_list_column())
        return plans, info

    def _plan_embedded_list_column(self):
        """Columns of this model shown inside a parent form (one2many / many2many).

        Example: the Journal Items table inside the Journal Entry form. Those
        columns are defined inline in the parent form, so patching only the
        child model's own list views has no effect there.
        """
        plans = []
        fname = self.field_id.name
        attrs = self._field_attrs()
        x2m_fields = self.env["ir.model.fields"].sudo().search([
            ("relation", "=", self.model_id.model),
            ("ttype", "in", ("one2many", "many2many")),
        ])
        for x2m in x2m_fields:
            parent_model = x2m.model
            if parent_model not in self.env:
                continue
            for form_view in self._get_base_views(view_type="form", model_name=parent_model):
                tree = self._combined_tree(form_view)
                nodes = tree.xpath(
                    "//field[@name=$x][not(ancestor::field)]"
                    "/*[self::list or self::tree]/field[@name=$f]",
                    x=x2m.name, f=fname,
                )
                specs = self._build_specs(tree, [(n, attrs) for n in nodes])
                if specs:
                    plans.append((parent_model, form_view, "form", specs, " [embedded]"))
        return plans

    # ------------------------------------------------------------------
    # View management
    # ------------------------------------------------------------------
    def _cleanup_generated_views(self):
        """Unlink every view previously created for this rule."""
        View = self.env["ir.ui.view"]
        to_drop = View.browse()
        if self.generated_view_id:
            to_drop |= self.generated_view_id
        if self.id:
            to_drop |= View.search([("name", "ilike", "field_manager:#%s " % self.id)])
        if to_drop:
            to_drop.unlink()

    def _create_inherit_view(self, *, model_name, base_view, arch, view_type, suffix=""):
        return self.env["ir.ui.view"].create({
            "name": "field_manager:#%s %s (base %s)%s" % (
                self.id or 0, self.name or "", base_view.id, suffix,
            ),
            "model": model_name,
            "inherit_id": base_view.id,
            "mode": "extension",
            "type": view_type,
            "arch_db": arch,
            "priority": 9999,  # applied after (and so beats) almost every other inherit
            "active": True,
        })

    def _clear_view_caches(self):
        try:
            self.env.registry.clear_cache()
        except Exception:
            _logger.debug("field.manager.rule: registry cache clear failed", exc_info=True)
        self.env.invalidate_all()

    def _not_found_message(self, info, checked):
        if self.target_type == "field":
            return _(
                "Field '%(field)s' was not found in any %(vtype)s view of model %(model)s "
                "(checked %(count)d view(s)). Open the real screen and confirm the field "
                "is displayed there. For columns inside a form table (e.g. Journal Items on "
                "a Journal Entry) use View Type = List — the embedded tables are updated too.",
                field=self.field_id.name, vtype=self.view_type,
                model=self.model_id.model, count=checked,
            )
        if self.target_type == "tab":
            labels = ", ".join(sorted(info["tab_labels"])) or _("none")
            return _(
                "No tab with the exact label '%(label)s' was found on the form of %(model)s "
                "(matching is case-sensitive). Tabs found: %(labels)s.",
                label=self.tab_label, model=self.model_id.model, labels=labels,
            )
        return _(
            "No button matching '%(ident)s' was found on the %(vtype)s view of %(model)s. "
            "Check spelling/capitalization or use the Technical Name.",
            ident=self.button_name or self.button_label,
            vtype=self.view_type, model=self.model_id.model,
        )

    def _apply_view_rule(self):
        """Create high-priority inherited view(s) for a Field / Tab / Button rule.

        EVERY matching element is patched (not only the first one) and the
        merged result is verified afterwards, so a rule can no longer report
        'Applied' while part of the screen is unchanged.
        """
        self.ensure_one()
        if (
            self.target_type == "field"
            and self.field_id
            and self.field_id.required
            and self.action == "hide"
        ):
            self._safe_message_post(_(
                "Warning: '%s' is required at the model level. It will be hidden in the "
                "view, but Odoo will still require a value on save. force_save is enabled "
                "so the current value is kept on write."
            ) % (self.field_id.field_description or self.field_id.name))

        # Start from a pristine state so our own previous views never
        # influence the lookup of targets.
        self._cleanup_generated_views()

        base_views = self._get_base_views()
        if not base_views:
            raise UserError(_(
                "No %s view found for model %s."
            ) % (self.view_type, self.model_id.model))

        plans, info = self._plan_view_changes()
        if not plans:
            raise UserError(self._not_found_message(info, len(base_views)))

        created = self.env["ir.ui.view"]
        report, problems = [], []
        total_targets = total_verified = 0
        for model_name, base, view_type, specs, suffix in plans:
            try:
                with self.env.cr.savepoint():
                    view = self._create_inherit_view(
                        model_name=model_name, base_view=base,
                        arch=self._specs_to_arch(specs), view_type=view_type, suffix=suffix,
                    )
            except Exception as exc:  # validation of the merged view failed
                problems.append(_("Skipped view id %(id)s: %(err)s") % {
                    "id": base.id, "err": str(exc).strip()[:400]})
                continue
            created |= view
            verified = self._verify_specs(self._combined_tree(base), specs)
            total_targets += len(specs)
            total_verified += verified
            report.append("• %s (id %s)%s: %d element(s) patched, %d verified" % (
                base.name or base.key or "view", base.id, suffix, len(specs), verified))
            if verified != len(specs):
                problems.append(_(
                    "View id %(id)s: only %(ok)d of %(total)d change(s) are effective in "
                    "the merged view."
                ) % {"id": base.id, "ok": verified, "total": len(specs)})

        if not created:
            raise UserError(_(
                "The element was found but no view could be patched:\n%s"
            ) % "\n".join(problems))

        self._clear_view_caches()
        summary = _("%(patched)d element(s) patched in %(views)d view(s) — %(ok)d/%(patched)d verified.") % {
            "patched": total_targets, "views": len(created), "ok": total_verified}
        result = "\n".join([summary] + report + ([""] + problems if problems else []))

        self.write({
            "generated_view_id": created[:1].id,
            "state": "applied",
            "applied_by": self.env.user.id,
            "applied_on": fields.Datetime.now(),
            "result_info": result,
        })
        self._safe_message_post(_("Rule applied: %s. %s") % (self.name, summary))
        if problems:
            self._safe_message_post(_("Attention: %s") % " | ".join(problems))

    # ------------------------------------------------------------------
    # Menu / Window action / Selection option rules (direct, reversible writes)
    # ------------------------------------------------------------------
    def _apply_menu(self):
        """Rename or hide a menu item (including Apps and nested sub-menus)."""
        self.ensure_one()
        menu = self.menu_id
        if not menu:
            raise UserError(_("No menu selected."))

        vals = {
            "state": "applied",
            "applied_by": self.env.user.id,
            "applied_on": fields.Datetime.now(),
        }
        if not self.menu_original_name:
            vals["menu_original_name"] = menu.name
            vals["menu_original_active"] = menu.active

        if self.action == "rename":
            menu.write({"name": self.new_label})
        elif self.action == "hide":
            menu.write({"active": False})

        self.write(vals)
        self._safe_message_post(_("Menu rule applied: %s.") % self.name)

    def _apply_action(self):
        """Rename a window action (the page title shown at the top of a screen)."""
        self.ensure_one()
        act = self.action_id
        if not act:
            raise UserError(_("No window action selected."))
        if self.action != "rename":
            raise UserError(_("Window Actions / Page Titles only support 'Rename'."))

        vals = {
            "state": "applied",
            "applied_by": self.env.user.id,
            "applied_on": fields.Datetime.now(),
        }
        if not self.action_original_name:
            vals["action_original_name"] = act.name

        act.write({"name": self.new_label})

        self.write(vals)
        self._safe_message_post(_("Action / Page Title rule applied: %s.") % self.name)

    def _safe_message_post(self, body):
        """Post a chatter message; never let a broken mail/follower setup abort the rule."""
        try:
            self.message_post(body=body)
        except Exception:
            # Common when another custom module corrupts res.partner / mail.followers
            _logger.warning(
                "field.manager.rule: could not post chatter message (mail stack broken). "
                "Rule still applied. Body was: %s", body, exc_info=True,
            )

    def _invalidate_selection_cache(self, field):
        """Force Odoo to re-read selection labels after we change ir.model.fields.selection."""
        if not field or not field.model or not field.name:
            return
        try:
            self.env.registry.clear_cache()
            self.env.invalidate_all()
        except Exception:
            _logger.debug("field.manager.rule: selection cache invalidation failed", exc_info=True)

    def _apply_selection_option(self):
        """Rename or hide a concrete selection / radio option (e.g. Send / Receive)."""
        self.ensure_one()
        opt = self.selection_id
        if not opt:
            raise UserError(_("No selection option selected."))

        # sudo so access rights on ir.model.fields.selection never block admins
        opt = opt.sudo()

        vals = {
            "state": "applied",
            "applied_by": self.env.user.id,
            "applied_on": fields.Datetime.now(),
        }
        if not self.selection_original_name:
            vals["selection_original_name"] = opt.name
            vals["selection_original_sequence"] = opt.sequence

        if self.action == "rename":
            opt.write({"name": self.new_label})
        elif self.action == "hide":
            # Soft-hide: prefix + high sequence (selection options have no 'active' flag)
            opt.write({
                "name": "[hidden] %s" % (opt.name or opt.value or ""),
                "sequence": 9999,
            })

        self._invalidate_selection_cache(opt.field_id)

        self.write(vals)
        self._safe_message_post(_("Selection option rule applied: %s.") % self.name)

    # ------------------------------------------------------------------
    # Revert / reset / delete
    # ------------------------------------------------------------------
    def action_revert(self):
        for rule in self:
            if rule.target_type == "menu":
                if rule.menu_id and rule.menu_original_name:
                    rule.menu_id.write({
                        "name": rule.menu_original_name,
                        "active": bool(rule.menu_original_active),
                    })
                rule.write({
                    "state": "reverted",
                    "menu_original_name": False,
                    "menu_original_active": False,
                })
                rule._safe_message_post(_("Menu rule reverted — original name/state restored."))
            elif rule.target_type == "action":
                if rule.action_id and rule.action_original_name:
                    rule.action_id.write({"name": rule.action_original_name})
                rule.write({
                    "state": "reverted",
                    "action_original_name": False,
                })
                rule._safe_message_post(_("Action rule reverted — original page title restored."))
            elif rule.target_type == "selection_option":
                if rule.selection_id and rule.selection_original_name:
                    restore = {"name": rule.selection_original_name}
                    if rule.selection_original_sequence is not False:
                        restore["sequence"] = rule.selection_original_sequence
                    rule.selection_id.sudo().write(restore)
                    rule._invalidate_selection_cache(rule.selection_id.field_id)
                rule.write({
                    "state": "reverted",
                    "selection_original_name": False,
                    "selection_original_sequence": False,
                })
                rule._safe_message_post(_("Selection option rule reverted — original label restored."))
            else:
                rule._cleanup_generated_views()
                rule._clear_view_caches()
                rule.write({"state": "reverted", "generated_view_id": False, "result_info": False})
                rule._safe_message_post(_("Rule reverted — original view(s) restored."))
        return True

    def action_reset_to_draft(self):
        for rule in self:
            if rule.state == "applied":
                raise UserError(_("Revert the rule before resetting it to draft."))
            rule.state = "draft"

    def unlink(self):
        for rule in self:
            if rule.state == "applied":
                rule.action_revert()
            if rule.generated_view_id:
                rule.generated_view_id.unlink()
        return super().unlink()
