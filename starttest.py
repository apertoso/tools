#!/usr/bin/env python
# -*- coding: utf-8 -*-
import argparse
import subprocess
import time
import json
import os
import etcd

if __name__ == '__main__' and __package__ is None:
    from os import sys, path

    sys.path.append(
        path.dirname(
            path.dirname(
                path.abspath(__file__)
            )
        )
    )
    from packages import instancedata


def container_exist(name):
    command = 'docker ps -aq -f name={}'.format(name)
    r = subprocess.check_output(command, shell=True)
    return len(r) > 0


def container_running(name):
    command = 'docker ps -q -f name={}'.format(name)
    r = subprocess.check_output(command, shell=True)
    return len(r) > 0


def container_kill(name):
    command = 'docker kill {}'.format(name)
    try:
        subprocess.check_call(command, shell=True)
    except subprocess.CalledProcessError:
        return False
    return True


def container_rm(name):
    command = 'docker rm {}'.format(name)
    try:
        subprocess.check_call(command, shell=True)
    except subprocess.CalledProcessError:
        return False
    return True


def get_exposed_port(name, internal_port, protocol):
    command = 'docker inspect {}'.format(name)
    o = subprocess.check_output(command, shell=True) or [{}]
    j = json.loads(o)[0]
    return j.get('NetworkSettings', {}).get('Ports', {}) \
            .get('{}/{}'.format(internal_port, protocol),
                 [{}])[0].get('HostPort')


def get_exposed_ports(container_name):
    command = 'docker inspect {}'.format(container_name)
    o = subprocess.check_output(command, shell=True) or [{}]
    j = json.loads(o)[0]
    return j.get('NetworkSettings', {}).get('Ports', {})


def publish_ports_etcd(etcd_ip, etcd_port, host, container_name):
    client = etcd.Client(host=etcd_ip, port=int(etcd_port))
    r = get_exposed_ports(container_name)
    for k, v in r.items():
        key = '/{}/{}/c{}'.format(host, container_name, k)
        value = '{}'.format(v[0].get('HostPort'))
        client.write(key, value)


def get_container_status(name):
    command = 'docker inspect {}'.format(name)
    try:
        o = subprocess.check_output(command, shell=True) or [{}]
        j = json.loads(o)[0]
        return j.get('State', {}).get('Status', {})
    except subprocess.CalledProcessError:
        return None


