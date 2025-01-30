import setuptools

with open('VERSION.txt', 'r') as f:
    version = f.read().strip()

setuptools.setup(
    name="odoo12-addons-akretion-odoo-import-helper",
    description="Meta package for akretion-odoo-import-helper Odoo addons",
    version=version,
    install_requires=[
        'odoo12-addon-account_import_helper',
        'odoo12-addon-product_template_import_helper',
        'odoo12-addon-storage_image_import',
        'odoo12-addon-storage_image_product_import',
    ],
    classifiers=[
        'Programming Language :: Python',
        'Framework :: Odoo',
        'Framework :: Odoo :: 12.0',
    ]
)
