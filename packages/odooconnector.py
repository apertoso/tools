# -*- coding: utf-8 -*-
import argparse

import odoorpc


def get_parser(parents=None):
    if parents is None:
        parents = []
    parser = argparse.ArgumentParser(parents=parents, add_help=False)

    parser.add_argument(
        '--debug',
        action='store_true',
        help="Debug mode")

    instance_group = parser.add_argument_group('Odoo connection options')
    instance_group.add_argument(
        '--login',
        help="Ask lUse this path as workdir instead of the current directory"
    )
    instance_group.add_argument(
        '--init',
        metavar="url",
        help="Init project with url containing odoo instance data")
    instance_group.add_argument(
        '--url',
        help="Url containing odoo instance data")

    return [parser, ]


class OdooConnector(object):
    def __init__(self):
        self.odoo = None

    def connect_saved(self, session_name):
        self.odoo = odoorpc.ODOO.load(session_name)

    def connect(self, username, password, database,
                host, protocol='jsonrpc', port='8069'):
        self.odoo = odoorpc.ODOO(
            host=host,
            protocol=protocol,
            port=port,
            timeout=120,
        )
        self.odoo.login(database, username, password)

    def save_login_session(self, session_name):
        self.odoo.save(session_name)

    @staticmethod
    def list():
        print ', '.join(odoorpc.ODOO.list())

    def _get_instance_data(self, instance_id):
        odoo_instance = self.odoo.env['odoo.instance'].browse(instance_id)
        # get dictionairy with data
        data = odoo_instance.get_instance_data()
        return data

    def find_instance_ids(self, extra_args=None, limit=False):
        if extra_args is None:
            extra_args = []

        domain = [
            ('state', '=', 'prod'),
            ('fqdn', '!=', False),
            ('ansible_group_ids', '!=', False)
        ]
        domain += extra_args
        instance_ids = self.odoo.env['odoo.instance'].search(domain,
                                                             limit=limit)

        return instance_ids

    def search_and_get_data(self, extra_args=None, limit=False):
        if extra_args is None:
            extra_args = []
        assert self.odoo is not None
        instance_ids = self.find_instance_ids(extra_args=extra_args,
                                              limit=limit)
        return [self._get_instance_data(item)
                for item in instance_ids
                ]
