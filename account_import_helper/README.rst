=====================
Account Import Helper
=====================

This module provides methods to help on the import of accounting-related data, in particular the chart of accounts.

First, in a standard test Odoo database with the chart of account of the official addons, use the wizard available via the menu *Configuration > Technical > Chart Generate > Chart Generate* to generate the file *account.account.csv*.

Then, in the future production database, after the installation of the official addons that has the chart of accounts for the country:

* Unconfigure the links to the accounts from several objects and ir.properties:

.. code::

  UPDATE account_journal set default_account_id=null, suspense_account_id=null;

  DELETE from pos_payment_method;

  UPDATE ir_property SET value_reference=null WHERE value_reference like 'account.account,%';

* Delete all accounts:

.. code::

  DELETE FROM account_account;

* In the menu *Invoicing > Configuration > Accounting > Chart of accounts*, import the file *account.account.csv* with *Encoding* set to **utf-8** and *Use first row as header* enabled.

* In the menu *Invoicing > Configuration > Accounting > Taxes*, reconfigure the account on taxes.

* In the menu *Invoicing > Configuration > Accounting > Fiscal Positions*, on each fiscal position, configure the account mapping.

* In the menu *Invoicing > Configuration > Accounting > Journals*, on each journal, configure all the fields that point to accounts.

* On the page *Invoicing > Configuration > Settings*, update the section *Default Accounts*

* In the menu *Settings > Technical > Parameters > Company Properties*, edit the 4 properties

  - property_account_receivable_id
  - property_account_payable_id
  - property_account_expense_categ_id
  - property_account_income_categ_id

and set the field *value* with **account.account,67** where 67 is the ID of the account you want to have as default for that property.


Contributors
============

This module has been written by Alexis de Lattre <alexis.delattre@akretion.com> from `Akretion France <https://akretion.com/fr>`_.
