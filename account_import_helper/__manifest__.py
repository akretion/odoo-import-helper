# -*- coding: utf-8 -*-
# © 2016 Akretion (http://www.akretion.com)
# @author Alexis de Lattre <alexis.delattre@akretion.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

{
    'name': 'Account Import Helper',
    'version': '10.0.1.0.0',
    'category': 'Partner',
    'license': 'AGPL-3',
    'summary': 'Helper methods to import accounting-related data',
    'description': """
Account Import Helper
=====================

This module provides methods to help on the import of accounting-related data, in particular the chart of accounts.

First, in a standard test Odoo database with the chart of account of the official addons, use this module to generate the file *account.account.csv*.

Then, in the future production database, after the installation of the official addons that has the chart of accounts for the country:

* Unconfigure the links to the accounts from taxes and ir.properties:

UPDATE account_tax SET account_id=null, refund_account_id=null;

UPDATE ir_property SET value_reference=null WHERE value_reference like 'account.account,%';

* Delete all accounts:

DELETE FROM account_account WHERE 1=1;

* Go to the menu *Accounting > Adviser > Chart of accounts* and import the file *account.account.csv* (DEPRECATED: enable the option *Show all fields for computation*, so that the columns *user_type_id/id* and *tax_ids/id* are mapped to the right fields *Type / External ID* and *Default Taxes / External ID*)

* In the menu *Accounting > Configuration > Accounting > Taxes*, on each tax, configure the *Tax Account* and *Tax Account on Refunds*.

* In the menu *Accounting > Configuration > Accounting > Fiscal Positions*, on each fiscal position, configure the account mapping.

* In the menu *Accounting > Configuration > Accounting > Journals*, on earch journal, configure the default debit account and the default credit account.

* On the page *Accounting > Configuration > Settings*, configure the *Inter-Banks Transfer Account*

* In the menu *Settings > Technical > Parameters > Company Properties*, edit the 4 properties

  - property_account_receivable_id
  - property_account_payable_id
  - property_account_expense_categ_id
  - property_account_income_categ_id

and set the field *value* with *account.account,67* where 67 is the ID of the account you want to have as default for that property.

This module has been written by Alexis de Lattre <alexis.delattre@akretion.com> from Akretion.
    """,
    'author': 'Akretion',
    'website': 'http://www.akretion.com',
    'depends': ['account'],
    'data': ['wizard/account_chart_generate_view.xml'],
    'installable': True,
}
