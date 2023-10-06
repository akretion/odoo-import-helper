# Copyright 2023 Akretion France (http://www.akretion.com/)
# @author: Alexis de Lattre <alexis.delattre@akretion.com>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import api, models, tools, Command, _
from odoo.exceptions import UserError
from odoo.addons.phone_validation.tools import phone_validation

import re
from unidecode import unidecode
from collections import defaultdict
from datetime import datetime
import openai
import pycountry
from stdnum.eu.vat import is_valid as vat_is_valid, check_vies
from stdnum.iban import is_valid as iban_is_valid
from stdnum.fr.siret import is_valid as siret_is_valid
from stdnum.fr.siren import is_valid as siren_is_valid
from email_validator import validate_email, EmailNotValidError

import logging
logger = logging.getLogger(__name__)


class ResPartner(models.Model):
    _inherit = 'res.partner'

    # TODO add support for states
    @api.model
    def _import_speedy(self):
        logger.debug('Start to prepare import speedy')
        openai_api_key = tools.config.get('openai_api_key', False)
        if not openai_api_key:
            raise UserError(_(
                "Missing entry openai_api_key in the Odoo server configuration file."))
        openai.api_key = openai_api_key

        speedy = {
            "o2m_phone": hasattr(self.env['res.partner'], 'phone_ids'),
            "openai_tokens": 0,
            "eu_country_ids": self.env.ref('base.europe').country_ids.ids,
            "fr_country_id": self.env.ref('base.fr').id,
            'country': {
                'name2code': {
                    "usa": "US",
                    "etatsunis": "US",
                    },
                'code2id': {},
                'id2code': {},  # used to check iban and vat number prefixes
                'code2name': {},  # used in log messages
                },
            "bank": {
                'bic2id': {},
                'bic2name': {},
                },
            'title': {
                'code2id': {
                    'madam': self.env.ref('base.res_partner_title_madam').id,
                    'miss': self.env.ref('base.res_partner_title_miss').id,
                    'mister': self.env.ref('base.res_partner_title_mister').id,
                    'doctor': self.env.ref('base.res_partner_title_doctor').id,
                    'prof': self.env.ref('base.res_partner_title_prof').id,
                },
            },
        'field2label': {},
        'logs': [],
        # 'logs' should contain a list of dict :
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
        for bank in self.env['res.bank'].with_context(active_test=False).search_read([('bic', '!=', False)], ['name', 'bic']):
            bic = bank['bic'].upper()
            speedy['bank']['bic2id'][bic] = bank['id']
            speedy['bank']['bic2name'][bic] = bank['name']
        for lang in self.env['res.lang'].search([]):
            logger.info('Working on lang %s', lang.code)
            for country in self.env['res.country'].with_context(lang=lang.code).search_read([], ['code', 'name']):
                country_name_match = self._import_prepare_country_name_match(country['name'])
                cyd['name2code'][country_name_match] = country['code']

        logger.debug('End preparation of import speedy')
        return speedy

    @api.model
    def _import_prepare_country_name_match(self, country_name):
        assert country_name
        country_name_match = unidecode(country_name).lower()
        country_name_match = ''.join(re.findall(r'[a-z]+', country_name_match))
        assert country_name_match
        return country_name_match

    def _import_create(self, vals, speedy, email_check_deliverability=True, create_bank=True):
        rvals = self._import_prepare_vals(vals, speedy, email_check_deliverability=email_check_deliverability, create_bank=create_bank)
        partner = self.create(rvals)
        if vals.get('create_date'):
            create_date = vals['create_date']
            create_date_dt = False
            if isinstance(create_date, str) and len(create_date) == 10:
                try:
                    create_date_dt = datetime.strptime(create_date, '%Y-%m-%d')
                except Exception as e:
                    speedy['logs'].append({
                        'msg': 'Failed to convert to datetime: %s' % e,
                        'value': vals['create_date'],
                        'vals': vals,
                        'field': 'res.partner,create_date',
                        'reset': True,
                        })
            elif isinstance(create_date, datetime):
                create_date_dt = create_date
            if create_date_dt:
                self._cr.execute(
                    "UPDATE res_partner SET create_date=%s WHERE id=%s",
                    (create_date_dt, partner.id))
        vals['display_name'] = partner.display_name
        vals['id'] = partner.id
        logger.info('New partner created: %s ID %d from line %d', partner.display_name, partner.id, vals['line'])
        return partner

    # vals is a dict to create a res.partner
    # It must contain a 'line' key, to indicate Excel/CSV import ref in logs
    # (removed before calling create)
    # it can contain some special keys, which will be replaced by the corresponding real key after processing:
    # 'country_name' => 'country_id'
    # 'title_code' can contain 'madam', 'miss', 'mister', 'doctor', 'prof' /  => 'title'
    # 'iban' => 'bank_ids': [(0, 0, {'acc_number': xxx})]
    # 'bic': => 'bank_ids': [(0, 0, {'acc_number': xxxx, 'bank_id': bank_id})]
    @api.model
    def _import_prepare_vals(self, vals, speedy, email_check_deliverability=True, create_bank=True):
        assert vals
        assert isinstance(vals, dict)
        assert isinstance(speedy, dict)
        for key, value in vals.items():
            if isinstance(value, str):
                vals[key] = value.strip() or False
        # STREET
        if vals.get('street2') and not vals.get('street'):
            vals['street'] = vals['street2']
            vals['street2'] = False
        # COUNTRY
        country_id = country_code = False
        if vals.get('country_name') and isinstance(vals['country_name'], str) and not vals.get('country_id'):
            country_id = self._match_country(vals, speedy)
            # Warning: country_id can be False
            vals['country_id'] = country_id
            country_code = speedy['country']['id2code'].get(country_id)
        # TITLE
        if not vals.get('is_company') and vals.get('title_code') and isinstance(vals['title_code'], str) and not vals.get('title'):
            title_id = self._match_title(vals, speedy)
            vals['title'] = title_id
        # PHONE/MOBILE
        # _phone_get_number_fields() is a method of phone_validation that return ['phone', 'mobile']
        for phone_field in self._phone_get_number_fields():
            if vals.get(phone_field):
                if speedy['o2m_phone'] and isinstance(vals[phone_field], list):
                    if 'phone_ids' not in vals:
                        vals['phone_ids'] = []
                    if phone_field == 'mobile':
                        ptype = '5_mobile_primary'
                    else:
                        ptype = '3_phone_primary'
                    for number in vals[phone_field]:
                        number = self._phone_number_clean(
                            number, country_code, phone_field, vals, speedy)
                        if number:
                            vals['phone_ids'].append(Command.create({
                                'type': ptype,
                                'phone': number,
                                }))
                            if phone_field == 'mobile':
                                ptype = '6_mobile_secondary'
                            else:
                                ptype = '4_phone_secondary'
                    vals.pop(phone_field)
                elif isinstance(vals[phone_field], str):
                    vals[phone_field] = self._phone_number_clean(
                        vals[phone_field], country_code, phone_field, vals, speedy)
                else:
                    speedy['logs'].append({
                        'msg': '%s key should be a string, not %s' % (phone_field, type(vals['email'])),
                        'value': vals[phone_field],
                        'vals': vals,
                        'field': 'res.partner,%s' % phone_field,
                        'reset': True,
                        })
                    vals[phone_field] = False
        # EMAIL
        if vals.get('email'):
            if speedy['o2m_phone'] and isinstance(vals['email'], list):
                if 'phone_ids' not in vals:
                    vals['phone_ids'] = []
                ptype = '1_email_primary'
                for email in vals['email']:
                    if email and isinstance(email, str):
                        email = self._email_validate(email, email_check_deliverability, vals, speedy)
                        if email:
                            vals['phone_ids'].append(Command.create({
                                'type': ptype,
                                'email': email,
                                }))
                            ptype = '2_email_secondary'
                vals.pop('email')
            elif isinstance(vals['email'], str):
                vals['email'] = self._email_validate(vals['email'], email_check_deliverability, vals, speedy)
            else:
                speedy['logs'].append({
                    'msg': 'email key should be a string, not %s' % type(vals['email']),
                    'value': vals['email'],
                    'vals': vals,
                    'field': 'res.partner,email',
                    'reset': True,
                    })
                vals['email'] = False
        # ZIP
        if country_id and country_id == speedy['fr_country_id'] and vals.get('zip'):
            zipcode = vals['zip']
            zipcode = vals['zip'].replace(' ', '')
            if len(zipcode) != 5:
                speedy['logs'].append({
                    'msg': 'Zip code has %d chars. In France, they have 5 chars.' % len(zipcode),
                    'value': zipcode,
                    'vals': vals,
                    'field': 'res.partner,zip',
                    })
            if not zipcode.isdigit():
                speedy['logs'].append({
                    'msg': 'In France, ZIP codes only contain digits.',
                    'value': zipcode,
                    'vals': vals,
                    'field': 'res.partner,zip',
                    })
            # if we have geonames, we could compare it with the DB of zip
        # is_company
        if not vals.get('is_company') and (vals.get('vat') or vals.get('siren') or vals.get('siret')):
            if vals.get('vat'):
                msg = 'Has a VAT number, but is not marked as a company'
            elif vals.get('siren'):
                msg = 'Has a SIREN, but is not marked as a company'
            elif vals.get('siret'):
                msg = 'Has a SIRET, but is not marked as a company'
            speedy['logs'].append({
                'msg': msg,
                'value': 'Individual',
                'vals': vals,
                'field': 'res.partner,is_company',
                })
        # VAT
        vat = False
        if vals.get('vat') and (not country_id or country_id in speedy['eu_country_ids']):
            vat = vals['vat'].upper()
            # clean VAT
            vat = ''.join(re.findall(r'[A-Z0-9]+', vat))
            if not vat_is_valid(vat):
                speedy['logs'].append({
                    'msg': 'VAT is not valid',
                    'value': vat,
                    'vals': vals,
                    'field': 'res.partner,vat',
                    'reset': True,
                    })
                vat = False
            if vat:
                try:
                    logger.info('Checking VAT %s on VIES', vat)
                    res = check_vies(vat)
                    if not res.valid:
                        logger.warning('VIES said that VAT %s is not valid', vat)
                        speedy['logs'].append({
                            'msg': 'VIES said that VAT is not valid',
                            'value': vat,
                            'vals': vals,
                            'field': 'res.partner,vat',
                            'reset': True,
                            })
                        vat = False
                except Exception as e:
                    logger.warning('Could not perform VIES validation on VAT %s: %s', vat, e)
                    speedy['logs'].append({
                        'msg': 'Could not perform VIES validation: %s' % e,
                        'value': vat,
                        'vals': vals,
                        'field': 'res.partner,vat',
                        })
            vals['vat'] = vat
        # IBAN / BIC
        iban = False
        if vals.get('iban'):
            iban = vals['iban'].upper().replace(' ', '')
            bic = False
            if not iban_is_valid(iban):
                speedy['logs'].append({
                    'msg': 'IBAN is not valid',
                    'value': iban,
                    'vals': vals,
                    'field': 'res.partner.bank,acc_number',
                    'reset': True,
                    })
                iban = False
            else:
                bank_id = False
                if vals.get('bic'):
                    bic = vals['bic'].upper()
                    if len(bic) not in (8, 11):
                        speedy['logs'].append({
                            'msg': 'Wrong BIC: length is %d, should be 8 or 11' % len(bic),
                            'value': bic,
                            'vals': vals,
                            'field': 'res.bank,bic',
                            'reset': True,
                            })
                        bic = False
                    if bic in speedy['bank']['bic2id']:
                        bank_id = speedy['bank']['bic2id'][bic]
                    elif create_bank:
                        bank = self.env['res.bank'].create(
                            self._prepare_bank(vals, speedy))
                        speedy['bank']['bic2id'][bic] = bank.id
                        speedy['bank']['bic2name'][bic] = bank.name
                        speedy['logs'].append({
                            'msg': "BIC not found in Odoo. New bank named '%s' created (ID %d)" % (bank.name, bank.id),
                            'value': bic,
                            'vals': vals,
                            'field': 'res.bank,bic',
                            })
                    else:
                        speedy['logs'].append({
                            'msg': "BIC not found in Odoo.",
                            'value': bic,
                            'vals': vals,
                            'field': 'res.bank,bic',
                            })
                if vals.get('bank_ids'):
                    raise UserError(_("vals contains both an 'iban' and a 'bank_ids' keys. This should never happen."))
                vals['bank_ids'] = [(0, 0, {'acc_number': iban, 'bank_id': bank_id})]
        # SIREN_OR_SIRET
        if vals.get('siren_or_siret') and hasattr(self, 'siret'):
            siren_or_siret = vals['siren_or_siret']
            siren_or_siret = ''.join(re.findall(r'[0-9]+', siren_or_siret))
            if siren_or_siret:
                if len(siren_or_siret) == 14:
                    vals['siret'] = siren_or_siret
                elif len(siren_or_siret) == 9:
                    vals['siren'] = siren_or_siret
                else:
                    speedy['logs'].append({
                        'msg': 'SIREN/SIRET has a length of %d instead of 9 or 14' % len(siren_or_siret),
                        'value': siren_or_siret,
                        'vals': vals,
                        'field': 'res.partner,siret',
                        'reset': True,
                        })
        # SIREN
        if vals.get('siren') and hasattr(self, 'siren'):
            siren = vals['siren']
            if isinstance(siren, int):
                siren = str(siren)
            siren = ''.join(re.findall(r'[0-9]+', siren))
            if len(siren) != 9:
                speedy['logs'].append({
                    'msg': 'SIREN has a length of %d instead of 9' % len(siren),
                    'value': siren,
                    'vals': vals,
                    'field': 'res.partner,siren',
                    'reset': True,
                    })
                siren = False
                vals.pop('siren')
            if not siren_is_valid(siren):
                speedy['logs'].append({
                    'msg': 'SIREN is not valid (wrong checksum)',
                    'value': siren,
                    'vals': vals,
                    'field': 'res.partner,siren',
                    'reset': True,
                    })
                siren = False
                vals.pop('siren')
            vals['siren'] = siren
            if siren and vat:
                if vat[:2] != 'FR':
                    speedy['logs'].append({
                    'msg': "Partner has SIREN '%s', so it's VAT number should start with FR" % siren,
                    'value': vat,
                    'vals': vals,
                    'field': 'res.partner,vat',
                    })
                if vat[4:] != siren:
                    speedy['logs'].append({
                    'msg': "Partner has SIREN '%s', so it must compose the 9 last digits of it's VAT number" % siren,
                    'value': vat,
                    'vals': vals,
                    'field': 'res.partner,vat',
                    })
        # SIRET
        if vals.get('siret') and hasattr(self, 'siret'):
            siret = vals['siret']
            if isinstance(siret, int):
                siret = str(siret)
            siret = ''.join(re.findall(r'[0-9]+', siret))
            if len(siret) != 14:
                speedy['logs'].append({
                    'msg': 'SIRET has a length of %d instead of 14' % len(siret),
                    'value': siret,
                    'vals': vals,
                    'field': 'res.partner,siret',
                    'reset': True,
                    })
                siret = False
                vals.pop('siret')
            elif not siret_is_valid(siret):
                speedy['logs'].append({
                    'msg': 'SIRET is not valid (wrong checksum)',
                    'value': siret,
                    'vals': vals,
                    'field': 'res.partner,siret',
                    'reset': True,
                    })
                siret = False
                vals.pop('siret')
            vals['siret'] = siret
            if siret and vat:
                if vat[:2] != 'FR':
                    speedy['logs'].append({
                    'msg': "Partner has SIRET '%s', so it's VAT number should start with FR" % siret,
                    'value': vat,
                    'vals': vals,
                    'field': 'res.partner,vat',
                    })
                if vat[4:] != siret[:9]:
                    speedy['logs'].append({
                    'msg': "Partner has SIRET '%s', so the 9 first digits of the SIRET must compose the 9 last digits of it's VAT number" % siret,
                    'value': vat,
                    'vals': vals,
                    'field': 'res.partner,vat',
                    })
        if vals.get('siren') and vals.get('siret'):
            if not vals['siret'].startswith(vals['siren']):
                speedy['logs'].append({
                    'msg': "Partner has both a SIREN and a SIRET, so its SIRET should start with its SIREN (%s)" % vals['siren'],
                    'value': vals['siret'],
                    'vals': vals,
                    'field': 'res.partner,siret',
                    'reset': True,
                    })
                vals['siren'] = False
                vals['siret'] = False
            else:
                vals.pop('siren')
        if country_id:
            country_code = speedy['country']['id2code'][country_id]
            # TODO Northern Ireland doesn't pass this check
            if vat and country_id in speedy['eu_country_ids']:
                expected_country_code = vat[:2]
                if expected_country_code == 'EL':  # special case for Greece
                    expected_country_code == 'GR'
                elif expected_country_code == 'XI':  # Northern Ireland
                    expected_country_code = 'GB'
                if expected_country_code != country_code:
                    speedy['logs'].append({
                        'msg': "The country prefix of the VAT number doesn't match the country code '%s'" % country_code,
                        'value': vat,
                        'vals': vals,
                        'field': 'res.partner,vat',
                        })
            if iban and not iban.startswith(country_code):
                speedy['logs'].append({
                    'msg': "The country prefix of the IBAN doesn't match the country code '%s'" % country_code,
                    'value': iban,
                    'vals': vals,
                    'field': 'res.partner.bank,acc_number',
                    })
        if hasattr(self, 'property_account_position_id'):
            print('')  # TODO
        # vals will keep the original keys
        # rvals will be used for create(), so we need to remove all the keys are don't exist on res.partner
        rvals = dict(vals)
        for key in ['line', 'create_date', 'iban', 'bic', 'siren_or_siret', 'title_code', 'country_name']:
            if key in rvals:
                rvals.pop(key)
        if not hasattr(self, 'siren') and 'siren' in rvals:
            rvals.pop('siren')
        if not hasattr(self, 'siret') and 'siret' in rvals:
            rvals.pop('siret')
        return rvals

    def _phone_number_clean(self, number, country_code, phone_field, vals, speedy):
        try:
            clean_number = phone_validation.phone_format(
                number,
                country_code,
                None,
                force_format="INTERNATIONAL",
                raise_exception=True
            )
            logger.info(
                'Phone number %s country %s reformatted to %s',
                number, country_code, clean_number)
            number = clean_number
        except Exception as e:
            speedy['logs'].append({
                'msg': "Failed to reformat with country '%s': %s" % (country_code, e),
                'value': number,
                'vals': vals,
                'field': 'res.partner,%s' % phone_field,
                })
        return number

    def _email_validate(self, email, email_check_deliverability, vals, speedy):
        try:
            validate_email(email, check_deliverability=email_check_deliverability)
        except EmailNotValidError as e:
            speedy['logs'].append({
                'msg': 'Invalid e-mail: %s' % e,
                'value': email,
                'vals': vals,
                'field': 'res.partner,email',
                'reset': True,
                })
            email = False
        return email

    def _prepare_bank(self, vals, speedy):
        assert vals.get('bic')
        bic = vals['bic'].upper()
        vals = {
            'bic': bic,
            'name': vals.get('bank_name', bic),
            }
        return vals

    def _match_title(self, vals, speedy):
        ttd = speedy['title']
        title_code = vals['title_code']
        if title_code in ttd['code2id']:
            title_id = ttd['code2id'][title_code]
            return title_id
        speedy['logs'].append({
            'msg': 'Could not find a title corresponding to code',
            'value': title_code,
            'vals': vals,
            'field': 'res.partner,title',
            'reset': True,
            })
        return False

    def _match_country(self, vals, speedy):
        country_name = vals['country_name']
        log = {
            'value': country_name,
            'vals': vals,
            'field': 'res.partner,country_id',
            }
        cyd = speedy['country']
        if len(country_name) in (2, 3):
            country_code = country_name.upper()
            if country_code in cyd['code2id']:
                logger.info("Country name '%s' is an ISO country code (%s)", country_name, cyd['code2name'][country_code])
                country_id = cyd['code2id'][country_code]
                return country_id
        country_name_match = self._import_prepare_country_name_match(country_name)
        if country_name_match in cyd['name2code']:
            country_code = cyd['name2code'][country_name_match]
            logger.info("Country '%s' matched on country %s (%s)", country_name, cyd['code2name'][country_code], country_code)
            country_id = cyd['code2id'][country_code]
            return country_id
        logger.info("No direct match for country '%s': now asking ChatGPT.", country_name)
        # ask ChatGPT !
        content = """ISO country code of "%s", nothing else""" % country_name
        logger.debug('ChatGPT question: %s', content)
        chat_completion = openai.ChatCompletion.create(
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
            logger.info('ChatGPT answer: %s', answer)
            if len(answer) == 2:
                country_code = answer.upper()
                if country_code in cyd['code2id']:
                    logger.info("ChatGPT matched country '%s' to %s (%s)", country_name, cyd['code2name'][country_code], country_code)
                    speedy['logs'].append(dict(log, msg="Country name could not be found in Odoo. ChatGPT said ISO code was '%s', which matched to '%s'" % (country_code, cyd['code2name'][country_code])))
                    country_id = cyd['code2id'][country_code]
                    cyd['name2code'][country_name_match] = country_code
                    return country_id
                else:
                    speedy['logs'].append(dict(log, msg="Country name could not be found in Odoo. ChatGPT said ISO code was '%s', which didn't match to any country" % country_code), reset=True)
            else:
                speedy['logs'].append(
                    dict(log, msg="ChatGPT didn't answer a 2 letter country code but '%s'" % answer, reset=True))
        else:
            logger.warning('No answer from chatGPT')
            speedy['logs'].append(dict(log, msg='No answer from chatGPT', reset=True))
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

    def _import_logs2html(self, speedy):
        line2logs = defaultdict(list)
        field2logs = defaultdict(list)
        for log in speedy['logs']:
            if log['vals'].get('line'):
                line2logs[log['vals']['line']].append(log)
            if log.get('field'):
                field2logs[log['field']].append(log)
        html = '<p><small>For the logs in <span style="color: red">red</span>, the data was <b>not imported</b> in Odoo</small><br/>'
        html += '<small><b>%d</b> OpenAI tokens where used</small></p>' % speedy['openai_tokens']
        html += '<h1>Logs per line</h1>'
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
                h3 += ' (%s ID %d)' % (log['vals']['display_name'], log['vals']['id'])
            html += '<h3>%s</h3>\n<p><ul>%s</ul></p>' % (h3, '\n'.join(log_labels))
        html += '<h1>Logs per field</h1>'
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

    def _import_result_action(self, speedy):
        action = {
            'name': 'Result',
            'type': 'ir.actions.act_window',
            'res_model': 'import.show.logs',
            'view_mode': 'form',
            'target': 'new',
            'context': dict(self._context, default_logs=self._import_logs2html(speedy)),
            }
        return action
