#!/usr/bin/env python3
# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

"""Keystone charm module."""

import logging
from datetime import datetime
from shutil import ExecError

from charms.keystone.v0 import cluster
from charms.observability_libs.v0.kubernetes_service_patch import KubernetesServicePatch
from config_validator import ValidationError
from ops import pebble
from ops.charm import ActionEvent, CharmBase, ConfigChangedEvent, UpdateStatusEvent
from ops.framework import StoredState
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, Container, MaintenanceStatus

from config import ConfigModel, get_environment, validate_config
from interfaces import KeystoneServer, MysqlClient

logger = logging.getLogger(__name__)


# We expect the keystone container to use the default port
PORT = 5000

KEY_SETUP_FILE = "/etc/keystone/key-setup"
CREDENTIAL_KEY_REPOSITORY = "/etc/keystone/credential-keys/"
FERNET_KEY_REPOSITORY = "/etc/keystone/fernet-keys/"
KEYSTONE_USER = "keystone"
KEYSTONE_GROUP = "keystone"
FERNET_MAX_ACTIVE_KEYS = 3
KEYSTONE_FOLDER = "/etc/keystone/"


class CharmError(Exception):
    """Charm error exception."""


class KeystoneCharm(CharmBase):
    """Keystone Charm operator."""

    on = cluster.ClusterEvents()
    _stored = StoredState()

    def __init__(self, *args) -> None:
        super().__init__(*args)
        event_observe_mapping = {
            self.on.keystone_pebble_ready: self._on_config_changed,
            self.on.config_changed: self._on_config_changed,
            self.on.update_status: self._on_update_status,
            self.on.cluster_keys_changed: self._on_cluster_keys_changed,
            self.on["keystone"].relation_joined: self._publish_keystone_info,
            self.on["db"].relation_changed: self._on_config_changed,
            self.on["db"].relation_broken: self._on_config_changed,
            self.on["db-sync"].action: self._on_db_sync_action,
        }
        for event, observer in event_observe_mapping.items():
            self.framework.observe(event, observer)
        self.cluster = cluster.Cluster(self)
        self.mysql_client = MysqlClient(self, relation_name="db")
        self.keystone = KeystoneServer(self, relation_name="keystone")
        self.service_patch = KubernetesServicePatch(self, [(f"{self.app.name}", PORT)])

    @property
    def container(self) -> Container:
        """Property to get keystone container."""
        return self.unit.get_container("keystone")

    def _on_db_sync_action(self, event: ActionEvent):
        process = self.container.exec(
            ["keystone-manage", "db_sync"],
            # user=KEYSTONE_USER,
            # group=KEYSTONE_GROUP,
        )
        try:
            process.wait()
            event.set_results({"output": "db-sync was successfully executed."})
        except pebble.ExecError as e:
            error_message = f"db-sync action failed with code {e.exit_code} and stderr {e.stderr}."
            logger.error(error_message)
            event.fail(error_message)

    def _publish_keystone_info(self, _):
        """Handler for keystone-relation-joined."""
        if self.unit.is_leader():
            config = ConfigModel(**dict(self.config))
            self.keystone.publish_info(
                host=f"http://{self.app.name}:{PORT}/v3",
                port=PORT,
                user_domain_name=config.user_domain_name,
                project_domain_name=config.project_domain_name,
                username=config.service_username,
                password=config.service_password,
                service=config.service_project,
                keystone_db_password=config.keystone_db_password,
                region_id=config.region_id,
                admin_username=config.admin_username,
                admin_password=config.admin_password,
                admin_project_name=config.admin_project,
            )

    def _on_config_changed(self, _: ConfigChangedEvent) -> None:
        """Handler for config-changed event."""
        if self.container.can_connect():
            try:
                # self._key_setup()
                self._handle_fernet_key_rotation()
                self._safe_restart()
                self.unit.status = ActiveStatus()
            except CharmError as e:
                self.unit.status = BlockedStatus(str(e))
            except ValidationError as e:
                self.unit.status = BlockedStatus(str(e))
        else:
            logger.info("pebble socket not available, deferring config-changed")
            self.unit.status = MaintenanceStatus("waiting for pebble to start")

    def _on_update_status(self, event: UpdateStatusEvent) -> None:
        """Handler for update-status event."""
        if self.container.can_connect():
            self._handle_fernet_key_rotation()
        else:
            logger.info("pebble socket not available, deferring config-changed")
            event.defer()
            self.unit.status = MaintenanceStatus("waiting for pebble to start")

    def _on_cluster_keys_changed(self, _) -> None:
        """Handler for ClusterKeysChanged event."""
        self._handle_fernet_key_rotation()

    def _handle_fernet_key_rotation(self) -> None:
        """Handles fernet key rotation.

        First, the function writes the existing keys in the relation to disk.
        Then, if the unit is the leader, checks if the keys should be rotated
        or not.
        """
        self._key_write()
        if self.unit.is_leader():
            self._fernet_keys_rotate_and_sync()

    def _key_write(self) -> None:
        """Write keys to container from the relation data."""
        if self.unit.is_leader():
            return
        keys = self.cluster.get_keys()
        if not keys:
            logger.debug('"key_repository" not in relation data yet...')
            return

        for key_repository in [FERNET_KEY_REPOSITORY, CREDENTIAL_KEY_REPOSITORY]:
            self._create_keys_folders()
            for key_number, key in keys[key_repository].items():
                logger.debug(f"writing key {key_number} in {key_repository}")
                file_path = f"{key_repository}{key_number}"
                if self._file_changed(file_path, key):
                    self.container.push(
                        file_path,
                        key,
                        user=KEYSTONE_USER,
                        group=KEYSTONE_GROUP,
                        permissions=0o600,
                    )
        self.container.push(KEY_SETUP_FILE, "")

    def _file_changed(self, file_path: str, content: str) -> bool:
        """Check if file in container has changed its value.

        This function checks if the file exists in the container. If it does,
        then it checks if the content of that file is equal to the content passed to
        this function. If the content is equal, the function returns False, otherwise True.

        Args:
            file_path (str): File path in the container.
            content (str): Content of the file.

        Returns:
            bool: True if the content of the file has changed, or the file doesn't exist in
                  the container. False if the content passed to this function is the same as
                  in the container.
        """
        if self._file_exists(file_path):
            old_content = self.container.pull(file_path).read()
            if old_content == content:
                return False
        return True

    def _create_keys_folders(self) -> None:
        """Create folders for Key repositories."""
        fernet_key_repository_found = False
        credential_key_repository_found = False
        for file in self.container.list_files(KEYSTONE_FOLDER):
            if file.type == pebble.FileType.DIRECTORY:
                if file.path == CREDENTIAL_KEY_REPOSITORY:
                    credential_key_repository_found = True
                if file.path == FERNET_KEY_REPOSITORY:
                    fernet_key_repository_found = True
        if not fernet_key_repository_found:
            self.container.make_dir(
                FERNET_KEY_REPOSITORY,
                user="keystone",
                group="keystone",
                permissions=0o700,
                make_parents=True,
            )
        if not credential_key_repository_found:
            self.container.make_dir(
                CREDENTIAL_KEY_REPOSITORY,
                user=KEYSTONE_USER,
                group=KEYSTONE_GROUP,
                permissions=0o700,
                make_parents=True,
            )

    def _fernet_keys_rotate_and_sync(self) -> None:
        """Rotate and sync the keys if the unit is the leader and the primary key has expired.

        The modification time of the staging key (key with index '0') is used,
        along with the config setting "token-expiration" to determine whether to
        rotate the keys.

        The rotation time = token-expiration / (max-active-keys - 2)
        where max-active-keys has a minimum of 3.
        """
        if not self.unit.is_leader():
            return
        try:
            fernet_key_file = self.container.list_files(f"{FERNET_KEY_REPOSITORY}0")[0]
            last_rotation = fernet_key_file.last_modified.timestamp()
        except pebble.APIError:
            logger.warning(
                "Fernet key rotation requested but key repository not " "initialized yet"
            )
            return

        config = ConfigModel(**self.config)
        rotation_time = config.token_expiration // (FERNET_MAX_ACTIVE_KEYS - 2)

        now = datetime.now().timestamp()
        if last_rotation + rotation_time > now:
            # No rotation to do as not reached rotation time
            logger.debug("No rotation needed")
            self._key_leader_set()
            return
        # now rotate the keys and sync them
        self._fernet_rotate()
        self._key_leader_set()

        logger.info("Rotated and started sync of fernet keys")

    def _key_leader_set(self) -> None:
        """Read current key sets and update peer relation data.

        The keys are read from the `FERNET_KEY_REPOSITORY` and `CREDENTIAL_KEY_REPOSITORY`
        directories. Note that this function will fail if it is called on the unit that is
        not the leader.
        """
        disk_keys = {}
        for key_repository in [FERNET_KEY_REPOSITORY, CREDENTIAL_KEY_REPOSITORY]:
            disk_keys[key_repository] = {}
            for file in self.container.list_files(key_repository):
                key_content = self.container.pull(f"{key_repository}{file.name}").read()
                disk_keys[key_repository][file.name] = key_content
        self.cluster.save_keys(disk_keys)

    def _fernet_rotate(self) -> None:
        """Rotate Fernet keys.

        To rotate the Fernet tokens, and create a new staging key, it calls (as the
        "keystone" user):

            keystone-manage fernet_rotate

        Note that we do not rotate the Credential encryption keys.

        Note that this does NOT synchronise the keys between the units.  This is
        performed in `self._key_leader_set`.
        """
        logger.debug("Rotating Fernet tokens")
        try:
            exec_command = [
                "keystone-manage",
                "fernet_rotate",
                "--keystone-user",
                KEYSTONE_USER,
                "--keystone-group",
                KEYSTONE_GROUP,
            ]
            logger.debug(f'Executing command: {" ".join(exec_command)}')
            self.container.exec(exec_command).wait()
            logger.info("Fernet keys successfully rotated.")
        except pebble.ExecError as e:
            logger.error(f"Fernet Key rotation failed: {e}")
            logger.error("Exited with code %d. Stderr:", e.exit_code)
            for line in e.stderr.splitlines():
                logger.error("    %s", line)

    def _key_setup(self) -> None:
        """Initialize Fernet and Credential encryption key repositories.

        To setup the key repositories:

            keystone-manage fernet_setup
            keystone-manage credential_setup

        In addition we migrate any credentials currently stored in database using
        the null key to be encrypted by the new credential key:

            keystone-manage credential_migrate

        Note that we only want to do this once, so we touch an empty file
        (KEY_SETUP_FILE) to indicate that it has been done.
        """
        if self._file_exists(KEY_SETUP_FILE) or not self.unit.is_leader():
            return

        logger.debug("Setting up key repositories for Fernet tokens and Credential encryption.")
        try:
            for command in ["fernet_setup", "credential_setup", "credential_migrate"]:
                exec_command = [
                    "keystone-manage",
                    command,
                    "--keystone-user",
                    KEYSTONE_USER,
                    "--keystone-group",
                    KEYSTONE_GROUP,
                ]
                logger.debug(f'Executing command: {" ".join(exec_command)}')
                process = self.container.exec(exec_command).wait()
                stdout, _ = process.wait_output()
            self.container.push(KEY_SETUP_FILE, "")
            logger.info("Key repositories initialized successfully.")
        except pebble.ExecError as e:
            logger.error("Failed initializing key repositories.")
            logger.error("Exited with code %d. Stderr:", e.exit_code)
            for line in e.stderr.splitlines():
                logger.error("    %s", line)

    def _file_exists(self, path: str) -> bool:
        """Check if a file exists in the container.

        Args:
            path (str): Path of the file to be checked.

        Returns:
            bool: True if the file exists, else False.
        """
        file_exists = None
        try:
            _ = self.container.pull(path)
            file_exists = True
        except pebble.PathError:
            file_exists = False
        exist_str = "exists" if file_exists else 'doesn"t exist'
        logger.debug(f"File {path} {exist_str}.")
        return file_exists

    def _safe_restart(self) -> None:
        """Safely restart the keystone service.

        This function (re)starts the keystone service after doing some safety checks,
        like validating the charm configuration, checking the mysql relation is ready.
        """
        validate_config(self.config)
        self._check_mysql_relation()
        # Workaround: OS_AUTH_URL is not ready when the entrypoint restarts apache2.
        # The function `self._patch_entrypoint` fixes that.
        self._patch_entrypoint()
        self._replan()

    def _patch_entrypoint(self) -> None:
        """Patches the entrypoint of the Keystone service.

        The entrypoint that restarts apache2, expects immediate communication to OS_AUTH_URL.
        This does not happen instantly. This function patches the entrypoint to wait until a
        curl to OS_AUTH_URL succeeds.
        """
        installer_script = self.container.pull("/keystone/start.sh").read()
        wait_until_ready_command = "until $(curl --output /dev/null --silent --head --fail $OS_AUTH_URL); do echo '...'; sleep 5; done"
        self.container.push(
            "/keystone/start-patched.sh",
            installer_script.replace(
                "source setup_env", f"source setup_env && {wait_until_ready_command}"
            ),
            permissions=0o755,
        )

    def _check_mysql_relation(self) -> None:
        """Check if the mysql relation is ready.

        Raises:
            CharmError: Error raised if the mysql relation is not ready.
        """
        if self.mysql_client.is_missing_data_in_unit():
            raise CharmError("mysql relation is missing")

    def _replan(self) -> None:
        """Replan keystone service.

        This function starts the keystone service if it is not running.
        If the service started already, this function will restart the
        service if there are any changes to the layer.
        """
        layer = {
            "summary": "keystone layer",
            "description": "pebble config layer for keystone",
            "services": {
                "keystone": {
                    "override": "replace",
                    "summary": "keystone service",
                    "command": "/keystone/start-patched.sh",
                    "startup": "enabled",
                    "environment": get_environment(self.app.name, self.config, self.mysql_client),
                }
            },
        }
        self.container.add_layer("keystone", layer, combine=True)
        self.container.replan()


if __name__ == "__main__":  # pragma: no cover
    main(KeystoneCharm, use_juju_for_storage=True)
