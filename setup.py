"""
Copyright 2024 Ovizro

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

import re
import warnings
from setuptools import setup, find_packages


description = long_description = "A simple Tinode chatbot framework."

try:
    with open("README.md", encoding='utf-8') as f:
        long_description = f.read()
except OSError:
    warnings.warn("Miss file 'README.md', using default description.", ResourceWarning)


try:
    with open("karuha/version.py") as f:
        version = re.search(r"__version__\s*=\s*\"(.*)\"\n", f.read()).group(1) # type: ignore
except Exception as e:
    raise ValueError("fail to read karuha version") from e

setup(
    name="KaruhaBot",
    version=version,
    description=description,
    long_description=long_description,
    long_description_content_type='text/markdown',
    
    author="Visecy",
    author_email="Visecy@visecy.org",
    maintainer="Ovizro",
    maintainer_email="Ovizro@visecy.org",
    license="Apache 2.0",

    url="https://github.com/Ovizro/Karuha",
    packages=find_packages(),
    python_requires=">=3.8",
    install_requires=[
        "typing_extensions>=4.0",
        "grpcio>=1.40.0",
        "tinode-grpc>=0.20.0b3",
        "pydantic>2.0",
        "aiofiles"
    ],
    extras_require={
        "image": ["pillow"],
        "data": ["greenback"],
        "all": ["pillow", "greenback"],
    },

    classifiers=[
        "Development Status :: 4 - Beta",
        "License :: OSI Approved :: Apache Software License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3 :: Only",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Topic :: Communications :: Chat",
    ]
)