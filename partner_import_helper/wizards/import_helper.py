# Copyright 2023 Akretion France (http://www.akretion.com/)
# @author: Alexis de Lattre <alexis.delattre@akretion.com>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import api, models, fields, Command, _
from odoo.exceptions import UserError
from odoo.addons.phone_validation.tools import phone_validation
from odoo.tools import plaintext2html

import re
import copy
import openpyxl, base64, io

from stdnum.eu.vat import is_valid as vat_is_valid, check_vies
from stdnum.iban import is_valid as iban_is_valid
from stdnum.fr.siret import is_valid as siret_is_valid
from stdnum.fr.siren import is_valid as siren_is_valid
from email_validator import validate_email, EmailNotValidError

import logging
logger = logging.getLogger(__name__)


class ImportHelper(models.TransientModel):
    _inherit = 'import.helper'

    file = fields.Binary(string = 'XML file')

    #===== XLSX import methods =====#
    def _get_sheet_names(self):
        return ['companies', 'contacts', 'banks',]
    
    def button_import_partner(self):
        """ Button pressed by user, triggering the import methods """
        # read xlsx
        bin_data = base64.b64decode(self.file)
        data = io.BytesIO(bin_data)
        workbook = openpyxl.load_workbook(data)
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
                if bool(value): # filter empty cells
                    vals[col_name] = str(value).strip()
            if row == 1015:
                assert vals
            vals_list.append(vals)
        
        return headers, vals_list

    def _get_companies_address_types(self):
        """ Suffixes of col names for company's address types
            :return: ['contact', 'invoice', 'delivery', 'other']
        """
        return [x[0] for x in self.env['res.partner']._fields['type'].selection]
    
    def _get_company_vals_default(self):
        return {
            'is_company': True,
            'lang': 'fr_FR',
            'country_name': 'FRA',
        }
    
    def _get_company_address_vals_default(self):
        return {
            'is_company': False,
            'lang': 'fr_FR',
            'country_name': 'FRA',
        }
    
    def _load_sheet_companies(self, speedy, headers, vals_list):
        """ Browse `companies` worksheet data in `vals_list`
             and call `_create_partner` to create companies and sub-addresses

            1 line contains:
             * company details
             * 1 bank account information
             * 1 invoice address details
             * 1 delivery address details

             Invoice and Delivery adresses may also be managed in `contacts` tab.
             They are here because it can be convenient to manage them directly linked to the company,
             if your customer only has 1 adress of this kind per company.
        """
        address_types = self._get_companies_address_types()
        company_fields = [
            x for x in headers
            if all([not x.startswith(address + '_') for address in address_types])
        ]

        company_vals_default = self._get_company_vals_default()
        address_vals_default = self._get_company_address_vals_default()

        row = 2
        for vals in vals_list:
            addresses_vals_list = []
            for address in address_types:
                address_vals = {}
                for col_name, value in vals.copy().items():
                    if col_name.startswith(address + '_'):
                        address_vals |= {col_name.replace(address + '_', ''): str(value).strip()}
                        vals.pop(col_name)
                if address_vals:
                    addresses_vals_list += [address_vals_default | {'type': address} | address_vals]
            
            vals = company_vals_default | {
                k: v for k, v in vals.items()
                if k in company_fields
            } | {
                'child_ids': [(0, 0, vals) for vals in addresses_vals_list],
                'line': 'companies_%d' % row,
            }
            self.sudo()._create_partner(vals, speedy) # sudo for multi-company
            row += 1

    def _load_sheet_contacts(self, speedy, headers, vals_list):
        """ Browse `contacts` sheet to create:
             a) if `ref` is given: sub-level contact of company
             b) else, 1st level person
        """
        row = 2
        Partner = self.env['res.partner'].sudo().with_context(active_test=False) # sudo for private addresses
        speedy['partner_parent_ids'] = {
            (x.ref, x.company_id.partner_id.ref): x.id
            for x in Partner.search([])
        }
        for vals in vals_list:
            if vals['ref']:
                company_ref = vals['company_ref'].strip() or False if 'company_ref' in vals else self.env.company.partner_id.ref
                parent_id = speedy['partner_parent_ids'].get((vals['ref'], company_ref))
                if not parent_id:
                    raise UserError(_("In `contacts` tab, parent ref %s not found in company %s", vals['ref'], company_ref))
                vals |= {
                    'parent_id': parent_id,
                    'line': 'contacts_%d' % row,
                }
            self.sudo()._create_partner(vals, speedy) # sudo for multi-company
            row += 1

    def _load_sheet_banks(self, speedy, headers, vals_list):
        """ Browse `banks` sheet to add IBAN to companies
             and create banks if needed
        """
        row = 2
        Partner = self.env['res.partner'].sudo().with_context(active_test=False) # sudo for private addresses
        speedy['partners'] = {
            (x.ref, x.company_id.partner_id.ref): x
            for x in Partner.search([])
        }
        for vals in vals_list:
            company_ref = vals['company_ref'].strip() or False if 'company_ref' in vals else self.env.company.partner_id.ref
            partner = speedy['partners'].get((vals['ref'], company_ref))
            if not partner:
                raise UserError(_("In `banks` tab, parent ref %s not found in company %s", vals['ref'], company_ref))
            
            # creates banks, returns 'bank_ids' key in vals
            vals |= {'line': 'banks_%d' % row,}
            rvals = self._prepare_partner_vals(vals, speedy)
            if 'bank_ids' in rvals:
                partner.write(rvals)
                logger.info('Bank added: %s to partner %s from line %s', vals['iban'], partner.id, vals['line'])
            else:
                logger.info('Bank ignored: partner %s, line %s', partner.id, vals['line'])
            
            row += 1

    # TODO add support for states
    @api.model
    def _prepare_speedy(self):
        speedy = super()._prepare_speedy()
        speedy["logs"]["res.partner"] = []
        speedy.update({
            "o2m_phone": hasattr(self.env['res.partner'], 'phone_ids'),
            "eu_country_ids": self.env.ref('base.europe').country_ids.ids,
            "fr_country_id": self.env.ref('base.fr').id,
            "mc_country_id": self.env.ref('base.mc').id,
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
            'company': {},
            'categories': {},
            'industry_name2id': {},
            'fiscal_position': {},
            # _phone_get_number_fields() is a method of phone_validation that return ['phone', 'mobile']
            'phone_fields': self.env['res.partner']._phone_get_number_fields(),
        })
        for bank in self.env['res.bank'].with_context(active_test=False).search_read([('bic', '!=', False)], ['name', 'bic']):
            bic = bank['bic'].upper()
            speedy['bank']['bic2id'][bic] = bank['id']
            speedy['bank']['bic2name'][bic] = bank['name']
        for indus in self.env['res.partner.industry'].with_context(active_test=False).search_read([('name', '!=', False)], ['name']):
            speedy['industry_name2id'][indus['name']] = indus['id']
        for categories in self.env['res.partner.category'].with_context(active_test=False).search_read([('name', '!=', False)], ['name']):
            speedy['categories'][categories['name']] = categories['id']
        for company in self.env['res.company'].with_context(active_test=False).sudo().search([]):
            speedy['company'][company.partner_id.ref] = company.id
        if (
                self.env.company.country_id.code == 'FR' and
                hasattr(self.env['res.partner'], 'property_account_position_id') and
                hasattr(self.env['account.fiscal.position'], 'fr_vat_type')):
            fp_count = self.env['account.fiscal.position'].search_count([('company_id', '=', self.env.company.id)])
            if fp_count:
                speedy['fiscal_position']['id2name'] = {}
                speedy['fiscal_position']['frvattype2id'] = {
                    'france': False,
                    'france_vendor_vat_on_payment': False,  # not used for the moment
                    'intracom_b2b': False,
                    'intracom_b2c': False,
                    'extracom': False,
                    }
                for fr_vat_type in speedy['fiscal_position']['frvattype2id'].keys():
                    fps = self.env['account.fiscal.position'].search_read([('company_id', '=', self.env.company.id), ('fr_vat_type', '=', fr_vat_type)], ['name'])
                    if not fps:
                        raise UserError(_("There are no fiscal position with fr_vat_type=%(fr_vat_type)s in company '%(company)s'.", fr_vat_type=fr_vat_type, company=self.env.company.display_name))
                    if len(fps) > 1:
                        logger.warning(
                            'There are %d fiscal positions with fr_vat_type=%s: %s',
                            len(fps), fr_vat_type, ' ,'.join([fp['name'] for fp in fps]))
                    fp = fps[0]
                    speedy['fiscal_position']['frvattype2id'][fr_vat_type] = fp['id']
                    speedy['fiscal_position']['id2name'][fp['id']] = fp['name']
        if "account.payment.term" in self.env:  # we don't depend on account
            speedy['payment_term'] = {
                1: self.env.ref('account.account_payment_term_immediate').id,
                15: self.env.ref('account.account_payment_term_15days').id,
                21: self.env.ref('account.account_payment_term_21days').id,
                30: self.env.ref('account.account_payment_term_30days').id,
                45: self.env.ref('account.account_payment_term_45days').id,
                }
        return speedy

    def _create_partner(self, vals, speedy, email_check_deliverability=True, create_bank=True):
        rvals = self._prepare_partner_vals(
            vals, speedy, email_check_deliverability=email_check_deliverability,
            create_bank=create_bank)
        partner = self.env['res.partner'].create(rvals)
        create_date_dt = self._prepare_create_date(vals, speedy)
        if create_date_dt:
            self._cr.execute(
                "UPDATE res_partner SET create_date=%s WHERE id=%s",
                (create_date_dt, partner.id))
        vals['display_name'] = partner.display_name
        vals['id'] = partner.id
        logger.info('New partner created: %s ID %d from line %s', partner.display_name, partner.id, vals['line'])
        return partner

    @api.model
    def _prepare_parent_child_partner_vals(self, vals, parent_or_child, speedy, email_check_deliverability=True, parent_country_id=False):
        assert vals
        assert isinstance(vals, dict)
        assert isinstance(speedy, dict)
        assert parent_or_child in ('parent', 'child')
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
            country_id = self._match_country(
                vals, "country_name", "res.partner", "country_id", speedy)
            # Warning: country_id can be False
            vals['country_id'] = country_id
        if parent_or_child == 'child' and not country_id and parent_country_id:
            country_id = parent_country_id
        if country_id:
            country_code = speedy['country']['id2code'].get(country_id)
        # TITLE
        if not vals.get('is_company') and vals.get('title_code') and isinstance(vals['title_code'], str) and not vals.get('title'):
            title_id = self._match_partner_title(vals, speedy)
            vals['title'] = title_id
        # PHONE/MOBILE
        for phone_field in speedy['phone_fields']:
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
                    speedy['logs']['res.partner'].append({
                        'msg': '%s key should be a string, not %s' % (phone_field, type(vals[phone_field]).__name__),
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
                speedy['logs']['res.partner'].append({
                    'msg': 'email key should be a string, not %s' % type(vals['email']).__name__,
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
                speedy['logs']['res.partner'].append({
                    'msg': 'Zip code has %d chars. In France, they have 5 chars.' % len(zipcode),
                    'value': zipcode,
                    'vals': vals,
                    'field': 'res.partner,zip',
                    })
            if not zipcode.isdigit():
                speedy['logs']['res.partner'].append({
                    'msg': 'In France, ZIP codes only contain digits.',
                    'value': zipcode,
                    'vals': vals,
                    'field': 'res.partner,zip',
                    })
            # if we have geonames, we could compare it with the DB of zip

    # vals is a dict to create a res.partner
    # It must contain a 'line' key, to indicate Excel/CSV import ref in logs
    # (removed before calling create)
    # it can contain some special keys, which will be replaced by the corresponding real key after processing:
    # 'country_name' => 'country_id'
    # 'title_code' can contain 'madam', 'miss', 'mister', 'doctor', 'prof' /  => 'title'
    # 'iban' => 'bank_ids': [(0, 0, {'acc_number': xxx})]
    # 'bic': => 'bank_ids': [(0, 0, {'acc_number': xxxx, 'bank_id': bank_id})]
    @api.model
    def _prepare_partner_vals(self, vals, speedy, email_check_deliverability=True, create_bank=True):
        self._prepare_parent_child_partner_vals(
            vals, 'parent', speedy, email_check_deliverability=email_check_deliverability)
        if vals.get('child_ids'):
            for child in vals['child_ids']:
                if 'line' not in child[2]:
                    child[2]['line'] = vals['line']
                self._prepare_parent_child_partner_vals(
                    child[2], 'child', speedy,
                    email_check_deliverability=email_check_deliverability,
                    parent_country_id=vals.get('country_id'))
        country_id = vals.get('country_id')
        # is_company
        if not vals.get('is_company') and (vals.get('vat') or vals.get('siren') or vals.get('siret')):
            if vals.get('vat'):
                msg = 'Has a VAT number, but is not marked as a company'
            elif vals.get('siren'):
                msg = 'Has a SIREN, but is not marked as a company'
            elif vals.get('siret'):
                msg = 'Has a SIRET, but is not marked as a company'
            speedy['logs']['res.partner'].append({
                'msg': msg,
                'value': 'Individual',
                'vals': vals,
                'field': 'res.partner,is_company',
                })
        # company_id
        if vals.get('company_ref'):
            if vals['company_ref'] not in speedy['company']:
                raise UserError(_("Company %s does not exist in Odoo. Contact not imported.", vals['company_ref']))
            else:
                vals['company_id'] = speedy['company'][vals['company_ref']]
        # VAT
        vat = False
        if vals.get('vat') and (not country_id or country_id in speedy['eu_country_ids']):
            vat = vals['vat'].upper()
            # clean VAT
            vat = ''.join(re.findall(r'[A-Z0-9]+', vat))
            if not vat_is_valid(vat):
                speedy['logs']['res.partner'].append({
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
                        speedy['logs']['res.partner'].append({
                            'msg': 'VIES said that VAT is not valid',
                            'value': vat,
                            'vals': vals,
                            'field': 'res.partner,vat',
                            'reset': True,
                            })
                        vat = False
                except Exception as e:
                    logger.warning('Could not perform VIES validation on VAT %s: %s', vat, e)
                    speedy['logs']['res.partner'].append({
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
                speedy['logs']['res.partner'].append({
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
                        speedy['logs']['res.partner'].append({
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
                            self._prepare_res_bank(vals, speedy))
                        bank_id = bank.id
                        speedy['bank']['bic2id'][bic] = bank_id
                        speedy['bank']['bic2name'][bic] = bank.name
                        speedy['logs']['res.partner'].append({
                            'msg': "BIC not found in Odoo. New bank named '%s' created (ID %d)" % (bank.name, bank.id),
                            'value': bic,
                            'vals': vals,
                            'field': 'res.bank,bic',
                            })
                    else:
                        speedy['logs']['res.partner'].append({
                            'msg': "BIC not found in Odoo.",
                            'value': bic,
                            'vals': vals,
                            'field': 'res.bank,bic',
                            })
                if vals.get('bank_ids'):
                    raise UserError(_("vals contains both an 'iban' and a 'bank_ids' keys. This should never happen."))
                vals['bank_ids'] = [(0, 0, {'acc_number': iban, 'bank_id': bank_id})]
        # SIREN_OR_SIRET
        if vals.get('siren_or_siret') and hasattr(self.env['res.partner'], 'siret'):
            siren_or_siret = vals['siren_or_siret']
            if isinstance(siren_or_siret, int):
                siren_or_siret = str(siren_or_siret)
            siren_or_siret = ''.join(re.findall(r'[0-9]+', siren_or_siret))
            if siren_or_siret:
                if len(siren_or_siret) == 14:
                    vals['siret'] = siren_or_siret
                elif len(siren_or_siret) == 9:
                    vals['siren'] = siren_or_siret
                else:
                    speedy['logs']['res.partner'].append({
                        'msg': 'SIREN/SIRET has a length of %d instead of 9 or 14' % len(siren_or_siret),
                        'value': siren_or_siret,
                        'vals': vals,
                        'field': 'res.partner,siret',
                        'reset': True,
                        })
        # SIREN
        if vals.get('siren') and hasattr(self.env['res.partner'], 'siren'):
            siren = vals['siren']
            if isinstance(siren, int):
                siren = str(siren)
            siren = ''.join(re.findall(r'[0-9]+', siren))
            if len(siren) != 9:
                speedy['logs']['res.partner'].append({
                    'msg': 'SIREN has a length of %d instead of 9' % len(siren),
                    'value': siren,
                    'vals': vals,
                    'field': 'res.partner,siren',
                    'reset': True,
                    })
                siren = False
                vals.pop('siren')
            if not siren_is_valid(siren):
                speedy['logs']['res.partner'].append({
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
                    speedy['logs']['res.partner'].append({
                    'msg': "Partner has SIREN '%s', so it's VAT number should start with FR" % siren,
                    'value': vat,
                    'vals': vals,
                    'field': 'res.partner,vat',
                    })
                if vat[4:] != siren:
                    speedy['logs']['res.partner'].append({
                    'msg': "Partner has SIREN '%s', so it must compose the 9 last digits of it's VAT number" % siren,
                    'value': vat,
                    'vals': vals,
                    'field': 'res.partner,vat',
                    })
        # SIRET
        if vals.get('siret') and hasattr(self.env['res.partner'], 'siret'):
            siret = vals['siret']
            if isinstance(siret, int):
                siret = str(siret)
            siret = ''.join(re.findall(r'[0-9]+', siret))
            if len(siret) != 14:
                speedy['logs']['res.partner'].append({
                    'msg': 'SIRET has a length of %d instead of 14' % len(siret),
                    'value': siret,
                    'vals': vals,
                    'field': 'res.partner,siret',
                    'reset': True,
                    })
                siret = False
                vals.pop('siret')
            elif not siret_is_valid(siret):
                speedy['logs']['res.partner'].append({
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
                    speedy['logs']['res.partner'].append({
                    'msg': "Partner has SIRET '%s', so it's VAT number should start with FR" % siret,
                    'value': vat,
                    'vals': vals,
                    'field': 'res.partner,vat',
                    })
                if vat[4:] != siret[:9]:
                    speedy['logs']['res.partner'].append({
                    'msg': "Partner has SIRET '%s', so the 9 first digits of the SIRET must compose the 9 last digits of it's VAT number" % siret,
                    'value': vat,
                    'vals': vals,
                    'field': 'res.partner,vat',
                    })
        if vals.get('siren') and vals.get('siret'):
            if not vals['siret'].startswith(vals['siren']):
                speedy['logs']['res.partner'].append({
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
        # CATEGORIES
        if vals.get('categories'):
            vals_categories = []
            categories = vals.get('categories').split(',')
            for category in categories:
                if category not in speedy['categories']:
                    speedy['categories'][category] = self.env['res.partner.category'].create({'name': category}).id
                vals_categories += [Command.link(speedy['categories'][category])]
            vals['category_id'] = vals_categories
        # INDUSTRY
        if vals.get('industry_name'):
            if vals['industry_name'] not in speedy['industry_name2id']:
                indus = self.env['res.partner.industry'].create(self._prepare_industry(vals, speedy))
                speedy['industry_name2id'][vals['industry_name']] = indus.id
            vals['industry_id'] = speedy['industry_name2id'][vals['industry_name']]
        if country_id:
            country_code = speedy['country']['id2code'][country_id]
            # TODO Northern Ireland doesn't pass this check
            if vat and country_id in speedy['eu_country_ids']:
                expected_country_code = vat[:2]
                if expected_country_code == 'EL':  # special case for Greece
                    expected_country_code = 'GR'
                elif expected_country_code == 'XI':  # Northern Ireland
                    expected_country_code = 'GB'
                if expected_country_code != country_code:
                    speedy['logs']['res.partner'].append({
                        'msg': f"Given the VAT number ({vat}), the country code should be '{expected_country_code}' but it is '{country_code}'",
                        'value': vat,
                        'vals': vals,
                        'field': 'res.partner,vat',
                        })
            if iban and not iban.startswith(country_code):
                speedy['logs']['res.partner'].append({
                    'msg': "The country prefix of the IBAN doesn't match the country code '%s'" % country_code,
                    'value': iban,
                    'vals': vals,
                    'field': 'res.partner.bank,acc_number',
                    })
        # Payment terms
        if speedy.get('payment_term'):
            if vals.get('customer_payment_term_code'):
                if vals['customer_payment_term_code'] in speedy['payment_term']:
                    vals['property_payment_term_id'] = speedy['payment_term'][vals['customer_payment_term_code']]
                else:
                    # try to convert to int
                    try:
                        customer_payment_term_int = int(vals['customer_payment_term_code'])
                    except:
                        customer_payment_term_int = None
                    if customer_payment_term_int in speedy['payment_term']:
                        vals['property_payment_term_id'] = speedy['payment_term'][customer_payment_term_int]
                    else:
                        speedy['logs']['res.partner'].append({
                            'msg': "Payment term code '%s' doesn't exist" % vals['customer_payment_term_code'],
                            'value': vals['customer_payment_term_code'],
                            'vals': vals,
                            'field': 'res.partner,property_payment_term_id',
                            'reset': True,
                            })
            if vals.get('supplier_payment_term_code'):
                if vals['supplier_payment_term_code'] in speedy['payment_term']:
                    vals['property_supplier_payment_term_id'] = speedy['payment_term'][vals['supplier_payment_term_code']]
                else:
                    # try to convert to int
                    try:
                        supplier_payment_term_int = int(vals['supplier_payment_term_code'])
                    except:
                        supplier_payment_term_int = None
                    if supplier_payment_term_int in speedy['payment_term']:
                        vals['property_supplier_payment_term_id'] = speedy['payment_term'][supplier_payment_term_int]
                    else:
                        speedy['logs']['res.partner'].append({
                            'msg': "Payment term code '%s' doesn't exist" % vals['supplier_payment_term_code'],
                            'value': vals['supplier_payment_term_code'],
                            'vals': vals,
                            'field': 'res.partner,property_supplier_payment_term_id',
                            'reset': True,
                            })

        # FISCAL POSITION for France
        if (
                hasattr(self.env['res.partner'], 'property_account_position_id') and
                speedy['fiscal_position'].get('frvattype2id') and country_id):
            if country_id in (speedy['fr_country_id'], speedy['mc_country_id']):
                vals['property_account_position_id'] = speedy['fiscal_position']['frvattype2id']['france']
                # DOMs
                if vals.get('zip') and len(vals['zip']) == 5 and vals['zip'].startswith('97'):
                    vals['property_account_position_id'] = speedy['fiscal_position']['frvattype2id']['extracom']
            elif country_id in speedy['eu_country_ids']:
                if vals.get('is_company'):
                    vals['property_account_position_id'] = speedy['fiscal_position']['frvattype2id']['intracom_b2b']
                    if not vals.get('vat'):
                        speedy['logs']['res.partner'].append({
                            'msg': "The fiscal position Intra-EU B2B has been set but the partner has no VAT.",
                            'value': speedy['fiscal_position']['id2name'][vals['property_account_position_id']],
                            'vals': vals,
                            'field': 'res.partner,property_account_position_id',
                            })
                else:
                    vals['property_account_position_id'] = speedy['fiscal_position']['frvattype2id']['intracom_b2c']
            else:
                vals['property_account_position_id'] = speedy['fiscal_position']['frvattype2id']['extracom']
        # Comment txt -> html
        if vals.get('comment_txt'):
            vals['comment'] = plaintext2html(vals['comment_txt'])
        # vals will keep the original keys
        # rvals will be used for create(), so we need to remove all the keys are don't exist on res.partner
        rvals = copy.deepcopy(vals)
        self._remove_technical_keys(rvals)
        if 'child_ids' in rvals:
            for child in rvals['child_ids']:
                self._remove_technical_keys(child[2])
        return rvals

    def _remove_technical_keys(self, rvals):
        keys_to_remove = [
            'line', 'create_date', 'company_ref', 'iban', 'bic', 'bank_name',
            'industry_name', 'categories',
            'siren_or_siret', 'title_code', 'country_name', 'comment_txt',
            'customer_payment_term_code', 'supplier_payment_term_code']
        for key in keys_to_remove:
            if key in rvals:
                rvals.pop(key)
        if not hasattr(self.env['res.partner'], 'siren') and 'siren' in rvals:
            rvals.pop('siren')
        if not hasattr(self.env['res.partner'], 'siret') and 'siret' in rvals:
            rvals.pop('siret')

    def _prepare_industry(self, vals, speedy):
        return {'name': vals['industry_name']}
    
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
            speedy['logs']['res.partner'].append({
                'msg': "Failed to reformat with country '%s': %s" % (country_code, e),
                'value': number,
                'vals': vals,
                'field': 'res.partner,%s' % phone_field,
                })
        return number

    def _email_validate(self, email, email_check_deliverability, vals, speedy):
        email = email.strip()
        if not email:
            return False
        try:
            validate_email(email, check_deliverability=email_check_deliverability)
        except EmailNotValidError as e:
            speedy['logs']['res.partner'].append({
                'msg': 'Invalid e-mail: %s' % e,
                'value': email,
                'vals': vals,
                'field': 'res.partner,email',
#                'reset': True,
                })
#            email = False
        return email

    def _prepare_res_bank(self, vals, speedy):
        assert vals.get('bic')
        bic = vals['bic'].upper()
        vals = {
            'bic': bic,
            'name': vals.get('bank_name', bic),
            }
        return vals

    def _match_partner_title(self, vals, speedy):
        ttd = speedy['title']
        title_code = vals['title_code']
        if title_code in ttd['code2id']:
            title_id = ttd['code2id'][title_code]
            return title_id
        speedy['logs']['res.partner'].append({
            'msg': 'Could not find a title corresponding to code',
            'value': title_code,
            'vals': vals,
            'field': 'res.partner,title',
            'reset': True,
            })
        return False
