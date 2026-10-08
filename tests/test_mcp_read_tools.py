import asyncio
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from kubernetes import client
from kubernetes.client.exceptions import ApiException


class ReadOnlyToolsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = Path(__file__).resolve().parents[1] / "mcp_server.py"
        spec = importlib.util.spec_from_file_location("mcp_server_under_test", path)
        cls.server = importlib.util.module_from_spec(spec)
        with patch("kubernetes.config.load_kube_config"), \
                patch("kubernetes.client.CoreV1Api"), \
                patch("kubernetes.client.AppsV1Api"):
            spec.loader.exec_module(cls.server)

    def setUp(self):
        self.core = Mock(spec=client.CoreV1Api)
        self.apps = Mock(spec=client.AppsV1Api)
        self.server.core_v1 = self.core
        self.server.apps_v1 = self.apps
        self.namespaced_tools = [
            (self.server.get_deployments, self.apps.list_namespaced_deployment),
            (self.server.get_services, self.core.list_namespaced_service),
            (self.server.list_secrets, self.core.list_namespaced_secret),
            (self.server.list_config_maps, self.core.list_namespaced_config_map),
        ]

    def test_tools_are_discoverable_with_namespace_schema(self):
        tools = {tool.name: tool for tool in asyncio.run(self.server.mcp.list_tools())}
        self.assertIn("get_namespaces", tools)
        for function, _ in self.namespaced_tools:
            schema = tools[function.__name__].input_schema
            self.assertIn("namespace", schema["required"])
            self.assertEqual(schema["properties"]["namespace"]["type"], "string")

    def test_namespace_listing(self):
        self.core.list_namespace.return_value = SimpleNamespace(items=[
            client.V1Namespace(
                metadata=client.V1ObjectMeta(name="dev"),
                status=client.V1NamespaceStatus(phase="Active"),
            ),
        ])
        self.assertEqual(self.server.get_namespaces(), [{"name": "dev", "phase": "Active"}])
        self.assertEqual([call[0] for call in self.core.mock_calls], ["list_namespace"])
        self.assertFalse(self.apps.mock_calls)

    def test_empty_lists_use_only_read_calls(self):
        for function, api in self.namespaced_tools:
            with self.subTest(tool=function.__name__):
                self.core.reset_mock()
                self.apps.reset_mock()
                api.return_value = SimpleNamespace(items=[])
                self.assertEqual(function("dev"), [])
                self.core.read_namespace.assert_called_once_with(name="dev")
                api.assert_called_once_with(namespace="dev")
                calls = self.core.mock_calls + self.apps.mock_calls
                self.assertEqual(len(calls), 2)
                self.assertTrue(all(c[0] == "read_namespace" or c[0].startswith("list_") for c in calls))

    def test_missing_namespace_and_permission_errors(self):
        for function, api in self.namespaced_tools:
            with self.subTest(tool=function.__name__):
                self.core.read_namespace.side_effect = ApiException(status=404)
                with self.assertRaisesRegex(ValueError, "namespace 'missing' does not exist"):
                    function("missing")
                api.assert_not_called()
                self.core.read_namespace.side_effect = ApiException(status=403)
                with self.assertRaises(ApiException) as error:
                    function("dev")
                self.assertEqual(error.exception.status, 403)
                api.assert_not_called()

    def test_resource_permission_errors_propagate(self):
        for function, api in self.namespaced_tools:
            with self.subTest(tool=function.__name__):
                api.side_effect = ApiException(status=403)
                with self.assertRaises(ApiException) as error:
                    function("dev")
                self.assertEqual(error.exception.status, 403)

    def test_deployment_without_status_and_environment_values(self):
        self.apps.list_namespaced_deployment.return_value = SimpleNamespace(items=[
            client.V1Deployment(
                metadata=client.V1ObjectMeta(name="web", namespace="dev"),
                spec=client.V1DeploymentSpec(
                    replicas=0,
                    selector=client.V1LabelSelector(match_labels={"app": "web"}),
                    template=client.V1PodTemplateSpec(spec=client.V1PodSpec(containers=[
                        client.V1Container(name="web", image="nginx:stable", env=[
                            client.V1EnvVar(name="PASSWORD", value="do-not-return")
                        ])
                    ])),
                ),
            )
        ])
        result = self.server.get_deployments("dev")
        self.assertEqual(result[0]["replicas"], 0)
        self.assertEqual(result[0]["ready_replicas"], 0)
        self.assertEqual(result[0]["containers"], [{"name": "web", "image": "nginx:stable"}])
        self.assertNotIn("do-not-return", json.dumps(result))

    def test_service_named_target_port_and_optional_fields(self):
        self.core.list_namespaced_service.return_value = SimpleNamespace(items=[
            client.V1Service(
                metadata=client.V1ObjectMeta(name="web", namespace="dev"),
                spec=client.V1ServiceSpec(type="ClusterIP", cluster_ip="None", ports=[
                    client.V1ServicePort(port=80, target_port="http", protocol="TCP")
                ]),
            ),
            client.V1Service(
                metadata=client.V1ObjectMeta(name="external", namespace="dev"),
                spec=client.V1ServiceSpec(type="ExternalName", external_name="example.com"),
            ),
        ])
        result = self.server.get_services("dev")
        self.assertEqual(result[0]["ports"][0]["target_port"], "http")
        self.assertEqual(result[0]["external_ips"], [])
        self.assertEqual(result[1]["ports"], [])
        self.assertEqual(result[1]["external_name"], "example.com")

    def test_secrets_and_configmaps_exclude_values_and_annotations(self):
        metadata = client.V1ObjectMeta(
            name="settings", namespace="dev", annotations={"snapshot": "sensitive-annotation"}
        )
        self.core.list_namespaced_secret.return_value = SimpleNamespace(items=[
            client.V1Secret(metadata=metadata, type="Opaque", data={"password": "c2VjcmV0"}),
            client.V1Secret(metadata=metadata, type="Opaque"),
        ])
        secrets = self.server.list_secrets("dev")
        self.assertEqual(secrets[0], {
            "name": "settings", "namespace": "dev", "type": "Opaque", "data_count": 1
        })
        self.assertEqual(secrets[1]["data_count"], 0)
        self.core.list_namespaced_config_map.return_value = SimpleNamespace(items=[
            client.V1ConfigMap(metadata=metadata, data={"config": "sensitive-config"},
                               binary_data={"binary": "c2VjcmV0"}),
            client.V1ConfigMap(metadata=metadata),
        ])
        maps = self.server.list_config_maps("dev")
        self.assertEqual(maps[0]["data_keys"], ["config"])
        self.assertEqual(maps[0]["binary_data_keys"], ["binary"])
        self.assertEqual(maps[1]["data_keys"], [])
        self.assertEqual(maps[1]["binary_data_keys"], [])
        serialized = json.dumps(secrets + maps)
        for sensitive in ["c2VjcmV0", "sensitive-annotation", "sensitive-config"]:
            self.assertNotIn(sensitive, serialized)


if __name__ == "__main__":
    unittest.main()
