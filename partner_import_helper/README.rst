=====================
Partner Import Helper
=====================

This module adds methods to help on the import of partners:

- help to match a country ID from a country name
- help to match title
- help to validate email adresses
- remap street2 to street if street is empty
- help to pre-validate IBANs, VAT, SIREN, SIRET and avoid a raise during import
- check that the SIREN/SIRET is consistant with the French VAT number
- show a warning log if the VAT and/or IBAN starts with a country code that is different from the country of the partner (with special case for Greece and Northern Ireland VAT numbers)

If it cannot find the country from the country name by comparing the imported country name with the list of countries in res.country in all the installed languages (the comparaison is made after converting to lower case and removing spaces and accents), it will ask `ChatGPT <https://chat.openai.com/>`_ to tell him the ISO country code corresponding to that country name. To make it work, you need to have an OpenAI API key.

Configuration
=============

Edit the Odoo server configuration file and add an entry **openai_api_key** that contains your OpenAI API key.

Sample code
===========

Here is some sample code:

.. code::

  # parse Excel or CSV that contains the partners to import in Odoo
  speedy = self.env['res.partner']._import_speedy()
  line = 0
  for row in reader:  # loop on lines of the Excel
      line += 1
      vals = {
          'line': line,
          'name': row[0],
          'is_company': True,
          'street': row[1],
          'street2': row[2],
          'zip': row[3],
          'city': row[4],
          'country_name': row[5],
          'vat': row[6],
          'siret': row[7],
          'iban': row[8],
          'email': row[9],
          'create_date': row[10],  # in format %Y-%m-%d
          }
      self.env['res.partner']._import_create(vals, speedy)
  action = self.env['res.partner']._import_result_action(speedy)
  return action  # show import logs to the user


In the sample code above, ``vals`` is the dictionary that will be passed to ``create()``, with few differences:

- it must contain a **'line'** key to indicate the Excel/CSV import ref in logs, which will be removed before calling ``create()``,
- it can contain a **'country_name'** key with the name of the country, that will be replaced by the native **'country_id'** key,
- it can contain a **'title_code'** key  with possible values 'madam', 'miss', 'mister', 'doctor' or 'prof' that will be replaced by the native **'title'** key,
- it can contain an **'iban'** key, that will be replaced by **'bank_ids': [(0, 0, {'acc_number': xxx})]** if the IBAN is valid,
- along with the 'iban' key, it can contain a **'bic'** key and a **'bank_name'** key that will be replaced by **'bank_ids': [(0, 0, {'acc_number': xxxx, 'bank_id': bank_id})]**. The bank will be created on the fly if the BIC is not already present in the Odoo database, unless ``create_bank=False`` is passed as argument of the method ``_import_create()``,
- it can contain a **'siren_or_siret'** key, that can contain either a SIREN or a SIRET.

Author
======

* Alexis de Lattre <alexis.delattre@akretion.com>
