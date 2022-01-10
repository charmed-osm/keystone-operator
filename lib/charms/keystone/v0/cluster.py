# Copyright 2021 Canonical Ltd.
# See LICENSE file for licensing details.

"""Keystone cluster library.

This library allows the integration with Apache Guacd charm. Is is published as part of the
[davigar15-apache-guacd]((https://charmhub.io/davigar15-apache-guacd) charm.

The charm that requires guacd should include the following content in its metadata.yaml:

```yaml
# ...
peers:
    cluster:
        interface: cluster
# ...
```

A typical example of including this library might be:

```python
# ...
from ops.framework import StoredState
from charms.keystone.v0 import cluster

class SomeApplication(CharmBase):
  on = cluster.ClusterEvents()

  def __init__(self, *args):
    # ...
    self.cluster = cluster.Cluster(self)
    self.framework.observe(self.on.cluster_keys_changed, self._cluster_keys_changed)
    # ...

  def _cluster_keys_changed(self, _):
    fernet_keys = self.cluster.fernet_keys
    credential_keys = self.cluster.credential_keys
    # ...
```
"""


import json
import logging
from typing import Any, Dict, List

from ops.charm import CharmEvents
from ops.framework import EventBase, EventSource, Object
from ops.model import Relation

# Number of keys need might need to be adjusted in the future
NUMBER_FERNET_KEYS = 2
NUMBER_CREDENTIAL_KEYS = 2

logger = logging.getLogger(__name__)


class ClusterKeysChangedEvent(EventBase):
    """Event to announce a change in the Guacd service."""


class ClusterEvents(CharmEvents):
    """Cluster Events."""

    cluster_keys_changed = EventSource(ClusterKeysChangedEvent)


class Cluster(Object):
    """Peer relation."""

    def __init__(self, charm):
        super().__init__(charm, "cluster")
        self.charm = charm

    @property
    def fernet_keys(self) -> List[str]:
        """Fernet keys."""
        relation: Relation = self.model.get_relation("cluster")
        application_data = relation.data[self.model.app]
        return json.loads(application_data.get("keys-fernet", "[]"))

    @property
    def credential_keys(self) -> List[str]:
        """Credential keys."""
        relation: Relation = self.model.get_relation("cluster")
        application_data = relation.data[self.model.app]
        return json.loads(application_data.get("keys-credential", "[]"))

    def save_keys(self, keys: Dict[str, Any]) -> None:
        """Generate fernet and credential keys.

        This method will generate new keys and fire the cluster_keys_changed event.
        """
        logger.debug("Saving keys...")
        relation: Relation = self.model.get_relation("cluster")
        data = relation.data[self.model.app]
        current_keys_str = data.get("key_repository", "{}")
        current_keys = json.loads(current_keys_str)
        if current_keys != keys:
            data["key_repository"] = json.dumps(keys)
            self.charm.on.cluster_keys_changed.emit()
        logger.info("Keys saved!")

    def get_keys(self) -> Dict[str, Any]:
        """Get keys from the relation.

        Returns:
            Dict[str, Any]: Dictionary with the keys.
        """
        relation: Relation = self.model.get_relation("cluster")
        data = relation.data[self.model.app]
        current_keys_str = data.get("key_repository", "{}")
        current_keys = json.loads(current_keys_str)
        return current_keys
