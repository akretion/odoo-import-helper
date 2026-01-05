# Copyright (c) 2026 Akretion.

from odoo import api, models, fields


class ProductTemplate(models.Model):
    _inherit = "product.template"

    default_code_import = fields.Char(
        "reference interne pour import",
        compute="_compute_default_code_import",
        store=True,
    )

    @api.depends("default_code")
    def _compute_default_code_import(self):
        for record in self:
            if record.default_code:
                record.default_code_import = record.default_code
