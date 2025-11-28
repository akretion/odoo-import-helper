# Copyright 2023 Akretion France (http://www.akretion.com/)
# @author: Alexis de Lattre <alexis.delattre@akretion.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo.tests.common import TransactionCase


class TestBaseImportHelper(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))
        # create data

    def test_match_country(self):
        iho = self.env["import.helper"]
        speedy = iho._prepare_speedy()
        country_id = iho._match_country(
            {"country_name": "fr"}, "country_name", "res.partner", "country_id", speedy
        )
        self.assertEqual(country_id, self.env.ref("base.fr").id)
        country_id = iho._match_country(
            {"country_name": "FRA"}, "country_name", "res.partner", "country_id", speedy
        )
        self.assertEqual(country_id, self.env.ref("base.fr").id)
        country_id = iho._match_country(
            {"country_name": "France"},
            "country_name",
            "res.partner",
            "country_id",
            speedy,
        )
        self.assertEqual(country_id, self.env.ref("base.fr").id)
        country_id = iho._match_country(
            {"country_name": "U.S.A."},
            "country_name",
            "res.partner",
            "country_id",
            speedy,
        )
        self.assertEqual(country_id, self.env.ref("base.us").id)
        # country_id = iho._match_country(
        #     {"country_name": "España"},
        #     "country_name",
        #     "res.partner",
        #     "country_id",
        #     speedy
        # )
        # self.assertEqual(country_id, self.env.ref('base.es').id)
