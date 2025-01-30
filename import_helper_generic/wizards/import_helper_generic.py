from typing import dataclass_transform
from decorator import append
from openpyxl.workbook import child
from odoo import api, fields, models
from tempfile import NamedTemporaryFile
import base64

from odoo.fields import Command

import openpyxl as opx

import logging
from stdnum.iban import is_valid as iban_is_valid

logger = logging.getLogger(__name__)

LIST_FR = ["FR", "France", "Martinique - France", "REUNION", "Paris"]
LIST_COL_POP = [
    "invoice_name",
    "invoice_title_code",
    "invoice_street",
    "invoice_street2",
    "invoice_city",
    "invoice_zip",
    "invoice_phone",
    "invoice_mobile",
    "invoice_lang",
    "delivery_name",
    "delivery_title_code",
    "delivery_street",
    "delivery_street2",
    "delivery_city",
    "delivery_zip",
    "delivery_phone",
    "delivery_mobile",
    "delivery_lang",
]


class ImportHelpergeneric(models.TransientModel):
    _name = "import.helper.generic"
    _description = "Import helper generic for importing information with template"

    file_import = fields.Binary(string="File to import")

    def speedy_categori_id(self):
        categ_id = {}
        categs = self.env["res.partner.category"].search([])
        for c in categs:
            categ_id[c.name] = c.id
        return categ_id

    def check_vals(self, vals):
        if "category_id" in vals:
            categ_ids = self.speedy_categori_id()
            list_categ = []
            for ctname in vals["category_id"].split("/"):
                if ctname and vals["category_id"] in categ_ids:
                    list_categ.append(categ_ids[ctname])
                vals["category_id"] = [Command.set(list_categ)]
        if "invoice_name" in vals:
            child_val = {"type": "invoice"}
            vals["child_ids"] = []
            for v in vals:
                if "invoice_" in v:
                    child_val[v.replace("invoice_", "")] = vals[v]
            vals["child_ids"].append((0, 0, child_val))
        if "delivery_name" in vals:
            child_val = {"type": "delivery"}
            for v in vals:
                if "delivery_" in v:
                    child_val[v.replace("delivery_", "")] = vals[v]
            if "child_ids" in vals:
                vals["child_ids"].append((0, 0, child_val))
            else:
                vals["child_ids"] = [(0, 0, child_val)]
        for i in LIST_COL_POP:
            if vals.get(i):
                vals.pop(i)
        return vals

    def partner_import_generic(self):
        fileobj = NamedTemporaryFile(
            "wb+", prefix="odoo-import_helper-", suffix=".xlsx"
        )
        file_bytes = base64.b64decode(self.file_import)
        fileobj.write(file_bytes)
        fileobj.seek(0)
        dataframe = opx.load_workbook(fileobj.name, read_only=True)
        reader = dataframe.active
        import_obj = self.env["import.helper"]
        speedy = import_obj._prepare_speedy(aiengine="NONE")
        line = 0
        colonnes = []
        speedy_categ_id = self.speedy_categori_id()
        for row in reader.iter_rows(min_row=4, max_col=39, values_only=True):
            vals = {}
            if row[0] == "Colonnes:":
                for c in range(len(row)):
                    if row[c]:
                        colonnes.append(row[c])
                    else:
                        colonnes.append("empty")
                continue

            if row[2]:
                line += 1
                vals["line"] = line
                for c in range(len(row)):
                    if row[c] and colonnes[c] != "empty":
                        vals[colonnes[c]] = str(row[c])
            vals = self.check_vals(vals)
            import_obj._create_partner(vals, speedy)
        action = import_obj._result_action(speedy)
        return action
