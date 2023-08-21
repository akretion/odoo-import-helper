# Copyright 2023 Akretion France (http://www.akretion.com/)
# @author: Alexis de Lattre <alexis.delattre@akretion.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo.tests.common import SavepointCase


class TestBaseImportHelper(SavepointCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))
        # create data

    def test_match_country(self):
        rpo = self.env['res.partner']
        speeddict = rpo._import_speeddict()
        country_id = rpo._match_country("fr", speeddict)
        self.assertEqual(country_id, self.env.ref('base.fr').id)
        country_id = rpo._match_country("France", speeddict)
        self.assertEqual(country_id, self.env.ref('base.fr').id)
        country_id = rpo._match_country("U.S.A.", speeddict)
        self.assertEqual(country_id, self.env.ref('base.us').id)
        country_id = rpo._match_country("España", speeddict)
        self.assertEqual(country_id, self.env.ref('base.es').id)
