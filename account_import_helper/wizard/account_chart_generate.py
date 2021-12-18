# Copyright 2017-2020 Akretion France
# @author: Alexis de Lattre <alexis.delattre@akretion.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import base64
import logging
from pprint import pprint
from tempfile import TemporaryFile
import csv

from odoo import _, fields, models
from odoo.exceptions import UserError

logger = logging.getLogger(__name__)


class AccountChartGenerate(models.TransientModel):
    _name = "account.chart.generate"
    _description = "Generate customer-specific chart of accounts"

    module = fields.Char(
        "Module Name",
        required=True,
        default="custom",
        help="Used for the first part of the XMLID (before the dot)",
    )
    xmlid_prefix = fields.Char("XMLID prefix", required=True, default="account_")
    fixed_size_code = fields.Boolean(default=True)
    with_taxes = fields.Boolean(default=True)
    csv_file = fields.Binary(required=True, string="CSV file")
    csv_filename = fields.Char()
    out_csv_file = fields.Binary(string="Result CSV file", readonly=True)
    out_csv_filename = fields.Char(readonly=True)
    state = fields.Selection(
        [("step1", "step1"), ("step2", "step2")], default="step1", required=True
    )

    def _prepare_custom2odoo_code_map(self):
        custom2odoo_code_map = {}
        return custom2odoo_code_map

    def run(self):
        fileobj = TemporaryFile("w+")
        decoded_csv = base64.b64decode(self.csv_file)
        fileobj.write(decoded_csv.decode('utf-8'))
        fileobj.seek(0)
        reader = csv.DictReader(
            fileobj,
            delimiter=",",
            fieldnames=["code", "name", "note"],
        )
        custom_chart = []
        for line in reader:
            if (
                    line["code"]
                    and line["name"]
                    and line["code"].strip()
                    and line["name"].strip()
            ):
                code = line["code"].strip()
                name = line["name"].strip()
                if len(code) < 3:
                    raise UserError(
                        _("Account Code '%s' is too small (len < 3)") % code)
                if not code[:3].isdigit():
                    raise UserError(
                        _("Account '%s': the 3 first caracters are not digits") % code)
                custom_chart.append(
                    (code, {"name": name, "note": line["note"] and line["note"].strip() or False})
                )
        pprint(custom_chart)
        logger.info("Starting to generate CSV file")
        res = self.env["account.account"].generate_custom_chart(
            custom_chart,
            module=self.module,
            xmlid_prefix=self.xmlid_prefix,
            fixed_size_code=self.fixed_size_code,
            custom2odoo_code_map=self._prepare_custom2odoo_code_map(),
            with_taxes=self.with_taxes,
        )
        fout = TemporaryFile("w+")
        w = csv.DictWriter(
            fout,
            [
                "id",
                "code",
                "name",
                "user_type_xmlid",
                "reconcile",
                "tax_xmlids",
                "note",
            ],
        )
        for account_dict in res:
            w.writerow(account_dict)
        fout.seek(0)
        res_file = fout.read()
        self.write(
            {
                "state": "step2",
                "out_csv_file": base64.b64encode(res_file.encode('utf-8')),
                "out_csv_filename": "account.account-%s.csv" % self.module,
            }
        )
        fout.close()
        logger.info("End of the generation of CSV file")
        action = self.env["ir.actions.actions"]._for_xml_id(
            "account_import_helper.account_chart_generate_action")
        action["res_id"] = self.ids[0]
        return action
