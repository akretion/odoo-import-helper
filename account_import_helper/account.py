# -*- coding: utf-8 -*-
# © 2016 Akretion (http://www.akretion.com)
# @author Alexis de Lattre <alexis.delattre@akretion.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import models, api, _
from openerp.exceptions import UserError
import logging
import unicodecsv
logger = logging.getLogger(__name__)


class AccountChartTemplate(models.Model):
    _inherit = 'account.chart.template'

    @api.model
    def generate_id2xmlid(self, object_name):
        irmdo = self.env['ir.model.data']
        obj_id2xmlid = {}
        irmd = irmdo.search([
            ('model', '=', object_name),
            ('res_id', '!=', False)])
        for entry in irmd:
            obj_id2xmlid[entry.res_id] = '%s.%s' % (entry.module, entry.name)
        return obj_id2xmlid

    @api.multi
    def generate_custom_chart(
            self, custom_chart, module='custom',
            xmlid_prefix='account_',
            csv_out_file='/tmp/account.account.csv',
            fixed_size_code=True,
            custom2odoo_code_map=None,
            with_taxes=True):
        # arg 'custom_chart': list of tuple
        # tuple: ('622600', {'name': 'Honoraires comptables'})
        # in the second value of the tuple, we often only put name,
        # but we can put other odoo properties
        self.ensure_one()
        aato = self.env['account.account.template']
        user_type_id2xmlid = self.generate_id2xmlid('account.account.type')
        taxtemplate2xmlid = self.generate_id2xmlid('account.tax.template')
        logger.info('taxtemplate2xmlid = %s', taxtemplate2xmlid)
        logger.info('user_type_id2xmlid = %s', user_type_id2xmlid)
        # pre-load odoo's chart of account
        odoo_chart = {}
        accounts = aato.search([('chart_template_id', '=', self.id)])
        odoo_code_size = False
        for account in accounts:
            user_type_xmlid = user_type_id2xmlid[account.user_type_id.id]
            taxes_xmlids = [
                taxtemplate2xmlid[tax.id] for tax in account.tax_ids]
            odoo_chart[account.code] = {
                'name': account.name,
                'reconcile': account.reconcile,
                'user_type_xmlid': user_type_xmlid,
                'tax_xmlids': ','.join(taxes_xmlids),
                }
            if not odoo_code_size:
                odoo_code_size = len(account.code)
        res = []
        # header line
        res.append({
            'id': 'id',
            'code': 'code',
            'name': 'name',
            'user_type_xmlid': 'user_type_id/id',
            'tax_xmlids': 'tax_ids/id',
            'reconcile': 'reconcile',
            'note': 'note',
        })
        custom_code_size = False
        for (custom_code, src_custom_dict) in custom_chart:
            if fixed_size_code:
                if custom_code_size:
                    if len(custom_code) != custom_code_size:
                        raise UserError(_(
                            "For account code %s, the size (%d) is different "
                            "from the size of other accounts (%d)") % (
                            custom_code, len(custom_code), custom_code_size))
                else:
                    custom_code_size = len(custom_code)
                    if custom_code_size < odoo_code_size:
                        raise UserError(_(
                            "For account code %s, the custom code size (%d) "
                            "is < odoo's code size (%d)") % (
                            custom_code, custom_code_size, odoo_code_size))
                size = odoo_code_size
            else:
                size = len(custom_code)
            match = False
            matching_code = custom_code
            if custom2odoo_code_map and custom_code in custom2odoo_code_map:
                matching_code = custom2odoo_code_map[custom_code]
            while size > 1 and not match:
                short_matching_code = matching_code[:size]
                for odoo_code, odoo_dict in odoo_chart.iteritems():
                    if odoo_code.startswith(short_matching_code):
                        custom_dict = odoo_dict.copy()
                        custom_dict['id'] = '%s.%s%s' % (
                            module, xmlid_prefix, custom_code)
                        custom_dict.update(src_custom_dict)
                        custom_dict['code'] = custom_code
                        if not with_taxes:
                            custom_dict['tax_xmlids'] = ''
                        res.append(custom_dict)
                        match = True
                        break
                size -= 1
            if not match:
                raise UserError(_(
                    "Customer account %s '%s' didn't match any Odoo account")
                    % (custom_code, src_custom_dict.get('name')))

        # generate file
        f = open(csv_out_file, 'w')  # it will over-write an existing file
        w = unicodecsv.DictWriter(f, [
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
        f.close()
        logger.info('File %s successfully generated', csv_out_file)
        return

    @api.model
    def generate_l10n_fr_custom(
            self, custom_fr_pcg, module='customer_specific',
            xmlid_prefix='account_',
            csv_out_file='/tmp/account.account.csv',
            fixed_size_code=True, custom2odoo_code_map=None,
            with_taxes=True):
        # This is a sample method
        # custom_fr_pcg is a list of tuple:
        # (code, {'name': 'Déplacement', 'note': 'My comment'})
        fr_pcg = self.env.ref('l10n_fr.l10n_fr_pcg_chart_template')
        company = self.env.user.company_id
        if company.chart_template_id != fr_pcg:
            raise UserError(_(
                'The chart of accounts of the company %s is not the chart of '
                'account of the official Odoo module l10n_fr') % company.name)
        assert isinstance(custom_fr_pcg, list), 'custom_fr_pcg must be a list'
        for (code, acc_dict) in custom_fr_pcg:
            assert len(code) > 3, 'account code is too small ?'
            assert isinstance(acc_dict.get('name'), (str, unicode)),\
                'missing account name'
            if not code[:3].isdigit():
                raise UserError(
                    _("Account '%s': the 3 first caracters are not digits")
                    % code)
        company.chart_template_id.generate_custom_chart(
            custom_fr_pcg, module=module, csv_out_file=csv_out_file,
            xmlid_prefix=xmlid_prefix,
            fixed_size_code=fixed_size_code,
            custom2odoo_code_map=custom2odoo_code_map,
            with_taxes=with_taxes)
