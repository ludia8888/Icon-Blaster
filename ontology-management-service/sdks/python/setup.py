"""
Setup script for oms-event-sdk
"""

from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

with open("requirements.txt", "r", encoding="utf-8") as fh:
    requirements = [line.strip() for line in fh if line.strip() and not line.startswith("#")]

setup(
    name="oms-event-sdk",
    version="1.0.0",
    author="OMS Team",
    description="Auto-generated SDK for OMS Event API",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/company/oms-event-sdk-py",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
    ],
    python_requires=">=3.8",
    install_requires=requirements,
    keywords=["oms", "events", "asyncapi", "python"],
    project_urls={
        "Bug Reports": "https://github.com/company/oms-event-sdk-py/issues",
        "Source": "https://github.com/company/oms-event-sdk-py",
    },
)
