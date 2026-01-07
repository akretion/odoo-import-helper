# Copyright 2022 Akretion France
# @author: Alexis de Lattre <alexis.delattre@akretion.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import api, fields, models
import logging

logger = logging.getLogger(__name__)

WIZARD2FIELD = {
    "partner_receivable_account_id": {
        'field': 'property_account_receivable_id', 'model': 'res.partner'},
    "partner_payable_account_id": {
        'field': "property_account_payable_id", 'model': 'res.partner'},
    "product_categ_income_account_id": {
        'field': "property_account_income_categ_id", 'model': 'product.category'},
    "product_categ_expense_account_id": {
        'field': "property_account_expense_categ_id", 'model': 'product.category'},
    }


class AccountChartImportPostprocess(models.TransientModel):
    _name = "account.chart.import.postprocess"
    _description = "Help to reconfigure accounts after CoA import"

    company_id = fields.Many2one(
        'res.company', string='Company', required=True)
    partner_receivable_account_id = fields.Many2one(
        'account.account',
        string='Partner Account Receivable', required=True, check_company=True,
        domain="[('account_type', '=', 'asset_receivable'), ('deprecated', '=', False), ('company_ids', 'in', company_id)]")
    # target field: property_account_receivable_id
    partner_payable_account_id = fields.Many2one(
        'account.account',
        string='Partner Payable Account', required=True, check_company=True,
        domain="[('account_type', '=', 'liability_payable'), ('deprecated', '=', False), ('company_ids', 'in', company_id)]")
    # target field: property_account_payable_id
    product_categ_income_account_id = fields.Many2one(
        'account.account',
        string='Product Category Income Account', required=True, check_company=True,
        domain="[('deprecated', '=', False), ('account_type', '=', 'income'), ('company_ids', 'in', company_id)]")
    # target field: property_account_income_categ_id
    product_categ_expense_account_id = fields.Many2one(
        'account.account',
        string='Product Category Expense Account', required=True, check_company=True,
        domain="[('deprecated', '=', False), ('account_type', '=', 'expense'), ('company_ids', 'in', company_id)]")
    # target field: property_account_expense_categ_id
    partner_receivable_account_default_id = fields.Many2one(
        'ir.default', readonly=True)
    partner_payable_account_default_id = fields.Many2one(
        'ir.default', readonly=True)
    product_categ_income_account_default_id = fields.Many2one(
        'ir.default', readonly=True)
    product_categ_expense_account_default_id = fields.Many2one(
        'ir.default', readonly=True)
    suspense_account_id = fields.Many2one(
        "account.account", string='Suspense Account of Bank/Cash Journals', check_company=True,
        domain="[('deprecated', '=', False), ('account_type', 'in', ('asset_current', 'liability_current')), ('company_ids', 'in', company_id)]",
        )
    transfer_account_id = fields.Many2one(
        'account.account', string="Inter-Banks Transfer Account", check_company=True,
        domain="[('reconcile', '=', True), ('account_type', '=', 'asset_current'), ('deprecated', '=', False), ('company_ids', 'in', company_id)]",
        )

    @api.model
    def _get_field_id(self, field_dict):
        assert field_dict
        imfo = self.env['ir.model.fields']
        field = imfo.search([
            ('name', '=', field_dict['field']),
            ('ttype', '=', 'many2one'),
            ('relation', '=', 'account.account'),
            ('model', '=', field_dict['model']),
            ])
        assert len(field) == 1
        return field.id

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        company_id = self.env.company.id
        res['company_id'] = company_id
        def_obj = self.env['ir.default']
        for wizard_field, field_dict in WIZARD2FIELD.items():

            ir_default = def_obj.search([
                ('company_id', '=', company_id),
                ('condition', '=', False),
                ('field_id', '=', self._get_field_id(field_dict)),
                ], limit=1)
            if ir_default:
                res[wizard_field.replace('_account_id', '_account_default_id')] = ir_default.id
        return res

    def run(self):
        self.ensure_one()
        def_obj = self.env['ir.default']
        company_id = self.company_id.id
        for wizard_field, field_dict in WIZARD2FIELD.items():
            default_wiz_field_name = wizard_field.replace('_account_id', '_account_default_id')
            account_id = self[wizard_field].id
            if self[default_wiz_field_name]:
                self[default_wiz_field_name].write({'json_value': account_id})
                logger.info(
                    'ir.default ID %d updated with account ID %d',
                    self[default_wiz_field_name].id, account_id)
            else:
                vals = {
                    'company_id': company_id,
                    'field_id': self._get_field_id(field_dict),
                    'json_value': account_id,
                    }
                default_rec = def_obj.create(vals)
                logger.info(
                    'ir.default ID %d created with account ID %d',
                    default_rec.id, account_id)
        company_vals = {}
        if self.transfer_account_id and not self.company_id.transfer_account_id:
            company_vals['transfer_account_id'] = self.transfer_account_id.id
        if self.suspense_account_id and not self.company_id.account_journal_suspense_account_id:
            company_vals['account_journal_suspense_account_id'] = self.suspense_account_id.id
        if company_vals:
            logger.info('Writing %s on company %s', company_vals, self.company_id.display_name)
            self.company_id.write(company_vals)
        if self.suspense_account_id:
            bank_journals = self.env['account.journal'].search([
                ('company_id', '=', company_id),
                ('suspense_account_id', '=', False),
                ('type', 'in', ('bank', 'cash', 'credit')),
                ])
            logger.info(
                'Writing suspense account %s on bank/cash journal IDs %s',
                self.suspense_account_id.display_name, bank_journals.ids)
            bank_journals.write({'suspense_account_id': self.suspense_account_id.id})
        return
