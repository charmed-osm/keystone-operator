# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

import pytest
from ops import pebble
from ops.model import ActiveStatus, BlockedStatus
from ops.testing import Harness
from pytest_mock import MockerFixture

from charm import FERNET_KEY_REPOSITORY, KEYSTONE_FOLDER, KeystoneCharm


@pytest.fixture
def harness_no_relations(mocker: MockerFixture):
    mocker.patch("charm.cluster")
    mocker.patch("charm.KubernetesServicePatch")
    keystone_harness = Harness(KeystoneCharm)
    keystone_harness.begin()
    container = keystone_harness.charm.unit.get_container("keystone")
    keystone_harness.set_can_connect(container, True)
    container.make_dir(KEYSTONE_FOLDER, make_parents=True)
    container.make_dir(FERNET_KEY_REPOSITORY, make_parents=True)
    container.push(f"{FERNET_KEY_REPOSITORY}0", "token")
    container.make_dir("/app", make_parents=True)
    container.push("/app/start.sh", "")
    container.exec = mocker.Mock()
    yield keystone_harness
    keystone_harness.cleanup()


@pytest.fixture
def harness(harness_no_relations: Harness):
    mysql_rel_id = harness_no_relations.add_relation("db", "mysql")
    harness_no_relations.add_relation_unit(mysql_rel_id, "mysql/0")
    harness_no_relations.update_relation_data(
        mysql_rel_id,
        "mysql/0",
        {
            "host": "host",
            "port": "3306",
            "user": "user",
            "root_password": "root_pass",
            "password": "password",
            "database": "db",
        },
    )
    return harness_no_relations


def test_mysql_missing_relation(mocker: MockerFixture, harness_no_relations: Harness):
    spy_safe_restart = mocker.spy(harness_no_relations.charm, "_safe_restart")
    harness_no_relations.charm.on.keystone_pebble_ready.emit("keystone")
    assert harness_no_relations.charm.unit.status == BlockedStatus("mysql relation is missing")
    assert spy_safe_restart.call_count == 1
    harness_no_relations.charm.on.config_changed.emit()
    assert harness_no_relations.charm.unit.status == BlockedStatus("mysql relation is missing")
    assert spy_safe_restart.call_count == 2


def test_mysql_relation_ready(mocker: MockerFixture, harness: Harness):
    spy = mocker.spy(harness.charm, "_safe_restart")
    harness.charm.on.config_changed.emit()
    assert harness.charm.unit.status == ActiveStatus()
    assert spy.call_count == 1


def test_db_sync_action(mocker: MockerFixture, harness: Harness):
    event_mock = mocker.Mock()
    harness.charm._on_db_sync_action(event_mock)
    event_mock.set_results.assert_called_once_with(
        {"output": "db-sync was successfully executed."}
    )
    event_mock.fail.assert_not_called()
    harness.charm.container.exec().wait.side_effect = pebble.ExecError(
        ["keystone-manage", "db_sync"], 1, "", "Error"
    )
    harness.charm._on_db_sync_action(event_mock)
    event_mock.fail.assert_called_once_with("db-sync action failed with code 1 and stderr Error.")


def test_provide_keystone_relation(mocker: MockerFixture, harness: Harness):
    # Non-leader
    mon_rel_id = harness.add_relation("keystone", "mon")
    harness.add_relation_unit(mon_rel_id, "mon/0")
    data = harness.get_relation_data(mon_rel_id, harness.charm.app)
    assert data == {}
    # Leader
    harness.set_leader(True)
    nbi_rel_id = harness.add_relation("keystone", "nbi")
    harness.add_relation_unit(nbi_rel_id, "nbi/0")
    data = harness.get_relation_data(nbi_rel_id, harness.charm.app)
    assert data == {
        "host": "http://osm-keystone:5000/v3",
        "port": "5000",
        "user_domain_name": "default",
        "project_domain_name": "default",
        "username": "nbi",
        "password": "nbi",
        "service": "service",
        "keystone_db_password": "admin",
        "region_id": "RegionOne",
        "admin_username": "admin",
        "admin_password": "admin",
        "admin_project_name": "admin",
    }


def test_update_status_rotation(mocker: MockerFixture, harness: Harness):
    spy_fernet_rotate = mocker.spy(harness.charm, "_fernet_rotate")
    harness.set_leader(True)
    harness._update_config({"token-expiration": -1})
    harness.charm.on.update_status.emit()
    assert spy_fernet_rotate.call_count == 1


def test_update_status_no_rotation(mocker: MockerFixture, harness: Harness):
    spy_fernet_rotate = mocker.spy(harness.charm, "_fernet_rotate")
    harness.set_leader(True)
    harness._update_config({"token-expiration": 3600})
    harness.charm.on.update_status.emit()
    assert spy_fernet_rotate.call_count == 0
