#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.


import base64
import logging
from pathlib import Path

import pytest
import yaml
from pytest_operator.plugin import OpsTest

logger = logging.getLogger(__name__)

METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())


@pytest.mark.abort_on_fail
async def test_build_and_deploy(ops_test: OpsTest):
    """Build the charm-under-test and deploy it together with related charms.

    Assert on the unit status before any relations/configurations take place.
    """
    await ops_test.model.set_config({"update-status-hook-interval": "10s"})
    await ops_test.model.deploy("charmed-osm-mariadb-k8s", application_name="mariadb-k8s")
    # build and deploy charm from local source folder
    charm = await ops_test.build_charm(".")
    resources = {
        "keystone-image": METADATA["resources"]["keystone-image"]["upstream-source"],
    }
    await ops_test.model.deploy(charm, resources=resources, application_name="keystone")
    await ops_test.model.add_relation("keystone:db", "mariadb-k8s:mysql")
    await ops_test.model.wait_for_idle(
        apps=["keystone", "mariadb-k8s"], status="active", timeout=1000
    )
    assert ops_test.model.applications["keystone"].units[0].workload_status == "active"

    await ops_test.model.set_config({"update-status-hook-interval": "60m"})


def base64_encode(phrase: str) -> str:
    return base64.b64encode(phrase.encode("utf-8")).decode("utf-8")
