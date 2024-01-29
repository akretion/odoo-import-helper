# Copyright 2016-2022 Akretion France (http://www.akretion.com)
# @author Alexis de Lattre <alexis.delattre@akretion.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

import logging

from odoo import _, api, models
from odoo.exceptions import UserError

logger = logging.getLogger(__name__)

# In v10, we were using data from
# account.chart.template/account.account.template but account 580001 was
# not part of account.account.template
# I don't remember the reason for choosing to use
# account.chart.template/account.account.template
# So we now switch to using account.account, with the following advantages:
# - you can customize the properties of the accounts used for the comparaison
# - can use 580001


class ResCompany(models.Model):
    _inherit = "res.company"

    @api.model
    def generate_id2xmlid(self, object_name):
        irmdo = self.env["ir.model.data"]
        obj_id2xmlid = {}
        irmd = irmdo.search([("model", "=", object_name), ("res_id", "!=", False)])
        for entry in irmd:
            obj_id2xmlid[entry.res_id] = "{}.{}".format(entry.module, entry.name)
        return obj_id2xmlid

    def generate_custom_chart(
        self,
        custom_chart,
        module="custom",
        xmlid_prefix="account_",
        fixed_size_code=True,
        custom2odoo_code_map=None,
        with_taxes=True,
    ):
        # arg 'custom_chart': list of tuple
        # tuple: ('622600', {'name': 'Honoraires comptables'})
        # in the second value of the tuple, we often only put name,
        # but we can put other odoo properties
        self.ensure_one()
        taxtemplate2xmlid = self.generate_id2xmlid("account.tax.template")
        logger.info("taxtemplate2xmlid = %s", taxtemplate2xmlid)
        # pre-load odoo's chart of account
        odoo_chart = {}
        accounts = self.env['account.account'].search([("company_id", "=", self.id)])
        odoo_code_size = False
        for account in accounts:
            taxes_xmlids = [taxtemplate2xmlid[tax.id] for tax in account.tax_ids]
            odoo_chart[account.code] = {
                "name": account.name,
                "reconcile": account.reconcile,
                "account_type": account.account_type,
                "tax_xmlids": ",".join(taxes_xmlids),
            }
            if not odoo_code_size:
                odoo_code_size = len(account.code)
        res = []
        # header line
        res.append(
            {
                "id": "id",
                "code": "code",
                "name": "name",
                "account_type": "account_type",
                "tax_xmlids": "tax_ids/id",
                "reconcile": "reconcile",
                "note": "note",
            }
        )
        custom_code_size = False
        for custom_code, src_custom_dict in custom_chart.items():
            if fixed_size_code:
                if custom_code_size:
                    if len(custom_code) != custom_code_size:
                        raise UserError(
                            _(
                                "For account code %s, the size (%d) is different "
                                "from the size of other accounts (%d)"
                            )
                            % (custom_code, len(custom_code), custom_code_size)
                        )
                else:
                    custom_code_size = len(custom_code)
                    if custom_code_size < odoo_code_size:
                        raise UserError(
                            _(
                                "For account code %s, the custom code size (%d) "
                                "is < odoo's code size (%d)"
                            )
                            % (custom_code, custom_code_size, odoo_code_size)
                        )
                size = odoo_code_size
            else:
                size = len(custom_code)
            exit_while = False
            matching_code = custom_code
            if custom2odoo_code_map and custom_code in custom2odoo_code_map:
                matching_code = custom2odoo_code_map[custom_code]
            while size > 1 and not exit_while:
                short_matching_code = matching_code[:size]
                for odoo_code, odoo_dict in odoo_chart.items():
                    if odoo_code.startswith(short_matching_code):
                        custom_dict = odoo_dict.copy()
                        custom_dict["id"] = "{}.{}{}".format(
                            module,
                            xmlid_prefix,
                            custom_code,
                        )
                        custom_dict.update(src_custom_dict)
                        custom_dict["code"] = custom_code
                        if not with_taxes:
                            custom_dict["tax_xmlids"] = ""
                        res.append(custom_dict)
                        exit_while = True
                        break
                size -= 1
            if not exit_while:
                raise UserError(
                    _("Customer account %s '%s' didn't match any Odoo account")
                    % (custom_code, src_custom_dict.get("name"))
                )
        return res
