#!/usr/bin/env python
# -*- coding: utf-8 -*-

import argparse
import json
import re
import sys
import warnings

from packages import odooconnector

odoo_ansible_field_mapping = [
    # odoo_field, ansible_field, default_value
    ('customer', 'customer', None),
    ('odoo_master_pwd', 'odoo_admin_pass', None),
    ('db_name', 'db_name', None),
    ('fqdn', 'fqdn', None),
    ('ip', 'ip', None),
    ('odoo_enterprise', 'odoo_enterprise', False),
    ('odoo_version', 'odoo_version', None),
    ('apt_package_ids', 'extra_apt_deps', None),
    ('pip_module_ids', 'extra_pip_requirements', None),
    ('openvz_production_cid', 'openvz_production_cid', None),
    ('ip_backup', 'ip_backup', None),
    ('openvz_backup_cid', 'openvz_backup_cid', None),
    ('psql_dbpass', 'psql_dbpass', None),
    ('odoo_dbfilter', 'odoo_dbfilter', None),
    ('configure_zabbix', 'configure_zabbix', None),
    ('sentry_enabled', 'sentry_enabled', None),
    ('sentry_client_dsn', 'sentry_client_dsn', None),
]


def branch_data_to_ansible_json(branch_data):
    git_url = branch_data.get('git_path_ssh')
    match = re.search('git@.+:(.+)/(.+)\.git', git_url)
    if not match:
        raise Exception()

    project = match.group(1)
    repository = match.group(2)
    return {
        "repo": repository,
        "server": branch_data.get('host'),
        "project": project,
        "branch": branch_data.get('branch'),
        "link": branch_data.get('enabled_modules'),
    }


def get_host_vars(instance_data):
    values = {}
    for odoo_field, ansible_field, default_value in odoo_ansible_field_mapping:
        field_value = instance_data.get(odoo_field, default_value)
        if field_value is not None:
            values.update({
                ansible_field: field_value
            })
    values.update({
        "extra_repo":
            [branch_data_to_ansible_json(b) for b in
             instance_data.get('branches').values()],

    })
    return values


def create_ansible_inventory(host_datas):
    ansible_inventory = {}
    ansible_host_vars = {}

    def add_host_to_groups(host, group):
        if group not in ansible_inventory:
            ansible_inventory.update({
                group: {
                    'hosts': [],
                    'vars': {},
                }
            })
        ansible_inventory.get(group).get('hosts').append(host)

    for host_data in host_datas:
        fqdn = host_data.get('fqdn', None)
        ansible_groups = host_data.get('ansible_group_ids', None)
        assert all((fqdn, ansible_groups))

        for group in ansible_groups:
            add_host_to_groups(fqdn, group)

        ansible_host_vars.update({
            fqdn: get_host_vars(host_data)
        })

    ansible_inventory.update({
        '_meta': {
            'hostvars': ansible_host_vars
        }
    })
    return ansible_inventory


def remove_null_values(dict_to_clean):
    dict_keys = []
    for key, value in dict_to_clean.iteritems():
        if type(value) is dict:
            dict_keys.append(key)
    for key in dict_keys:
        remove_null_values(dict_to_clean.get(key))

    none_keys = []
    for key, value in dict_to_clean.iteritems():
        if value is None:
            none_keys.append(key)
    for key in none_keys:
        del dict_to_clean[key]


def main():
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            import caffeine
            caffeine.on(display=False)
    except (ImportError, OSError):
        pass

    parser = argparse.ArgumentParser(
    )
    ansible_inventory_args = parser.add_argument_group(
        'Ansible Inventory args')
    ansible_inventory_args.add_argument(
        '--list',
        action='store_true',
        help="output a JSON encoded hash/dictionary of all the groups to be "
             "managed to stdout")
    ansible_inventory_args.add_argument(
        '--host',
        help="hash/dictionary of variables to make available to templates "
             "and playbooks")
    odoo_args = parser.add_argument_group(
        'Odoo connection args')
    odoo_args.add_argument(
        '--save',
        help='save the login details for further usage'
    )
    odoo_args.add_argument(
        '--load',
        default='apertoso',
        help='Load the login details from earlier save'
    )
    odoo_args.add_argument('--username')
    odoo_args.add_argument('--password')
    odoo_args.add_argument('--hostname')
    odoo_args.add_argument('--database')
    odoo_args.add_argument('--protocol', choices=('jsonrpc', 'jsonrpc+ssl'),
                           default='jsonrpc+ssl')
    odoo_args.add_argument('--port', default='8069')
    odoo_args.add_argument('--list-odoo', help='show saved sessions')
    args, options = parser.parse_known_args()

    if args.list_odoo:
        odooconnector.OdooConnector.list()
        sys.exit(1)

    odoo = odooconnector.OdooConnector()

    if all((args.username, args.password, args.database, args.hostname)):
        odoo.connect(args.username, args.password, args.database,
                     args.hostname,
                     args.protocol, args.port)

    if args.save:
        odoo.save_login_session(args.save)
    elif args.load:
        odoo.connect_saved(args.load)

    if args.host:
        instance_data = odoo.search_and_get_data([('fqdn', '=', args.host)],
                                                 limit=1)
        instance_data = instance_data[0]
        remove_null_values(instance_data)
        ansible_vars = get_host_vars(instance_data)
        print json.dumps(ansible_vars,
                         sort_keys=True,
                         indent=4,
                         separators=(',', ': '), )

    else:
        instance_datas = odoo.search_and_get_data()
        ansible_inventory = create_ansible_inventory(instance_datas)
        map(remove_null_values, instance_datas)
        print json.dumps(ansible_inventory,
                         sort_keys=True,
                         indent=4,
                         separators=(',', ': '), )


if __name__ == '__main__':
    main()
