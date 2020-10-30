# Copyright 2017-2020 Akretion France
# @author: Alexis de Lattre <alexis.delattre@akretion.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import fields, models, _
from odoo.exceptions import UserError
from tempfile import TemporaryFile
import unicodecsv
from pprint import pprint
import logging
import base64
logger = logging.getLogger(__name__)


class AccountChartGenerate(models.TransientModel):
    _name = 'account.chart.generate'
    _description = 'Generate customer-specific chart of accounts'

    module = fields.Char(
        'Module Name', required=True, default='custom',
        help="Used for the first part of the XMLID (before the dot)")
    xmlid_prefix = fields.Char(
        'XMLID prefix', required=True, default='account_')
    fixed_size_code = fields.Boolean(default=True)
    with_taxes = fields.Boolean(default=True)
    csv_file = fields.Binary(required=True, string='CSV file')
    csv_filename = fields.Char()
    out_csv_file = fields.Binary(string='Result CSV file', readonly=True)
    out_csv_filename = fields.Char(readonly=True)
    state = fields.Selection(
        [('step1', 'step1'), ('step2', 'step2')],
        default='step1', required=True)

    def _prepare_custom2odoo_code_map(self):
        custom2odoo_code_map = {}
        return custom2odoo_code_map

    def run(self):
        fileobj = TemporaryFile('wb+')
        decoded_csv = base64.b64decode(self.csv_file)
        fileobj.write(decoded_csv)
        fileobj.seek(0)
        reader = unicodecsv.DictReader(
            fileobj, encoding='utf-8', delimiter=',',
            fieldnames=[u'code', u'name', u'note'])
        custom_chart = []
        for line in reader:
            if line['code'] and line['name']:
                if len(line['code']) < 3:
                    raise UserError(_(
                        "Account Code '%s' is too small (len < 3)")
                        % line['code'])
                if not line['code'][:3].isdigit():
                    raise UserError(
                        _("Account '%s': the 3 first caracters are not digits")
                        % line['code'])
                custom_chart.append((
                    line['code'],
                    {'name': line['name'], 'note': line['note']}))
        pprint(custom_chart)
        logger.info('Starting to generate CSV file')
        res = self.env['account.account'].generate_custom_chart(
            custom_chart, module=self.module,
            xmlid_prefix=self.xmlid_prefix,
            fixed_size_code=self.fixed_size_code,
            custom2odoo_code_map=self._prepare_custom2odoo_code_map(),
            with_taxes=self.with_taxes)
        fout = TemporaryFile('wb+')
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
            'out_csv_file': base64.b64encode(res_file),
            'out_csv_filename': 'account.account-%s.csv' % self.module,
            })
        fout.close()
        logger.info('End of the generation of CSV file')
        action = self.env.ref(
            'account_import_helper.account_chart_generate_action').read()[0]
        action['res_id'] = self.ids[0]
        return action
