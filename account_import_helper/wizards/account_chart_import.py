# Copyright 2017-2022 Akretion France
# @author: Alexis de Lattre <alexis.delattre@akretion.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import fields, models, Command
from odoo.tools import file_open
from odoo.exceptions import UserError
import base64
import logging
from io import BytesIO
import csv
from pprint import pprint

logger = logging.getLogger(__name__)
try:
    import openpyxl
except ImportError:
    logger.debug('Cannot import openpyxl')


class AccountChartImport(models.TransientModel):
    _name = "account.chart.import"
    _description = "Import customer-specific chart of accounts"

    fixed_size_code = fields.Boolean(default=True)
    # with_taxes = fields.Boolean(default=True)
    source_module = fields.Selection([
        ('l10n_fr_account', 'l10n_fr_account'),
        ('l10n_fr_account_oca', 'l10n_fr_account_oca'),
        ], default='l10n_fr_account_oca', required=True)
    input_file = fields.Binary(required=True, string="XLSX file")
    input_filename = fields.Char()
    input_start_line = fields.Integer(string="Start Line", default=2, required=True)
    input_sheet_number = fields.Integer(string="Sheet Number", default=1, required=True)
    company_ids = fields.Many2many(
        'res.company', string="Companies", required=True,
        default=lambda self: [self.env.company.id])
    delete_existing_accounts = fields.Selection([
        ('selected_companies', 'In Selected Companies'),
        ('all_companies', 'In All Companies'),
        ('no', 'No'),
        ], default='selected_companies', required=True, string="Delete All Existing Accounts")
    create_unaffected_earnings_account = fields.Boolean(
        default=True,
        help="If enabled, Odoo will auto-create an Unaffected Earnings Account "
        "if none is found in the imported accounts.")

    def _prepare_custom2odoo_code_map(self):
        """This method is designed to be inherited"""
        custom2odoo_code_map = {}
        return custom2odoo_code_map

    def _prepare_accounts(self, vals_list):
        """This method is designed to be inherited"""
        vals_list_final = []
        for vals in vals_list:
            vals_list_final.append(dict(vals, company_ids=[Command.set([self.company_ids[0].id])]))
        return vals_list_final

    def _prepare_equity_unaffected_account(self, equity_unaffected_companies, custom_code_size):
        code_size = self.fixed_size_code and custom_code_size or 6
        vals = {
            'code': '9' * code_size,
            'name': self.env._("Undistributed Profits/Losses"),
            "account_type": "equity_unaffected",
            "company_ids": [Command.set(equity_unaffected_companies.ids)],
            }
        return vals

    def run(self):
        self.ensure_one()
        if self.input_start_line <= 0:
            raise UserError(self.env._("The Start Line must be strictly positive."))
        if self.input_sheet_number <= 0:
            raise UserError(self.env._("The Sheet Number must be strictly positive."))
        self._delete_existing_accounts()
        fileobj = BytesIO()
        file_bytes = base64.b64decode(self.input_file)
        fileobj.write(file_bytes)
        fileobj.seek(0)
        try:
            wb = openpyxl.load_workbook(fileobj, read_only=True)
        except Exception:
            raise UserError(self.env._("The input file '%s' is not an XLSX file.") % self.input_filename)
        try:
            sheet = wb.worksheets[self.input_sheet_number - 1]
        except Exception:
            raise UserError(self.env._("Sheet n°%(sheet_number)s doen't exist in file '%(filename)s'.", sheet_number=self.input_sheet_number, filename=self.input_filename))

        custom_chart = {}
        line = 0
        for row in sheet.rows:
            line += 1
            if line < self.input_start_line:
                logger.info('Skipped line %d', line)
                continue
            if len(row) < 2:
                logger.info('Skipping line %d because col A and/or B are empty', line)
                continue
            code = row[0].value and str(row[0].value).strip() or False
            name = row[1].value and row[1].value.strip() or False
            note = len(row) > 2 and row[2].value and row[2].value.strip() or False
            if code and name:
                if len(code) < 3:
                    raise UserError(
                        self.env._("Line %(line)s: account Code '%(code)s' is too small (length < 3).", line=line, code=code))
                if not code[:3].isdigit():
                    raise UserError(
                        self.env._("Line %(line)s: account '%(code)s': the 3 first caracters are not digits.", line=line, code=code))
                if code in custom_chart:
                    raise UserError(self.env._(
                        "Double entry in the chart of account: account '%s'.", code))
                custom_chart[code] = {"name": name, "note": note}
        # print('custom_chart ====')
        # pprint(custom_chart)
        vals_list, custom_code_size = self._generate_custom_chart(custom_chart)
        vals_list_final = self._prepare_accounts(vals_list)
        first_company_id = self.company_ids[0].id
        accounts = self.env['account.account'].sudo().with_company(first_company_id).create(vals_list_final)
        logger.info(f"{len(accounts)} accounts created in company ID {first_company_id}")
        if len(self.company_ids) > 1:
            for company in self.company_ids[1:]:
                logger.info(f"Adding accounts in company ID {company.id} with the same code")
                for account in accounts:
                    account.with_company(company.id).sudo().write(
                        {
                            'company_ids': [Command.link(company.id)],
                            'code': account.with_company(first_company_id).code,
                        })
        if self.create_unaffected_earnings_account:
            equity_unaffected_companies = self.env['res.company']
            for company in self.company_ids:

                has_equity_unaffected_account = self.env['account.account'].search_count([
                    ('account_type', '=', 'equity_unaffected'),
                    ('company_ids', 'in', company.id),
                    ])
                if not has_equity_unaffected_account:
                    equity_unaffected_companies |= company
            if equity_unaffected_companies:
                equity_unaffected_account = self.env['account.account'].sudo().create(self._prepare_equity_unaffected_account(equity_unaffected_companies, custom_code_size))
                accounts |= equity_unaffected_account
        action = self.env["ir.actions.actions"]._for_xml_id("account.action_account_form")
        action['domain'] = [('id', 'in', accounts.ids)]
        return action

    def _delete_existing_accounts(self):
        if self.delete_existing_accounts == 'selected_companies':
            companies = self.company_ids
        elif self.delete_existing_accounts == 'all_companies':
            companies = self.env['res.company'].search([])
        else:
            companies = False
        if companies:
            company_ids = companies.ids
            # on account.journal, only default_account_id and suspense_account_id have ondelete='restrict'
            journals = self.env['account.journal'].sudo().search([('company_id', 'in', company_ids)])
            logger.info('Setting default_account_id and suspense_account_id to false on account.journal IDs %s', journals.ids)
            journals.write({'default_account_id': False, 'suspense_account_id': False})
            if 'pos.payment.method' in self.env:
                pos_pay_methods = self.env['pos.payment.method'].sudo().search([('company_id', 'in', company_ids)])
                logger.info('Setting outstanding_account_id and receivable_account_id to false on pos.payment.method IDs %s', pos_pay_methods.ids)
                pos_pay_methods.write({'outstanding_account_id': False, 'receivable_account_id': False})
            account_account_field_ids = list(self.env['ir.model.fields']._search([('relation', '=', 'account.account')]))
            ir_defaults = self.env['ir.default'].sudo().search([('field_id', 'in', account_account_field_ids), ('company_id', 'in', company_ids)])
            logger.info('Setting json_value to false on ir.default IDs %s', ir_defaults.ids)
            ir_defaults.write({'json_value': 'false'})
            fp_accounts = self.env['account.fiscal.position.account'].sudo().search([('company_id', 'in', company_ids)])
            logger.info('Deleting account.fiscal.position.account IDs %s', fp_accounts.ids)
            fp_accounts.unlink()
            # for tax rep lines, we set account_id to false, not because of ondelete='restrict'
            # but because there is a constraint on unlink() of account.account
            tax_rep_lines = self.env['account.tax.repartition.line'].sudo().search([('account_id', '!=', False), ('company_id', 'in', company_ids)])
            logger.info('Setting account_id to false on account.tax.repartition.line IDs %s', tax_rep_lines.ids)
            tax_rep_lines.write({'account_id': False})
            accounts = self.env['account.account'].sudo().search([('company_ids', 'in', company_ids)])
            logger.info('Deleting account.account IDs %s', accounts.ids)
            accounts.unlink()

    def _generate_custom_chart(self, custom_chart):
        # arg 'custom_chart': list of tuple
        # tuple: ('622600', {'name': 'Honoraires comptables'})
        # in the second value of the tuple, we often only put name,
        # but we can put other odoo properties
        self.ensure_one()
        custom2odoo_code_map = self._prepare_custom2odoo_code_map()
        fixed_size_code = self.fixed_size_code
        # taxtemplate2xmlid = self.generate_id2xmlid("account.tax.template")
        # logger.info("taxtemplate2xmlid = %s", taxtemplate2xmlid)
        # pre-load odoo's chart of account
        odoo_chart = {}
        assert self.source_module in ('l10n_fr_account', 'l10n_fr_account_oca')
        if self.source_module == 'l10n_fr_account':
            odoo_chart_csv_path = 'addons/l10n_fr_account/data/template/account.account-fr.csv'
        elif self.source_module == 'l10n_fr_account_oca':
            odoo_chart_csv_path = 'addons/l10n_fr_account_oca/data/template/account.account-fr_oca.csv'
        odoo_code_size = False
        try:
            odoo_chart_file = file_open(odoo_chart_csv_path)
        except FileNotFoundError:
            raise UserError(self.env._("Cannot find file '%(path)s'. Make sure the module %(module)s is available in Odoo server's addons_path.", path=odoo_chart_csv_path, module=self.source_module))
        bool_map = {
            'true': True,
            'false': False,
            }
        for row in csv.DictReader(odoo_chart_file):
            # taxes_xmlids = [taxtemplate2xmlid[tax.id] for tax in account.tax_ids]
            non_trade = row['non_trade'] and row['non_trade'].strip().lower() or False
            if non_trade:
                non_trade = bool_map.get(non_trade)
            reconcile = row['reconcile'] and row['reconcile'].strip().lower() or False
            if reconcile:
                reconcile = bool_map.get(reconcile)

            odoo_chart[row['code']] = {
                "reconcile": reconcile,
                "account_type": row['account_type'],
                "non_trade": non_trade,
                # "tax_xmlids": ",".join(taxes_xmlids),
            }
            if not odoo_code_size:
                odoo_code_size = len(row['code'])
        # print('odoo_chart====')
        # pprint(odoo_chart)
        vals_list = []
        custom_code_size = False
        for custom_code, src_custom_dict in custom_chart.items():
            if fixed_size_code:
                if custom_code_size:
                    if len(custom_code) != custom_code_size:
                        raise UserError(
                            self.env._(
                                "For account code %(custom_code)s, "
                                "the size (%(cur_code_size)s) is different "
                                "from the size of other accounts (%(custom_code_size)s).",
                                custom_code=custom_code,
                                cur_code_size=len(custom_code),
                                custom_code_size=custom_code_size)
                            )
                else:
                    custom_code_size = len(custom_code)
                    if custom_code_size < odoo_code_size:
                        raise UserError(
                            self.env._(
                                "For account code %(custom_code)s, "
                                "the custom code size (%(custom_code_size)s) "
                                "is < odoo's code size (%(odoo_code_size)s)",
                                custom_code=custom_code,
                                custom_code_size=custom_code_size,
                                odoo_code_size=odoo_code_size)
                            )
                size = odoo_code_size
            else:
                size = len(custom_code)
            exit_while = False
            matching_code = custom_code
            if custom2odoo_code_map and custom_code in custom2odoo_code_map:
                matching_code = custom2odoo_code_map[custom_code]
            while size > 1 and not exit_while:
                short_matching_code = matching_code[:size]
                for odoo_code, odoo_dict in odoo_chart.items():
                    if odoo_code.startswith(short_matching_code):
                        custom_dict = odoo_dict.copy()
                        custom_dict.update(src_custom_dict)
                        custom_dict["code"] = custom_code
                        vals_list.append(custom_dict)
                        exit_while = True
                        break
                size -= 1
            if not exit_while:
                raise UserError(
                    self.env._("Account %(code)s '%(name)s' didn't match any Odoo account.",
                    code=custom_code, name=src_custom_dict.get("name")))
        # print('vals_list===')
        # pprint(vals_list)
        return vals_list, custom_code_size
