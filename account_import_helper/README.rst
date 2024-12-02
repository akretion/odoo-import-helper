=====================
Account Import Helper
=====================

This module provides methods to help on the import of accounting-related data, in particular the chart of accounts.

First, in a standard test Odoo database with the chart of account of the official addons, use the wizard available via the menu *Configuration > Technical > Chart Generate > Chart Generate* to generate the file *account.account.csv*.

Then, in the future production database, after the installation of the official addons that has the chart of accounts for the country:

* Unconfigure the links to the accounts from several objects and ir.properties:

.. code::

  UPDATE account_journal SET default_account_id=null, suspense_account_id=null WHERE company_id=X;

  UPDATE FROM pos_payment_method SET outstanding_account_id=null, receivable_account_id=null WHERE company_id=X;

  UPDATE ir_default SET json_value = false FROM ir_model_fields f WHERE f.id = ir_default.field_id AND f.relation = 'account.account' AND ir_default.company_id = X

  DELETE FROM account_fiscal_position_account WHERE company_id=X;

* Delete all accounts:

.. code::

  DELETE FROM account_account_res_company_rel WHERE res_company_id=X

  DELETE FROM account_account WHERE id in (SELECT a.id FROM account_account a LEFT JOIN account_account_res_company_rel rel ON rel.account_account_id = a.id WHERE rel.account_account_id IS NULL)

* In the menu *Invoicing > Configuration > Accounting > Chart of accounts*, import the file *account.account.csv* with *Encoding* set to **utf-8** and *Use first row as header* enabled.

* In the menu *Invoicing > Configuration > Accounting > Taxes*, reconfigure the account on taxes.

* In the menu *Invoicing > Configuration > Accounting > Fiscal Positions*, on each fiscal position, configure the account mapping.

* In the menu *Invoicing > Configuration > Accounting > Journals*, on each journal, configure all the fields that point to accounts.

* On the page *Invoicing > Configuration > Settings*, update the section *Default Accounts*

* In the menu *Settings > Technical > Actions > User-defined Defaults*, edit the default having a 0 value including : 

  - Account Receivable
  - Account Payable
  - Expense Account
  - Income Account

and set the field *Default Value (JSON format)* with **67** where 67 is the ID of the account you want to have as default for that property.


Contributors
============

This module has been written by Alexis de Lattre <alexis.delattre@akretion.com> from `Akretion France <https://akretion.com/fr>`_.
