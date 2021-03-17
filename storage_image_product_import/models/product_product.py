# Copyright 2021 Akretion (https://www.akretion.com).
# @author Sébastien BEAU <sebastien.beau@akretion.com>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import _, api, fields, models


class ProductProduct(models.Model):
    _inherit = 'product.product'

    def _convert_image_vals(self, vals):
        # TODO we should fix odoo ORM
        if "image_ids" in vals:
            tmpl_id = vals["product_tmpl_id"]
            tmpl = self.env["product.template"].browse(tmpl_id)
            tmpl.write({"image_ids": vals.pop("image_ids")})

    def write(self, vals):
        self._convert_image_vals(vals)
        return super().write(vals)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            self._convert_image_vals(vals)
        return super().create(vals_list)
