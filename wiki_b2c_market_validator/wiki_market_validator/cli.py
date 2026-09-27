"""Unified CLI entrypoint for Wikipedia B2C Market Validator Agent Skill.

Outputs compact, token-efficient JSON for LLM agents (Claude Haiku 4.5 / Gemini Flash)
and orchestrates chart generation and 1-page executive PDF reporting.
"""

import argparse
import datetime
import json
import os
import sys
from typing import Any, Dict, List, Optional

import pandas as pd

from wiki_market_validator.analytics.hampel import apply_hampel_filter
from wiki_market_validator.analytics.stl_decomp import decompose_seasonality_and_spikes
from wiki_market_validator.analytics.theil_sen import calculate_robust_trend
from wiki_market_validator.analytics.trust_score import calculate_trust_score
from wiki_market_validator.api_client import WikimediaClient
from wiki_market_validator.metrics.localization_matrix import compute_localization_matrix
from wiki_market_validator.metrics.tam_proxy import calculate_tam_proxy
from wiki_market_validator.reporting.chart_generator import generate_market_validation_chart
from wiki_market_validator.reporting.pdf_builder import generate_executive_pdf_report


def run_pipeline(
    target_topic: str,
    langs: List[str],
    years: float = 2.0,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    benchmark_topic: Optional[str] = None,
    benchmark_market_size_usd: float = 10_000_000.0,
    target_titles_map: Optional[Dict[str, str]] = None,
    output_pdf: Optional[str] = None,
    output_png: Optional[str] = None,
    output_json: Optional[str] = None,
    use_cache: bool = True,
    audit_trust: bool = True,
) -> Dict[str, Any]:
    """Execute complete analysis pipeline across specified languages."""
    client = WikimediaClient()

    # Determine date range
    if end_date is None:
        today = datetime.date.today()
        end_dt = today - datetime.timedelta(days=1)
        end_str = end_dt.strftime("%Y%m%d")
    else:
        end_str = end_date.replace("-", "")[:8]
        end_dt = datetime.datetime.strptime(end_str, "%Y%m%d").date()

    if start_date is None:
        days_back = int(years * 365.25)
        start_dt = end_dt - datetime.timedelta(days=days_back)
        start_str = start_dt.strftime("%Y%m%d")
    else:
        start_str = start_date.replace("-", "")[:8]
        start_dt = datetime.datetime.strptime(start_str, "%Y%m%d").date()

    # Step 1: Multilingual resolution via Wikidata or explicit map
    primary_lang = langs[0]
    resolved_titles = client.resolve_multilingual_titles(
        target_topic, source_lang=primary_lang, target_langs=langs, use_cache=use_cache
    )
    if target_titles_map:
        for l_code, custom_title in target_titles_map.items():
            resolved_titles[l_code] = {"title": custom_title.replace(" ", "_"), "is_exact": True, "source": "user_override"}

    results_by_lang: Dict[str, Any] = {}
    candidate_records: List[Dict[str, Any]] = []
    primary_df: Optional[pd.DataFrame] = None
    primary_trend: Optional[Dict[str, Any]] = None
    comparison_series: List[Dict[str, Any]] = []

    benchmark_views = 0
    if benchmark_topic:
        b_proj = f"{primary_lang}.wikipedia.org"
        _, b_df, b_meta = client.get_article_pageviews(
            b_proj, benchmark_topic, start_str, end_str, agent="user", use_cache=use_cache
        )
        benchmark_views = b_meta.get("total_views", 0)

    for lang in langs:
        project = f"{lang}.wikipedia.org"
        title_info = resolved_titles.get(lang, {"title": target_topic, "is_exact": True})
        article_title = title_info["title"]

        # Fetch pageviews (human user)
        status, df, meta = client.get_article_pageviews(
            project, article_title, start_str, end_str, agent="user", use_cache=use_cache
        )

        if status == "PAGE_NOT_FOUND" or df.empty:
            results_by_lang[lang] = {
                "status": "PAGE_NOT_FOUND",
                "article_title": article_title,
                "error": f"Article '{article_title}' does not exist or has 0 views in {project}.",
            }
            continue

        # Fetch bot audit
        bot_audit = client.get_bot_audit(project, article_title, start_str, end_str, use_cache=use_cache)

        # Fetch edits count
        edits_data = client.get_article_edits(project, article_title, start_str, end_str, use_cache=use_cache)

        # Step 2: Analytics - Hampel Filter
        cleaned_y, outlier_mask, hampel_stats = apply_hampel_filter(df["views"].values, window_half_width=7, n_sigmas=3.0)
        df["cleaned_views"] = cleaned_y

        # Step 3: STL Decomposition & Seasonality
        decomp_df, seasonality_stats = decompose_seasonality_and_spikes(df, date_col="date", value_col="views")
        df["trend"] = decomp_df["trend"]
        df["is_spike"] = decomp_df["is_spike"]

        # Step 4: Theil-Sen Robust Trend
        trend_stats = calculate_robust_trend(df["cleaned_views"].values)

        # Step 5: Trust Score
        # Fetch macro language wiki aggregate growth
        agg_status, agg_df, agg_meta = client.get_aggregate_project_pageviews(
            project, start_str, end_str, granularity="monthly", use_cache=use_cache
        )
        macro_growth = 0.0
        if agg_status == "SUCCESS" and len(agg_df) >= 2:
            agg_start = agg_df["views"].iloc[:3].mean()
            agg_end = agg_df["views"].iloc[-3:].mean()
            if agg_start > 0:
                macro_growth = ((agg_end - agg_start) / agg_start) * 100.0

        trust_res = calculate_trust_score(
            bot_ratio=bot_audit.get("bot_ratio", 0.0),
            spike_traffic_share=seasonality_stats.get("spike_traffic_share", 0.0),
            edits_count=edits_data.get("total_edits", 0),
            topic_growth_pct=trend_stats.get("robust_growth_pct", 0.0),
            macro_wiki_growth_pct=macro_growth,
            academic_seasonality_index=seasonality_stats.get("academic_seasonality_index", 1.0),
            total_views=meta.get("total_views", 0),
        )

        # Save primary language data for charting
        if lang == primary_lang:
            primary_df = df
            primary_trend = trend_stats
        else:
            comparison_series.append(
                {
                    "label": f"{lang.upper()}: {article_title[:15]}",
                    "df": df[["date", "views"]],
                }
            )

        lang_summary = {
            "status": status,
            "article_title": article_title,
            "is_exact_sitelink": title_info.get("is_exact", True),
            "total_views": meta.get("total_views", 0),
            "mean_daily_views": round(meta.get("mean_views", 0.0), 1),
            "cagr": trend_stats.get("cagr", 0.0),
            "trend_direction": trend_stats.get("trend_direction", ""),
            "theil_sen_slope_daily": trend_stats.get("slope", 0.0),
            "trust_score": trust_res.get("trust_score", 0.0),
            "trust_level": trust_res.get("trust_level", ""),
            "bot_ratio": bot_audit.get("bot_ratio", 0.0),
            "academic_seasonality_index": seasonality_stats.get("academic_seasonality_index", 1.0),
            "seasonality_type": seasonality_stats.get("seasonality_type", ""),
            "spikes_detected": seasonality_stats.get("spike_count", 0),
            "recommendation": trust_res.get("recommendation", ""),
        }
        if audit_trust:
            lang_summary["trust_audit"] = trust_res

        results_by_lang[lang] = lang_summary

        candidate_records.append(
            {
                "lang": lang,
                "article_title": article_title,
                "views": meta.get("total_views", 0),
                "growth_pct": trend_stats.get("cagr", 0.0),
                "trust_score": trust_res.get("trust_score", 0.0),
            }
        )

    # Step 6: Multi-Market Localization Matrix
    loc_matrix = compute_localization_matrix(candidate_records)

    # Step 7: TAM Proxy (for primary topic)
    primary_views = results_by_lang.get(primary_lang, {}).get("total_views", 0)
    tam_res = calculate_tam_proxy(
        primary_views,
        benchmark_views=benchmark_views if benchmark_views > 0 else int(primary_views * 1.5),
        benchmark_market_size_usd=benchmark_market_size_usd,
    )

    # Step 8: Visualization & 1-Page PDF
    chart_file = None
    pdf_file = None

    if output_png or output_pdf:
        if output_png is None and output_pdf:
            # Derive PNG path from PDF
            output_png = output_pdf.replace(".pdf", "_chart.png")

        if primary_df is not None and not primary_df.empty:
            chart_file = generate_market_validation_chart(
                primary_data=primary_df,
                topic_name=target_topic,
                output_png_path=output_png,
                theil_sen_info=primary_trend,
                comparison_series=comparison_series,
            )

            if output_pdf:
                primary_info = results_by_lang.get(primary_lang, {})
                if loc_matrix and len(loc_matrix) > 0 and len(langs) > 1:
                    top_item = loc_matrix[0]
                    top_lang = top_item["lang"]
                    top_info = results_by_lang.get(top_lang, primary_info)
                    pdf_total_views = top_item.get("views", primary_info.get("total_views", 0))
                    pdf_trust_data = top_info.get("trust_audit", {"trust_score": top_info.get("trust_score", 50.0)})
                    pdf_trend_data = {"cagr": top_item.get("growth_pct", 0.0), "trend_direction": top_info.get("trend_direction", "")}
                    pdf_seasonality = {
                        "academic_seasonality_index": top_info.get("academic_seasonality_index", 1.0),
                        "seasonality_type": top_info.get("seasonality_type", "Evergreen"),
                        "spike_traffic_share": top_info.get("trust_audit", {}).get("sub_scores", {}).get("organic_continuity_score", 85.0) / 100.0,
                    }
                else:
                    pdf_total_views = primary_info.get("total_views", 0)
                    pdf_trust_data = primary_info.get("trust_audit", {"trust_score": primary_info.get("trust_score", 50.0)})
                    pdf_trend_data = primary_trend or {}
                    pdf_seasonality = {
                        "academic_seasonality_index": primary_info.get("academic_seasonality_index", 1.0),
                        "seasonality_type": primary_info.get("seasonality_type", "Evergreen"),
                        "spike_traffic_share": primary_info.get("trust_audit", {}).get("sub_scores", {}).get("organic_continuity_score", 80.0) / 100.0,
                    }

                pdf_file = generate_executive_pdf_report(
                    output_pdf_path=output_pdf,
                    topic_name=target_topic,
                    chart_png_path=chart_file,
                    trust_data=pdf_trust_data,
                    trend_data=pdf_trend_data,
                    tam_data=tam_res,
                    seasonality_data=pdf_seasonality,
                    localization_matrix=loc_matrix,
                    total_views=pdf_total_views,
                    timeframe_str=f"{start_str} to {end_str}",
                )

    # Final Payload (concise, structured JSON for AI Agent)
    payload = {
        "target_topic": target_topic,
        "timeframe": {"start": start_str, "end": end_str, "years": years},
        "benchmark_topic": benchmark_topic,
        "tam_proxy": tam_res,
        "results_by_language": results_by_lang,
        "localization_ranking": loc_matrix,
        "artifacts": {
            "chart_png": chart_file,
            "executive_pdf": pdf_file,
        },
    }

    if output_json:
        os.makedirs(os.path.dirname(os.path.abspath(output_json)), exist_ok=True)
        with open(output_json, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

    return payload


def main():
    """CLI Parser."""
    parser = argparse.ArgumentParser(
        description="Wikipedia B2C Market Validator - Autonomous Agent Skill CLI",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--target", required=True, help="Target topic or Wikipedia article title")
    parser.add_argument("--target-titles", default=None, help="Explicit mapping of language to title, e.g. 'pl:Głodówka,cs:Přerušovaný_půst'")
    parser.add_argument("--langs", default="en", help="Comma-separated language codes, e.g. 'pl,cs' or 'uk'")
    parser.add_argument("--years", type=float, default=2.0, help="Number of years to analyze (e.g. 2.0 or 1.0)")
    parser.add_argument("--start", default=None, help="Explicit start date YYYYMMDD")
    parser.add_argument("--end", default=None, help="Explicit end date YYYYMMDD")
    parser.add_argument("--benchmark", default=None, help="Benchmark topic for TAM estimation")
    parser.add_argument("--output-pdf", default=None, help="Path to generate 1-page executive PDF")
    parser.add_argument("--output-png", default=None, help="Path to generate 300 DPI chart PNG")
    parser.add_argument("--output-json", default=None, help="Path to save full JSON output")
    parser.add_argument("--no-cache", action="store_true", help="Disable SQLite cache")

    args = parser.parse_args()

    langs_list = [lg.strip().lower() for lg in args.langs.split(",") if lg.strip()]

    target_titles_map = None
    if args.target_titles:
        target_titles_map = {}
        for pair in args.target_titles.split(","):
            if ":" in pair:
                l_part, t_part = pair.split(":", 1)
                target_titles_map[l_part.strip().lower()] = t_part.strip()

    result = run_pipeline(
        target_topic=args.target,
        langs=langs_list,
        years=args.years,
        start_date=args.start,
        end_date=args.end,
        benchmark_topic=args.benchmark,
        target_titles_map=target_titles_map,
        output_pdf=args.output_pdf,
        output_png=args.output_png,
        output_json=args.output_json,
        use_cache=not args.no_cache,
    )

    # Print compact JSON to stdout with UTF-8
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
