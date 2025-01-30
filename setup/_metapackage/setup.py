import setuptools

with open('VERSION.txt', 'r') as f:
    version = f.read().strip()

setuptools.setup(
    name="odoo-addons-akretion-odoo-import-helper",
    description="Meta package for akretion-odoo-import-helper Odoo addons",
    version=version,
    install_requires=[
        'odoo-addon-account_import_helper>=16.0dev,<16.1dev',
        'odoo-addon-account_ir_property_helper>=16.0dev,<16.1dev',
        'odoo-addon-import_helper_base>=16.0dev,<16.1dev',
        'odoo-addon-partner_import_helper>=16.0dev,<16.1dev',
        'odoo-addon-product_import_helper>=16.0dev,<16.1dev',
    ],
    classifiers=[
        'Programming Language :: Python',
        'Framework :: Odoo',
        'Framework :: Odoo :: 16.0',
    ]
)
