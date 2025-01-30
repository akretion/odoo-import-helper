import setuptools

with open('VERSION.txt', 'r') as f:
    version = f.read().strip()

setuptools.setup(
    name="odoo13-addons-akretion-odoo-import-helper",
    description="Meta package for akretion-odoo-import-helper Odoo addons",
    version=version,
    install_requires=[
        'odoo13-addon-account_import_helper',
    ],
    classifiers=[
        'Programming Language :: Python',
        'Framework :: Odoo',
        'Framework :: Odoo :: 13.0',
    ]
)
