import unittest
from fastapi.testclient import TestClient
from agentarium.dashboard import create_app


class DashboardAssetTests(unittest.TestCase):
    def test_frontend_entrypoint_and_its_dependencies_are_served(self):
        with TestClient(create_app()) as client:
            response = client.get('/')
            self.assertEqual(response.status_code, 200)
            self.assertIn('id="detail-dialog"', response.text)
            for asset in ('styles.css', 'run_view.js', 'script.js'):
                with self.subTest(asset=asset):
                    self.assertEqual(client.get('/' + asset).status_code, 200)
