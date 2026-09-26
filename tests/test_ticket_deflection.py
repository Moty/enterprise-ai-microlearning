"""Comprehensive test suite for the Automated Support Ticket Deflection Engine."""

import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from main import app as cli_app
from src.dashboard.app import app as fastapi_app
from src.pipeline.ticket_deflection import SupportTicket, TicketCluster, TicketDeflectionEngine


@pytest.fixture
def deflection_engine():
    return TicketDeflectionEngine()


@pytest.fixture
def sample_tickets(deflection_engine):
    return deflection_engine.get_sample_tickets()


def test_sample_tickets_loading(sample_tickets):
    """Verifies that sample enterprise support tickets are correctly loaded and typed."""
    assert len(sample_tickets) >= 5
    for t in sample_tickets:
        assert isinstance(t, SupportTicket)
        assert t.ticket_id.startswith("INC")
        assert t.resolution_time_minutes > 0
        assert t.cost_per_ticket_usd > 0
        assert len(t.title) > 0


def test_ticket_ingestion_from_json(tmp_path, deflection_engine):
    """Verifies ingestion of tickets from JSON exports."""
    raw_data = [
        {
            "ticket_id": "TEST_001",
            "source_system": "servicenow",
            "title": "Posting period F5201 error during invoice",
            "description": "Period closed",
            "error_code": "F5201",
            "category": "SAP FI/CO",
            "resolution_time_minutes": 20.0,
            "cost_per_ticket_usd": 40.0,
        },
        {
            "ticket_id": "TEST_002",
            "source_system": "servicenow",
            "title": "F5201 period closed company code 1000",
            "description": "Cannot post",
            "error_code": "F5201",
            "category": "SAP FI/CO",
            "resolution_time_minutes": 25.0,
            "cost_per_ticket_usd": 45.0,
        },
    ]
    json_file = tmp_path / "test_tickets.json"
    with open(json_file, "w", encoding="utf-8") as f:
        json.dump(raw_data, f)

    ingested = deflection_engine.ingest_from_file(json_file)
    assert len(ingested) == 2
    assert ingested[0].ticket_id == "TEST_001"
    assert ingested[1].error_code == "F5201"


def test_ticket_ingestion_from_csv(tmp_path, deflection_engine):
    """Verifies ingestion of tickets from CSV exports."""
    csv_file = tmp_path / "test_tickets.csv"
    with open(csv_file, "w", encoding="utf-8") as f:
        f.write("ticket_id,source_system,title,description,error_code,category,resolution_time_minutes,cost_per_ticket_usd\n")
        f.write("CSV_1,jira,Deficit of stock M7021,Stock issue,M7021,SAP MM,30.0,45.0\n")
        f.write("CSV_2,jira,M7021 goods issue blocked,Stock issue,M7021,SAP MM,20.0,45.0\n")

    ingested = deflection_engine.ingest_from_file(csv_file)
    assert len(ingested) == 2
    assert ingested[0].ticket_id == "CSV_1"
    assert ingested[1].error_code == "M7021"


def test_ticket_ingestion_invalid_file(tmp_path, deflection_engine):
    """Verifies error handling on missing or invalid ticket files."""
    with pytest.raises(FileNotFoundError):
        deflection_engine.ingest_from_file(tmp_path / "nonexistent.json")

    invalid_txt = tmp_path / "invalid.txt"
    invalid_txt.write_text("hello", encoding="utf-8")
    with pytest.raises(ValueError, match="Unsupported file format"):
        deflection_engine.ingest_from_file(invalid_txt)


