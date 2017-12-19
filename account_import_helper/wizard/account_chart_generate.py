# -*- coding: utf-8 -*-
# © 2017 Akretion (Alexis de Lattre <alexis.delattre@akretion.com>)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import fields, models
from tempfile import TemporaryFile
import unicodecsv
from pprint import pprint
import logging
logger = logging.getLogger(__name__)


class AccountChartGenerate(models.TransientModel):
    _name = 'account.chart.generate'

    module = fields.Char(
        'Module Name', required=True, default='custom',
        help="Used for the first part of the XMLID (before the dot)")
    xmlid_prefix = fields.Char(
        'XMLID prefix', required=True, default='account_')
    fixed_size_code = fields.Boolean(default=True)
    with_taxes = fields.Boolean(default=True)
    csv_file = fields.Binary(required=True, string='CSV file')
    out_csv_file = fields.Binary(string='Result CSV file', readonly=True)
    out_csv_filename = fields.Char(readonly=True)
    state = fields.Selection(
        [('step1', 'step1'), ('step2', 'step2')],
        default='step1', required=True)

    def _prepare_custom2odoo_code_map(self):
        custom2odoo_code_map = {}
        return custom2odoo_code_map

    def run(self):
        fileobj = TemporaryFile('w+')
        fileobj.write(self.csv_file.decode('base64'))
        fileobj.seek(0)
        reader = unicodecsv.DictReader(
            fileobj, encoding='utf-8', delimiter=',',
            fieldnames=[u'code', u'name', u'note'])
        custom_fr_pcg = []
        for line in reader:
            if line['code'] and line['name']:
                custom_fr_pcg.append((
                    line['code'],
                    {'name': line['name'], 'note': line['note']}))
        pprint(custom_fr_pcg)
        logger.info('Starting to generate CSV file')
        res = self.env['account.chart.template'].generate_l10n_fr_custom(
            custom_fr_pcg, module=self.module,
            xmlid_prefix=self.xmlid_prefix,
            fixed_size_code=self.fixed_size_code,
            custom2odoo_code_map=self._prepare_custom2odoo_code_map(),
            with_taxes=self.with_taxes)
        fout = TemporaryFile('w+')
        w = unicodecsv.DictWriter(fout, [
            'id',
            'code',
            'name',
            'user_type_xmlid',
            'reconcile',
            'tax_xmlids',
            'note',
            ], encoding='utf-8')
        for account_dict in res:
            w.writerow(account_dict)
        fout.seek(0)
        res_file = fout.read()
        self.write({
            'state': 'step2',
            'out_csv_file': res_file.encode('base64'),
            'out_csv_filename' : 'account.account-%s.csv' % self.module,
            })
        fout.close()
        logger.info('End of the generation of CSV file')
        action = self.env['ir.actions.act_window'].for_xml_id(
            'account_import_helper', 'account_chart_generate_action')
        action['res_id'] = self.ids[0]
        return action
