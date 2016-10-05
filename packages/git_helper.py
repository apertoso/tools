#!/usr/bin/env python
# -*- coding: utf-8 -*-
import logging
import os

import sh

"""
    Setup a development project structure
"""

_logger = logging.getLogger(__name__)


class GitRepo(object):
    def __init__(self, repo_dir, clone_url=None, branch_name=None):
        self.remote_names = {}
        self.remote_urls = {}
        self.clone_url = clone_url
        self.repo_dir = repo_dir
        self.branch_name = branch_name
        self.git = sh.git.bake('-C', repo_dir)

    ##############################
    # Bare repository management #
    ##############################
    def check_repo_exists(self):
        _logger.debug('Checking repo {}'.format(self.repo_dir))
        return self.repo_dir and \
            os.path.isdir(self.repo_dir) and \
            os.path.isfile(os.path.join(self.repo_dir, 'FETCH_HEAD'))

    def check_remote_tracking_branch_exists(self):
        remote_branch = 'remotes/{}/{}'.format(self.get_remote(),
                                               self.branch_name)
        _logger.debug(
            'Checking repo {} for remote {}'.format(
                self.repo_dir, remote_branch))
        return remote_branch in self.git.branch('-a')

    def clone_repo(self):
        _logger.debug(
            'Cloning repo {} into {}'.format(self.clone_url, self.repo_dir))
        sh.mkdir('-p', self.repo_dir)
        # init repo
        self.git.init('--bare', self.repo_dir)
        self.fetch()

    def fetch(self):
        _logger.debug('Fetching repo from {}'.format(self.clone_url))
        remote = self.get_remote()
        return self.git.fetch(remote)

    ##########################
    # git remotes management #
    ##########################
    def get_remote(self):
        remote = self.find_remote(self.clone_url)
        if not remote:
            remote = self.add_remote(self.clone_url)
        return remote

    def find_remote(self, url):
        if url in self.remote_urls:
            return self.remote_urls.get(url)
        # else:
        for remote in self.git.remote.show(_iter=True):
            remote = remote.rstrip()
            remote_url = self.git.remote('get-url', remote).rstrip()
            # add forward and backward mappings
            self.remote_names.update({remote: remote_url})
            self.remote_urls.update({remote_url: remote})
        return self.remote_urls.get(url)

    def add_remote(self, url):
        if 'apertoso' in url:
            remote_prefix = 'apertoso'
        elif 'github' in url:
            remote_prefix = 'github'
        elif 'gitlab' in url:
            remote_prefix = 'gitlab'
        else:
            remote_prefix = 'rem'

        suffix_nr = 0
        remote_name = '%s_%02d' % (remote_prefix, suffix_nr)
        while remote_name in self.remote_names:
            suffix_nr += 1
            remote_name = '%s_%02d' % (remote_prefix, suffix_nr)

        self.git.remote.add(remote_name, url)
        self.remote_names.update({remote_name: url})
        self.remote_urls.update({url: remote_name})
        return remote_name

    ###########################
    # Git worktree management #
    ###########################
    def worktree_check(self, worktree_dir, update_workdir=False):
        _logger.debug('Checking worktree in {} for branch {}'.format(
            worktree_dir, self.branch_name))
        remote = self.get_remote()
        self.worktree_prune()
        worktree_ok = (
            os.path.isdir(worktree_dir) and
            os.path.isfile(os.path.join(worktree_dir, '.git'))
        )
        if worktree_ok and update_workdir:
            return self.worktree_pull(worktree_dir, remote)
        if not worktree_ok:
            return self.worktree_add(worktree_dir, remote)

    def worktree_prune(self):
        _logger.debug('Pruning work trees')
        return self.git.worktree.prune()

    def worktree_pull(self, worktree_dir, remote):
        _logger.debug('Pulling worktree in {} branch {}'.format(
            worktree_dir, self.branch_name))
        remote_branch = "{}/{}".format(remote, self.branch_name)
        worktree_git = sh.git.bake('-C', worktree_dir)
        worktree_git.checkout('--detach', remote_branch)
        return worktree_git.pull(remote, self.branch_name)

    def worktree_add(self, worktree_dir, remote):
        _logger.debug('Adding worktree in {} branch {}'.format(
            worktree_dir, self.branch_name))
        remote_branch = "{}/{}".format(remote, self.branch_name)
        return self.git.worktree.add('--detach', worktree_dir, remote_branch)