def clean_dangling_images():
    command = 'docker images -q -f dangling=true | xargs docker rmi'
    try:
        subprocess.check_call(command, shell=True)
    except subprocess.CalledProcessError:
        return False
    return True


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        '--url',
        help="Instance configuration URL"
    )
    parser.add_argument(
        '--keep_existing',
        action='store_true',
        help="Default: destroy existing containers")
    parser.add_argument(
        '--pgversion',
        default='9.3',
        help="Override default postgres version (9.3)"
    )

    args = parser.parse_args()
    instance_data = instancedata.InstanceData(
        init_url=args.url,
    )

    if args.url:
        instance_data.fetch(args.url)
        instance_data.save_to_data_file()
    else:
        print "No instance url given, can't continue"
        exit(1)

    if instance_data.get_data('state') == 'devel':
        print "This tool can't be used for development instances, exiting..."
        exit(1)

    instance_name_clean = ''.join(c for c in instance_data.get_name()
                                  if c.isalnum()).lower()
    init_url = args.url
    db_container_name = 'db_{}'.format(instance_data.get_name())
    db_user = instance_data.get_customer_name()
    db_name = instance_name_clean
    db_password = instance_data.get_db_password()
    odoo_db_filter = '^{}$'.format(instance_name_clean)
    backup_file = "/srv/{}.zip".format(instance_name_clean)
    odoo_container_name = 'odoo_{}'.format(instance_data.get_name())
    odoo_container = "%s:%s" % (instance_data.get_docker_image(),
                                instance_data.get_docker_image_tag())
    data_container_name = 'data_{}'.format(instance_data.get_name())

    # Clean dangling images
    print 'Cleaning dangling images (if any)...'
    clean_dangling_images()

    # Check if containers are already present and/or running
    for c in [odoo_container_name, db_container_name, data_container_name]:
        if container_exist(c):
            if args.keep_existing:
                print 'Container {} exists and keep_existing is enabled' \
                      .format(c)
                exit(1)
            if container_running(c):
                print 'Killing container:'
                container_kill(c)
            print 'Removing container:'
            container_rm(c)

    # Setup data_container
    command = 'docker create -v /srv --name {} debian:jessie /bin/true' \
              .format(data_container_name)
    subprocess.check_call(command, shell=True)

    # Setup project
    command = '''docker run --volumes-from {} -it --rm ''' \
              '''-e "DOCKER_CONF=$(cat $HOME/.docker/config.json)" ''' \
              '''-v /var/run/docker.sock:/var/run/docker.sock ''' \
              '''registry.gitlab.apertoso.be/apertoso/tools:latest ''' \
              '''/opt/tools/projectsetup --init {} --offline ''' \
              '''--work-dir /srv''' \
              .format(data_container_name, init_url)
    subprocess.check_call(command, shell=True)

    # Start database server
    print 'Starting database server'
    command = 'docker run -d --name {} -e POSTGRES_USER={} ' \
              '-e POSTGRES_PASSWORD={} -e POSTGRES_DB=postgres ' \
              'postgres:{}' \
              .format(db_container_name, db_user,
                      db_password, args.pgversion)
    subprocess.check_call(command, shell=True)

    # Check if DB is up & running, wait max 10 seconds
    # We need to check if the container is up first

    print 'Waiting for PostgreSQL container...'
    db_container_up = False
    for i in range(0, 60):
        if get_container_status(db_container_name) and \
               get_container_status(db_container_name) == 'running':
            db_container_up = True
            print 'Container started'
            break
        time.sleep(1)
    if not db_container_up:
        print 'Postgres container failed to start within time, exiting...'
        exit(1)

    print 'Check PostgreSQL status - is it up & running?'
    command = """docker exec -u postgres {} """ \
              """/bin/bash -c 'pg_ctl status -D $PGDATA'""" \
              .format(db_container_name)
    db_server_up = False
    for i in range(0, 60):
        r = None
        try:
            r = subprocess.check_output(command, shell=True)
        except subprocess.CalledProcessError:
            pass
        if r and 'pg_ctl: server is running (PID: 1)' in r:
            db_server_up = True
            print 'Server up & running'
            break
        time.sleep(1)

    if not db_server_up:
        print 'Postgres database failed to start within time, exiting...'
        exit(1)

    # Run dbbackup
    command = '''docker run --volumes-from {} -it --rm --link {}:{} ''' \
              '''-v /var/run/docker.sock:/var/run/docker.sock ''' \
              '''-e "DOCKER_CONF=$(cat $HOME/.docker/config.json)" ''' \
              '''registry.gitlab.apertoso.be/apertoso/tools:latest ''' \
              '''/opt/tools/dbbackup --filename {} --work-dir /srv''' \
              .format(data_container_name, db_container_name,
                      db_container_name, backup_file)
    subprocess.check_call(command, shell=True)

    # Run dbrestore
    command = '''docker run --volumes-from {} -it --rm ''' \
              '''--link {}:{} ''' \
              '''-v /var/run/docker.sock:/var/run/docker.sock ''' \
              '''-e "DOCKER_CONF=$(cat $HOME/.docker/config.json)" ''' \
              '''registry.gitlab.apertoso.be/apertoso/tools:latest ''' \
              '''/opt/tools/dbrestore --database={} --dbhost={} ''' \
              '''--dbuser={} --dbpassword={} --work-dir /srv --zip {} ''' \
              '''--docker --pgversion {} --nologinreset''' \
              .format(data_container_name,
                      db_container_name, db_container_name, db_name,
                      db_container_name, db_user, db_password, backup_file,
                      args.pgversion)
    subprocess.check_call(command, shell=True)

    # Cleanup the zip file
    command = 'docker run --volumes-from {} --rm debian:jessie rm {}' \
              .format(data_container_name, backup_file)
    subprocess.check_call(command, shell=True)

    # Run Odoo container
    odoo_addons_path = ['/opt/odoo/addons-extra']
    if instance_data.get_data('odoo_enterprise'):
        odoo_addons_path.append('/opt/odoo/odoo-enterprise')
    odoo_addons_path.append('/opt/odoo/odoo/addons')

    command = 'docker run --link {}:{} -d -P --name={} --volumes-from {} ' \
              '{} --db_host={} --db_user={} ' \
              '--db_password={} --database={} --db-filter={} ' \
              '--data-dir=/srv/data ' \
              '--addons-path={}' \
              .format(db_container_name, db_container_name,
                      odoo_container_name, data_container_name,
                      odoo_container, db_container_name, db_user, db_password,
                      db_name, odoo_db_filter, ','.join(odoo_addons_path))
    subprocess.check_call(command, shell=True)

    # publish_ports_etcd('164.132.193.105', '2379',
    #                   os.environ.get('DOCKER_MACHINE_NAME'),
    #                   odoo_container_name)

    print "*******************************************************************"
    print "Instance {} up & running on:\nhttp://{}:{}" \
          .format(instance_data.get_name(),
                  os.environ.get('DOCKER_MACHINE_NAME'),
                  get_exposed_port(odoo_container_name, '8069', 'tcp'))
    print "*******************************************************************"

if __name__ == '__main__':
    main()
