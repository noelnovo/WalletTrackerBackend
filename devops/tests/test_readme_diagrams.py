"""Keep the technology overview connected, concise and faithful to delivery policy."""
import pathlib
import re
import unittest


class PortfolioDiagramTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = pathlib.Path(__file__).resolve().parents[2]
        cls.readme = (cls.root / 'README.md').read_text()
        cls.diagrams = re.findall(r'```mermaid\n(.*?)\n```', cls.readme, re.DOTALL)

    def test_one_end_to_end_diagram_followed_by_responsibility_table(self):
        self.assertEqual(len(self.diagrams), 1)
        self.assertTrue(self.diagrams[0].startswith('flowchart '))
        diagram_end = self.readme.index('\n```', self.readme.index('```mermaid'))
        table_start = self.readme.index('| Area | Technology |')
        self.assertGreater(table_start, diagram_end)

    def test_source_ci_security_and_publication_are_connected(self):
        diagram = self.diagrams[0]
        for edge in ('Developer[', 'GitLab --> CI', 'CI --> SonarQube',
                     'Syft --> DependencyTrack', 'SonarQube --> Gate',
                     'DependencyTrack --> Gate', 'Gate --> Publish'):
            self.assertIn(edge, diagram)
        for technology in ('GitHub', 'Docker / DinD', 'Syft / CycloneDX',
                           'SonarQube', 'Dependency-Track', 'Harbor'):
            self.assertIn(technology, diagram)
        self.assertIn('not automatic CI or deployment failover', self.readme)
        self.assertIn('SHA-256', self.readme)

    def test_gitops_image_and_rollout_flows_are_distinct(self):
        diagram = self.diagrams[0]
        for edge in ('Publish -->|"Push image"| Harbor',
                     'Publish -->|"Commit image reference"| GitOps',
                     'GitOps -->|"CI refresh webhook"| ArgoCD',
                     'Harbor -->|"Pull image"| Workloads',
                     'ArgoCD -->|"Dev auto / prod manual"| Workloads'):
            self.assertIn(edge, diagram)
        for name in ('Kustomize', 'Alembic', 'Kubernetes / k3s', 'MariaDB'):
            self.assertIn(name, diagram)
        self.assertIn('protected `vX.Y.Z`', self.readme)

    def test_secrets_cover_ci_and_runtime_without_literal_credentials(self):
        diagram = self.diagrams[0]
        for name in ('HashiCorp Vault', 'Vault Secrets Operator', 'CI secrets / OIDC'):
            self.assertIn(name, diagram)
        for edge in ('Vault -.', 'VSO -. "Application secrets" .-> Workloads',
                     'VSO -. "DB credentials" .-> MariaDB'):
            self.assertIn(edge, diagram)
        self.assertIn('Private keys and passwords stay out of Git and images', self.readme)

    def test_public_and_internal_routes_remain_separate(self):
        diagram = self.diagrams[0]
        self.assertIn('Cloudflare -->|"Production Service"| Workloads', diagram)
        self.assertIn('Nginx -->|"Development Service"| Workloads', diagram)
        self.assertIn('Internal proxy / TLS certs', diagram)
        self.assertIn('Databases and development are not publicly exposed', self.readme)

    def test_logs_flow_through_alloy_loki_and_grafana(self):
        diagram = self.diagrams[0]
        for edge in ('Workloads -->|"stdout / stderr"| Alloy',
                     'MariaDB -->|"stdout / stderr"| Alloy',
                     'Alloy --> Loki', 'Loki --> Grafana'):
            self.assertIn(edge, diagram)
        self.assertIn('not custom business analytics or distributed tracing', self.readme)

    def test_overview_avoids_inventory_and_out_of_scope_services(self):
        for omitted in ('Proxmox', 'LXC', 'Malza', '10.2.', 'NodePort', 'Keycloak',
                        'mail-gateway', 'Prometheus', 'AdGuard', 'Terraform', 'Jenkins'):
            self.assertNotIn(omitted.lower(), self.readme.lower())
        self.assertIn('no scheduled\n  WalletTracker database backup', self.readme)
