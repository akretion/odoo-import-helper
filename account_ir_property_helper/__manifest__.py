# Copyright 2022 Akretion (http://www.akretion.com)
# @author Alexis de Lattre <alexis.delattre@akretion.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

{
    "name": "Account Ir Property Helper",
    "version": "14.0.1.0.1",
    "category": "Partner",
    "license": "AGPL-3",
    "summary": "Helper methods to create/update default ir.property for accounting",
    "author": "Akretion",
    "website": "https://github.com/akretion/odoo-import-helper",
    "depends": ["account"],
    "data": [
        "security/ir.model.access.csv",
        "wizards/account_default_ir_property_view.xml",
    ],
    "installable": True,
}
