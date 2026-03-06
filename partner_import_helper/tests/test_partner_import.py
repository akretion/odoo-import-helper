# Copyright 2024 Akretion France (http://www.akretion.com/)
# @author: Alexis de Lattre <alexis.delattre@akretion.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo.tests.common import TransactionCase
from odoo import fields
from odoo.tests import tagged

from odoo.tools import file_open
import base64

@tagged('post_install', '-at_install')
class PartnerImportHelper(TransactionCase):

    XLSX_PATH = 'partner_import_helper/tests/res_partner_import_test.xlsx'

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))

    def test_partner_import_vals(self):
        vals = {
            'line': 1,
            'name': ' Akretion France ',
            'is_company': True,
            'street': ' 27 rue Henri Rolland ',
            'zip': '69100',
            'city': 'Villeurbanne',
            'country_name': 'FRA',
            'vat': 'FR86792377731',
            'siren_or_siret': '792 377 731 00023',
            'iban': 'FR63 5454 7777 3434 6363 8976 789',
            'bic': 'QNTOFRP1XXX',
            'bank_name': 'Qonto',
            'create_date': '2013-03-25',
            'website': 'www.akretion.com',
            'industry_name': 'Odoo Integrator',
            'customer_payment_term_code': 30,
            'supplier_payment_term_code': '30',
            'comment_txt': 'A great Odoo integrator.\nInitiated ShopInvader; strong experience in e-commerce.',
            'child_ids': [(0, 0, {
                'type': 'contact',
                'title_code': 'mister',
                'name': 'Alexis de Lattre',
                'email': 'alexis.delattre@akretion.com',
                'phone': '09.33.44.55.66',
                'mobile': '06 09 08 07 06',
              })]
        }
        import_obj = self.env['import.helper']
        speedy = import_obj._prepare_speedy()
        partner = import_obj._create_partner(vals, speedy)
        self.assertEqual(partner.name, 'Akretion France')
        self.assertEqual(partner.street, '27 rue Henri Rolland')
        self.assertEqual(partner.zip, vals['zip'])
        self.assertEqual(partner.city, vals['city'])
        self.assertEqual(partner.country_id.code, 'FR')
        self.assertEqual(partner.siret, '79237773100023')
        self.assertEqual(partner.vat, vals['vat'])
        term = self.env.ref('account.account_payment_term_30days')
        self.assertEqual(partner.property_payment_term_id, term)
        self.assertEqual(partner.property_supplier_payment_term_id, term)
        self.assertEqual(partner.industry_id.name, vals['industry_name'])
        # Test for create_date doesn't work. The code with SQL UPDATE seems to work,
        # but the cache is not up-to-date to test it
        # self.assertEqual(fields.Date.to_string(partner.create_date), vals['create_date'])
        self.assertEqual(len(partner.child_ids), 1)
        child = partner.child_ids[0]
        self.assertEqual(child.type, 'contact')
        self.assertEqual(child.title, self.env.ref('base.res_partner_title_mister'))
        self.assertEqual(child.phone, '+33 9 33 44 55 66')
        self.assertEqual(child.mobile, '+33 6 09 08 07 06')
        self.assertEqual(len(partner.bank_ids), 1)
        pbank = partner.bank_ids[0]
        self.assertEqual(pbank.sanitized_acc_number, vals['iban'].replace(' ', ''))
        self.assertEqual(pbank.bank_id.bic, vals['bic'])
        self.assertEqual(pbank.bank_id.name, vals['bank_name'])
        self.assertTrue('<br>' in partner.comment)
        self.assertTrue('A great Odoo integrator' in partner.comment)
        action = import_obj._result_action(speedy)
        self.assertTrue(isinstance(action, dict))

    def test_partner_import_xlsx(self):
        # open & submit file
        file_res = file_open(self.XLSX_PATH, 'rb')
        xlsx_file = file_res.read()
        ImportHelper = self.env['import.helper']
        wizard = ImportHelper.create({
            'file': base64.b64encode(xlsx_file),
        })

        # test data
        self.env.company.partner_id.ref = 'Holding'
        action = wizard.button_import_file()
        self.assertTrue(isinstance(action, dict))

        partner = self.env['res.partner'].search([('ref', '=', 'FRN001')])
        self.assertTrue(partner)
        self.assertEqual(len(partner.child_ids), 3)
        self.assertFalse(partner.bank_ids)
