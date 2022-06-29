# Copyright 2022 Akretion France
# @author: Alexis de Lattre <alexis.delattre@akretion.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import api, fields, models
# from odoo.exceptions import UserError
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


class AccountDefaultIrProperty(models.TransientModel):
    _name = "account.default.ir.property"
    _description = "Generate/Update default ir.property"

    company_id = fields.Many2one(
        'res.company', string='Company', required=True, readonly=True)
    del_existing_property_res_partner = fields.Boolean(default=True, string='Delete Existing Specific Partner Account Properties')
    del_existing_property_product_category = fields.Boolean(default=False, string='Delete Existing Specific Product Category Account Properties')
    partner_receivable_account_id = fields.Many2one(
        'account.account',
        string='Partner Account Receivable', required=True,
        domain="[('internal_type', '=', 'receivable'), ('deprecated', '=', False), ('company_id', '=', company_id)]")
    # target field: property_account_receivable_id
    partner_payable_account_id = fields.Many2one(
        'account.account',
        string='Partner Payable Account', required=True,
        domain="[('internal_type', '=', 'payable'), ('deprecated', '=', False), ('company_id', '=', company_id)]")
    # target field: property_account_payable_id
    product_categ_income_account_id = fields.Many2one(
        'account.account',
        string='Product Category Income Account', required=True,
        domain="[('deprecated', '=', False), ('internal_type', '=', 'other'), ('company_id', '=', company_id), ('is_off_balance', '=', False)]")
    # target field: property_account_income_categ_id
    product_categ_expense_account_id = fields.Many2one(
        'account.account',
        string='Product Category Expense Account', required=True,
        domain="[('deprecated', '=', False), ('internal_type', '=', 'other'), ('company_id', '=', company_id), ('is_off_balance', '=', False)]")
    # target field: property_account_expense_categ_id
    partner_receivable_account_property_id = fields.Many2one(
        'ir.property', readonly=True)
    partner_payable_account_property_id = fields.Many2one(
        'ir.property', readonly=True)
    product_categ_income_account_property_id = fields.Many2one(
        'ir.property', readonly=True)
    product_categ_expense_account_property_id = fields.Many2one(
        'ir.property', readonly=True)

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
        ipo = self.env['ir.property']
        for wizard_field, field_dict in WIZARD2FIELD.items():

            ir_property = ipo.search([
                ('company_id', '=', company_id),
                ('type', '=', 'many2one'),
                ('res_id', '=', False),
                ('value_reference', '=like', 'account.account,%'),
                ('fields_id', '=', self._get_field_id(field_dict)),
                ], limit=1)
            if ir_property:
                account_id = int(ir_property.value_reference.split(',')[1])
                res[wizard_field] = account_id
                res[wizard_field.replace('_id', '_property_id')] = ir_property.id
        return res

    def run(self):
        self.ensure_one()
        ipo = self.env['ir.property']
        company_id = self.company_id.id
        property_ids = []
        for wizard_field, field_dict in WIZARD2FIELD.items():
            field_id = self._get_field_id(field_dict)
            if self['del_existing_property_%s' % field_dict['model'].replace('.', '_')]:
                properties = ipo.search([
                    ('company_id', '=', company_id),
                    ('type', '=', 'many2one'),
                    ('fields_id', '=', field_id),
                    ('res_id', '!=', False),
                    ])
                logger.info('Deleted %d ir.properties %s', len(properties), wizard_field)
                properties.sudo().unlink()
            prop_field_name = wizard_field.replace('_id', '_property_id')
            value_reference = 'account.account,%d' % self[wizard_field].id
            if self[prop_field_name]:
                self[prop_field_name].write({'value_reference': value_reference})
                property_ids.append(self[prop_field_name].id)
            else:
                new_prop = ipo.create({
                    'company_id': company_id,
                    'name': field_dict['field'],
                    'fields_id': field_id,
                    'type': 'many2one',
                    'res_id': False,
                    'value_reference': value_reference,
                    })
                property_ids.append(new_prop.id)
        action = self.env["ir.actions.actions"]._for_xml_id("base.ir_property_form")
        action['domain'] = [('id', 'in', property_ids)]
        return action
