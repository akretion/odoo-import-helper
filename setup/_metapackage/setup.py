import setuptools

with open('VERSION.txt', 'r') as f:
    version = f.read().strip()

setuptools.setup(
    name="odoo10-addons-akretion-odoo-import-helper",
    description="Meta package for akretion-odoo-import-helper Odoo addons",
    version=version,
    install_requires=[
        'odoo10-addon-account_import_helper',
    ],
    classifiers=[
        'Programming Language :: Python',
        'Framework :: Odoo',
        'Framework :: Odoo :: 10.0',
    ]
)