def test_ticket_clustering_and_roi(deflection_engine, sample_tickets):
    """Verifies clustering algorithm, thresholding, and ROI calculations."""
    clusters = deflection_engine.cluster_tickets(sample_tickets, min_frequency=2)
    assert len(clusters) >= 2

    # Check top cluster (F5201 or M7021)
    f5201_cluster = next((c for c in clusters if c.primary_error_code == "F5201"), None)
    assert f5201_cluster is not None
    assert f5201_cluster.ticket_count == 3
    assert f5201_cluster.projected_monthly_savings_usd > 1000.0
    assert f5201_cluster.projected_hours_saved_monthly > 10.0
    assert f5201_cluster.deflection_priority == "CRITICAL"
    assert len(f5201_cluster.quick_fix_steps) == 3


def test_generate_deflection_tutorial(tmp_path, deflection_engine, sample_tickets):
    """Verifies autonomous 60s microlearning tutorial generation for ticket clusters."""
    clusters = deflection_engine.cluster_tickets(sample_tickets, min_frequency=2)
    target_cluster = clusters[0]

    result = deflection_engine.generate_deflection_tutorial(
        cluster=target_cluster,
        output_dir=tmp_path,
        dry_run=True,
        export_scorm=True,
    )

    assert result["cluster_id"] == target_cluster.cluster_id
    assert Path(result["video_path"]).exists() or "final.mp4" in result["video_path"]
    assert Path(result["kb_article_path"]).exists()
    assert Path(result["scorm_package_path"]).exists()
    assert result["projected_monthly_savings_usd"] > 0


def test_generate_kb_article_content(deflection_engine, sample_tickets):
    """Verifies markdown and HTML formatting of generated service desk KB articles."""
    clusters = deflection_engine.cluster_tickets(sample_tickets, min_frequency=2)
    c = clusters[0]

    from src.core.models import VideoLayout, VideoRenderJob, VideoScript
    job = VideoRenderJob(
        job_id="test_kb_job",
        script=VideoScript(
            script_id="test_kb_job",
            topic="Test Topic",
            persona_id="erp_functional_consultant",
            sections=[],
            post_caption="caption",
        ),
        layout=VideoLayout.WIDESCREEN_16_9,
    )

    kb_article = deflection_engine.generate_kb_article(job, c)
    assert "# Knowledge Base Article:" in kb_article
    assert "<video controls" in kb_article
    assert "Step-by-Step Self-Service Resolution" in kb_article
    assert "Verification Checklist" in kb_article


def test_dashboard_ticket_endpoints():
    """Verifies FastAPI dashboard endpoints for ticket clusters and deflection."""
    client = TestClient(fastapi_app)

    # 1. GET /api/tickets/clusters
    res = client.get("/api/tickets/clusters")
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, list)
    assert len(data) >= 2
    assert "cluster_id" in data[0]
    assert "projected_monthly_savings_usd" in data[0]

    # 2. POST /api/tickets/deflect/{cluster_id}
    first_cluster_id = data[0]["cluster_id"]
    post_res = client.post(f"/api/tickets/deflect/{first_cluster_id}?dry_run=true&export_scorm=true")
    assert post_res.status_code == 200
    res_data = post_res.json()
    assert res_data["cluster_id"] == first_cluster_id
    assert "kb_article_path" in res_data
    assert "projected_monthly_savings_usd" in res_data

    # 3. 404 on nonexistent cluster
    bad_res = client.post("/api/tickets/deflect/cluster_nonexistent")
    assert bad_res.status_code == 404


def test_cli_analyze_and_deflect():
    """Verifies CLI execution of analyze-tickets and deflect-ticket commands."""
    runner = CliRunner()

    # 1. analyze-tickets
    result = runner.invoke(cli_app, ["analyze-tickets", "--min-frequency", "2"])
    assert result.exit_code == 0
    assert "Support Ticket Deflection Analysis" in result.output
    assert "Total Projected Monthly Deflection Savings" in result.output

    # 2. deflect-ticket
    result_deflect = runner.invoke(cli_app, ["deflect-ticket", "--cluster-id", "cluster_f5201", "--dry-run"])
    assert result_deflect.exit_code == 0
    assert "Ticket Deflection Package Created Successfully" in result_deflect.output
    assert "Knowledge Base Article" in result_deflect.output
