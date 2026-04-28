=====================
Account Import Helper
=====================

This module is designed to replace the standard chart of account of Odoo by the chart of accounts of the company before go-live.

This module has been fully re-written on december 30th 2025 ; if you were used to the old procedure, please read carefully the new procedure below.

In the production database, install this module **account_import_helper** before go-live. As you are before go-live, there should be no journal items in the database.

In developer mode, go to the menu **Invoicing > Configuration > Tools for Chart of Accounts > Import Chart of Accounts** : it will start a wizard to import a custom chart of account from an XLSX file. The XLSX file should contain 2 columns with an optional third column:

- column A: the account code (required)
- column B: the label of the account (required)
- column C: some notes related to the account (optional)

When you run the import, Odoo will use the account code and label (and notes) from the XLSX file and the fields *Type*, *Allow Reconciliation* and *Non Trade* from the standard Odoo chart of accounts (you can choose between using the chart of account of the module *l10n_fr_account* or the OCA module *l10n_fr_account_oca*).

If you select several companies in the *Companies* field of the wizard, Odoo will import the chart of accounts as shared accounts between those companies (new feature of Odoo 18).

Once the chart of account has been imported, check that the imported accounts are ok. Check that you have one and only one account with type *Current Year Earnings*.

Go to the menu **Invoicing > Configuration > Tools for Chart of Accounts > Re-configure after Chart of Account Import**: it starts a wizard that make it easy to re-configure the default accounts for partners and product categories, and also the suspense account for bank/cash journals and the transfer account of the company.

Eventually:

* In the menu *Invoicing > Configuration > Accounting > Taxes*, reconfigure the account on taxes.

* In the menu *Invoicing > Configuration > Accounting > Fiscal Positions*, on each fiscal position, configure the account mapping.

* In the menu *Invoicing > Configuration > Accounting > Journals*, on each journal, configure all the fields that point to accounts.

* On the page *Invoicing > Configuration > Settings*, update the section *Default Accounts*.

Once you have finished, you can uninstall the module **account_import_helper**.

Contributors
============

This module has been written by Alexis de Lattre <alexis.delattre@akretion.com> from `Akretion France <https://akretion.com/fr>`_.
