# Copyright 2021-2023 Akretion (https://www.akretion.com).
# @author Sébastien BEAU <sebastien.beau@akretion.com>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

{
    "name": "Product Import Helper",
    "summary": "Helper for importing product",
    "version": "18.0.1.0.0",
    "category": "Import",
    "website": "https://github.com/akretion/odoo-import-helper",
    "author": " Akretion",
    "license": "AGPL-3",
    "depends": [
        "stock_account",  # for stock levels and accounts on products
        "import_helper_base",
        # account_product_fiscal_classification is now optional
    ],
    "external_dependencies": {
        "python": ["openpyxl"],
        "bin": [],
    },
    "installable": True,
}
