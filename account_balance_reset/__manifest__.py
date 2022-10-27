# Copyright 2022 Akretion France (http://www.akretion.com/)
# @author: Alexis de Lattre <alexis.delattre@akretion.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

{
    "name": "Account Balance Reset",
    "version": "14.0.1.0.1",
    "category": "Accounting",
    "license": "AGPL-3",
    "summary": "Rest accounting balance at a particular date",
    "author": "Akretion",
    "website": "https://github.com/akretion/odoo-import-helper",
    "depends": ["account"],
    "data": [
        "wizards/account_balance_reset_view.xml",
        "security/ir.model.access.csv",
    ],
    "installable": True,
}
