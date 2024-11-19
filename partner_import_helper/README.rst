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
  import_obj = self.env['import.helper']
  speedy = import_obj._prepare_speedy()
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
          'country_name': row[5],  # name or ISO code
          'vat': row[6],
          'siret': row[7],
          'iban': row[8],
          'email': row[9],
          'industry_name': row[10],
          'create_date': row[11],  # in format %Y-%m-%d
          'child_ids': [(0, 0, {
              'type': 'contact',
              'name': row[12],
              'phone': row[13],
              'moile': row[14],
              })]
          }
      import_obj._create_partner(vals, speedy)
  action = import_obj._result_action(speedy)
  return action  # show import logs to the user


In the sample code above, ``vals`` is the dictionary that will be passed to ``create()`` of res.partner, with few differences:

- it must contain a **'line'** key to indicate the Excel/CSV import ref in logs, which will be removed before calling ``create()``,
- it can contain a **'country_name'** key with the name of the country, that will be replaced by the native **'country_id'** key,
- it can contain an **'industry_name'** key that will be used to match an existing industry or create a new one,
- it can contain a **'title_code'** key  with possible values 'madam', 'miss', 'mister', 'doctor' or 'prof' that will be replaced by the native **'title'** key,
- it can contain an **'iban'** key, that will be replaced by **'bank_ids': [(0, 0, {'acc_number': xxx})]** if the IBAN is valid,
- along with the 'iban' key, it can contain a **'bic'** key and a **'bank_name'** key that will be replaced by **'bank_ids': [(0, 0, {'acc_number': xxxx, 'bank_id': bank_id})]**. The bank will be created on the fly if the BIC is not already present in the Odoo database, unless ``create_bank=False`` is passed as argument of the method ``_create_partner()``,
- it can contain a **'siren_or_siret'** key, that can contain either a SIREN or a SIRET.
- it can contain a key **'customer_invoice_transmit_method_code'** or **'supplier_invoice_transmit_method_code'** that contain the code of an invoice transmit method,
- it can contain a key **'customer_payment_term_code'** or **'supplier_payment_term_code'** that contain the code given by this module to a payment term. Current codes : 1 (immediate payment), 15 (15 days net), 21 (21 days net), 30, 45, 60.
- it can contain a key **'comment_txt'** with a block of text, that will be converted to an HTML block with proper breaks for the **'comment'** field.

For **child_ids**, use the old syntax *[(0, 0, child_vals)]* and not the new syntax *[Command.create(child_vals)]*.

Author
======

* Alexis de Lattre <alexis.delattre@akretion.com>
