=====
berry
=====

.. image:: https://travis-ci.org/zalando-stups/berry.svg?branch=master
   :target: https://travis-ci.org/zalando-stups/berry
   :alt: Build Status

.. image:: https://coveralls.io/repos/zalando-stups/berry/badge.svg
   :target: https://coveralls.io/r/zalando-stups/berry
   :alt: Code Coverage

.. image:: https://img.shields.io/pypi/dw/stups-berry.svg
   :target: https://pypi.python.org/pypi/stups-berry/
   :alt: PyPI Downloads

.. image:: https://img.shields.io/pypi/v/stups-berry.svg
   :target: https://pypi.python.org/pypi/stups-berry/
   :alt: Latest PyPI version

.. image:: https://img.shields.io/pypi/l/stups-berry.svg
   :target: https://pypi.python.org/pypi/stups-berry/
   :alt: License

Berry is the partner component for `mint`_. Berry is a tiny agent, that
constantly updates the local credentials file, so that applications can read their most recent passwords easily.

Installation
============

Python 2.7+ is required.

.. code-block:: bash

    $ sudo pip3 install --upgrade stups-berry

Usage
=====

See the help for configuration options:

.. code-block:: bash

    $ berry --help

In addition, berry takes all the `standard AWS SDK inputs`_
(local credentials file, environment variables and instance profiles).

License
=======

Copyright © 2015 Zalando SE

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.

.. _mint: https://github.com/zalando-stups/mint
.. _standard AWS SDK inputs: http://blogs.aws.amazon.com/security/post/Tx3D6U6WSFGOK2H/A-New-and-Standardized-Way-to-Manage-Credentials-in-the-AWS-SDKs
