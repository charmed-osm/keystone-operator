<!-- Copyright 2021 Canonical Ltd.
See LICENSE file for licensing details. -->

# Upgrades

## From old charm

```shell
unset OSM_USER OSM_PROJECT OSM_PASSWORD
# Install osm
./install_osm.sh --charmed --tag 10.0.3
# Create user
osm user-create test_user --password test_password
osm user-list
osm user-show test_user
osm user-update --set-project admin,system_admin test_user
osm user-update --add-project-role 'admin,project_user' test_user
osm user-show test_user
export OSM_USER=test_user
export OSM_PROJECT=admin
export OSM_PASSWORD=test_password
# Validate user
osm ns-list
# Remove old keystone
juju remove-application keystone
# Build keystone
charmcraft build
# Deploy new keystone
juju deploy ./keystone-k8s_ubuntu-20.04-amd64.charm --resource keystone-image=opensourcemano/keystone:11 --trust 
juju relate mariadb-k8s keystone-k8s
juju relate nbi keystone-k8s
juju relate mon keystone-k8s
# if charm is stuck in allocating status
juju upgrade-controller
microk8s.kubectl -n controller-osm-vca get pods -w
juju upgrade-model
microk8s.kubectl -n osm get pods -w
# In mysql, update the endpoint
microk8s.kubectl -n osm exec -it mariadb-k8s-0 -- mysql -uroot -posm4u -Dkeystone --execute='update endpoint set url="http://keystone-k8s:5000/v3/" where url="http://keystone:5000/v3/";'
# Run db_sync
juju run-action keystone-k8s/0 db-sync --wait
# validate user again (nbi might takes a bit to be alive...)
osm ns-list
```
