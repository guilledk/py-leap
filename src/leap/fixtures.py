#!/usr/bin/env python3

import json
import logging
import time

from typing import Optional
from pathlib import Path

import docker
import pytest

from docker.types import Mount

from leap.protocol import gen_key_pair

from .cleos import CLEOS
from .sugar import (
    get_container,
    get_free_port,
)


DEFAULT_NODEOS_REPO = 'guilledk/py-leap'
DEFAULT_NODEOS_IMAGE = 'leap-4.0.4'


def default_nodeos_image():
    return f'{DEFAULT_NODEOS_REPO}:{DEFAULT_NODEOS_IMAGE}'


@pytest.fixture(scope='session')
def single_node_chain(tmp_path_factory):
    tmp_path = tmp_path_factory.getbasetemp()
    leap_path = tmp_path / 'leap'
    leap_path.mkdir(parents=True, exist_ok=True)
    leap_path = leap_path.resolve()

    logging.info(f'created tmp path at {leap_path}')

    dclient = docker.from_env()

    container_img = default_nodeos_image()
    logging.info(f'launching {container_img} container...')

    cmd = ['nodeos', '-e', '-p', 'eosio', '--config-dir', '/root']

    for plugin in [
        'net_plugin',
        'http_plugin',
        'chain_plugin',
        'producer_plugin',
        'chain_api_plugin',
        'producer_api_plugin'
    ]:
        cmd += ['--plugin', f'eosio::{plugin}']

    http_port = get_free_port()
    cmd += ['--http-server-address', '0.0.0.0:8888']
    cmd += ['--http-validate-host', '0']

    priv, pub = gen_key_pair()
    cmd += ['--signature-provider', f'{pub}=KEY:{priv}']

    with open(leap_path / 'genesis.json', 'w+') as genesis_file:
        genesis_file.write(
            json.dumps({
                'initial_timestamp': '2019-04-15T11:00:00.000',
                'initial_key': pub,
                'initial_configuration': {
                    'max_block_net_usage': 1048576,
                    'target_block_net_usage_pct': 1000,
                    'max_transaction_net_usage': 1048575,
                    'base_per_transaction_net_usage': 12,
                    'net_usage_leeway': 500,
                    'context_free_discount_net_usage_num': 20,
                    'context_free_discount_net_usage_den': 100,
                    'max_block_cpu_usage': 200000,
                    'target_block_cpu_usage_pct': 1000,
                    'max_transaction_cpu_usage': 150000,
                    'min_transaction_cpu_usage': 100,
                    'max_transaction_lifetime': 3600,
                    'deferred_trx_expiration_window': 600,
                    'max_transaction_delay': 3888000,
                    'max_inline_action_size': 4096,
                    'max_inline_action_depth': 4,
                    'max_authority_depth': 6
                }
            }, indent=4)
        )

    cmd += ['--genesis-json', '/root/genesis.json']

    cmd += ['--contracts-console']
    vtestnet = get_container(
        dclient,
        container_img,
        force_unique=True,
        name=f'{tmp_path.name}-leap',
        detach=True,
        remove=True,
        ports={'8888/tcp': http_port},
        mounts=[Mount('/root', str(leap_path), 'bind')],
        command=cmd
    )

    try:
        cleos = CLEOS(url=f'http://127.0.0.1:{http_port}')

        cleos.import_key('eosio', priv)

        # maybe download sys contracts
        download_location = Path('tests/contracts')
        download_location.mkdir(exist_ok=True, parents=True)

        def maybe_download_contract(
            account_name: str,
            local_name: Optional[str] = None
        ):
            if not local_name:
                local_name = account_name

            logging.info(f'maybe download {local_name}')

            contract_loc = download_location / local_name
            if contract_loc.is_dir():
                logging.info('...skip already downloaded.')
                return

            else:
                logging.info('downloading...')
                contract_loc.mkdir()

            cleos.download_contract(
                account_name, contract_loc,
                target_url=cleos.remote_endpoint,
                local_name=local_name
            )
            logging.info('done.')

        maybe_download_contract('eosio.token')
        maybe_download_contract('eosio.msig')
        maybe_download_contract('eosio.wrap')
        maybe_download_contract('eosio', local_name='eosio.system')
        maybe_download_contract('telos.decide')

        cleos.wait_blocks(1)
        cleos.boot_sequence(
            contracts=download_location)

        yield cleos

    finally:
        try:
            vtestnet.stop()

        except docker.errors.NotFound:
            ...