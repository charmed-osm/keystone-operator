# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

"""Interfaces used by this charm."""

import ops.charm
import ops.framework
import ops.model


class BaseRelationClient(ops.framework.Object):
    """Requires side of a Kafka Endpoint."""

    def __init__(
        self,
        charm: ops.charm.CharmBase,
        relation_name: str,
        mandatory_fields: list = [],
    ):
        super().__init__(charm, relation_name)
        self.relation_name = relation_name
        self.mandatory_fields = mandatory_fields
        self._update_relation()

    def get_data_from_unit(self, key: str):
        """Get data from unit relation data."""
        if not self.relation:
            # This update relation doesn't seem to be needed, but I added it because apparently
            # the data is empty in the unit tests.
            # In reality, the constructor is called in every hook.
            # In the unit tests when doing an update_relation_data, apparently it is not called.
            self._update_relation()
        if self.relation:
            for unit in self.relation.units:
                data = self.relation.data[unit].get(key)
                if data:
                    return data

    def get_data_from_app(self, key: str):
        """Get data from app relation data."""
        if not self.relation or self.relation.app not in self.relation.data:
            # This update relation doesn't seem to be needed, but I added it because apparently
            # the data is empty in the unit tests.
            # In reality, the constructor is called in every hook.
            # In the unit tests when doing an update_relation_data, apparently it is not called.
            self._update_relation()
        if self.relation and self.relation.app in self.relation.data:
            data = self.relation.data[self.relation.app].get(key)
            if data:
                return data

    def is_missing_data_in_unit(self):
        """Check if mandatory fields are present in any of the unit's relation data."""
        return not all([self.get_data_from_unit(field) for field in self.mandatory_fields])

    def is_missing_data_in_app(self):
        """Check if mandatory fields are set in relation data."""
        return not all([self.get_data_from_app(field) for field in self.mandatory_fields])

    def _update_relation(self):
        self.relation = self.framework.model.get_relation(self.relation_name)


class MysqlClient(BaseRelationClient):
    """Requires side of a Mysql Endpoint."""

    mandatory_fields = ["host", "port", "user", "password", "root_password"]

    def __init__(self, charm: ops.charm.CharmBase, relation_name: str):
        super().__init__(charm, relation_name, self.mandatory_fields)

    @property
    def host(self):
        """Host."""
        return self.get_data_from_unit("host")

    @property
    def port(self):
        """Port."""
        return self.get_data_from_unit("port")

    @property
    def user(self):
        """User."""
        return self.get_data_from_unit("user")

    @property
    def password(self):
        """Password."""
        return self.get_data_from_unit("password")

    @property
    def root_password(self):
        """Root password."""
        return self.get_data_from_unit("root_password")

    @property
    def database(self):
        """Database."""
        return self.get_data_from_unit("database")

    def get_root_uri(self, database: str):
        """Get the URI for the mysql connection with the root user credentials.

        Args:
            database: Database name

        Return:
            A string with the following format:
                mysql://root:<root_password>@<mysql_host>:<mysql_port>/<database>
        """
        return "mysql://root:{}@{}:{}/{}".format(
            self.root_password, self.host, self.port, database
        )

    def get_uri(self):
        """Get the URI for the mysql connection with the standard user credentials.

        Args:
            database: Database name
        Return:
            A string with the following format:
                    mysql://<user>:<password>@<mysql_host>:<mysql_port>/<database>
        """
        return "mysql://{}:{}@{}:{}/{}".format(
            self.user, self.password, self.host, self.port, self.database
        )


class KeystoneServer(ops.framework.Object):
    """Provides side of a Keystone Endpoint."""

    relation_name: str = None

    def __init__(self, charm: ops.charm.CharmBase, relation_name: str):
        super().__init__(charm, relation_name)
        self.relation_name = relation_name

    def publish_info(
        self,
        host: str,
        port: int,
        user_domain_name: str,
        project_domain_name: str,
        username: str,
        password: str,
        service: str,
        keystone_db_password: str,
        region_id: str,
        admin_username: str,
        admin_password: str,
        admin_project_name: str,
    ):
        """Publish information in Keystone relation."""
        if self.framework.model.unit.is_leader():
            for relation in self.framework.model.relations[self.relation_name]:
                relation_data = relation.data[self.framework.model.app]
                relation_data["host"] = str(host)
                relation_data["port"] = str(port)
                relation_data["user_domain_name"] = str(user_domain_name)
                relation_data["project_domain_name"] = str(project_domain_name)
                relation_data["username"] = str(username)
                relation_data["password"] = str(password)
                relation_data["service"] = str(service)
                relation_data["keystone_db_password"] = str(keystone_db_password)
                relation_data["region_id"] = str(region_id)
                relation_data["admin_username"] = str(admin_username)
                relation_data["admin_password"] = str(admin_password)
                relation_data["admin_project_name"] = str(admin_project_name)
