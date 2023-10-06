# Copyright 2021-2023 Akretion France (https://www.akretion.com).
# @author Sébastien BEAU <sebastien.beau@akretion.com>
# @author: Alexis de Lattre <alexis.delattre@akretion.com>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import api, models, Command, _
from stdnum.ean import is_valid
from odoo.exceptions import UserError
from datetime import datetime

import logging
logger = logging.getLogger(__name__)


class ProductProduct(models.Model):
    _inherit = "product.product"

#    fullname = fields.Char(compute="_compute_fullname", store=True)

#    @api.depends(
#        "product_tmpl_id.name", "default_code", "product_template_attribute_value_ids"
#    )
#    def _compute_fullname(self):
#        for record in self.with_context(display_default_code=True, partner_id=False):
#            record.fullname = record.display_name

    @api.model
    def _import_speedy(self):
        speedy = self.env['import.show.logs']._import_speedy(chatgpt=True)
        speedy.update({
            'vat_rate2fc_id': {},
            'currency2id': {},
            'categ2id': {},
            'barcode2name': {},
            'default_code2name': {},
            'pos': hasattr(self, 'pos_categ_id'),
            'pos_categ2id': {},
            })
        for fc in self.env['account.product.fiscal.classification'].search([]):
            if len(fc.purchase_tax_ids) == 1 and len(fc.sale_tax_ids) == 1:
                purchase_rate = int(round(fc.purchase_tax_ids[0].amount * 10))
                sale_rate = int(round(fc.sale_tax_ids[0].amount * 10))
                if sale_rate != purchase_rate:
                    raise UserError(_("On fiscal classification %s (ID %d), the purchase tax rate (%s) is different from the sale tax rate (%s)") % (fc.display_name, fc.id, purchase_rate, sale_rate))
                speedy['vat_rate2fc_id'][sale_rate] = fc.id
            elif not fc.purchase_tax_ids and not fc.sale_tax_ids:
                speedy['vat_rate2fc_id'][0] = fc.id
            else:
                logger.warning('Ignoring fiscal classification %s ID %d', fc.display_name, fc.id)
        logger.info('Fiscal classification map: %s', speedy['vat_rate2fc_id'])
        for cur in self.env['res.currency'].search_read([], ['name']):
            speedy['currency2id'][cur['name']] = cur['id']
        for categ in self.env['product.category'].search_read([], ['name']):
            speedy['categ2id'][categ['name']] = categ['id']
        if speedy['pos']:
            for pos_categ in self.env['pos.category'].search_read([], ['name']):
                speedy['pos_categ2id'][pos_categ['name']] = pos_categ['id']
        wh = self.env['stock.warehouse'].search([('company_id', '=', self.env.company.id)], limit=1)
        if wh:
            speedy['default_location_id'] = wh.lot_stock_id.id
        products = self.env['product.product'].with_context(active_test=False).search_read([], ['display_name', 'barcode', 'default_code'])
        for product in products:
            if product['barcode']:
                speedy['barcode2name'][product['barcode']] = '%s (ID %d)' % (product['display_name'], product['id'])
            if product['default_code']:
                speedy['default_code2name'][product['default_code']] = '%s (ID %d)' % (product['display_name'], product['id'])

        return speedy

    def _import_create(self, vals, speedy, inventory=True, location_id=False):
        stock_qty = vals.get('stock_qty', 0)
        location_id = location_id or speedy.get('default_location_id')
        rvals = self._import_prepare_vals(vals, location_id, speedy)
        if not rvals:
            logger.warning('Product on line %s skipped', vals.get('line'))
            return False
        product = self.create(rvals)
        create_date_dt = self.env['import.show.logs']._prepare_create_date(vals, speedy)
        if create_date_dt:
            self._cr.execute(
                "UPDATE product_product SET create_date=%s WHERE id=%s",
                (create_date_dt, product.id))
            self._cr.execute(
                "UPDATE product_template SET create_date=%s WHERE id=%s",
                (create_date_dt, product.product_tmpl_id.id))
        vals['display_name'] = product.display_name
        vals['id'] = product.id
        if product.barcode:
            speedy['barcode2name'][product.barcode] = '%s (ID %d)' % (vals['display_name'], vals['id'])
        if product.default_code:
            speedy['default_code2name'][product.default_code] = '%s (ID %d)' % (vals['display_name'], vals['id'])
        logger.info('New product created: %s ID %d from line %d', product.display_name, product.id, vals['line'])
        if inventory and stock_qty:
            if product.type == 'product':
                product._set_stock_level(stock_qty, location_id, speedy)
            else:
                speedy['logs'].append({
                    'msg': 'Cannot set stock_qty=%s on product with type=%s' (stock_qty, product.type),
                    'value': stock_qty,
                    'vals': vals,
                    'field': 'product.product,qty_available',
                    'reset': True,
                    })
        return product

    def _set_stock_level(self, stock_qty, location_id, speedy):
        if not location_id:
            raise UserError(_("location_id argument is not set and no warehouse in company '%s'.") % self.env.company.display_name)
        self.env['stock.quant'].with_context(inventory_mode=True).create({
            'product_id': self.id,
            'location_id': location_id,
            'inventory_quantity': stock_qty,
        })._apply_inventory()
        logger.info('Stock qty %s set on product %s', stock_qty, self.display_name)

    # vals is a dict to create a product.product
    # It must contain a 'line' key, to indicate Excel/CSV import ref in logs
    # (removed before calling create)
    # it can contain some special keys, which will be replaced by the corresponding real key after processing:
    # - vat_rate: 200, 100, 55, 21, 0
    # - supplier_id: res.partner ID of the supplier
    # - supplier_price
    # - supplier_currency
    # - supplier_product_code
    # - supplier_product_name
    # - supplier_delay
    # - categ_name
    # - pos_categ_name
    # - stock_qty
    # - orderpoint_min_qty
    # - orderpoint_max_qty
    # - orderpoint_trigger
    @api.model
    def _import_prepare_vals(self, vals, location_id, speedy):
        # TODO add support for pos_product_multi_barcode
        assert vals
        assert isinstance(vals, dict)
        assert isinstance(speedy, dict)
        for key, value in vals.items():
            if isinstance(value, str):
                vals[key] = value.strip() or False
        if vals.get('default_code'):
            if vals['default_code'] in speedy['default_code2name']:
                speedy['logs'].append({
                    'msg': "PRODUCT NOT IMPORTED: internal reference '%s' used on another product '%s'" % (vals['default_code'], speedy['default_code2name'][vals['default_code']]),
                    'value': vals['default_code'],
                    'vals': vals,
                    'field': 'product.product,default_code',
                    'reset': True,
                    })
                return False
        if vals.get('barcode'):
            barcode = vals['barcode']
            if barcode in speedy['barcode2name']:
                speedy['logs'].append({
                    'msg': "PRODUCT NOT IMPORTED: barcode '%s' used on another product '%s'" % (barcode, speedy['barcode2name'][barcode]),
                    'value': barcode,
                    'vals': vals,
                    'field': 'product.product,barcode',
                    'reset': True,
                    })
                return False
            if len(barcode) in (8, 13):
                if not is_valid(barcode):
                    speedy['logs'].append({
                        'msg': 'Barcode %s has an invalid checksum' % barcode,
                        'value': barcode,
                        'vals': vals,
                        'field': 'product.product,barcode',
                        })
            else:
                speedy['logs'].append({
                    'msg': 'Barcode %s has %d caracters (should be 8 or 13 for an EAN barcode)' % (barcode, len(barcode)),
                    'value': barcode,
                    'vals': vals,
                    'field': 'product.product,barcode',
                    })
        if 'vat_rate' in vals:
            vat_rate = vals['vat_rate']
            if not isinstance(vat_rate, int):
                speedy['logs'].append({
                    'msg': 'vat_rate key must be an integer, not %s' % type(vat_rate),
                    'value': vat_rate,
                    'vals': vals,
                    'field': 'product.product,barcode',
                    'reset': True,
                    })

            if vat_rate in speedy['vat_rate2fc_id']:
                vals['fiscal_classification_id'] = speedy['vat_rate2fc_id'][vat_rate]
            else:
                speedy['logs'].append({
                    'msg': '%s is not a know VAT rate (%s)' % (vat_rate, ', '.join([str(x) for x in speedy['vat_rate2fc_id']])),
                    'value': vat_rate,
                    'vals': vals,
                    'field': 'product.product,barcode',
                    'reset': True,
                    })
        if vals.get('categ_name'):
            if vals['categ_name'] not in speedy['categ2id']:
                categ = self.env['product.category'].create(self._import_prepare_product_category(vals, speedy))
                speedy['categ2id'][vals['categ_name']] = categ.id
            vals['categ_id'] = speedy['categ2id'][vals['categ_name']]
        if speedy['pos'] and vals.get('pos_categ_name'):
            if vals['pos_categ_name'] not in speedy['pos_categ2id']:
                pos_categ = self.env['pos.category'].create(self._import_prepare_pos_category(vals, speedy))
                speedy['pos_categ2id'][vals['pos_categ_name']] = pos_categ.id
            vals['pos_categ_id'] = speedy['pos_categ2id'][vals['pos_categ_name']]

        supplierinfo_vals = {}
        if vals.get('supplier_id'):
            partner_id = vals['supplier_id']
            supplierinfo_vals = {
                'partner_id': vals['supplier_id'],
                'price': vals.get('supplier_price'),
                'product_code': vals.get('supplier_product_code'),
                'product_name': vals.get('supplier_product_name'),
                }
            if vals.get('supplier_delay'):
                supplierinfo_vals['delay'] = vals['supplier_delay']
            if vals.get('supplier_currency'):
                if isinstance(vals['supplier_currency'], int):
                    supplierinfo_vals['currency_id'] = vals['supplier_currency']
                elif isinstance(vals['supplier_currency'], str):
                    currency = vals['supplier_currency'].upper().strip()
                    if currency in speedy['currency2id']:
                        supplierinfo_vals['currency_id'] = speedy['currency2id'][currency]
                    else:
                        speedy['logs'].append({
                            'msg': '%s is not a known currency ISO code' % currency,
                            'value': currency,
                            'vals': vals,
                            'field': 'product.supplierinfo,currency_id',
                            'reset': True,
                            })
            vals['seller_ids'] = [Command.create(supplierinfo_vals)]
        if vals.get('orderpoint_min_qty'):
            if not location_id:
                raise UserError(_("location_id argument is not set and no warehouse in company '%s'.") % self.env.company.display_name)
            orderpoint_vals = {
                'product_min_qty': vals['orderpoint_min_qty'],
                'product_max_qty': vals.get('orderpoint_max_qty', vals['orderpoint_min_qty']),
                'location_id': location_id,
                }
            if vals.get('orderpoint_trigger'):
                vals['trigger'] = vals['orderpoint_trigger']
            vals['orderpoint_ids'] = [Command.create(orderpoint_vals)]
        if not vals.get('responsible_id'):
            # field 'responsible_id' is add by the module 'stock'
            # Avoid to have current user as responsible for all imported products !
            vals['responsible_id'] = False
        # Remove all keys that start with supplier_
        # vals will keep the original keys
        # rvals will be used for create(), so we need to remove all the keys are don't exist on res.partner
        rvals = dict(vals)
        for key in ['line', 'create_date', 'vat_rate', 'categ_name', 'pos_categ_name', 'stock_qty']:
            if key in rvals:
                rvals.pop(key)
        for key in vals.keys():
            if key != 'orderpoint_ids' and (key.startswith('supplier_') or key.startswith('orderpoint_')):
                rvals.pop(key)
        return rvals

    def _import_prepare_product_category(self, vals, speedy):
        return {'name': vals['categ_name']}

    def _import_prepare_pos_category(self, vals, speedy):
        return {'name': vals['pos_categ_name']}

    def _import_result_action(self, speedy):
        return self.env['import.show.logs']._import_result_action(speedy)
