# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import pytest
from ops.model import BlockedStatus, MaintenanceStatus
from ops.testing import Harness
from pytest_mock import MockerFixture

from charm import KeystoneCharm


@pytest.fixture
def harness(mocker: MockerFixture):
    mocker.patch("charm.cluster")
    mocker.patch("charm.KubernetesServicePatch")
    keystone_harness = Harness(KeystoneCharm)
    keystone_harness.begin()
    yield keystone_harness
    keystone_harness.cleanup()


def test_keystone_pebble_ready(mocker: MockerFixture, harness: Harness):
    spy = mocker.spy(harness.charm, "_restart")
    harness.charm.on.keystone_pebble_ready.emit("keystone")
    assert harness.charm.unit.status == BlockedStatus("mysql relation is missing")
    assert spy.call_count == 0


def test_config_changed_can_connect(mocker: MockerFixture, harness: Harness):
    spy = mocker.spy(harness.charm, "_restart")
    container = harness.charm.container
    container.push = mocker.Mock()
    harness.update_config({"token-expiration": -1})
    assert harness.charm.unit.status == BlockedStatus("mysql relation is missing")
    assert spy.call_count == 0


def test_config_changed_cannot_connect(mocker: MockerFixture, harness: Harness):
    spy = mocker.spy(harness.charm, "_restart")
    container_mock = mocker.Mock()
    container_mock.can_connect.return_value = False
    mocker.patch(
        "charm.KeystoneCharm.container",
        return_value=container_mock,
        new_callable=mocker.PropertyMock,
    )
    harness.charm.on.config_changed.emit()
    assert harness.charm.unit.status == MaintenanceStatus("waiting for pebble to start")
    assert spy.call_count == 0


def test_restart_service_service_not_exists(mocker: MockerFixture, harness: Harness):
    container_mock = mocker.Mock()
    plan_mock = mocker.Mock()
    plan_mock.services = {}
    container_mock.get_plan.return_value = plan_mock
    mocker.patch(
        "charm.KeystoneCharm.container",
        return_value=container_mock,
        new_callable=mocker.PropertyMock,
    )
    harness.charm._restart_service()
    container_mock.restart.assert_not_called()
