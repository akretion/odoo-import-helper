import setuptools

with open('VERSION.txt', 'r') as f:
    version = f.read().strip()

setuptools.setup(
    name="odoo14-addons-akretion-odoo-import-helper",
    description="Meta package for akretion-odoo-import-helper Odoo addons",
    version=version,
    install_requires=[
        'odoo14-addon-account_balance_reset',
        'odoo14-addon-account_import_helper',
        'odoo14-addon-account_ir_property_helper',
        'odoo14-addon-product_import_helper',
        'odoo14-addon-product_pattern_import_helper',
        'odoo14-addon-shopinvader_url_import',
    ],
    classifiers=[
        'Programming Language :: Python',
        'Framework :: Odoo',
        'Framework :: Odoo :: 14.0',
    ]
)
