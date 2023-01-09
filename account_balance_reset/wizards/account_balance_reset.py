# Copyright 2022 Akretion France (http://www.akretion.com/)
# @author: Alexis de Lattre <alexis.delattre@akretion.com>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools.misc import format_date

logger = logging.getLogger(__name__)


class AccountBalanceRest(models.TransientModel):
    _name = "account.balance.reset"
    _description = "Accounting Switchover: reset trial balance"

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        today = fields.Date.context_today(self)
        res["date"] = today + relativedelta(years=-1, month=12, day=31)
        company_id = self.env.company.id
        res["company_id"] = company_id
        journal = self.env["account.journal"].search(
            [
                ("company_id", "=", company_id),
                ("type", "=", "general"),
            ],
            limit=1,
        )
        res["journal_id"] = journal and journal.id or False
        return res

    date = fields.Date(required=True, string="Reset Date")
    company_id = fields.Many2one("res.company", required=True)
    journal_id = fields.Many2one(
        "account.journal",
        required=True,
        domain="[('company_id', '=', company_id), ('type', '=', 'general')]",
    )
    ref = fields.Char(string="Reference")

    def run(self):
        self.ensure_one()
        company_id = self.company_id.id
        ccur = self.company_id.currency_id
        amo = self.env["account.move"]
        amlo = self.env["account.move.line"]
        domain = [
            ("company_id", "=", company_id),
            ("date", "<=", self.date),
        ]
        draft_count = amo.search_count(domain + [("state", "=", "draft")])
        if draft_count:
            raise UserError(
                _("There are %d draft journal entries dated before %s.")
                % (draft_count, format_date(self.env, self.date))
            )
        domain += [("parent_state", "=", "posted"), ("display_type", "=", False)]
        rg_res = amlo.read_group(
            domain,
            ["account_id", "partner_id", "balance"],
            ["account_id", "partner_id"],
            lazy=False,
        )
        vals = {
            "date": self.date,
            "company_id": company_id,
            "journal_id": self.journal_id.id,
            "ref": self.ref,
            "line_ids": [],
        }
        for res in rg_res:
            account_id = res["account_id"][0]
            partner_id = res["partner_id"] and res["partner_id"][0] or False
            balance = ccur.round(res["balance"])
            fc = ccur.compare_amounts(balance, 0)
            if not fc:
                continue
            elif fc > 0:
                debit = 0
                credit = balance
            else:
                credit = 0
                debit = balance * -1
            vals["line_ids"].append(
                (
                    0,
                    0,
                    {
                        "partner_id": partner_id,
                        "account_id": account_id,
                        "debit": debit,
                        "credit": credit,
                    },
                )
            )
        move = self.env["account.move"].create(vals)
        move._post(soft=False)
        # reconciliation strategy:
        # we decided that we don't want to delete existing reconcilication
        # across self.date
        # so we just reconcile what we can easily reconcile, and nothing else
        for line in move.line_ids:
            if not line.account_id.reconcile:
                continue
            rec_domain = [
                ("account_id", "=", line.account_id.id),
                ("partner_id", "=", line.partner_id.id or False),
                ("full_reconcile_id", "=", False),
                ("date", "<=", self.date),
                ("company_id", "=", company_id),
            ]
            rec_rg = amlo.read_group(
                rec_domain, ["account_id", "balance"], ["account_id"]
            )
            # There is always at least the line of the move we juste created
            balance = rec_rg[0]["balance"]
            if ccur.is_zero(balance):
                lines = amlo.search(rec_domain)
                lines.reconcile()
                logger.info(
                    "Reconciled %d lines for account %s partner %s",
                    len(lines),
                    line.account_id.code,
                    line.partner_id.display_name or False,
                )

        action = self.env["ir.actions.actions"]._for_xml_id(
            "account.action_move_journal_line"
        )
        action.update(
            {
                "view_mode": "form,tree",
                "res_id": move.id,
                "view_id": False,
                "views": False,
            }
        )
        return action
