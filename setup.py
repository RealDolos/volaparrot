#!/usr/bin/env python3
"""
Set it up!!!!
"""

from setuptools import setup
import re

def version():
    """Thanks python!"""
    with open("volaparrot/_version.py") as filep:
        return re.search('__version__ = "(.+?)"', filep.read()).group(1)

setup(
    name="volaparrot",
    version=version(),
    description="Just fuck up some rooms",
    url="https://github.com/RealDolos/volaparrot",
    license="MIT",
    author="RealDolos",
    author_email="dolos@cock.li",
    packages=['volaparrot', 'volaparrot.commands', 'volaparrot.extracommands'],
    include_package_data=True,
    entry_points={"console_scripts": ["volaparrot = volaparrot.__main__:run"]},
    classifiers=[
        "Development Status :: 4 - Beta",
        "Environment :: Console",
        "Intended Audience :: End Users/Desktop",
        "License :: OSI Approved :: MIT License",
        "Natural Language :: English",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3 :: Only",
        "Topic :: Internet :: WWW/HTTP",
        "Topic :: System :: Archiving",
        "Topic :: Utilities",
    ],
    install_requires=[l.strip() for l in open("requirements.txt").readlines()]
    )
