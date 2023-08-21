# Copyright 2023 Akretion France (http://www.akretion.com/)
# @author: Alexis de Lattre <alexis.delattre@akretion.com>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

{
    'name': 'Partner Import Helper',
    'version': '16.0.1.0.0',
    'category': 'Accounting',
    'license': 'AGPL-3',
    'summary': 'Helper methods to import partners',
    'author': 'Akretion',
    'website': 'https://github.com/akretion/odoo-import-helper',
    'depends': ['base'],
    'data': [
        'security/ir.model.access.csv',
        'wizards/import_show_logs_view.xml',
        ],
    'installable': True,
}
