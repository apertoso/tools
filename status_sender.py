#!/usr/bin/env python
# -*- coding: utf-8 -*-
import argparse

import requests

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


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        '--success',
        action='store_true',
    )
    parser.add_argument(
        '--build-tag',
    )

    args = parser.parse_args()
    i = instancedata.InstanceData()
    url = i.get_export_url()
    build_tag = args.build_tag or i.get_ts_tag()

    data = {
        'docker_image': i.get_docker_image(),
        'docker_image_tag': i.get_docker_image_tag(),
        'build_status': 'success' if args.success else 'failed'
    }

    # Status for default tag:
    result = requests.post(url, data=data)
    result.raise_for_status()

    # On success, status for TS tag:
    if args.success and build_tag:
        data.update({'docker_image_tag': build_tag})
        result = requests.post(url, data=data)
        result.raise_for_status()

if __name__ == '__main__':
    main()
