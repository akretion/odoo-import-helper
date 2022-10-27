# Copyright 2022 Akretion (https://www.akretion.com).
# @author Sébastien BEAU <sebastien.beau@akretion.com>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import _, api, fields, models
from odoo.exceptions import UserError


# TODO this is a patch to import url
# the right way to do it is to refctor the url module (TODO V16)
class UrlUrl(models.Model):
    _inherit = "url.url"

    product_template_id = fields.Many2one(
        "product.template", "Product Template", compute="_compute_importable_data"
    )
    category_id = fields.Many2one(
        "product.category", "Category", compute="_compute_importable_data"
    )
    shopinvader_backend_id = fields.Many2one(
        "shopinvader.backend", "Shopinvader Backend", compute="_compute_importable_data"
    )

    @api.depends("backend_id", "model_id")
    def _compute_importable_data(self):
        for record in self:
            if record.model_id._name == "shopinvader.product":
                record.product_template_id = record.model_id.record_id
            elif record.model_id._name == "shopinvader.category":
                record.category_id = record.model_id.record_id
            if record.backend_id._name == "shopinvader.backend":
                record.shopinvader_backend_id = record.backend_id

    def _update_importable_data(self, vals):
        if "shopinvader_backend_id" in vals:
            backend = self.env["shopinvader.backend"].browse(
                vals.pop("shopinvader_backend_id")
            )
            if not backend:
                raise UserError(_("Shopinvader Backend is required"))

            vals["backend_id"] = f"shopinvader.backend,{backend.id}"
            if vals.get("product_template_id"):
                template = self.env["product.template"].browse(
                    vals.pop("product_template_id")
                )
                binding = template.shopinvader_bind_ids.filtered(
                    lambda s: s.backend_id == backend
                )
                if not binding:
                    raise UserError(
                        _("The product template id: %s is not on the backend %s")
                        % (template.name, backend.name)
                    )
                vals["model_id"] = f"shopinvader.product,{binding.id}"

            if vals.get("category_id"):
                categ = self.env["product.category"].browse(vals.pop("category_id"))
                binding = categ.shopinvader_bind_ids.filtered(
                    lambda s: s.backend_id == backend
                )
                if not binding:
                    raise UserError(
                        _("The category: %s is not on the backend %s")
                        % (categ.name, backend.name)
                    )
                vals["model_id"] = f"shopinvader.category,{binding.id}"
        return vals

    def write(self, vals):
        self._update_importable_data(vals)
        return super().write(vals)

    @api.model_create_multi
    def create(self, list_vals):
        for vals in list_vals:
            self._update_importable_data(vals)
        return super().create(list_vals)
