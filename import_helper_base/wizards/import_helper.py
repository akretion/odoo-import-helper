# Copyright 2023 Akretion France (http://www.akretion.com/)
# @author: Alexis de Lattre <alexis.delattre@akretion.com>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging
import re
from collections import defaultdict
from datetime import datetime

from unidecode import unidecode

from odoo import _, api, fields, models, tools
from odoo.exceptions import UserError

logger = logging.getLogger(__name__)

try:
    import pycountry
except ImportError:
    logger.debug("Cannot import pycountry")
try:
    from openai import OpenAI
except ImportError:
    logger.debug("Cannot import openai")


class ImportHelper(models.TransientModel):
    _name = "import.helper"
    _description = "Helper to import data in Odoo"

    logs = fields.Html(readonly=True)

    @api.model
    def _prepare_speedy(self, aiengine="chatgpt"):
        logger.debug("Start to prepare import speedy")
        speedy = {
            # country is used both for partner and product
            "country": {
                "name2code": {
                    "usa": "US",
                    "etatsunis": "US",
                    "grandebretagne": "GB",
                    "angleterre": "GB",
                },
                "code2id": {},
                "id2code": {},  # used to check iban and vat number prefixes
                "code2name": {},  # used in log messages
            },
            "aiengine": aiengine,
            "field2label": {},
            "logs": {},
            # 'logs' is a dict {'res.partner': [], 'product.product': []}
            # where the value is a list of dict :
            # {'msg': 'Checksum IBAN wrong',
            #  'value': 'FR9879834739',
            #  'vals': vals,  # used to get the line
            #                   (and display_name if partner has been created)
            #  'field': 'res.partner,email',
            #  'reset': True,  # True if the data is NOT imported in Odoo
            # }
        }
        cyd = speedy["country"]
        code2to3 = {}
        for country in pycountry.countries:
            code2to3[country.alpha_2] = country.alpha_3
        for country in self.env["res.country"].search_read([], ["code", "name"]):
            cyd["code2id"][country["code"]] = country["id"]
            cyd["id2code"][country["id"]] = country["code"]
            cyd["code2name"][country["code"]] = country["name"]
            code3 = code2to3.get(country["code"])
            if code3:
                cyd["code2id"][code3] = country["id"]
                cyd["code2name"][code3] = country["name"]
        for lang in self.env["res.lang"].search([]):
            logger.info("Working on lang %s", lang.code)
            for country in (
                self.env["res.country"]
                .with_context(lang=lang.code)
                .search_read([], ["code", "name"])
            ):
                country_name_match = self._prepare_country_name_match(country["name"])
                cyd["name2code"][country_name_match] = country["code"]
        if aiengine == "chatgpt":
            openai_api_key = tools.config.get("openai_api_key", False)
            if not openai_api_key:
                raise UserError(
                    _(
                        "Missing entry openai_api_key in the Odoo server "
                        "configuration file."
                    )
                )
            speedy["openai_client"] = OpenAI(api_key=openai_api_key)
            speedy["openai_tokens"] = 0
        return speedy

    @api.model
    def _prepare_country_name_match(self, country_name):
        assert country_name
        country_name_match = unidecode(country_name).lower()
        country_name_match = "".join(re.findall(r"[a-z]+", country_name_match))
        assert country_name_match
        return country_name_match

    def _match_country(self, vals, country_key, model, country_field_name, speedy):
        assert isinstance(model, str)
        country_name = vals[country_key]
        log = {
            "value": country_name,
            "vals": vals,
            "field": f"{model},{country_field_name}",
        }
        cyd = speedy["country"]
        if len(country_name) in (2, 3):
            country_code = country_name.upper()
            if country_code in cyd["code2id"]:
                logger.info(
                    "Country name '%s' is an ISO country code (%s)",
                    country_name,
                    cyd["code2name"][country_code],
                )
                country_id = cyd["code2id"][country_code]
                return country_id
        country_name_match = self._prepare_country_name_match(country_name)
        if country_name_match in cyd["name2code"]:
            country_code = cyd["name2code"][country_name_match]
            logger.info(
                "Country '%s' matched on country %s (%s)",
                country_name,
                cyd["code2name"][country_code],
                country_code,
            )
            country_id = cyd["code2id"][country_code]
            return country_id
        logger.info(
            "No direct match for country '%s': now asking ChatGPT.", country_name
        )
        # ask ChatGPT !
        content = f"""ISO country code of "{country_name}", nothing else"""
        logger.debug("ChatGPT question: %s", content)
        chat_completion = speedy["openai_client"].chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": content}],
            temperature=0,
        )

        # print the chat completion
        tokens = chat_completion.usage.total_tokens
        logger.debug("%d tokens have been used", tokens)
        speedy["openai_tokens"] += tokens
        answer = chat_completion.choices[0].message.content
        if answer:
            answer = answer.strip()
            logger.info("ChatGPT answer: %s", answer)
            if len(answer) == 2:
                country_code = answer.upper()
                if country_code in cyd["code2id"]:
                    cyd_code2n_cntry = cyd["code2name"][country_code]
                    logger.info(
                        "ChatGPT matched country '%s' to %s (%s)",
                        country_name,
                        cyd_code2n_cntry,
                        country_code,
                    )
                    speedy["logs"][model].append(
                        dict(
                            log,
                            msg=(
                                "Country name could not be found in Odoo. "
                                f"ChatGPT said ISO code was '{country_code}', "
                                f"which matched to '{cyd_code2n_cntry}'"
                            ),
                        )
                    )
                    country_id = cyd["code2id"][country_code]
                    cyd["name2code"][country_name_match] = country_code
                    return country_id
                else:
                    speedy["logs"][model].append(
                        dict(
                            log,
                            msg=(
                                "Country name could not be found in Odoo. "
                                f"ChatGPT said ISO code was '{country_code}', "
                                "which didn't match to any country"
                            ),
                        ),
                        reset=True,
                    )
            else:
                speedy["logs"][model].append(
                    dict(
                        log,
                        msg="ChatGPT didn't answer a 2 letter country code "
                        f"but '{answer}'",
                        reset=True,
                    )
                )
        else:
            logger.warning("No answer from chatGPT")
            speedy["logs"][model].append(
                dict(log, msg="No answer from chatGPT", reset=True)
            )
        return False

    def _field_label(self, field, speedy):
        if field not in speedy["field2label"]:
            field_split = field.split(",")
            ofield = self.env["ir.model.fields"].search(
                [
                    ("model", "=", field_split[0]),
                    ("name", "=", field_split[1]),
                ],
                limit=1,
            )
            if ofield:
                speedy["field2label"][field] = ofield.field_description
            else:
                speedy["field2label"][field] = f"{field_split[1]} ({field_split[0]})"
        return speedy["field2label"][field]

    def _convert_logs2html(self, speedy):
        html = (
            '<p><small>For the logs in <span style="color: red">red</span>, '
            "the data was <b>not imported</b> in Odoo</small><br/>"
        )
        if speedy.get("aiengine") == "chatgpt":
            html += "<small><b>{}</b> OpenAI tokens where used</small></p>".format(
                speedy["openai_tokens"]
            )
        for obj_name, log_list in speedy["logs"].items():
            obj_rec = self.env["ir.model"].search([("model", "=", obj_name)], limit=1)
            assert obj_rec
            html += f'<h1 style="color:darkblue;">{obj_rec.name}</h1>'
            line2logs = defaultdict(list)
            field2logs = defaultdict(list)
            for log in log_list:
                if log["vals"].get("line"):
                    line2logs[log["vals"]["line"]].append(log)
                if log.get("field"):
                    field2logs[log["field"]].append(log)
            html += '<h2 style="color:darkgreen;">Logs per line</h2>'
            for line, logs in line2logs.items():
                log_labels = []
                for log in logs:
                    log_labels.append(
                        '<li style="color: {}"><b>{}</b>: <b>{}</b> - {}</li>'.format(
                            log.get("reset") and "red" or "black",
                            self._field_label(log["field"], speedy),
                            log["value"],
                            log["msg"],
                        )
                    )
                h3 = f"Line {line}"
                if log["vals"].get("id"):
                    h3 += f": {log['vals']['display_name']} (ID {log['vals']['id']})"
                html += "<h3>{}</h3>\n<p><ul>{}</ul></p>".format(
                    h3, "\n".join(log_labels)
                )
            html += '<h2 style="color:darkgreen;">Logs per field</h2>'
            for field, logs in field2logs.items():
                log_labels = []
                for log in logs:
                    line_label = f"Line {log['vals'].get('line', 'unknown')}"
                    if log["vals"].get("id"):
                        line_label += " (%(display_name)s ID %(id)d)" % {
                            "display_name": log["vals"]["display_name"],
                            "id": log["vals"]["id"],
                        }
                    log_labels.append(
                        (
                            '<li style="color: {}"><b>{}</b>: ' "<b>{}</b> - {}</li>"
                        ).format(
                            log.get("reset") and "red" or "black",
                            line_label,
                            log["value"],
                            log["msg"],
                        )
                    )
                html += (
                    f"<h3>{self._field_label(field, speedy)}</h3>\n<p><ul>"
                    "{'\n'.join(log_labels)}</ul></p>"
                )
        return html

    def _result_action(self, speedy):
        action = {
            "name": "Result",
            "type": "ir.actions.act_window",
            "res_model": "import.helper",
            "view_mode": "form",
            "target": "new",
            "context": dict(
                self._context, default_logs=self._convert_logs2html(speedy)
            ),
        }
        return action

    def _prepare_create_date(self, vals, speedy):
        create_date = vals.get("create_date")
        create_date_dt = False
        if isinstance(create_date, str) and len(create_date) == 10:
            try:
                create_date_dt = datetime.strptime(create_date, "%Y-%m-%d")
            except Exception as e:
                speedy["logs"].append(
                    {
                        "msg": f"Failed to convert '{create_date}' to datetime: {e}",
                        "value": vals["create_date"],
                        "vals": vals,
                        "field": "product.product,create_date",
                        "reset": True,
                    }
                )
        elif isinstance(create_date, datetime):
            create_date_dt = create_date
        if create_date_dt and create_date_dt.date() > fields.Date.context_today(self):
            speedy["logs"].append(
                {
                    "msg": f"create_date {create_date_dt} cannot be in the future",
                    "value": create_date,
                    "vals": vals,
                    "field": "product.product,create_date",
                    "reset": True,
                }
            )
        return create_date_dt
