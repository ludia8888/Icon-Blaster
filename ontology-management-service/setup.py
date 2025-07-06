from setuptools import setup, find_packages

setup(
    name="ontology_management_service",
    version="0.1.0",
    description="Ontology Management Service for Arrakis Project",
    author="Arrakis Corp",
    author_email="dev@arrakis.corp",
    packages=find_packages(),
    install_requires=[
        # Dependencies are managed by requirements.txt files
        # to separate production and development dependencies.
    ],
    entry_points={
        'console_scripts': [
            'oms-server=main:app',
        ],
    },
    zip_safe=False,
) 