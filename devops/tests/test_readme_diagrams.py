"""Keep the portfolio diagrams aligned with real integrations, not generic boxes."""
import pathlib
import re
import unittest


class PortfolioDiagramTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = pathlib.Path(__file__).resolve().parents[2]
        cls.readme = (cls.root / 'README.md').read_text()
        cls.diagrams = re.findall(r'```mermaid\n(.*?)\n```', cls.readme, re.DOTALL)

    def test_delivery_runtime_observability_and_history_have_separate_diagrams(self):
        self.assertEqual(len(self.diagrams), 7)
        for diagram in self.diagrams:
            self.assertTrue(diagram.startswith('flowchart '))

    def test_both_security_integrations_are_explicit_and_connected(self):
        delivery = '\n'.join(self.diagrams[:2])
        for name in ('SonarQube', 'Dependency-Track', 'Syft', 'CycloneDX', 'security-gates'):
            self.assertIn(name, delivery)
        self.assertIn('Syft --> DependencyTrack', delivery)
        self.assertIn('SonarQube -->|"Quality gate passed"| SecurityGate', delivery)
        self.assertIn('DependencyTrack -->|"SBOM processing completed"| SecurityGate', delivery)
        self.assertIn('SecurityGate --> Publish', delivery)

    def test_provenance_oidc_gitops_and_rollout_proof_are_not_hidden(self):
        delivery = '\n'.join(self.diagrams[:2])
        for name in ('SHA-256', 'GitLab OIDC', 'CI_JOB_TOKEN', 'Harbor', 'Kustomize',
                     'AppProjects', 'MigrationHook', 'RolloutProof', 'GitHub', 'protected vX.Y.Z'):
            self.assertIn(name, delivery)

    def test_runtime_shows_both_environments_and_all_secret_consumers(self):
        runtime = '\n'.join(self.diagrams[2:4])
        for name in ('wallettracker-dev', 'wallettracker-prod', 'MariaDB', 'VSO',
                     'DevSecrets', 'ProdSecrets', 'PullSecrets', 'RepoSecret',
                     'TunnelSecret', 'local-path', 'VaultBackup'):
            self.assertIn(name, runtime)
        self.assertIn('VSO --> DevSecrets', runtime)
        self.assertIn('VSO --> ProdSecrets', runtime)

    def test_observability_includes_logs_metrics_alerting_and_actual_sso(self):
        operations = '\n'.join(self.diagrams[4:6])
        for name in ('Alloy', 'Loki', 'Prometheus', 'Grafana', 'kube-state-metrics',
                     'node-exporter', 'cAdvisor', 'Freelens', 'Vault Agent',
                     'Keycloak', 'MailRelay', 'MailGateway'):
            self.assertIn(name, operations)
        self.assertRegex(operations, r'Keycloak(?:\[[^\n]+\])? --> Grafana')
        self.assertIn('Keycloak --> GitLabSSO', operations)
        self.assertIn('Keycloak --> ProxmoxSSO', operations)
        self.assertNotIn('Keycloak --> Argo', operations)
        self.assertIn('not financial KPIs', self.readme)

    def test_public_and_internal_traffic_target_the_correct_environment(self):
        runtime = self.diagrams[2]
        self.assertIn('Tunnel -->|"Cluster-local HTTP origin :5000"| ProdService', runtime)
        self.assertIn('NPM -->|"HTTP to Malza NodePort 31410"| DevService', runtime)
        self.assertNotIn('Tunnel --> DevService', runtime)

    def test_retired_tools_are_not_presented_as_current_delivery(self):
        current = '\n'.join(self.diagrams[:6])
        self.assertNotIn('Terraform', current)
        self.assertNotIn('Jenkins', current)
        self.assertIn('Historical: Terraform', self.diagrams[6])
        self.assertIn('Jenkins', self.diagrams[6])
