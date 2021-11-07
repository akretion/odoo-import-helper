# Copyright 2021 Akretion (https://www.akretion.com).
# @author Sébastien BEAU <sebastien.beau@akretion.com>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import api, fields, models


class ProductProduct(models.Model):
    _inherit = "product.product"

    fullname = fields.Char(compute="_compute_fullname", store=True)

    @api.depends(
        "product_tmpl_id.name", "default_code", "product_template_attribute_value_ids"
    )
    def _compute_fullname(self):
        for record in self.with_context(display_default_code=True, partner_id=False):
            record.fullname = record.display_name
