#!/usr/bin/env bash

for config in ~/Workspace/tools/flake_cfg/*.cfg; do
    flake8 --config=$config $*
done
