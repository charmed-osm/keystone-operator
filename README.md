<!-- Copyright 2021 Canonical Ltd.
See LICENSE file for licensing details. -->

# Keystone Operator

[![code style](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black/tree/main)

[![Keystone](https://charmhub.io/keystone/badge.svg)](https://charmhub.io/keystone)

## Description

This charm deploys Keystone in K8s. It is mainly developed to be used as part of the OSM deployment.

## Usage

The Keystone Operator may be deployed using the Juju command line as in

```shell
$ juju add-model keystone
$ juju deploy charmed-osm-mariadb-k8s db
$ juju deploy keystone-k8s --trust
$ juju relate keystone-k8s db
```

## OCI Images

- [keystone](https://hub.docker.com/r/opensourcemano/keystone)

## Contributing

Please see the [Juju SDK docs](https://juju.is/docs/sdk) for guidelines
on enhancements to this charm following best practice guidelines, and
`CONTRIBUTING.md` for developer guidance.
