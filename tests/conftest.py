#!/usr/bin/env python3

import os

from leap.sugar import is_module_installed


if 'MANAGED_LEAP' in os.environ:
    if not is_module_installed('docker'):
        raise ImportError(
            f'MANAGED_LEAP present but package docker not installed, '
            'try reinstalling like this \"poetry install --with=nodemngr\"'
        )

    import pytest
    from leap.fixtures import bootstrap_test_nodeos


    @pytest.fixture(scope='module')
    def cleos_w_bootstrap(request, tmp_path_factory):
        request.applymarker(pytest.mark.bootstrap(True))
        with bootstrap_test_nodeos(request, tmp_path_factory) as cleos:
            yield cleos


    @pytest.fixture(scope='module')
    def cleos_w_testcontract(request, tmp_path_factory):
        deploy_marker = pytest.mark.contracts(
            testcontract='tests/contracts/testcontract')

        request.applymarker(deploy_marker)

        with bootstrap_test_nodeos(request, tmp_path_factory) as cleos:
            yield cleos
