#!/usr/bin/env python
# -*- coding: utf-8 -*-
import logging
import os
import stat
import subprocess

import sh

from git_helper import GitRepo

"""
    Setup a development project structure
"""

_logger = logging.getLogger(__name__)

# courtesy https://github.com/sbidoul
# https://github.com/acsone/setuptools-odoo/blob/master/setuptools_odoo
# /external_dependencies.py
EXTERNAL_DEPENDENCIES_MAP = {
    'python': {
        'Asterisk': 'py-Asterisk',
        'coda': 'pycoda',
        'cups': 'pycups',
        'dateutil': 'python-dateutil',
        'ldap': 'python-ldap',
        'serial': 'pyserial',
        'Crypto.Cipher.DES3': 'pycrypto',
        'usb.core': 'pyusb',
        'aeroolib':
            'git+https://github.com/aeroo/aeroolib.git#egg=aeroolib',
        'bs4': 'beautifulsoup4',
    },
    'bin': {
        '/usr/bin/java': 'default-jre-headless',
        '/usr/sbin/cupsctl': 'cups-client',
    },
}

ODOO_BRANCH = {
    'gitproject': 'odoo',
    'git_path_ssh': 'git@github.com:odoo/odoo.git',
}
ODOO_ENTERPRISE_BRANCH = {
    'gitproject': 'odoo-enterprise',
    'git_path_ssh': 'git@github.com:apertoso/odoo-enterprise.git',
}

PYCHARM_DEBUG_EGG = "/Applications/PyCharm.app/Contents/" \
                    "debug-eggs/pycharm-debug.egg"

INSTANCE_DATA_FILENAME = '.instance_data.json'


class DockerRunException(Exception):
    pass


def run_command(command):
    return_value = subprocess.call(command)
    if return_value != 0:
        raise DockerRunException(
            'Command "%s" exited with return value %s != 0' % (
                ' '.join(command), return_value))


def build_docker_image(workdir_path, image_name, tag, pull=True):
    docker_build = ['docker', 'build', ]
    if pull:
        docker_build += ['--pull', '--no-cache', ]
    run_command(
        docker_build + ['-t', '%s:%s' % (image_name, tag),
                        workdir_path])


def pull_docker_image(image_name, tag):
    run_command(
        ['docker', 'pull', '%s:%s' % (image_name, tag)]
    )


def tag_docker_image(image_name, tag, newtag):
    run_command(
        ['docker', 'tag',
         '%s:%s' % (image_name, tag),
         '%s:%s' % (image_name, newtag)])


def push_docker_image(image_name, tag):
    run_command(
        ['docker', 'push', '%s:%s' % (image_name, tag)])


def check_docker_image(image_name, tag):
    image_id = sh.docker.images('--quiet', '%s:%s' % (image_name, tag))
    return image_id or None


def parse_openerp_module(module_path):
    """
    :param module_path:
    :return:
        tuple with (pip dependencies, apt dependencies)
    """
    stat_info = os.stat(module_path)

    if not stat.S_ISDIR(stat_info.st_mode):
        return [], []
    # else:
    module_files = os.listdir(module_path)
    if '__openerp__.py' not in module_files:
        return [], []
    # else
    # found odoo module
    odoo_module_file_name = os.path.join(module_path, '__openerp__.py')
    result = {}
    with open(odoo_module_file_name, 'r') as odoo_module_file:
        odoo_module_info = eval(odoo_module_file.read())
        external_dependencies = odoo_module_info.get(
            'external_dependencies',
            {})
        for key in ('bin', 'python'):
            dependencies = external_dependencies.get(key, [])
            dependencies_mapped = [
                EXTERNAL_DEPENDENCIES_MAP.get(key, {}).get(
                    item, item)
                for item in dependencies
                ]
            result.update({key: dependencies_mapped})
    return result.get('python', []), result.get('bin', [])


def check_folders(*directories):
    mkdir = sh.mkdir.bake('-p')
    for directory in directories:
        if not os.path.isdir(directory):
            mkdir(directory)


def get_odoo_branches(instance_data):
    odoo_branches = list()
    odoo_branches.append(
        dict(ODOO_BRANCH.items() +
             [('branch', instance_data.get_data('odoo_version'))]
             )
    )
    if instance_data.get_data('odoo_enterprise'):
        odoo_branches.append(
            dict(ODOO_ENTERPRISE_BRANCH.items() +
                 [('branch', instance_data.get_data('odoo_version'))]
                 )
        )
    return odoo_branches


def fetch_odoo(instance_data, baredir, update_repo=False):
    odoo_branches = get_odoo_branches(instance_data)
    return fetch_repos(odoo_branches, baredir,
                       update_repo=update_repo)


def checkout_odoo(instance_data, baredir, reposdir, update_workdir=False):
    odoo_branches = get_odoo_branches(instance_data)
    return checkout_workdirs(odoo_branches, baredir, reposdir,
                             update_workdir=update_workdir)


