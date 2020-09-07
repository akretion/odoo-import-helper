# Copyright 2020 Akretion (https://www.akretion.com).
# @author Sébastien BEAU <sebastien.beau@akretion.com>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import _, api, fields, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    # TODO resoudre le soucis d'import des nouvelles ligne
    # il faut qu'on réutilise les lignes existante et qu'on supprime
    # les attributes non importé
    # on va surcharger le write a la bourrin pour la V1
    # ensuite il faudra faire un truc générique
    def _process_pattern_import_attribute_line(self, attribute_lines):
        # We need to ensure that the value match the value
        converter = self.env["ir.fields.converter"].for_model(self.attribute_line_ids)
        for attribute_line in attribute_lines:
            attr_name = attribute_line["attribute_id"].get("name")
            if attr_name:
                attr = self.env["product.attribute"].search([("name", "=", attr_name)])
                attribute_line["attribute_id"] = {'.id': attr.id}
                vals = []
                for value in attribute_line["value_ids"]:
                    value_name = value.get("name")
                    if value_name:
                        attr_val = self.env["product.attribute.value"].search([
                            ("name", "=", value_name),
                            ("attribute_id.id", "=", attr.id),
                            ])
                        if len(attr_val) > 1:
                            raise UserError(
                                _(
                                    "Too many attribute value found for '{}' "
                                ).format(value_name)
                                )
                        elif len(attr_val) == 0 :
                            raise UserError(
                                _(
                                    "No value found for attribute value '{}' "
                                ).format(value_name)
                                )
                        vals.append({'.id': attr_val.id})
                attribute_line["value_ids"] = vals

    def _flatty2json(self, row):
        result = super()._flatty2json(row)
        if "attribute_line_ids" in result:
            self._process_pattern_import_attribute_line(result["attribute_line_ids"])
        return result
