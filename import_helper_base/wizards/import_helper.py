# Copyright 2023 Akretion France (http://www.akretion.com/)
# @author: Alexis de Lattre <alexis.delattre@akretion.com>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import api, fields, models, tools, _
from odoo.exceptions import UserError
from collections import defaultdict
from datetime import datetime
from unidecode import unidecode
import re

import base64, io
import traceback
import logging
logger = logging.getLogger(__name__)


try:
    import pycountry
except ImportError:
    logger.debug('Cannot import pycountry')

try:
    from openai import OpenAI
except ImportError:
    logger.debug('Cannot import openai')

try:
    import openpyxl
except ImportError:
    logger.debug('Cannot import openpyxl')


class ImportHelper(models.TransientModel):
    _name = "import.helper"
    _description = "Helper to import data in Odoo"

    ai_engine = fields.Selection(
        string='AI engine',
        selection=[('chatgpt', 'ChatGPT')],
        default=False,
        help="If used, the import will send AI requests to improve data quality"
             "(only when helpful), like correcting country names into ISO country codes.",
    )
    file = fields.Binary(string='File')
    logs = fields.Html(readonly=True)

    #====== File import methods ======#
    def button_download_template(self):
        url = self._context.get('template_path')
        if url:
            return {
                'type': 'ir.actions.act_url',
                'name': _('Download import template'),
                'target': 'download',
                'url': url,
            }

    def _get_sheet_names(self):
        """ Sheet name of XLSX template
            To inherit (e.g. in `partner_import_helper`, `product_import_helper`)
        """
        return []
    
    def button_import_file(self):
        """ Button pressed by user, triggering the import methods """
        # read xlsx
        try:
            bin_data = base64.b64decode(self.file)
            data = io.BytesIO(bin_data)
            workbook = openpyxl.load_workbook(data)
        except ImportError:
            logger.debug('Cannot open file. Maybe missing openpyxl requirement?')
            return
        
        sheets = {name: workbook[name] for name in self._get_sheet_names() if name in workbook}

        # load sheets and commit data to database
        speedy = self._prepare_speedy()
        for sheet_name, sheet in sheets.items():
            method = '_load_sheet_' + sheet_name
            if hasattr(self, method):
                logger.info("Loading sheet: %s", sheet_name)
                headers, vals_list = self._sheet_to_dict(sheet)
                getattr(self, method)(speedy, headers, vals_list)
            else:
                logger.warning("Sheet ignored: %s", sheet_name)
        
        return self._result_action(speedy)

    def _sheet_to_dict(self, worksheet):
        """ Transform `worksheet` into a `vals_list` """
        # Get headers: {'col_name': col_index}
        headers, col_index, col_name = {}, 1, True
        while col_name:
            col_name = worksheet.cell(1, col_index).value
            if bool(col_name):
                headers[col_name] = col_index
            col_index += 1
        
        # Read rows
        vals_list = []
        for row in range(2, worksheet.max_row+1):
            vals = {}
            for col_name, col_index in headers.items():
                value = worksheet.cell(row, col_index).value
                if bool(value) or isinstance(value, bool): # filter empty cells
                    vals[col_name] = value if isinstance(value, bool) else str(value).strip()
            vals_list.append(vals)
        
        return headers, vals_list

    #===== Data logics methods =====#
    @api.model
    def _prepare_speedy(self):
        logger.debug('Start to prepare import speedy')
        speedy = {
            # country is used both for partner and product
            'country': {
                'name2code': {
                    "usa": "US",
                    "etatsunis": "US",
                    "grandebretagne": "GB",
                    "angleterre": "GB",
                    "ilemaurice": "MU",  # string is simply "Maurice' in Odoo
                    },
                'code2id': {},
                'id2code': {},  # used to check iban and vat number prefixes
                'code2name': {},  # used in log messages
                },
            'aiengine': self.ai_engine,
            'field2label': {},
            'logs': {},
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
        cyd = speedy['country']
        code2to3 = {}
        for country in pycountry.countries:
            code2to3[country.alpha_2] = country.alpha_3
        for country in self.env['res.country'].search_read([], ['code', 'name']):
            cyd['code2id'][country['code']] = country['id']
            cyd['id2code'][country['id']] = country['code']
            cyd['code2name'][country['code']] = country['name']
            code3 = code2to3.get(country['code'])
            if code3:
                cyd['code2id'][code3] = country['id']
                cyd['code2name'][code3] = country['name']
        for lang in self.env['res.lang'].search([]):
            logger.info('Working on lang %s', lang.code)
            for country in self.env['res.country'].with_context(lang=lang.code).search_read([], ['code', 'name']):
                country_name_match = self._prepare_country_name_match(country['name'])
                cyd['name2code'][country_name_match] = country['code']
        if self.ai_engine == 'chatgpt':
            openai_api_key = tools.config.get('openai_api_key', False)
            if not openai_api_key:
                raise UserError(_(
                    "Missing entry openai_api_key in the Odoo server configuration file."))
            speedy['openai_client'] = OpenAI(api_key=openai_api_key)
            speedy['openai_tokens'] = 0
        return speedy

    @api.model
    def _prepare_country_name_match(self, country_name):
        assert country_name
        country_name_match = unidecode(country_name).lower()
        country_name_match = ''.join(re.findall(r'[a-z]+', country_name_match))
        assert country_name_match
        return country_name_match

    def _match_country(self, vals, country_key, model, country_field_name, speedy):
        assert isinstance(model, str)
        country_name = vals[country_key]
        log = {
            'value': country_name,
            'vals': vals,
            'field': f'{model},{country_field_name}',
            }
        cyd = speedy['country']
        if len(country_name) in (2, 3):
            country_code = country_name.upper()
            if country_code in cyd['code2id']:
                logger.info("Country name '%s' is an ISO country code (%s)", country_name, cyd['code2name'][country_code])
                country_id = cyd['code2id'][country_code]
                return country_id
        country_name_match = self._prepare_country_name_match(country_name)
        if country_name_match in cyd['name2code']:
            country_code = cyd['name2code'][country_name_match]
            logger.info("Country '%s' matched on country %s (%s)", country_name, cyd['code2name'][country_code], country_code)
            country_id = cyd['code2id'][country_code]
            return country_id
        logger.info("No direct match for country '%s': now asking ChatGPT.", country_name)
        # ask ChatGPT !
        answer = None
        if speedy.get('openai_client'):
            content = """ISO country code of "%s", nothing else""" % country_name
            logger.debug('ChatGPT question: %s', content)
            try:
                chat_completion = speedy['openai_client'].chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=[{"role": "user", "content": content}],
                    temperature=0,
                )
                tokens = chat_completion.usage.total_tokens
                logger.debug("%d tokens have been used", tokens)
                speedy["openai_tokens"] += tokens
                answer = chat_completion.choices[0].message.content
            except Exception as e:
                error = """
                    Error when asking this to Chatgpt: %s\n
                    It answered: %s
                """ % (content, traceback.format_exc())
                logger.warning(error)
                speedy['logs'][model].append(dict(log, msg=error, reset=True))

            # print the chat completion
            if answer:
                answer = answer.strip()
                logger.info('ChatGPT answer: %s', answer)
                if len(answer) == 2:
                    country_code = answer.upper()
                    if country_code in cyd['code2id']:
                        logger.info("ChatGPT matched country '%s' to %s (%s)", country_name, cyd['code2name'][country_code], country_code)
                        speedy['logs'][model].append(dict(log, msg="Country name could not be found in Odoo. ChatGPT said ISO code was '%s', which matched to '%s'" % (country_code, cyd['code2name'][country_code])))
                        country_id = cyd['code2id'][country_code]
                        cyd['name2code'][country_name_match] = country_code
                        return country_id
                    else:
                        speedy['logs'][model].append(dict(log, msg="Country name could not be found in Odoo. ChatGPT said ISO code was '%s', which didn't match to any country" % country_code), reset=True)
                else:
                    speedy['logs'][model].append(
                        dict(log, msg="ChatGPT didn't answer a 2 letter country code but '%s'" % answer, reset=True))
            else:
                logger.warning('No answer from chatGPT')
                speedy['logs'][model].append(dict(log, msg='No answer from chatGPT', reset=True))
        return False

    def _field_label(self, field, speedy):
        if field not in speedy['field2label']:
            field_split = field.split(',')
            ofield = self.env['ir.model.fields'].search([
                ('model', '=', field_split[0]),
                ('name', '=', field_split[1]),
                ], limit=1)
            if ofield:
                speedy['field2label'][field] = ofield.field_description
            else:
                speedy['field2label'][field] = '%s (%s)' % (
                    field_split[1], field_split[0])
        return speedy['field2label'][field]

    def _convert_logs2html(self, speedy):
        html = '<p><small>For the logs in <span style="color: red">red</span>, the data was <b>not imported</b> in Odoo</small><br/>'
        if speedy.get('aiengine') == 'chatgpt':
            html += '<small><b>%d</b> OpenAI tokens where used</small></p>' % speedy['openai_tokens']
        for obj_name, log_list in speedy['logs'].items():
            obj_rec = self.env['ir.model'].search([('model', '=', obj_name)], limit=1)
            assert obj_rec
            html += '<h1 style="color:darkblue;">%s</h1>' % obj_rec.name
            line2logs = defaultdict(list)
            field2logs = defaultdict(list)
            for log in log_list:
                if log['vals'].get('line'):
                    line2logs[log['vals']['line']].append(log)
                if log.get('field'):
                    field2logs[log['field']].append(log)
            html += '<h2 style="color:darkgreen;">Logs per line</h2>'
            for line, logs in line2logs.items():
                log_labels = []
                for log in logs:
                    log_labels.append(
                        '<li style="color: %s"><b>%s</b>: <b>%s</b> - %s</li>' % (
                            log.get('reset') and 'red' or 'black',
                            self._field_label(log['field'], speedy),
                            log['value'],
                            log['msg'],
                            ))
                h3 = 'Line %s' % line
                if log['vals'].get('id'):
                    h3 += ': %s (ID %d)' % (log['vals']['display_name'], log['vals']['id'])
                html += '<h3>%s</h3>\n<p><ul>%s</ul></p>' % (h3, '\n'.join(log_labels))
            html += '<h2 style="color:darkgreen;">Logs per field</h2>'
            for field, logs in field2logs.items():
                log_labels = []
                for log in logs:
                    line_label = 'Line %s' % log['vals'].get('line', 'unknown')
                    if log['vals'].get('id'):
                        line_label += ' (%s ID %d)' % (log['vals']['display_name'], log['vals']['id'])
                    log_labels.append(
                        '<li style="color: %s"><b>%s</b>: <b>%s</b> - %s</li>' % (
                            log.get('reset') and 'red' or 'black',
                            line_label,
                            log['value'],
                            log['msg'],
                            ))
                html += '<h3>%s</h3>\n<p><ul>%s</ul></p>' % (
                    self._field_label(field, speedy), '\n'.join(log_labels))
        return html

    def _result_action(self, speedy):
        action = {
            'name': 'Result',
            'type': 'ir.actions.act_window',
            'res_model': 'import.helper',
            'view_mode': 'form',
            'target': 'new',
            'context': dict(self._context, default_logs=self._convert_logs2html(speedy)),
            }
        return action

    def _prepare_create_date(self, vals, speedy):
        create_date = vals.get('create_date')
        create_date_dt = False
        if isinstance(create_date, str) and len(create_date) == 10:
            try:
                create_date_dt = datetime.strptime(create_date, '%Y-%m-%d')
            except Exception as e:
                speedy['logs'].append({
                    'msg': "Failed to convert '%s' to datetime: %s" % (create_date, e),
                    'value': vals['create_date'],
                    'vals': vals,
                    'field': 'product.product,create_date',
                    'reset': True,
                    })
        elif isinstance(create_date, datetime):
            create_date_dt = create_date
        if create_date_dt and create_date_dt.date() > fields.Date.context_today(self):
            speedy['logs'].append({
                'msg': 'create_date %s cannot be in the future' % create_date_dt,
                'value': create_date,
                'vals': vals,
                'field': 'product.product,create_date',
                'reset': True,
                })
        return create_date_dt
