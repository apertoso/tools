#!/usr/bin/env python
# -*- coding: utf-8 -*-
import datetime
import logging
import os
import re
import stat
import subprocess
import sys
import uuid
from contextlib import contextmanager

import netifaces
import psycopg2
import sh

_logger = logging.getLogger(__name__)

MODULE_TS_PREFIX = 'apertoso.module_timestamp_'


@contextmanager
def get_cursor(db_connection):
    with db_connection as conn:
        with conn.cursor() as cr:
            try:
                yield cr
            except Exception:
                conn.rollback()
                raise
            else:
                conn.commit()


def get_db_host():
    # first try to look for a loopback alias addr
    loopback_addr = get_lo_alias_addr()
    if loopback_addr:
        return loopback_addr

    # if we did not find any IP on the loopback if, find the
    # interface of the default gateway and use that.
    try:
        default_if = netifaces.gateways().get('default', {}).values()[0][1]
        if_addr = netifaces.ifaddresses(default_if)[netifaces.AF_INET][0].get(
            'addr')
        return if_addr
    except KeyError:
        raise Exception('Cannot find DB address for the current host')


def get_lo_alias_addr():
    # check all interfaces an try to find one with address 127.0.0.1
    # If that interface has another address, that's the one we need.
    ifname_loopback = None
    for interface in netifaces.interfaces():
        ip_addresses = []
        interface_addresses = netifaces.ifaddresses(interface)
        if netifaces.AF_INET not in interface_addresses:
            continue
        for address_data in interface_addresses[netifaces.AF_INET]:
            if address_data.get('addr') == '127.0.0.1':
                ifname_loopback = interface
            elif address_data.get('addr'):
                ip_addresses.append(address_data.get('addr'))
        if interface == ifname_loopback and ip_addresses:
            return ip_addresses[0]