def fetch_repos(branches, baredir, update_repo=False):
    for branch in branches:
        _logger.debug('Fetching repos for branch {}'.format(
            branch.get('gitproject')))
        repo_dir = os.path.join(baredir,
                                '{}.git'.format(branch.get('gitproject')))
        git = GitRepo(
            repo_dir=repo_dir,
            clone_url=branch.get('git_path_ssh'),
            branch_name=branch.get('branch')
        )
        if not git.check_repo_exists():
            git.clone_repo()
        elif update_repo or not git.check_remote_tracking_branch_exists():
            git.fetch()


def checkout_workdirs(branches, baredir, reposdir, update_workdir=False):
    for branch in branches:
        _logger.debug('Checking out workdirs for branch {}'.format(
            branch.get('gitproject')))
        repo_dir = os.path.join(baredir,
                                '{}.git'.format(branch.get('gitproject')))
        work_dir = os.path.join(reposdir, branch.get('gitproject'))
        git = GitRepo(
            repo_dir=repo_dir,
            clone_url=branch.get('git_path_ssh'),
            branch_name=branch.get('branch')
        )
        git.worktree_check(work_dir, update_workdir=update_workdir)


def link_addons(branches, addonsdir, reposdir):
    for branch in branches:
        _logger.debug('Linking addons for branch {}'.format(
            branch.get('gitproject')))
        for addon in branch.get('enabled_modules'):
            addon_path = os.path.join(
                reposdir,
                branch.get('gitproject'),
                addon,
            )
            link_destination = os.path.join(
                addonsdir,
                addon
            )
            if os.path.islink(link_destination):
                continue
            # use relative path for symlink, so it keeps working in
            # directories mounted elsewhere
            relative_source = os.path.relpath(addon_path,
                                              addonsdir)
            sh.ln('-s', relative_source, link_destination)


def copy_addons(branches, addonsdir, reposdir):
    for branch in branches:
        _logger.debug('copying addons for branch {}'.format(
            branch.get('gitproject')))
        for addon in branch.get('enabled_modules'):
            addon_path = os.path.join(
                reposdir,
                branch.get('gitproject'),
                addon)
            sh.cp('-r', addon_path, addonsdir)


def get_extra_deps_pip(module_list):
    statements = []
    statements.append('RUN set -x && ')
    statements.append('    pip install ')
    for module in module_list:
        statements.append('        {} '.format(module))

    return '\\\n'.join(statements)


def get_extra_deps_apt(module_list):
    statements = []
    statements.append('RUN set -x && ')
    statements.append('    apt-get install -y ')
    for module in module_list:
        statements.append('        {} '.format(module))

    return '\\\n'.join(statements)


def write_docker_file(workdir_path, instance_data, devel_mode=False):
    pycharm_debug_egg = False
    if os.path.isfile(PYCHARM_DEBUG_EGG):
        sh.cp(PYCHARM_DEBUG_EGG, workdir_path)
        pycharm_debug_egg = os.path.basename(PYCHARM_DEBUG_EGG)
    elif devel_mode:
        print "Warning: Pycharm debug egg not found at {}, " \
              "debugging with pycharm will not work".format(PYCHARM_DEBUG_EGG)

    parent_docker_image = instance_data.get_parent_docker_image()
    parent_docker_image_tag = instance_data.get_parent_docker_image_tag()
    apt_packages = instance_data.get_data('apt_package_ids')
    pip_modules = instance_data.get_data('pip_module_ids')

    with open(os.path.join(workdir_path, 'Dockerfile'), 'w') as dockerfile:
        dockerfile.write(
            '# This file will be overwritten on the next ProjectSetup run \n')
        if parent_docker_image_tag:
            dockerfile.write('FROM {}:{}\n\n'.format(parent_docker_image,
                                                     parent_docker_image_tag))
        else:
            dockerfile.write('FROM {}\n\n'.format(parent_docker_image))

        dockerfile.write('USER root\n'.format(parent_docker_image))
        if apt_packages:
            dockerfile.write('{}\n'.format(get_extra_deps_apt(apt_packages)))

        if pip_modules:
            dockerfile.write('{}\n'.format(get_extra_deps_pip(pip_modules)))

        # add pycharm debug egg and debug start script
        if pycharm_debug_egg:
            dockerfile.write('ADD {} /opt/odoo/odoo/\n'.format(
                pycharm_debug_egg)
            )
            dockerfile.write(
                'RUN set -x; easy_install /opt/odoo/odoo/{}\n'.format(
                    pycharm_debug_egg)
            )

        dockerfile.write('USER odoo\n'.format(parent_docker_image))

        if not devel_mode:
            dockerfile.write('ADD addons-extra /opt/odoo/addons-extra\n')

    with open(os.path.join(workdir_path, '.dockerignore'),
              'w') as docker_ignore_file:
        docker_ignore_file.write(
            '# This file will be overwritten on the next ProjectSetup run\n')
        for line in [
            '*.zip', '*.dump', 'repos',
            'odoo', 'data', 'odoo-enterprise',
        ]:
            docker_ignore_file.write('{}\n'.format(line))
