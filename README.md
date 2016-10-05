# A collection of scripts aiding in Apertoso development workflow #

***These scripts bluntly assume that this repo, and the scripts are
located in*** `~/Workspace/tools`

## Contents: ##
* flake_run.sh: run flake tests

## Requirements: ##
* postgres.app, see http://postgresapp.com/
* p7zip  ( brew install p7zip )
* git 2.9.3+ (brew install git)
* newer bash ( brew install bash + chsh ) for auto completion

## INSTALL: ##

* Make sure you have a directory "Workspace" in your home dir
* in Workspace, clone this repo
* use this code to adjust your path:

```
CAT << EOF >> ~/.bash_profile

# Apertoso tools
export PATH=\$PATH:~/Workspace/tools:/Applications/Postgres.app/Contents/Versions/latest/bin
EOF

cd ~/Workspace/tools
sudo pip install -r requirements.txt

```

* If you want to use bash completion, check here: https://github.com/kislyuk/argcomplete#global-completion

## Docker tooling ##

* create empty project dir:
```
✔ ~/Workspace/Projects
16:26 $ mkdir bgs_docker
```
* create project instance in odoo and copy URL
* run projectsetup
```
✔ ~/Workspace/Projects/bgs_docker
16:44 $ projectsetup --init http://apertoso.odoo.apertoso.net:8069/customer_docker/blueglobesports_test/aGFv7pXjJaygoZCDZ00vstFF/devel
```
* run dbbackup
```
✔ ~/Workspace/Projects/bgs_docker
17:55 $ dbbackup
Downloading database blueglobesports from https://www.blueglobesports.be/ with 8.0 api
downloading blueglobesports_20160810-180202-CEST.zip:    457081/0
✔ ~/Workspace/Projects/bgs_docker
```
* run dbrestore
 ```
 ✔ ~/Workspace/Projects/bgs_docker
19:07 $ dbrestore --zip blueglobesports_20160810-180202-CEST.zip
No handlers could be found for logger "ProjectSetup"
Restoring attachments for database blueglobesports from zip file
Resetting login passwords to 'admin'
Disabling ir_crons
Resetting db uuid
Resetting Aeroo config to localhost
Resetting mail config to debugmail.io
```
* start odoo docker
```
09:31 $ runserver
Starting docker with args:
/usr/local/bin/docker run -it --publish=8069:8069 --rm --name=blueglobesports_test --volume=/Users/josdg/Workspace/Projects/bgs_docker/data:/data --volume=/Users/josdg/Workspace/Projects/bgs_docker/addons-extra:/opt/odoo/addons-extra --volume=/Users/josdg/Workspace/Projects/bgs_docker/repos:/opt/odoo/repos bgs-docker --db_host=192.168.5.177 --db_user=josdg --database=blueglobesports --db-filter=^blueglobesports$ --data-dir=/data --addons-path=/opt/odoo/addons-extra,/opt/odoo/odoo/addons
2016-08-10 19:09:58,069 1 INFO ? openerp: OpenERP version 8.0
2016-08-10 19:09:58,069 1 INFO ? openerp: addons paths: ['/data/addons/8.0', u'/opt/odoo/addons-extra', u'/opt/odoo/odoo/addons', '/opt/odoo/odoo/openerp/addons']
```
