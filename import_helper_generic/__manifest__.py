# Copyright 2023 Akretion France (http://www.akretion.com/)
# @author: Thomas Bonnerue <thomas.bonnerue@akretion.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

{
    "name": "Import Helper Generic",
    "version": "18.0.1.0.0",
    "category": "Extra Tools",
    "license": "AGPL-3",
    "summary": "Helper methods to import database",
    "author": "Akretion",
    "depends": [
        "import_helper_base",
        "phone_validation",  # would be nice to avoid depending on it ?
        "partner_import_helper",
        "product_import_helper",
        # "account_import_helper",
    ],
    "installable": True,
    "data": [
        # "security/ir.model.access.csv",
        "security/ir.model.access.csv",
        "views/technical_view_menu_generic.xml",
    ],
}
