# Copyright 2023 Akretion France (http://www.akretion.com/)
# @author: Alexis de Lattre <alexis.delattre@akretion.com>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class ImportShowLogs(models.TransientModel):
    _name = "import.show.logs"
    _description = "Pop-up to show warnings after import"

    logs = fields.Html(readonly=True)
