# Copyright 2023 Akretion France (http://www.akretion.com/)
# @author: Alexis de Lattre <alexis.delattre@akretion.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

{
    'name': 'Partner Import Helper',
    'version': '17.0.1.0.0',
    'category': 'Extra Tools',
    'license': 'AGPL-3',
    'summary': 'Helper methods to import partners',
    'author': 'Akretion',
    'website': 'https://github.com/akretion/odoo-import-helper',
    'depends': [
        'import_helper_base',
        'phone_validation',  # would be nice to avoid depending on it ?
        ],
    'installable': False,
}
