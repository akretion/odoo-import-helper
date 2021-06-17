# Copyright 2020 Akretion (https://www.akretion.com).
# @author Sébastien BEAU <sebastien.beau@akretion.com>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.addons.component.tests.common import SavepointComponentCase


class TestImportImage(SavepointComponentCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

    def test_process_import_from_url(self):
        self.env["image.relation.abstract"]._process_import_from_url(
            {
                "import_from_url": (
                    "https://xml.andapresent.com/product_images/"
                    "0x0/auto/ap844042-01_pbogyy3c.jpg?v=1"
                )
            }
        )
