# Copyright 2016-2022 Akretion (http://www.akretion.com)
# @author Alexis de Lattre <alexis.delattre@akretion.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

{
    "name": "Account Import Helper",
    "version": "16.0.1.0.0",
    "category": "Partner",
    "license": "AGPL-3",
    "summary": "Helper methods to import accounting-related data",
    "author": "Akretion",
    "website": "https://github.com/akretion/odoo-import-helper",
    "depends": ["account"],
    "external_dependencies": {"python": ["openpyxl"]},
    "data": [
        "security/ir.model.access.csv",
        "wizard/account_chart_generate_view.xml",
    ],
    "installable": True,
}
