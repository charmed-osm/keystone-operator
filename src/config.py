#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

"""Module that takes take of the charm configuration."""

from typing import Any, Dict, Optional

from config_validator import ConfigValidator
from ops.model import ConfigData

from interfaces import MysqlClient


def validate_config(config: ConfigData):
    """Validate charm configuration.

    Args:
        config (ConfigData): Charm configuration.

    Raises:
        config_validator.ValidationError if the validation failed.
    """
    kwargs: Dict[str, Any] = config
    ConfigModel(**kwargs)
    ConfigLdapModel(**kwargs)


def get_environment(
    service_name: str, config: ConfigData, mysql_client: MysqlClient
) -> Dict[str, Any]:
    """Get environment variables.

    Args:
        service_name (str): Cluster IP service name.
        config (ConfigData): Charm configuration.

    Returns:
        Dict[str, Any]: Dictionary with the environment variables for Keystone service.
    """
    kwargs: Dict[str, Any] = config
    config = ConfigModel(**kwargs)
    config_ldap = ConfigLdapModel(**kwargs)
    environment = {
        "DB_HOST": mysql_client.host,
        "DB_PORT": mysql_client.port,
        "ROOT_DB_USER": "root",
        "ROOT_DB_PASSWORD": mysql_client.root_password,
        "REGION_ID": config.region_id,
        "KEYSTONE_HOST": service_name,
        "KEYSTONE_DB_PASSWORD": config.keystone_db_password,
        "ADMIN_USERNAME": config.admin_username,
        "ADMIN_PASSWORD": config.admin_password,
        "ADMIN_PROJECT": config.admin_project,
        "SERVICE_USERNAME": config.service_username,
        "SERVICE_PASSWORD": config.service_password,
        "SERVICE_PROJECT": config.service_project,
    }
    if config_ldap.ldap_enabled:
        environment.update(
            {
                "LDAP_AUTHENTICATION_DOMAIN_NAME": config_ldap.ldap_authentication_domain_name,
                "LDAP_URL": config_ldap.ldap_url,
                "LDAP_PAGE_SIZE": str(config_ldap.ldap_page_size),
                "LDAP_USER_OBJECTCLASS": config_ldap.ldap_user_objectclass,
                "LDAP_USER_ID_ATTRIBUTE": config_ldap.ldap_user_id_attribute,
                "LDAP_USER_NAME_ATTRIBUTE": config_ldap.ldap_user_name_attribute,
                "LDAP_USER_PASS_ATTRIBUTE": config_ldap.ldap_user_pass_attribute,
                "LDAP_USER_ENABLED_MASK": str(config_ldap.ldap_user_enabled_mask),
                "LDAP_USER_ENABLED_DEFAULT": config_ldap.ldap_user_enabled_default,
                "LDAP_USER_ENABLED_INVERT": str(config_ldap.ldap_user_enabled_invert),
                "LDAP_GROUP_OBJECTCLASS": config_ldap.ldap_group_objectclass,
            }
        )
        if config_ldap.ldap_use_starttls:
            environment.update(
                {
                    "LDAP_USE_STARTTLS": str(config_ldap.ldap_use_starttls),
                    "LDAP_TLS_CACERT_BASE64": config_ldap.ldap_tls_cacert_base64,
                    "LDAP_TLS_REQ_CERT": config_ldap.ldap_tls_req_cert,
                }
            )
        optional_ldap_configs = {
            "LDAP_BIND_USER": config_ldap.ldap_bind_user,
            "LDAP_BIND_PASSWORD": config_ldap.ldap_bind_password,
            "LDAP_USER_TREE_DN": config_ldap.ldap_user_tree_dn,
            "LDAP_USER_FILTER": config_ldap.ldap_user_filter,
            "LDAP_USER_ENABLED_ATTRIBUTE": config_ldap.ldap_user_enabled_attribute,
            "LDAP_CHASE_REFERRALS": config_ldap.ldap_chase_referrals,
            "LDAP_GROUP_TREE_DN": config_ldap.ldap_group_tree_dn,
            "LDAP_TLS_CACERT_BASE64": config_ldap.ldap_tls_cacert_base64,
        }
        for env, value in optional_ldap_configs.items():
            if value:
                environment[env] = value
    return environment


class ConfigModel(ConfigValidator):
    """Keystone Configuration."""

    region_id: str
    keystone_db_password: str
    admin_username: str
    admin_password: str
    admin_project: str
    service_username: str
    service_password: str
    service_project: str
    user_domain_name: str
    project_domain_name: str
    token_expiration: int


class ConfigLdapModel(ConfigValidator):
    """LDAP Configuration."""

    ldap_enabled: bool
    ldap_authentication_domain_name: Optional[str]
    ldap_url: Optional[str]
    ldap_bind_user: Optional[str]
    ldap_bind_password: Optional[str]
    ldap_chase_referrals: Optional[str]
    ldap_page_size: Optional[int]
    ldap_user_tree_dn: Optional[str]
    ldap_user_objectclass: Optional[str]
    ldap_user_id_attribute: Optional[str]
    ldap_user_name_attribute: Optional[str]
    ldap_user_pass_attribute: Optional[str]
    ldap_user_filter: Optional[str]
    ldap_user_enabled_attribute: Optional[str]
    ldap_user_enabled_mask: Optional[int]
    ldap_user_enabled_default: Optional[str]
    ldap_user_enabled_invert: Optional[bool]
    ldap_group_objectclass: Optional[str]
    ldap_group_tree_dn: Optional[str]
    ldap_use_starttls: Optional[bool]
    ldap_tls_cacert_base64: Optional[str]
    ldap_tls_req_cert: Optional[str]
