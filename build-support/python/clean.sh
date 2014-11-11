#!/bin/bash

PANTS_BASE=$(dirname $0)/../..
rm -rf ${HOME}/.pex
rm -rf ${PANTS_BASE}/build-support/pants_deps.venv
rm -rf ${PANTS_BASE}/build-support/pants_dev_deps.venv
if [ ! -z ${PANTS_VENV} ]; then
  rm -rf ${PANTS_VENV}
fi
rm -f  ${PANTS_BASE}/pants.pex
rm -rf ${PANTS_BASE}/.pants.d
find ${PANTS_BASE} -name '*.pyc' | xargs rm -f
