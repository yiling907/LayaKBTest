import json
import unittest
from unittest.mock import patch, MagicMock

import azure.functions as func


class TestHealthEndpoint(unittest.TestCase):
    def test_health_returns_ok(self):
        from function_app import health

        req = func.HttpRequest(
            method="GET",
            body=b"",
            url="http://localhost:7071/api/health",
            params={},
        )
        response = health(req)
        self.assertEqual(response.status_code, 200)
        body = json.loads(response.get_body())
        self.assertEqual(body["status"], "ok")


class TestQueryEndpoint(unittest.TestCase):
    @patch("function_app.cosmos_client")
    @patch("function_app.search_client")
    @patch("function_app.openai_client")
    def test_query_returns_answer(self, mock_openai, mock_search, mock_cosmos):
        from function_app import query

        mock_openai.get_embedding.return_value = [0.0] * 1536
        mock_search.vector_search.return_value = [
            {"document_name": "doc.pdf", "content": "Refunds are allowed within 30 days."}
        ]
        mock_openai.chat_completion.return_value = "You can get a refund within 30 days."

        req = func.HttpRequest(
            method="POST",
            body=json.dumps({"question": "What is the refund policy?"}).encode(),
            url="http://localhost:7071/api/query",
            params={},
            headers={"Content-Type": "application/json"},
        )
        response = query(req)
        self.assertEqual(response.status_code, 200)
        body = json.loads(response.get_body())
        self.assertIn("answer", body)
        self.assertIn("sources", body)

    def test_query_missing_question(self):
        from function_app import query

        req = func.HttpRequest(
            method="POST",
            body=json.dumps({}).encode(),
            url="http://localhost:7071/api/query",
            params={},
            headers={"Content-Type": "application/json"},
        )
        response = query(req)
        self.assertEqual(response.status_code, 400)


class TestChunkText(unittest.TestCase):
    def test_chunk_splits_long_text(self):
        from function_app import _chunk_text

        long_text = "word " * 2000
        chunks = _chunk_text(long_text, chunk_size=200, overlap=20)
        self.assertGreater(len(chunks), 1)
        for chunk in chunks:
            self.assertTrue(len(chunk.strip()) > 0)