class DBTool(object):
    def __init__(self, target_db, addons_dir, data_dir, pgversion=None,
                 db_host='localhost', db_user=None, db_password=None):
        self.pgversion = pgversion
        self.target_db = target_db
        self.db_host = db_host
        self.db_user = db_user
        self.db_password = db_password
        self.data_dir = data_dir
        self.addons_dir = addons_dir
        self.odoo_user = 'odoo'
        self.odoo_group = 'odoo'
        self.timestamp = datetime.datetime.utcnow()
        self.conn_postgres = psycopg2.connect(dbname='postgres',
                                              user=self.db_user,
                                              password=self.db_password,
                                              host=self.db_host)
        self.actual_module_timestamps = {}
        self.conn = False

    def check_target_db_exists(self):
        """
        Check if the db named self.target_db exists and connect to the DB
        :return:
        """
        with get_cursor(self.conn_postgres) as cr:
            cr.execute('SELECT 1 FROM pg_database WHERE datname=%s',
                       (self.target_db,))
            result = bool(cr.fetchone())
        if result:
            self.conn = psycopg2.connect(dbname=self.target_db,
                                         user=self.db_user,
                                         password=self.db_password,
                                         host=self.db_host)
        return result

    def check_data_dir_exists(self):
        """
        Check if the datadir contains attachments
        :return:
        """
        attachments_dir = os.path.join(self.data_dir,
                                       'filestore',
                                       self.target_db)
        return os.path.isdir(attachments_dir)

    def check_valid_odoo_db(self):
        """
        Check if the our db conn is a valid odoo DB
        :return:
        """
        found_odoo_db = False
        with get_cursor(self.conn) as cr:
            try:
                cr.execute('SELECT 1 FROM res_users WHERE id=1')
                found_odoo_db = bool(cr.fetchone())
            except psycopg2.ProgrammingError:
                pass
        return found_odoo_db

    def createdb_if_not_exists(self):
        if self.check_target_db_exists():
            return
        # else
        # there is no way to pass the table name as a parameter :(
        with self.conn_postgres as conn_postgres:
            with conn_postgres.cursor() as cr:
                conn_postgres.set_isolation_level(0)
                cr.execute('CREATE DATABASE ' + self.target_db)
                conn_postgres.set_isolation_level(1)
        self.conn = psycopg2.connect(dbname=self.target_db,
                                     host=self.db_host,
                                     user=self.db_user,
                                     password=self.db_password)

    def do_drop_db_if_exists(self):
        with self.conn_postgres as conn_postgres:
            with conn_postgres.cursor() as cr:
                conn_postgres.set_isolation_level(0)
                cr.execute(
                    'SELECT pg_terminate_backend(pid) FROM pg_stat_activity '
                    'WHERE datname=%s', (self.target_db,)
                )
                cr.execute(
                    'DROP DATABASE IF EXISTS "{}"'.format(self.target_db)
                )
                conn_postgres.set_isolation_level(1)

    def restore_db_slow(self, zipfile):
        # This works but is about 20% slower somehow
        unzip = sh.unzip.bake('-c', '-qq')
        psql = sh.psql.bake('--quiet')
        psql(
            unzip(zipfile, 'dump.sql', _piped=True),
            self.target_db, _out=sys.stdout
        )

    # unzip actually fails to extract some archives on mac :(
    # nice part, with the -q option it does not even print an error
    # $ unzip -c mooddesign_20160812-093324-CEST.zip dump.sql
    # Archive:  mooddesign_20160812-093324-CEST.zip
    # skipping: dump.sql                need PK compat. v4.5 (can do v2.1)
    def restore_db_unzip(self, zipfile):
        command = "set -o pipefail; " \
                  "unzip -c -qq {} dump.sql | " \
                  "psql --file=- --quiet {} " \
                  "> /dev/null".format(zipfile, self.target_db)
        subprocess.check_call(command, shell=True)

    def restore_db(self, zipfile):
        command = "set -o pipefail; " \
                  "7z x -so {} dump.sql | " \
                  "psql --file=- --quiet {} " \
                  "> /dev/null".format(zipfile, self.target_db)
        subprocess.check_call(command, shell=True)

    # For docker, we need bash (sh by default) and full path to 7z
    # Also, we need to go full blown docker!
    # Instead of using the "psql" command locally (which isn't here)

    def restore_db_docker(self, zipfile):
        command = ''' /usr/bin/7z x -so {} dump.sql | ''' \
                  ''' docker run -i --rm --link {}:{} postgres:{} ''' \
                  ''' /bin/bash -c 'echo "{}:5432:*:{}:{}" ''' \
                  ''' > ~/.pgpass; chmod 600 ~/.pgpass; ''' \
                  ''' /usr/lib/postgresql/{}/bin/psql ''' \
                  ''' -q -h {} -U {} {} > /dev/null' ''' \
                  .format(zipfile, self.db_host, self.db_host, self.pgversion,
                          self.db_host, self.db_user, self.db_password,
                          self.pgversion, self.db_host, self.db_user,
                          self.target_db
                          )
        subprocess.check_call(command, shell=True)

    def restore_attachments(self, zipfile, docker=False):
        unzip = sh.unzip.bake('-x', '-qq', '-n')
        restore_folder = os.path.join(self.data_dir,
                                      'filestore',
                                      self.target_db)
        sh.mkdir('-p', restore_folder)
        # unzip will place files are in <datadir>/filestore/<dbname>/filestore,
        # we create a symlink to <datadir>/filestore/<dbname> so they wind up
        # in the right spot
        restore_folder_faulty = os.path.join(restore_folder, 'filestore')
        sh.ln('-s', restore_folder, restore_folder_faulty)
        unzip(zipfile, 'filestore/*', '-d', restore_folder)
        # cleanup the symlink
        sh.rm(restore_folder_faulty)
        # When running in docker mode, change permissions
        if docker:
            sh.chown('-R', '999:999', self.data_dir)

    def set_test_logins(self):
        """resetting user passwords to 'admin'"""
        with get_cursor(self.conn) as cr:
            cr.execute("UPDATE res_users SET password='admin'")
            cr.execute("UPDATE res_users SET login = 'admin' WHERE id = 1")

    def set_db_uuid(self):
        """updating database uuid"""
        new_uuid = uuid.uuid1()
        with get_cursor(self.conn) as cr:
            cr.execute(
                "UPDATE ir_config_parameter SET value = %s WHERE KEY = "
                "'database.uuid'",
                (str(new_uuid),)
            )
            cr.execute(
                "DELETE FROM ir_config_parameter WHERE key IN "
                "('database.enterprise_code',"
                " 'database.expiration_date', "
                " 'database.expiration_reason');"
            )

    def set_aeroo_localhost(self):
        """changing aeroo report server to localhost"""
        with get_cursor(self.conn) as cr:
            for key, value in [
                ('localhost', 'aeroo.docs_host'),
                ('8989', 'aeroo.docs_port'),
                ('simple', 'aeroo.docs_auth_type'),
                ('anonymous', 'aeroo.docs_username'),
                ('anonymous', 'aeroo.docs_password'),
            ]:
                cr.execute(
                    'UPDATE ir_config_parameter SET value=%s WHERE key=%s',
                    (key, value,)
                )

    def set_ir_crons_disabled(self):
        """disabling ir.cron automated tasks"""
        with get_cursor(self.conn) as cr:
            for cron_name in (
                    'Email Queue Manager',
                    'Auto-vacuum internal data',
                    'Garbage Collect Mail Attachments',
                    'Fetchmail Service',
            ):
                cr.execute(
                    'UPDATE ir_cron SET active=FALSE WHERE name=%s',
                    (cron_name,)
                )

    def set_mail_debugmail(self):
        with get_cursor(self.conn) as cr:
            cr.execute("""
                UPDATE ir_mail_server
                SET
                  name            = CONCAT('debugmail-', name),
                  smtp_host       = 'debugmail.io',
                  smtp_port       = '9025',
                  smtp_user       = 'info@apertoso.be',
                  smtp_pass       = '8e9352a0-1070-11e6-acb8-b387215ae1ba',
                  smtp_encryption = 'none',
                  smtp_debug      = TRUE;
            """)

    def get_module_timestamps(self, modules=None):
        if not modules:
            modules = os.listdir(self.addons_dir)
        self.actual_module_timestamps = {}
        for module in modules:
            module_path = os.path.join(self.addons_dir, module)
            mtime = self.check_module_timestamps(module_path)
            self.actual_module_timestamps.update({module: mtime})
        return self.actual_module_timestamps

    def check_module_timestamps(self, module_path=False, mtime=0):
        extensions = ('.py', '.xml', '.csv')
        "Walk the tree of a module to find the last updated file"
        for file in os.listdir(module_path):
            file_path = os.path.join(module_path, file)
            statinfo = os.stat(file_path)
            file_mtime = 0
            if stat.S_ISDIR(statinfo.st_mode):
                file_mtime = self.check_module_timestamps(file_path)
            elif stat.S_ISREG(statinfo.st_mode):
                if any(file.endswith(ex) for ex in extensions):
                    file_mtime = statinfo.st_mtime
            else:
                raise Exception(
                    'Unknown file mode in module path %s' % file_path)
            if file_mtime > mtime:
                mtime = file_mtime
        return mtime

    def read_module_timestamps_from_db(self):
        results = {}
        with get_cursor(self.conn) as cr:
            cr.execute(
                "SELECT key, value FROM ir_config_parameter WHERE key "
                "LIKE %s",
                (MODULE_TS_PREFIX + '%',))
            for key, value in cr.fetchall():
                try:
                    module_name = key.replace(MODULE_TS_PREFIX, '')
                    timestamp = float(value)
                    results.update({module_name: timestamp})
                except ValueError:
                    _logger.exception(
                        'Exception while reading timestamps from DB')
            return results

    def save_actual_module_timestamps_in_db(self):
        if not len(self.actual_module_timestamps):
            self.get_module_timestamps()
        self.save_module_timestamps_in_db(self.actual_module_timestamps)

    def save_module_timestamps_in_db(self, module_timestamps):
        if not len(module_timestamps):
            _logger.warning(
                'No timestamp data, not saving anything')
            return
        db_values = dict(
            [
                (MODULE_TS_PREFIX + module_name, timestamp) for
                module_name, timestamp in
                module_timestamps.iteritems()
                ])
        with get_cursor(self.conn) as cr:
            clean_qry = "DELETE FROM ir_config_parameter WHERE key IN %s"
            clean_qry_values = (tuple(db_values.keys()),)
            _logger.debug("Cleaning up old timestamps in DB")
            _logger.debug(cr.mogrify(clean_qry, clean_qry_values))
            cr.execute(clean_qry, clean_qry_values)

            qry = (
                "INSERT INTO ir_config_parameter "
                "(create_uid, create_date, write_uid, write_date, key, value) "
                "VALUES (%(create_uid)s, %(create_date)s, %(write_uid)s, "
                "%(write_date)s, %(module_key)s, %(ts_value)s)"
            )
            for module_key, timestamp in db_values.iteritems():
                values = {
                    'create_uid': 1,
                    'create_date': self.timestamp,
                    'write_uid': 1,
                    'write_date': self.timestamp,
                    'module_key': module_key,
                    'ts_value': '{}'.format(timestamp),
                }
                _logger.debug("Writing values in DB")
                _logger.debug(cr.mogrify(qry, values))
                cr.execute(qry, values)

    def find_modules_to_update(self, modules):
        if not len(self.actual_module_timestamps):
            self.get_module_timestamps(modules)
        db_timestamps = self.read_module_timestamps_from_db()
        modules_to_update = []
        for module in modules:
            actual_ts = self.actual_module_timestamps.get(module, 0)
            database_ts = db_timestamps.get(module, -1)
            if actual_ts > database_ts:
                modules_to_update.append(module)
        return modules_to_update
