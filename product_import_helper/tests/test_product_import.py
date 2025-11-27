# Copyright 2024 Akretion France (http://www.akretion.com/)
# @author: Alexis de Lattre <alexis.delattre@akretion.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class ProductImportHelper(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))

    def test_product_import(self):
        vals = {
            "line": 1,
            "name": " Carte-postale Ventoux ",
            "default_code": " CPVTX ",
            "barcode": "12345678",
            "type": "consu",
            "is_storable": True,
            "categ_name": "Cartes Postales",
            "orderpoint_min_qty": 5,
            "orderpoint_max_qty": 12,
            "stock_qty": 10,
            "create_date": "2012-12-12",
            "origin_country_name": "FRA",
            "hs_code_code": "84717050",
        }
        import_obj = self.env["import.helper"]
        speedy = import_obj._prepare_speedy()
        product = import_obj._create_product(vals, speedy)
        action = import_obj._result_action(speedy)
        self.assertEqual(product.name, vals["name"].strip())
        self.assertEqual(product.default_code, vals["default_code"].strip())
        self.assertEqual(product.categ_id.name, vals["categ_name"])
        self.assertEqual(product.qty_available, vals["stock_qty"])
        self.assertEqual(len(product.orderpoint_ids), 1)
        self.assertEqual(
            product.orderpoint_ids[0].product_min_qty, vals["orderpoint_min_qty"]
        )
        self.assertEqual(
            product.orderpoint_ids[0].product_max_qty, vals["orderpoint_max_qty"]
        )
        self.assertTrue(isinstance(action, dict))
