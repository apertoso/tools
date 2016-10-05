# -*- coding: utf-8 -*-
import datetime
import os
import shutil
import subprocess
import tempfile
from StringIO import StringIO
from contextlib import contextmanager

import requests
import sh
from clint.textui import progress
from lxml import etree
from tzlocal import get_localzone


@contextmanager
def tempdir():
    tmpdir = tempfile.mkdtemp()
    try:
        yield tmpdir
    finally:
        shutil.rmtree(tmpdir)


def do_download_db(database_name=None, master_pwd=None, base_url=None,
                   backup_format='zip', filename=None, api='9.0',
                   hostname=None):
    if base_url is None:
        base_url = 'https://%s.odoo.apertoso.net' % database_name
    if base_url.endswith('/'):
        base_url = base_url.strip('/')
    if filename is None:
        ts = datetime.datetime.now(get_localzone()).strftime(
            '%Y%m%d-%H%M%S-%Z')
        filename = "%s_%s.%s" % (database_name, ts, backup_format)

    if api.startswith('9.0'):
        return do_download_db_v9(
            database_name=database_name,
            master_pwd=master_pwd, base_url=base_url,
            backup_format=backup_format,
            filename=filename)
    elif api == '8.0':
        return do_download_db_v8(
            database_name=database_name,
            master_pwd=master_pwd, base_url=base_url,
            backup_format=backup_format,
            filename=filename)
    elif api == 'ssh':
        server_name = hostname or \
            'openerp.production.{}.clients.apertoso.net'.format(database_name)
        return do_download_db_ssh(database_name=database_name,
                                  server=server_name,
                                  filename=filename)
    else:
        raise NotImplementedError("No support for api %s" % api)


def do_download_db_v8(database_name=None, master_pwd=None, base_url=None,
                      backup_format='zip', filename=None):
    # get the token:
    token_req = requests.get('%s/web/database/manager' % base_url,
                             params={'db': database_name},
                             allow_redirects=True)
    token_req.raise_for_status()
    parser = etree.XMLParser(recover=True)
    response = etree.parse(StringIO(token_req.content), parser)
    token = False
    for elem in response.xpath(
            "//form[@name='backup_db_form']/input[@name='token']"):
        token = elem.text

    params = {
        'token': token,
        'backup_pwd': master_pwd,
        'backup_db': database_name,
        'backup_format': backup_format
    }

    backup_request = requests.get('%s/web/database/backup' % base_url,
                                  params, stream=True, timeout=900, )

    if not backup_request.headers.get('Content-Type', '').startswith(
            'application/octet-stream;'):
        # get error text from content template is:
        # <div class="alert alert-danger">{{ error }}</div>
        print "Error:"
        print backup_request.content
        return 0

    total_size = int(backup_request.headers.get('content-length', 0))
    size = 0
    with open(filename, 'wb') as archive_file:
        for chunk in progress.mill(
                backup_request.iter_content(chunk_size=1024),
                label='downloading %s: ' % filename,
                expected_size=total_size):
            if not chunk:
                continue
            archive_file.write(chunk)
            size += len(chunk)
    return size


def do_download_db_v9(database_name=None, master_pwd=None, base_url=None,
                      backup_format='zip', filename=None):
    # get the cookie (creates new session_id):
    cookie_params = {
        'db': database_name,
    }
    cookie_req = requests.get('%s/web/login' % base_url, params=cookie_params,
                              allow_redirects=True)

    params = {
        'master_pwd': master_pwd,
        'name': database_name,
        'backup_format': backup_format
    }
    backup_request = requests.post('%s/web/database/backup' % base_url,
                                   params, stream=True, timeout=900,
                                   cookies=cookie_req.cookies)

    if not backup_request.headers.get('Content-Type', '').startswith(
            'application/octet-stream;'):

        # get error text from content template is:
        # <div class="alert alert-danger">{{ error }}</div>
        print "Error:"
        parser = etree.XMLParser(recover=True)
        response = etree.parse(StringIO(backup_request.content), parser)
        for elem in response.xpath("//div[@class='alert alert-danger']"):
            print elem.text
        return 0

    total_size = int(backup_request.headers.get('content-length', 0))
    size = 0
    with open(filename, 'wb') as file:
        for chunk in progress.mill(
                backup_request.iter_content(chunk_size=1024),
                label='downloading %s: ' % filename,
                expected_size=total_size):
            if not chunk:
                continue
            file.write(chunk)
            size += len(chunk)
    return size


def do_download_db_ssh(database_name=None, server=None,
                       filename=None):
    """
        Only suitable for our own hosting setups
    """
    filename_fullpath = os.path.abspath(filename)
    # get the DB:
    with tempdir() as temp_dir:
        # Get the DB
        print "Transferring database"
        remote_command = '. /etc/profile; ' \
                         'pg_dump --no-owner --no-privileges ' \
                         '--format=plain {}'.format(database_name)
        command = 'ssh root@{} "{}" > {}'.format(
            server, remote_command, os.path.join(temp_dir, 'dump.sql'))

        subprocess.check_call(command, shell=True)

        # Get the attachments
        print "Transferring attachments"
        filestore_localpath = os.path.join(temp_dir, 'filestore')
        sh.mkdir('-p', filestore_localpath)
        subprocess.check_call([
            'rsync', '-qr',
            "root@{}:/srv/odoo/filestore/{}/*".format(server,
                                                      database_name),
            filestore_localpath,
        ])

        print "zipping archive {} in workdir {}".format(filename_fullpath,
                                                        temp_dir)
        zip_command = " ( " \
                      " cd {} && " \
                      " 7z a -tzip -bd {} dump.sql filestore " \
                      " ) ".format(temp_dir, filename_fullpath)
        subprocess.check_call(zip_command, shell=True)


def do_test_archive(filename):
    sevenzip = sh.Command('7z')
    return sevenzip.t(filename)
