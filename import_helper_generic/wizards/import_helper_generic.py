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
    "attributes",
    "ref_supplier",
    "ref_template",
    "Colonnes:",
]


class ImportHelpergeneric(models.TransientModel):
    _name = "import.helper.generic"
    _description = "Import helper generic for importing information with template"

    file_import = fields.Binary(string="File to import")

    def speedy_partner_categori_id(self):
        categ_id = {}
        categs = self.env["res.partner.category"].search([])
        for c in categs:
            categ_id[c.name] = c.id
        return categ_id

    def speedy_partner_id(self):
        partner_list = {}
        partner_ids = self.env["res.partner"].search([])
        for p in partner_ids:
            partner_list[p.ref] = p.id
        return partner_list

    def check_vals_partner(self, vals):
        if "category_id" in vals:
            categ_ids = self.speedy_partner_categori_id()
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
        partner_ids_list = self.speedy_partner_id()
        for row in reader.iter_rows(min_row=4, values_only=True):
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
            vals = self.check_vals_partner(vals)
            if vals["ref"] in partner_ids_list:
                import_obj._prepare_partner_vals(vals, speedy)
                record = self.env["res.partner"].browse(partner_ids_list[vals["ref"]])
                res = record.write(vals)
                if res:
                    logger.info(
                        f"{record.display_name},id {record.id} has been update with line {line}"
                    )
            else:
                import_obj._create_partner(vals, speedy)
        action = import_obj._result_action(speedy)
        return action

    def prepare_speedy_attribute_value(self):
        speedy_attribute_value = {}
        attribute_value = self.env["product.attribute.value"].search([])
        for att in attribute_value:
            speedy_attribute_value[att.fullname] = {
                "id": att.id,
                "attribute_id": att.attribute_id.id,
            }
        return speedy_attribute_value

    def check_vals_product(self, vals):
        variant_att = ()
        list_attribute_ids = {}
        template = False
        if "attributes" in vals:
            speedy_attribute_value = self.prepare_speedy_attribute_value()
            variant_att = vals["attributes"].split("/")
            for v in variant_att:
                if speedy_attribute_value.get(v):
                    if speedy_attribute_value[v]["attribute_id"] in list_attribute_ids:
                        list_attribute_ids[
                            speedy_attribute_value[v]["attribute_id"]
                        ].append(
                            speedy_attribute_value[v]["id"],
                        )
                    else:
                        list_attribute_ids[
                            speedy_attribute_value[v]["attribute_id"]
                        ] = [speedy_attribute_value[v]["id"]]

        if "ref_supplier" in vals:
            speedy_partner_id = self.speedy_partner_id()
            if vals["ref_supplier"] in speedy_partner_id:
                vals["supplier_id"] = speedy_partner_id[vals["ref_supplier"]]
        if vals.get("Colonnes:") == "product.template":
            template = True
        for i in LIST_COL_POP:
            if vals.get(i):
                vals.pop(i)
        return vals, variant_att, list_attribute_ids, template

    def product_import_generic(self):
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
        reference = ""
        for row in reader.iter_rows(min_row=1, max_row=2, max_col=6, values_only=True):
            if row[0] == "Information":
                if row[1] == "Champ de reference":
                    reference = row[2]
        product_ids = self.env["product.product"].search_read(
            [], ["default_code", "barcode"]
        )
        speedy_product_list = {}
        if reference == "default_code":
            for p in product_ids:
                speedy_product_list[p["default_code"]] = p["id"]
        if reference == "barcode":
            for p in product_ids:
                speedy_product_list[p["barcode"]] = p["id"]
        product_template_ids = self.env["product.template"].search_read(
            [], ["default_code_import"]
        )
        speedy_product_template_list = {}
        for p in product_template_ids:
            speedy_product_template_list[p["default_code_import"]] = p["id"]
        list_product_create = {}
        count = 0
        for row in reader.iter_rows(min_row=4, values_only=True):
            vals = {}
            if count >= 200:
                self.env.cr.commit()
                count = 0
                logger.info("commit 200 product")
            if row[0] == "Colonnes:":
                for c in range(len(row)):
                    if row[c]:
                        colonnes.append(row[c])
                    else:
                        colonnes.append("empty")
                continue
            if row[0]:
                line += 1
                count += 1
                vals["line"] = line
                for c in range(len(row)):
                    if row[c] and colonnes[c] != "empty":
                        vals[colonnes[c]] = str(row[c])
                if (
                    vals.get("ref_template")
                    and vals["ref_template"] in speedy_product_template_list
                ):
                    vals["product_tmpl_id"] = speedy_product_template_list[
                        vals["ref_template"]
                    ]
                vals, variant_att, list_attribue_ids, template = (
                    self.check_vals_product(vals)
                )
                # if (
                #     not vals.get("product_tmpl_id")
                #     and vals["default_code"] in speedy_product_template_list
                # ):
                #     location_id = vals.get("location_id") or speedy.get(
                #         "default_location_id"
                #     )
                #     vals = import_obj._prepare_product_vals(vals, location_id, speedy)
                #     res = (
                #         self.env["product.template"]
                #         .browse(speedy_product_list[vals["default_code"]])
                #         .write(vals)
                #     )
                #     if res:
                #         logger.info(
                #             f"{res.display_name},id {res.id} has been update with line {line}"
                #         )
                #     else:
                #         logger.warning(f"line {line} have done nothing")
                if not template:
                    if vals.get(reference) in speedy_product_list:
                        location_id = vals.get("location_id") or speedy.get(
                            "default_location_id"
                        )
                        ref_product = vals.pop(reference)
                        record = self.env["product.product"].browse(
                            speedy_product_list[ref_product]
                        )
                        if record:
                            if record.location_id and record.location_id != location_id:
                                location_id = record.location_id
                            if vals.get("default_code") == record.default_code:
                                vals.pop("default_code")
                            if vals.get("barcode") == record.barcode:
                                vals.pop("barcode")
                            vals = import_obj._prepare_product_vals(
                                vals, location_id, speedy
                            )
                            if not vals:
                                logger.warning("Product on line %s skipped", line)
                                continue
                            if vals.get("standard_price"):
                                vals["standard_price"] = float(vals["standard_price"])
                            res = record.write(vals)
                            if res:
                                logger.info(
                                    f"{record.display_name}, id {record.id} has been update with line {line}"
                                )
                            else:
                                logger.warning(f"line {line} have done nothing")
                            continue
                    elif vals.get("product_tmpl_id"):
                        location_id = vals.get("location_id") or speedy.get(
                            "default_location_id"
                        )
                        vals = import_obj._prepare_product_vals(
                            vals, location_id, speedy
                        )
                        if not vals:
                            logger.warning("Product on line %s skipped", line)
                            continue
                        if vals["product_tmpl_id"] in list_product_create:
                            template = list_product_create[vals["product_tmpl_id"]]
                        else:
                            template = self.env["product.template"].browse(
                                vals["product_tmpl_id"]
                            )
                        for p in template.product_variant_ids:
                            if p.product_template_attribute_value_ids:
                                for v in p.product_template_attribute_value_ids:
                                    if (
                                        v.product_attribute_value_id.fullname
                                        in variant_att
                                    ):
                                        if vals.get("standard_price"):
                                            vals["standard_price"] = float(
                                                vals["standard_price"]
                                            )
                                        if vals.get("list_price") and hasattr(
                                            p, "fix_price"
                                        ):
                                            vals["fix_price"] = vals["list_price"]
                                            vals.pop("list_price")
                                        elif vals.get("list_price"):
                                            vals.pop("list_price")
                                        p.write(vals)
                        continue
                    else:
                        res = import_obj._create_product(vals, speedy)
                        continue
                elif template:
                    if vals.get(reference) in speedy_product_list:
                        location_id = vals.get("location_id") or speedy.get(
                            "default_location_id"
                        )
                        ref_product = vals.pop(reference)
                        record = self.env["product.product"].browse(
                            speedy_product_list[ref_product]
                        )
                        if record:
                            if record.location_id and record.location_id != location_id:
                                location_id = record.location_id
                            if vals.get("default_code") == record.default_code:
                                vals.pop("default_code")
                            if vals.get("barcode") == record.barcode:
                                vals.pop("barcode")
                            vals = import_obj._prepare_product_vals(
                                vals, location_id, speedy
                            )
                            if not vals:
                                logger.warning("Product on line %s skipped", line)
                                continue
                            if vals.get("standard_price"):
                                vals["standard_price"] = float(vals["standard_price"])
                            res = record.write(vals)
                            if res:
                                logger.info(
                                    f"{record.display_name}, id {record.id} has been update with line {line}"
                                )
                            else:
                                logger.warning(f"line {line} have done nothing")
                            continue
                    elif vals.get("default_code") in speedy_product_template_list:
                        location_id = vals.get("location_id") or speedy.get(
                            "default_location_id"
                        )
                        record = self.env["product.template"].browse(
                            speedy_product_template_list[vals["default_code"]]
                        )
                        ref_product = vals.pop("default_code")
                        if record:
                            if record.location_id and record.location_id != location_id:
                                location_id = record.location_id
                            if vals.get("barcode") == record.barcode:
                                vals.pop("barcode")
                            vals = import_obj._prepare_product_vals(
                                vals, location_id, speedy
                            )
                            if not vals:
                                logger.warning("Product on line %s skipped", line)
                                continue

                            res = record.write(vals)
                            if res:
                                if variant_att:
                                    speedy_line_attr = {}
                                    for line_id in record.attribute_line_ids:
                                        speedy_line_attr[line_id.attribute_id.id] = {
                                            "id": line_id.id,
                                            "value_ids": line_id.value_ids.ids,
                                        }

                                    for att in list_attribue_ids:
                                        b = list_attribue_ids[att]
                                        if (
                                            speedy_line_attr.get(att)
                                            and b != speedy_line_attr[att]["value_ids"]
                                        ):
                                            record.attribute_line_ids = [
                                                Command.update(
                                                    speedy_line_attr[att]["id"],
                                                    {
                                                        "value_ids": [
                                                            Command.set(
                                                                speedy_line_attr[att][
                                                                    "value_ids"
                                                                ]
                                                            )
                                                        ]
                                                    },
                                                )
                                            ]
                                        elif (
                                            speedy_line_attr.get(att)
                                            and b == speedy_line_attr[att]["value_ids"]
                                        ):
                                            continue
                                        else:
                                            record.attribute_line_ids = [
                                                Command.create(
                                                    {
                                                        "attribute_id": att,
                                                        "value_ids": [Command.set(b)],
                                                    }
                                                )
                                            ]
                                    record.default_code = ref_product
                                logger.info(f"Update {record.name} {record.id} Ok")
                                continue
                            else:
                                logger.warning(
                                    f"ERREUR lors de la mise a jour du product line {line}"
                                )
                                continue
                        else:
                            logger.warning(f"No product found for {line}")
                    else:
                        location_id = vals.get("location_id") or speedy.get(
                            "default_location_id"
                        )
                        vals = import_obj._prepare_product_vals(
                            vals, location_id, speedy
                        )
                        if not vals:
                            logger.warning("Product on line %s skipped", line)
                            continue
                        p_tmpl = self.env["product.template"].create(vals)
                        speedy_product_template_list[p_tmpl.default_code] = p_tmpl.id
                        list_product_create[p_tmpl.id] = p_tmpl
                        if p_tmpl and variant_att:
                            for att in list_attribue_ids:
                                b = list_attribue_ids[att]
                                p_tmpl.attribute_line_ids = [
                                    Command.create(
                                        {
                                            "attribute_id": att,
                                            "value_ids": [Command.set(b)],
                                        }
                                    )
                                ]
                            p_tmpl.default_code = vals["default_code"]
                            logger.info(
                                f"{p_tmpl.id} has been create with {len(list_attribue_ids)} variant"
                            )
                        else:
                            logger.warning(f"{p_tmpl.id} has been create")
                            continue
                # elif (not template or template) and not variant_att:
                #     res = import_obj._create_product(vals, speedy)
                #     continue
                else:
                    logger.warning(f"NO PRODUCT IMPORTED line {line} Name {row[1]}")
            else:
                break
        for t in speedy_product_template_list:
            record = self.env["product.template"].browse(
                speedy_product_template_list[t]
            )
            record.default_code = t
        action = import_obj._result_action(speedy)
        return action
