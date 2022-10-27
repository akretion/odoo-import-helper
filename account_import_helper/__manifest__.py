# Copyright 2016-2020 Akretion (http://www.akretion.com)
# @author Alexis de Lattre <alexis.delattre@akretion.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

{
    "name": "Account Import Helper",
    "version": "14.0.1.0.1",
    "category": "Partner",
    "license": "AGPL-3",
    "summary": "Helper methods to import accounting-related data",
    "description": """
Account Import Helper
=====================

This module provides methods to help on the import of accounting-related data, in particular the chart of accounts.

First, in a standard test Odoo database with the chart of account of the official addons, use the wizard available via the menu *Configuration > Technical > Chart Generate > Chart Generate* to generate the file *account.account.csv*.

Then, in the future production database, after the installation of the official addons that has the chart of accounts for the country:

* Unconfigure the links to the accounts from several objects and ir.properties:

UPDATE account_journal set default_account_id=null, suspense_account_id=null, payment_debit_account_id=null, payment_credit_account_id=null;

DELETE from pos_payment_method;

UPDATE ir_property SET value_reference=null WHERE value_reference like 'account.account,%';

* Delete all accounts:

DELETE FROM account_account;

* Go to the menu *Invoicing > Configuration > Accounting > Chart of accounts* and import the file *account.account.csv* with Encoding = UTF-8

* In the menu *Accounting > Configuration > Accounting > Taxes* and reconfigure the account on taxes.

* In the menu *Accounting > Configuration > Accounting > Fiscal Positions*, on each fiscal position, configure the account mapping.

* In the menu *Accounting > Configuration > Accounting > Journals*, on each journal, configure all the fields that point to accounts.

* On the page *Accounting > Configuration > Settings*, configure the *Inter-Banks Transfer Account* (field displayed by my module account_usability)

* In the menu *Settings > Technical > Parameters > Company Properties*, edit the 4 properties

  - property_account_receivable_id
  - property_account_payable_id
  - property_account_expense_categ_id
  - property_account_income_categ_id

and set the field *value* with *account.account,67* where 67 is the ID of the account you want to have as default for that property.

This module has been written by Alexis de Lattre <alexis.delattre@akretion.com> from Akretion.
    """,
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
