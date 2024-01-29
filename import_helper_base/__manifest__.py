# Copyright 2023 Akretion France (http://www.akretion.com/)
# @author: Alexis de Lattre <alexis.delattre@akretion.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

{
    'name': 'Import Helper Base',
    'version': '17.0.1.0.0',
    'category': 'Extra Tools',
    'license': 'AGPL-3',
    'summary': 'Common code for all import helper modules',
    'author': 'Akretion',
    'website': 'https://github.com/akretion/odoo-import-helper',
    'depends': [
        'base',
        ],
    'data': [
        'security/ir.model.access.csv',
        'wizards/import_helper_view.xml',
        ],
    'installable': False,
}
