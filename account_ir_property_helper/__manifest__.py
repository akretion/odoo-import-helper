# Copyright 2022 Akretion (http://www.akretion.com)
# @author Alexis de Lattre <alexis.delattre@akretion.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

{
    "name": "Account Ir Property Helper",
    "version": "16.0.1.0.0",
    "category": "Partner",
    "license": "AGPL-3",
    "summary": "Helper methods to create/update default ir.property for accounting",
    "description": """
Account Ir Property Helper
==========================

Adds a wizard to easily set default ir.property for:

* payable/receivable accounts on partners
* income/expense accounts on product categories

I developped this module for a project with many companies where the accountant needed to be autonomous to setup new companies by himself.

    """,
    "author": "Akretion",
    "website": "https://github.com/akretion/odoo-import-helper",
    "depends": ["account"],
    "data": [
        "security/ir.model.access.csv",
        "wizards/account_default_ir_property_view.xml",
    ],
    "installable": True,
}
