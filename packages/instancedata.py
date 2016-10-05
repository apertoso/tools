#!/usr/bin/env python
# -*- coding: utf-8 -*-
import argparse
import json
import logging
import os

import requests

"""
    Setup a development project structure
"""

_logger = logging.getLogger(__name__)

INSTANCE_DATA_FILENAME = '.instance_data.json'


class InstanceDataNotFoundException(Exception):
    pass


def find_workdir(path=None, raise_if_not_found=True):
    if path is None:
        path = os.getcwd()
    instance_file = os.path.join(path, INSTANCE_DATA_FILENAME)
    if os.path.isfile(instance_file):
        return os.path.abspath(path)
    else:
        parent_path = os.path.split(path)[0]
        if not parent_path or parent_path == '/':
            if raise_if_not_found:
                raise InstanceDataNotFoundException(
                    'Error: instance_data not found in path')
            else:
                return None
        else:
            return find_workdir(parent_path,
                                raise_if_not_found=raise_if_not_found)


def get_parser(parents=None):
    if parents is None:
        parents = []
    parser = argparse.ArgumentParser(parents=parents, add_help=False)

    parser.add_argument(
        '--debug',
        action='store_true',
        help="Debug mode")

    instance_group = parser.add_argument_group('Project instance data options')
    instance_group.add_argument(
        '--work-dir',
        default='.',
        help="Use this path as workdir instead of the current directory"
    )
    instance_group.add_argument(
        '--init',
        metavar="url",
        help="Init project with url containing odoo instance data")
    instance_group.add_argument(
        '--url',
        help="Url containing odoo instance data")

    return [parser, ]


class InstanceData(object):
    def __init__(self, workdir=None, init_url=None, url=None):
        self.data = {}
        self.branches = []
        if init_url:
            self.workdir = os.path.abspath(workdir or os.getcwd())
            self.data_file = os.path.join(self.workdir, INSTANCE_DATA_FILENAME)
            self.init(init_url)
        elif url:
            self.fetch(url)
            self.workdir = find_workdir(workdir, raise_if_not_found=False)
        else:
            self.workdir = find_workdir(workdir)
            self.data_file = os.path.join(self.workdir, INSTANCE_DATA_FILENAME)
            self.load_from_data_file()

    def get_work_dir(self):
        return self.workdir

    def init(self, url):
        _logger.debug('Initializing new project')
        self.fetch(url)
        self.save_to_data_file()

    def fetch(self, url):
        _logger.debug('Fetching data from url {}'.format(url))
        request = requests.get(url)
        # raise error if not status 200
        request.raise_for_status()
        json_data = request.json()
        self.data = json_data
        self.branches = self.data.get('branches').values()

    def get_data(self, key, default=None):
        return self.data.get(key, default)

    def get_ts_tag(self):
        ret = self.data.get('ts_tag', None)
        return ret

    def get_export_url(self):
        ret = self.data.get('export_url', None)
        assert ret is not None
        return ret

    def get_docker_image(self):
        if self.data.get('state', 'devel') == 'devel':
            ret = (self.data.get('docker_image_id', None) or
                   self.data.get('db_name', None))
        else:
            ret = self.data.get('docker_image_id', None)
        assert ret is not None
        return ret

    def get_docker_image_tag(self):
        ret = self.data.get('docker_image_tag_id', 'latest')
        return ret

    def get_parent_docker_image(self):
        ret = self.data.get('parent_docker_image_id', None)
        assert ret is not None
        return ret

    def get_parent_docker_image_tag(self):
        ret = self.data.get('parent_docker_image_tag_id', 'latest')
        return ret

    def get_db_name(self):
        ret = self.data.get('db_name', None)
        assert ret is not None
        return ret

    def get_db_password(self):
        ret = self.data.get('psql_dbpass', None)
        assert ret is not None
        return ret

    def get_odoo_dbfilter(self):
        ret = self.data.get('odoo_dbfilter', None)
        assert ret is not None
        return ret

    def get_customer_name(self):
        ret = self.data.get('customer', None)
        assert ret is not None
        return ret

    def get_name(self):
        ret = self.data.get('name', None)
        assert ret is not None
        return ret.replace(' ', '_').replace('.', '_')

    def refresh_from_saved_url(self):
        return self.fetch(self.data.get('export_url'))

    def get_modules(self):
        ret = []
        for branch in self.branches:
            ret.extend(branch.get('enabled_modules'))
        return ret

    def load_from_data_file(self):
        _logger.debug('loading data from file {}'.format(self.data_file))
        with open(self.data_file, 'r') as file_stream:
            json_data = json.load(file_stream)
        self.data = json_data
        self.branches = self.data.get('branches').values()

    def save_key_to_data_file(self, key, value):
        _logger.debug('adding key/value pair to file {}'.format(
                      self.data_file))
        self.data.update({key: value})
        with open(self.data_file, 'w') as file_stream:
            json.dump(self.data,
                      file_stream,
                      sort_keys=True,
                      indent=4,
                      separators=(',', ': '), )

    def save_to_data_file(self):
        _logger.debug('writing data to file {}'.format(self.data_file))
        with open(self.data_file, 'w') as file_stream:
            json.dump(self.data,
                      file_stream,
                      sort_keys=True,
                      indent=4,
                      separators=(',', ': '), )
