"""Integration tests for CLI pipeline and verification of strict 1-Page PDF generation."""

import os
import tempfile
import numpy as np
import pandas as pd
from pypdf import PdfReader
import pytest

from wiki_market_validator.reporting.chart_generator import generate_market_validation_chart
from wiki_market_validator.reporting.pdf_builder import generate_executive_pdf_report


def test_pdf_strict_one_page_guarantee():
    """Verify generated PDF report strictly has exactly 1 page and does not overflow."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        chart_path = os.path.join(tmp_dir, "test_chart.png")
        pdf_path = os.path.join(tmp_dir, "test_report.pdf")

        # Create dummy chart
        dates = pd.date_range("2023-01-01", "2023-12-31")
        views = np.random.randint(50, 200, len(dates))
        df = pd.DataFrame({"date": dates, "views": views, "trend": views * 1.05, "is_spike": False})

        generate_market_validation_chart(
            primary_data=df,
            topic_name="Synthetic Test Topic",
            output_png_path=chart_path,
            theil_sen_info={"start_fitted": 100, "end_fitted": 150, "cagr": 25.0},
        )
        assert os.path.exists(chart_path)

        # Generate PDF with rich localization matrix
        loc_matrix = [
            {"rank": 1, "lang": "pl", "article_title": "Post", "views": 150000, "growth_pct": 35.0, "trust_score": 85.0, "priority_score": 82.5, "action_recommendation": "Priority 1 GO"},
            {"rank": 2, "lang": "cs", "article_title": "Půst", "views": 50000, "growth_pct": 40.0, "trust_score": 80.0, "priority_score": 75.0, "action_recommendation": "Priority 2 Expansion"},
            {"rank": 3, "lang": "uk", "article_title": "Голод", "views": 30000, "growth_pct": 10.0, "trust_score": 65.0, "priority_score": 55.0, "action_recommendation": "Priority 3 Monitor"},
            {"rank": 4, "lang": "de", "article_title": "Fasten", "views": 20000, "growth_pct": 5.0, "trust_score": 70.0, "priority_score": 50.0, "action_recommendation": "Monitor"},
        ]

        generate_executive_pdf_report(
            output_pdf_path=pdf_path,
            topic_name="Synthetic Test Topic with Very Long Title Explaining Market Potential",
            chart_png_path=chart_path,
            trust_data={
                "trust_score": 82.0,
                "trust_level": "High Trust",
                "recommendation": "Very strong and reliable organic demand signal.",
                "sub_scores": {
                    "human_integrity_score": 92.0,
                    "organic_continuity_score": 85.0,
                    "community_curation_score": 80.0,
                    "macro_outperformance_score": 75.0,
                },
            },
            trend_data={"cagr": 28.5, "trend_direction": "Rapid Growth"},
            tam_data={"tam_proxy_usd": 4_500_000.0, "market_scale_category": "Direct Scale"},
            seasonality_data={"academic_seasonality_index": 1.05, "seasonality_type": "Evergreen", "spike_traffic_share": 0.05},
            localization_matrix=loc_matrix,
            total_views=125000,
        )

        assert os.path.exists(pdf_path)

        # Inspect page count via PdfReader
        reader = PdfReader(pdf_path)
        page_count = len(reader.pages)
        assert page_count == 1, f"Expected strictly 1 page, but generated {page_count} pages!"
