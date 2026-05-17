"""
test_mcp_integration.py — Unit tests for Phase 4 MCP HTTP clients (mocked).
"""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MCP_DIR = PROJECT_ROOT / "src" / "Phase4-mcp"

import importlib.util as _ilu


def _load(module_name: str, file_path: Path, package_name: str | None = None):
    spec = _ilu.spec_from_file_location(module_name, file_path)
    mod = _ilu.module_from_spec(spec)
    if package_name:
        mod.__package__ = package_name
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


pkg = type(sys)("Phase4_mcp")
pkg.__path__ = [str(MCP_DIR)]
sys.modules["Phase4_mcp"] = pkg

_load("Phase4_mcp.exceptions", MCP_DIR / "exceptions.py", "Phase4_mcp")
_publish_mod = _load("Phase4_mcp.publish_result", MCP_DIR / "publish_result.py", "Phase4_mcp")
_config_mod = _load("Phase4_mcp.config", MCP_DIR / "config.py", "Phase4_mcp")
_http_mod = _load("Phase4_mcp.mcp_http_client", MCP_DIR / "mcp_http_client.py", "Phase4_mcp")
_docs_mod = _load("Phase4_mcp.google_docs_client", MCP_DIR / "google_docs_client.py", "Phase4_mcp")
_gmail_mod = _load("Phase4_mcp.gmail_client", MCP_DIR / "gmail_client.py", "Phase4_mcp")
_publisher_mod = _load("Phase4_mcp.publisher", MCP_DIR / "publisher.py", "Phase4_mcp")

MCPSettings = _config_mod.MCPSettings
MCPHttpClient = _http_mod.MCPHttpClient
MCPGoogleDocsClient = _docs_mod.MCPGoogleDocsClient
MCPGmailClient = _gmail_mod.MCPGmailClient
PulsePublisher = _publisher_mod.PulsePublisher
ConfigurationError = _config_mod.ConfigurationError
document_url = _publish_mod.document_url


@pytest.fixture()
def settings(tmp_path, monkeypatch):
    monkeypatch.setenv("GOOGLE_MASTER_DOC_ID", "test-doc-id-123")
    monkeypatch.setenv("PULSE_EMAIL_RECIPIENT", "team@example.com")
    monkeypatch.setenv("MCP_SERVER_URL", "https://mcp.example.com")
    monkeypatch.setenv("OUTPUT_LOGS_DIR", str(tmp_path / "logs"))
    return MCPSettings.load(project_root=PROJECT_ROOT)


def test_document_url():
    assert document_url("abc") == "https://docs.google.com/document/d/abc/edit"


def test_settings_missing_doc_id(monkeypatch):
    monkeypatch.delenv("GOOGLE_MASTER_DOC_ID", raising=False)
    monkeypatch.setenv("PULSE_EMAIL_RECIPIENT", "team@example.com")
    with pytest.raises(ConfigurationError):
        MCPSettings.load(project_root=PROJECT_ROOT)


def test_append_to_doc_success(settings):
    http = MCPHttpClient(settings.base_url, max_retries=1)
    mock_response = MagicMock()
    mock_response.content = json.dumps(
        {"status": "success", "document_id": "test-doc-id-123"}
    ).encode()
    mock_response.json.return_value = {
        "status": "success",
        "document_id": "test-doc-id-123",
    }
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.Client") as client_cls:
        client_cls.return_value.__enter__.return_value.post.return_value = mock_response
        client = MCPGoogleDocsClient(http, settings)
        doc_id, url = client.append_pulse_section("# Pulse\n\nBody", "15 May 2026")

    assert doc_id == "test-doc-id-123"
    assert "test-doc-id-123" in url


def test_create_draft_success(settings):
    http = MCPHttpClient(settings.base_url, max_retries=1)
    mock_response = MagicMock()
    mock_response.content = json.dumps(
        {"status": "success", "draft_id": "draft-xyz"}
    ).encode()
    mock_response.json.return_value = {"status": "success", "draft_id": "draft-xyz"}
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.Client") as client_cls:
        client_cls.return_value.__enter__.return_value.post.return_value = mock_response
        client = MCPGmailClient(http, settings)
        draft_id = client.create_draft(
            body="Pulse text",
            subject="[Weekly Pulse] Test",
            doc_url=document_url(settings.master_doc_id),
        )

    assert draft_id == "draft-xyz"


def test_publish_writes_correlation_log(settings, tmp_path):
    pulse_md = tmp_path / "pulse_2026-05-15.md"
    pulse_md.write_text("# Groww Weekly Pulse\n\nContent here.", encoding="utf-8")
    pulse_txt = tmp_path / "pulse_2026-05-15.txt"
    pulse_txt.write_text("Plain pulse for email.", encoding="utf-8")

    publisher = PulsePublisher(settings=settings, project_root=PROJECT_ROOT)

    health = {"message": "ok"}
    append_result = {"status": "success", "document_id": settings.master_doc_id}
    draft_result = {"status": "success", "draft_id": "draft-001"}

    with patch.object(publisher._http, "health_check", return_value=health), patch.object(
        publisher._http, "post_tool", side_effect=[append_result, draft_result]
    ):
        result, log_path = publisher.publish(pulse_md, pulse_txt)

    assert result.draft_id == "draft-001"
    assert log_path.exists()
    logged = json.loads(log_path.read_text(encoding="utf-8"))
    assert logged["document_id"] == settings.master_doc_id
    assert logged["draft_id"] == "draft-001"
