# Copyright 2021 Akretion (https://www.akretion.com).
# @author Sébastien BEAU <sebastien.beau@akretion.com>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import _, api, fields, models


class ProductAttributeValue(models.Model):
    _inherit = 'product.attribute.value'

    fullname = fields.Char(
        compute="_compute_fullname",
        store=True
        )

    @api.depends("attribute_id.name", "name")
    def _compute_fullname(self):
        for record in self:
            record.fullname = f"{record.attribute_id.name} : {record.name}"
