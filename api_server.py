from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, HTMLResponse
import asyncio
import json
import io
import csv
import logging
from datetime import datetime, date, timedelta
import pytz
from spx_calculator import SPXStraddleCalculator
from spy_calculator import SPYCalculator
from discord_notifier import DiscordNotifier
from gist_publisher import GistPublisher
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO")),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="SPX 0DTE Straddle Calculator API",
    description="Calculate and track SPX 0DTE straddle costs using Polygon.io data",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global instances
calculator = None
spy_calculator = None
discord_notifier = None
gist_publisher = None

@app.on_event("startup")
async def startup_event():
    """Initialize the SPX calculator, SPY calculator, Discord notifier, and Gist publisher on startup"""
    global calculator, spy_calculator, discord_notifier, gist_publisher
    
    # Initialize calculators
    polygon_api_key = os.getenv("POLYGON_API_KEY")
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
    
    if not polygon_api_key:
        raise ValueError("POLYGON_API_KEY environment variable is required")
    
    # Initialize SPX calculator
    calculator = SPXStraddleCalculator(polygon_api_key, redis_url)
    await calculator.initialize()
    logger.info("SPX Straddle Calculator initialized")
    
    # Initialize SPY calculator
    spy_calculator = SPYCalculator()
    logger.info("SPY Expected Move Calculator initialized")
    
    # Initialize Discord notifier
    discord_notifier = DiscordNotifier()
    await discord_notifier.initialize()
    if discord_notifier.is_enabled():
        logger.info("Discord notifier initialized and connected")
    else:
        logger.info("Discord notifier disabled or not configured")
    
    # Initialize Gist publisher
    gist_publisher = GistPublisher()
    if gist_publisher.is_enabled():
        logger.info("Gist publisher initialized and ready")
    else:
        logger.info("Gist publisher disabled or not configured")

@app.on_event("shutdown")
async def shutdown_event():
    """Clean up on shutdown"""
    global calculator, spy_calculator, discord_notifier, gist_publisher
    if calculator:
        await calculator.close()
    if discord_notifier:
        await discord_notifier.close()

# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.now(pytz.timezone('US/Eastern')).isoformat(),
        "services": {
            "calculator": calculator is not None,
            "discord": discord_notifier.is_enabled() if discord_notifier else False,
            "gist_publisher": gist_publisher.is_enabled() if gist_publisher else False
        }
    }

# SPX Straddle endpoints
@app.get("/api/spx-straddle/today")
async def get_spx_straddle_today():
    """Get today's SPX straddle cost data"""
    try:
        result = await calculator.get_spx_straddle_cost()
        return result
    except Exception as e:
        logger.error(f"Error getting today's straddle data: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve SPX straddle data")

@app.post("/api/spx-straddle/calculate")
async def calculate_spx_straddle(background_tasks: BackgroundTasks, notify_discord: bool = True):
    """Trigger SPX straddle cost calculation with optional Discord notification"""
    try:
        result = await calculator.calculate_spx_straddle_cost()
        
        # Send Discord notification in background if enabled and requested
        if notify_discord and discord_notifier and discord_notifier.is_enabled():
            background_tasks.add_task(discord_notifier.notify_straddle_result, result)
        
        return result
    except Exception as e:
        logger.error(f"Error calculating straddle cost: {e}")
        
        # Send error notification to Discord
        if discord_notifier and discord_notifier.is_enabled():
            background_tasks.add_task(discord_notifier.notify_error, str(e), "Straddle Calculation")
        
        raise HTTPException(status_code=500, detail="Failed to calculate SPX straddle cost")

@app.get("/api/spx-straddle/history")
async def get_spx_straddle_history(days: int = 30):
    """Get historical SPX straddle data"""
    try:
        if days < 1 or days > 1000:
            raise HTTPException(status_code=400, detail="Days parameter must be between 1 and 1000")
        
        result = await calculator.get_spx_straddle_history(days)
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting straddle history: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve SPX straddle history")

@app.get("/api/spx-straddle/statistics")
async def get_spx_straddle_statistics(days: int = 30):
    """Get SPX straddle statistical analysis"""
    try:
        if days < 1 or days > 1000:
            raise HTTPException(status_code=400, detail="Days parameter must be between 1 and 1000")
        
        result = await calculator.calculate_spx_straddle_statistics(days)
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting straddle statistics: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve SPX straddle statistics")

# Quick access endpoints for daily timeframes
@app.get("/api/spx-straddle/statistics/daily")
async def get_daily_timeframes_summary():
    """Get summary of all daily timeframes (1D-7D) for quick access"""
    try:
        daily_results = {}
        
        for days in [1, 2, 3, 4, 5, 6, 7]:
            try:
                stats = await calculator.calculate_spx_straddle_statistics(days)
                if stats.get('status') == 'success':
                    daily_results[f"{days}d"] = {
                        "period_days": days,
                        "data_points": stats.get('data_points', 0),
                        "mean_cost": stats.get('descriptive_stats', {}).get('mean', 0),
                        "median_cost": stats.get('descriptive_stats', {}).get('median', 0),
                        "std_dev": stats.get('descriptive_stats', {}).get('std_dev', 0),
                        "trend_direction": stats.get('trend_analysis', {}).get('direction', 'unknown'),
                        "volatility_category": stats.get('volatility_analysis', {}).get('category', 'unknown'),
                        "min_cost": stats.get('descriptive_stats', {}).get('min', 0),
                        "max_cost": stats.get('descriptive_stats', {}).get('max', 0)
                    }
            except Exception as e:
                logger.warning(f"Failed to get {days}D statistics: {e}")
                continue
        
        return {
            "status": "success",
            "daily_timeframes": daily_results,
            "available_periods": list(daily_results.keys()),
            "timestamp": datetime.now(pytz.timezone('US/Eastern')).isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error getting daily timeframes summary: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve daily timeframes summary")

@app.get("/api/spx-straddle/statistics/multi-timeframe")
async def get_multi_timeframe_statistics():
    """Get SPX straddle statistics across multiple timeframes"""
    try:
        # Calculate YTD (Year-to-Date) days
        et_tz = pytz.timezone('US/Eastern')
        current_date = datetime.now(et_tz).date()
        year_start = date(current_date.year, 1, 1)
        ytd_days = (current_date - year_start).days + 1  # +1 to include today
        
        # Define timeframes (in days) - include daily granularity and YTD as dynamic timeframe
        daily_timeframes = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14]
        # Include timeframes up to 2 years (720 days) - no need to go beyond our data range
        weekly_monthly_timeframes = [30, 45, 60, 90, 120, 180, 240, 360, 540, 720]
        timeframes = daily_timeframes + weekly_monthly_timeframes
        
        # Add YTD if it's different from existing timeframes and reasonable
        if ytd_days >= 5 and ytd_days not in timeframes:
            timeframes.append(ytd_days)
            timeframes.sort()
        
        results = {
            "status": "success",
            "timeframes": {},
            "summary": {
                "available_timeframes": [],
                "data_coverage": {},
                "timestamp": datetime.now(pytz.timezone('US/Eastern')).isoformat()
            }
        }
        
        for days in timeframes:
            try:
                stats = await calculator.calculate_spx_straddle_statistics(days)
                
                # Show all timeframes regardless of data points - we want to see running trends
                if stats.get('status') == 'success' and stats.get('data_points', 0) > 0:
                    # Determine timeframe key (YTD gets special treatment)
                    if days == ytd_days:
                        timeframe_key = "ytd"
                        timeframe_label = f"YTD ({days}d)"
                    else:
                        timeframe_key = f"{days}d"
                        timeframe_label = f"{days}d"
                    
                    # Track actual valid market days - no confusing "coverage" calculations
                    valid_market_days = stats.get('data_points', 0)
                    
                    # Only include timeframes with sufficient data (5+ valid market days)
                    results["timeframes"][timeframe_key] = {
                        "period_days": days,
                        "period_label": timeframe_label,
                        "is_ytd": days == ytd_days,
                        "valid_market_days": valid_market_days,
                        "descriptive_stats": stats.get('descriptive_stats', {}),
                        "trend_analysis": stats.get('trend_analysis', {}),
                        "volatility_analysis": stats.get('volatility_analysis', {}),
                        "recent_comparison": stats.get('recent_comparison', {}),
                        "percentiles": {
                            "25th": stats.get('descriptive_stats', {}).get('percentile_25', 0),
                            "75th": stats.get('descriptive_stats', {}).get('percentile_75', 0),
                            "90th": stats.get('descriptive_stats', {}).get('percentile_90', 0),
                            "95th": stats.get('descriptive_stats', {}).get('percentile_95', 0)
                        }
                    }
                    results["summary"]["available_timeframes"].append(days)
                    
                    results["summary"]["data_coverage"][timeframe_key] = {
                        "valid_market_days": valid_market_days,
                        "period_days": days,
                        "is_ytd": days == ytd_days
                    }
            
            except Exception as e:
                logger.warning(f"Failed to calculate {days}-day statistics: {e}")
                continue
        
        # Add summary insights
        if results["timeframes"]:
            # Find timeframe with most data
            max_data_timeframe = max(results["timeframes"].keys(), 
                                   key=lambda x: results["timeframes"][x]["valid_market_days"])
            
            results["summary"]["recommended_timeframe"] = max_data_timeframe
            results["summary"]["total_timeframes"] = len(results["timeframes"])
            
            # Add YTD information
            results["summary"]["ytd_info"] = {
                "ytd_days": ytd_days,
                "year": current_date.year,
                "ytd_included": "ytd" in results["timeframes"],
                "ytd_start_date": year_start.isoformat(),
                "ytd_end_date": current_date.isoformat()
            }
            
            # Calculate trend consistency across timeframes
            trends = [tf["trend_analysis"].get("direction", "unknown") 
                     for tf in results["timeframes"].values()]
            trend_consistency = len(set(trends)) == 1 if trends else False
            results["summary"]["trend_consistency"] = trend_consistency
            
        else:
            results["status"] = "insufficient_data"
            results["message"] = "Insufficient data for multi-timeframe analysis (need 5+ data points)"
        
        return results
        
    except Exception as e:
        logger.error(f"Error getting multi-timeframe statistics: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve multi-timeframe statistics")

@app.get("/api/spx-straddle/statistics/full-report")
async def get_full_statistics_report():
    """Get a comprehensive formatted text report of all timeframe statistics for GitHub Gist"""
    try:
        # Get multi-timeframe data
        multi_stats = await get_multi_timeframe_statistics()
        
        if multi_stats.get('status') != 'success':
            raise HTTPException(status_code=500, detail="Failed to retrieve statistics data")
        
        timeframes = multi_stats.get('timeframes', {})
        summary = multi_stats.get('summary', {})
        
        # Generate formatted report
        et_tz = pytz.timezone('US/Eastern')
        timestamp = datetime.now(et_tz).strftime('%Y-%m-%d %H:%M:%S ET')
        
        report = f"""# SPX 0DTE Straddle Complete Multi-Timeframe Analysis
Generated: {timestamp}
Total Historical Data: {summary.get('total_valid_market_days', 'N/A')} trading days

## Executive Summary
This comprehensive analysis covers {len(timeframes)} timeframes from daily (1D) to long-term (900D) perspectives, providing insights into SPX 0DTE straddle cost volatility patterns across different time horizons.

## Detailed Timeframe Analysis

"""
        
        # Sort timeframes by period days for logical progression
        sorted_timeframes = sorted(timeframes.items(), key=lambda x: x[1].get('period_days', 0))
        
        for timeframe_key, tf_data in sorted_timeframes:
            period_label = tf_data.get('period_label', timeframe_key)
            period_days = tf_data.get('period_days', 0)
            valid_market_days = tf_data.get('valid_market_days', 0)
            coverage = tf_data.get('coverage_percentage', 0)
            
            # Descriptive stats
            desc_stats = tf_data.get('descriptive_stats', {})
            mean_cost = desc_stats.get('mean', 0)
            median_cost = desc_stats.get('median', 0)
            std_dev = desc_stats.get('std_dev', 0)
            min_cost = desc_stats.get('min', 0)
            max_cost = desc_stats.get('max', 0)
            
            # Trend analysis
            trend_analysis = tf_data.get('trend_analysis', {})
            trend_direction = trend_analysis.get('direction', 'unknown')
            trend_strength = trend_analysis.get('strength', 'unknown')
            
            # Volatility analysis
            vol_analysis = tf_data.get('volatility_analysis', {})
            vol_category = vol_analysis.get('category', 'unknown')
            coefficient_of_variation = vol_analysis.get('coefficient_of_variation', 0)
            
            # Percentiles
            percentiles = tf_data.get('percentiles', {})
            p25 = percentiles.get('25th', 0)
            p75 = percentiles.get('75th', 0)
            p90 = percentiles.get('90th', 0)
            p95 = percentiles.get('95th', 0)
            
            # Format section
            report += f"""### {period_label}
**Data Coverage:** {valid_market_days} valid market days

**Central Tendency:**
- Mean: ${mean_cost:.2f}
- Median: ${median_cost:.2f}
- Standard Deviation: ${std_dev:.2f}

**Range & Distribution:**
- Minimum: ${min_cost:.2f}
- Maximum: ${max_cost:.2f}
- 25th Percentile: ${p25:.2f}
- 75th Percentile: ${p75:.2f}
- 90th Percentile: ${p90:.2f}
- 95th Percentile: ${p95:.2f}

**Trend Analysis:**
- Direction: {trend_direction.title()}
- Strength: {trend_strength.title()}

**Volatility Profile:**
- Category: {vol_category.title()}
- Coefficient of Variation: {coefficient_of_variation:.1f}%

---

"""
        
        # Add comparative analysis
        report += """## Comparative Analysis

### Volatility Regime Classification
"""
        
        # Group by volatility categories
        vol_categories = {'low': [], 'medium': [], 'high': []}
        for timeframe_key, tf_data in timeframes.items():
            vol_cat = tf_data.get('volatility_analysis', {}).get('category', 'unknown')
            if vol_cat in vol_categories:
                vol_categories[vol_cat].append((timeframe_key, tf_data))
        
        for vol_cat, timeframe_list in vol_categories.items():
            if timeframe_list:
                report += f"\n**{vol_cat.title()} Volatility Timeframes:**\n"
                for tf_key, tf_data in timeframe_list:
                    period_label = tf_data.get('period_label', tf_key)
                    mean_cost = tf_data.get('descriptive_stats', {}).get('mean', 0)
                    cv = tf_data.get('volatility_analysis', {}).get('coefficient_of_variation', 0)
                    report += f"- {period_label}: ${mean_cost:.2f} avg (CV: {cv:.1f}%)\n"
        
        # Add trend analysis summary
        report += "\n### Trend Direction Summary\n"
        trend_categories = {'increasing': [], 'decreasing': [], 'stable': []}
        for timeframe_key, tf_data in timeframes.items():
            trend_dir = tf_data.get('trend_analysis', {}).get('direction', 'unknown')
            if trend_dir in trend_categories:
                trend_categories[trend_dir].append((timeframe_key, tf_data))
        
        for trend_dir, timeframe_list in trend_categories.items():
            if timeframe_list:
                report += f"\n**{trend_dir.title()} Trend Timeframes:**\n"
                for tf_key, tf_data in timeframe_list:
                    period_label = tf_data.get('period_label', tf_key)
                    mean_cost = tf_data.get('descriptive_stats', {}).get('mean', 0)
                    report += f"- {period_label}: ${mean_cost:.2f} avg\n"
        
        # Add methodology note
        report += f"""

## Methodology
- **Data Source:** Polygon.io SPX and SPXW options data
- **Calculation:** At-the-money (ATM) straddle cost at 9:30 AM ET
- **Strike Selection:** Rounded to nearest $5 increment
- **Timeframes:** {len(timeframes)} periods from 1 day to 900 days
- **Analysis Date:** {timestamp}

## Disclaimer
This analysis is for educational and informational purposes only. Past performance does not guarantee future results. Options trading involves significant risk and may not be suitable for all investors.
"""
        
        return {
            "status": "success",
            "report": report,
            "metadata": {
                "timestamp": timestamp,
                "timeframes_analyzed": len(timeframes),
                "total_valid_market_days": summary.get('total_valid_market_days', 0),
                "report_length": len(report)
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating full statistics report: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate statistics report")

@app.post("/api/spx-straddle/statistics/publish-gist")
async def publish_statistics_gist():
    """Publish the full statistics report as a GitHub Gist"""
    try:
        if not gist_publisher or not gist_publisher.is_enabled():
            raise HTTPException(status_code=503, detail="GitHub Gist publishing is not configured")
        
        # Get the full report
        full_report_response = await get_full_statistics_report()
        
        if full_report_response.get("status") != "success":
            raise HTTPException(status_code=500, detail="Failed to generate statistics report")
        
        # Publish to Gist
        gist_result = await gist_publisher.publish_analysis_report(
            full_report_response["report"],
            full_report_response["metadata"]
        )
        
        if not gist_result or gist_result.get("status") != "success":
            error_msg = gist_result.get("error", "Unknown error") if gist_result else "Failed to create Gist"
            raise HTTPException(status_code=500, detail=f"Failed to publish Gist: {error_msg}")
        
        return {
            "status": "success",
            "message": "Analysis report published to GitHub Gist",
            "gist": {
                "url": gist_result["url"],
                "id": gist_result["id"],
                "created_at": gist_result["created_at"],
                "description": gist_result["description"]
            },
            "report_metadata": full_report_response["metadata"]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error publishing statistics Gist: {e}")
        raise HTTPException(status_code=500, detail="Failed to publish statistics Gist")

@app.get("/api/spx-straddle/patterns")
async def get_spx_straddle_patterns(days: int = 30):
    """Get SPX straddle pattern analysis"""
    try:
        if days < 1 or days > 1000:
            raise HTTPException(status_code=400, detail="Days parameter must be between 1 and 1000")
        
        # This method doesn't exist in the calculator yet, so let's create a placeholder
        return {
            "status": "not_implemented",
            "message": "Pattern analysis not yet implemented",
            "timestamp": datetime.now(pytz.timezone('US/Eastern')).isoformat()
        }
    except Exception as e:
        logger.error(f"Error getting straddle patterns: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve SPX straddle patterns")

@app.get("/api/spx-straddle/export/csv")
async def export_spx_straddle_csv(days: int = 30):
    """Export SPX straddle historical data as CSV"""
    try:
        if days < 1 or days > 1000:
            raise HTTPException(status_code=400, detail="Days parameter must be between 1 and 1000")
        
        # Get historical data
        result = await calculator.get_spx_straddle_history(days)
        
        if result.get('status') != 'success' or not result.get('data'):
            raise HTTPException(status_code=404, detail="No historical data available")
        
        # Convert to CSV format
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write header
        writer.writerow(['Date', 'SPX_Price_930AM', 'ATM_Strike', 'Call_Price_931AM', 'Put_Price_931AM', 'Straddle_Cost', 'Timestamp'])
        
        # Write data
        for record in result['data']:
            writer.writerow([
                record.get('date', ''),
                record.get('spx_price_930am', ''),
                record.get('atm_strike', ''),
                record.get('call_price_931am', ''),
                record.get('put_price_931am', ''),
                record.get('straddle_cost', ''),
                record.get('timestamp', '')
            ])
        
        output.seek(0)
        
        # Return as streaming response
        return StreamingResponse(
            io.BytesIO(output.getvalue().encode()),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename=spx_straddle_history_{days}days.csv"}
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error exporting CSV: {e}")
        raise HTTPException(status_code=500, detail="Failed to export SPX straddle data")

@app.get("/api/spx-straddle/status")
async def get_spx_straddle_status():
    """Get SPX straddle system health and status"""
    try:
        # Get current straddle data to check status
        straddle_data = await calculator.get_spx_straddle_cost()
        
        status = {
            "system_status": "operational",
            "last_calculation": straddle_data.get('last_calculation_date'),
            "calculation_status": straddle_data.get('calculation_status', 'unknown'),
            "redis_connected": calculator.redis is not None,
            "polygon_configured": True,  # If we got here, Polygon is configured
            "discord_enabled": discord_notifier.is_enabled() if discord_notifier else False,
            "gist_publisher_enabled": gist_publisher.is_enabled() if gist_publisher else False,
            "timestamp": datetime.now(pytz.timezone('US/Eastern')).isoformat()
        }
        
        return status
        
    except Exception as e:
        logger.error(f"Error getting system status: {e}")
        return {
            "system_status": "error",
            "error": str(e),
            "timestamp": datetime.now(pytz.timezone('US/Eastern')).isoformat()
        }

# Chart data endpoints
@app.get("/api/spx-straddle/chart-data")
async def get_chart_data(days: int = 730, timeframe: str = "daily"):
    """
    Get chart data for SPX straddle trends
    
    Args:
        days: Number of days of historical data (default 730 = ~2 years)
        timeframe: Chart timeframe - 'daily', 'weekly', 'monthly'
    """
    try:
        # Get historical data
        history = await calculator.get_spx_straddle_history(days)
        
        if history.get('status') != 'success' or not history.get('data'):
            return {
                "status": "no_data",
                "message": "No historical data available for charting",
                "days_requested": days
            }
        
        data_points = history['data']
        
        # Process data for charting
        chart_data = _process_chart_data(data_points, timeframe)
        
        # Calculate trend line using linear regression
        trend_line = _calculate_trend_line(chart_data['costs']) if chart_data['costs'] else []
        
        # Calculate moving averages
        ma_7 = _calculate_moving_average(chart_data['costs'], 7) if len(chart_data['costs']) >= 7 else []
        ma_30 = _calculate_moving_average(chart_data['costs'], 30) if len(chart_data['costs']) >= 30 else []
        
        return {
            "status": "success",
            "timeframe": timeframe,
            "days_requested": days,
            "data_points": len(chart_data['dates']),
            "date_range": {
                "start": chart_data['dates'][0] if chart_data['dates'] else None,
                "end": chart_data['dates'][-1] if chart_data['dates'] else None
            },
            "chart_data": {
                "dates": chart_data['dates'],
                "costs": chart_data['costs'],
                "trend_line": trend_line,
                "moving_averages": {
                    "ma_7": ma_7,
                    "ma_30": ma_30
                },
                "statistics": {
                    "min": min(chart_data['costs']) if chart_data['costs'] else 0,
                    "max": max(chart_data['costs']) if chart_data['costs'] else 0,
                    "mean": sum(chart_data['costs']) / len(chart_data['costs']) if chart_data['costs'] else 0,
                    "range_low": [min(chart_data['costs'])] * len(chart_data['dates']) if chart_data['costs'] else [],
                    "range_high": [max(chart_data['costs'])] * len(chart_data['dates']) if chart_data['costs'] else []
                }
            }
        }
        
    except Exception as e:
        logger.error(f"Error generating chart data: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate chart data")

@app.get("/api/spx-straddle/chart-config/{chart_type}")
async def get_chart_config(chart_type: str, days: int = 730):
    """
    Get Chart.js configuration for different chart types
    
    Args:
        chart_type: 'trend', 'comparison', 'volatility', 'range'
        days: Historical data period
    """
    try:
        # Get chart data
        chart_data_response = await get_chart_data(days, "daily")
        
        if chart_data_response.get('status') != 'success':
            return chart_data_response
        
        chart_data = chart_data_response['chart_data']
        
        base_config = {
            "type": "line",
            "options": {
                "responsive": True,
                "maintainAspectRatio": False,
                "scales": {
                    "x": {
                        "title": {
                            "display": True,
                            "text": "Date"
                        }
                    },
                    "y": {
                        "title": {
                            "display": True,
                            "text": "Straddle Cost ($)"
                        },
                        "beginAtZero": False
                    }
                },
                "plugins": {
                    "legend": {
                        "display": True,
                        "position": "top"
                    },
                    "tooltip": {
                        "mode": "index",
                        "intersect": False
                    }
                },
                "interaction": {
                    "mode": "nearest",
                    "axis": "x",
                    "intersect": False
                }
            }
        }
        
        datasets = []
        
        if chart_type == "trend":
            datasets = [
                {
                    "label": "Straddle Cost",
                    "data": [{"x": chart_data['dates'][i], "y": chart_data['costs'][i]} for i in range(len(chart_data['dates']))],
                    "borderColor": "rgb(37, 99, 235)",
                    "backgroundColor": "rgba(37, 99, 235, 0.1)",
                    "borderWidth": 2,
                    "fill": False,
                    "tension": 0.1,
                    "pointRadius": 1,
                    "pointHoverRadius": 4
                },
                {
                    "label": "Trend Line",
                    "data": [{"x": chart_data['dates'][i], "y": chart_data['trend_line'][i]} for i in range(len(chart_data['trend_line']))],
                    "borderColor": "rgb(220, 38, 38)",
                    "backgroundColor": "transparent",
                    "borderDash": [8, 4],
                    "borderWidth": 3,
                    "fill": False,
                    "pointRadius": 0,
                    "tension": 0
                }
            ]
        elif chart_type == "comparison":
            datasets = [
                {
                    "label": "Straddle Cost",
                    "data": [{"x": chart_data['dates'][i], "y": chart_data['costs'][i]} for i in range(len(chart_data['dates']))],
                    "borderColor": "rgb(37, 99, 235)",
                    "backgroundColor": "rgba(37, 99, 235, 0.1)",
                    "borderWidth": 2,
                    "fill": False,
                    "tension": 0.1,
                    "pointRadius": 1,
                    "pointHoverRadius": 4
                }
            ]
            
            if chart_data['moving_averages']['ma_7']:
                datasets.append({
                    "label": "7-Day MA",
                    "data": [{"x": chart_data['dates'][i], "y": chart_data['moving_averages']['ma_7'][i]} for i in range(len(chart_data['moving_averages']['ma_7']))],
                    "borderColor": "rgb(22, 163, 74)",
                    "backgroundColor": "transparent",
                    "borderWidth": 2,
                    "fill": False,
                    "pointRadius": 0,
                    "tension": 0.2
                })
            
            if chart_data['moving_averages']['ma_30']:
                datasets.append({
                    "label": "30-Day MA",
                    "data": [{"x": chart_data['dates'][i], "y": chart_data['moving_averages']['ma_30'][i]} for i in range(len(chart_data['moving_averages']['ma_30']))],
                    "borderColor": "rgb(147, 51, 234)",
                    "backgroundColor": "transparent",
                    "borderWidth": 2,
                    "fill": False,
                    "pointRadius": 0,
                    "tension": 0.2
                })
        elif chart_type == "range":
            datasets = [
                {
                    "label": "Straddle Cost",
                    "data": [{"x": chart_data['dates'][i], "y": chart_data['costs'][i]} for i in range(len(chart_data['dates']))],
                    "borderColor": "rgb(37, 99, 235)",
                    "backgroundColor": "rgba(37, 99, 235, 0.2)",
                    "borderWidth": 2,
                    "fill": False,
                    "tension": 0.1,
                    "pointRadius": 1,
                    "pointHoverRadius": 4
                },
                {
                    "label": f"Range (${chart_data['statistics']['min']:.2f} - ${chart_data['statistics']['max']:.2f})",
                    "data": [
                        {"x": chart_data['dates'][0], "y": chart_data['statistics']['min']},
                        {"x": chart_data['dates'][-1], "y": chart_data['statistics']['min']}
                    ],
                    "borderColor": "rgba(239, 68, 68, 0.5)",
                    "backgroundColor": "transparent",
                    "borderDash": [3, 3],
                    "fill": False,
                    "pointRadius": 0
                },
                {
                    "label": "",
                    "data": [
                        {"x": chart_data['dates'][0], "y": chart_data['statistics']['max']},
                        {"x": chart_data['dates'][-1], "y": chart_data['statistics']['max']}
                    ],
                    "borderColor": "rgba(239, 68, 68, 0.5)",
                    "backgroundColor": "transparent",
                    "borderDash": [3, 3],
                    "fill": False,
                    "pointRadius": 0
                }
            ]
        else:
            raise HTTPException(status_code=400, detail="Invalid chart type. Use 'trend', 'comparison', or 'range'")
        
        config = {
            **base_config,
            "data": {
                "datasets": datasets
            }
        }
        
        return {
            "status": "success",
            "chart_type": chart_type,
            "config": config,
            "data_points": len(chart_data['dates']),
            "date_range": chart_data_response['date_range']
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating chart config: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate chart configuration")

# Helper functions for chart data processing
def _process_chart_data(data_points, timeframe):
    """Process raw data points for charting"""
    if timeframe == "daily":
        # Return data as-is for daily charts
        dates = [point.get('date', '') for point in data_points]
        costs = [point.get('straddle_cost', 0) for point in data_points]
        return {"dates": dates, "costs": costs}
    elif timeframe == "weekly":
        # Group by week (simplified - could be enhanced)
        return _group_data_by_week(data_points)
    elif timeframe == "monthly":
        # Group by month (simplified - could be enhanced)
        return _group_data_by_month(data_points)
    else:
        # Default to daily
        dates = [point.get('date', '') for point in data_points]
        costs = [point.get('straddle_cost', 0) for point in data_points]
        return {"dates": dates, "costs": costs}

def _group_data_by_week(data_points):
    """Group data points by week"""
    # Simplified weekly grouping - average costs per week
    weekly_data = {}
    for point in data_points:
        date_str = point.get('date', '')
        if date_str:
            # Get week start date (Monday)
            date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
            week_start = date_obj - timedelta(days=date_obj.weekday())
            week_key = week_start.strftime('%Y-%m-%d')
            
            if week_key not in weekly_data:
                weekly_data[week_key] = []
            weekly_data[week_key].append(point.get('straddle_cost', 0))
    
    # Calculate averages
    dates = sorted(weekly_data.keys())
    costs = [sum(weekly_data[week]) / len(weekly_data[week]) for week in dates]
    
    return {"dates": dates, "costs": costs}

def _group_data_by_month(data_points):
    """Group data points by month"""
    # Simplified monthly grouping - average costs per month
    monthly_data = {}
    for point in data_points:
        date_str = point.get('date', '')
        if date_str:
            # Get month start date
            date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
            month_key = date_obj.strftime('%Y-%m-01')
            
            if month_key not in monthly_data:
                monthly_data[month_key] = []
            monthly_data[month_key].append(point.get('straddle_cost', 0))
    
    # Calculate averages
    dates = sorted(monthly_data.keys())
    costs = [sum(monthly_data[month]) / len(monthly_data[month]) for month in dates]
    
    return {"dates": dates, "costs": costs}

def _calculate_trend_line(costs):
    """Calculate linear trend line using simple linear regression"""
    if len(costs) < 2:
        return costs
    
    n = len(costs)
    x_values = list(range(n))
    x_mean = sum(x_values) / n
    y_mean = sum(costs) / n
    
    # Calculate slope
    numerator = sum((x_values[i] - x_mean) * (costs[i] - y_mean) for i in range(n))
    denominator = sum((x - x_mean) ** 2 for x in x_values)
    
    if denominator == 0:
        return costs
    
    slope = numerator / denominator
    intercept = y_mean - slope * x_mean
    
    # Generate trend line points
    trend_line = [slope * x + intercept for x in x_values]
    return trend_line

def _calculate_moving_average(costs, window):
    """Calculate moving average"""
    if len(costs) < window:
        return []
    
    moving_avg = []
    for i in range(len(costs)):
        if i < window - 1:
            # Pad with None for the beginning
            moving_avg.append(None)
        else:
            avg = sum(costs[i - window + 1:i + 1]) / window
            moving_avg.append(avg)
    
    return moving_avg

# SPY Expected Move endpoints
@app.get("/api/spy-expected-move/today")
async def get_spy_expected_move_today():
    """Get today's SPY expected move data"""
    try:
        today = datetime.now().strftime('%Y-%m-%d')
        result = await spy_calculator.get_spy_data_for_date(today)
        
        if result:
            return {
                "status": "success",
                "date": result['date'],
                "spy_price_930am": result['spy_price_930am'],
                "atm_strike": result['atm_strike'],
                "call_price_932am": result['call_price_932am'],
                "put_price_932am": result['put_price_932am'],
                "straddle_cost": result['straddle_cost'],
                "expected_move_1sigma": result['expected_move_1sigma'],
                "expected_move_2sigma": result['expected_move_2sigma'],
                "implied_volatility": result['implied_volatility'],
                "range_efficiency": result.get('range_efficiency'),
                "orb_high": result.get('orb_high'),
                "orb_low": result.get('orb_low'),
                "timestamp": result['timestamp']
            }
        else:
            return {
                "status": "no_data",
                "message": "No SPY expected move data available for today",
                "date": today
            }
    except Exception as e:
        logger.error(f"Error getting today's SPY expected move data: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve SPY expected move data")

@app.post("/api/spy-expected-move/calculate")
async def calculate_spy_expected_move(background_tasks: BackgroundTasks, notify_discord: bool = True):
    """Trigger SPY expected move calculation with optional Discord notification"""
    try:
        result = await spy_calculator.calculate_spy_expected_move()
        
        if result:
            response_data = {
                "status": "success",
                "date": result.date,
                "spy_price_930am": result.spy_price_930am,
                "atm_strike": result.atm_strike,
                "call_price_932am": result.call_price_932am,
                "put_price_932am": result.put_price_932am,
                "straddle_cost": result.straddle_cost,
                "expected_move_1sigma": result.expected_move_1sigma,
                "expected_move_2sigma": result.expected_move_2sigma,
                "implied_volatility": result.implied_volatility,
                "range_efficiency": result.range_efficiency,
                "orb_high": result.orb_high,
                "orb_low": result.orb_low,
                "timestamp": result.timestamp
            }
            
            # TODO: Send SPY Discord notification in background if enabled and requested
            # if notify_discord and spy_discord_notifier and spy_discord_notifier.is_enabled():
            #     background_tasks.add_task(spy_discord_notifier.notify_expected_move_result, response_data)
            
            return response_data
        else:
            raise HTTPException(status_code=500, detail="Failed to calculate SPY expected move")
            
    except Exception as e:
        logger.error(f"Error calculating SPY expected move: {e}")
        raise HTTPException(status_code=500, detail="Failed to calculate SPY expected move")

@app.get("/api/spy-expected-move/history")
async def get_spy_expected_move_history(days: int = 30):
    """Get historical SPY expected move data"""
    try:
        if days < 1 or days > 1000:
            raise HTTPException(status_code=400, detail="Days parameter must be between 1 and 1000")
        
        historical_data = await spy_calculator.get_spy_historical_data(days)
        
        return {
            "status": "success",
            "days_requested": days,
            "data_points": len(historical_data),
            "data": historical_data
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting SPY expected move history: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve SPY expected move history")

@app.get("/api/spy-expected-move/statistics")
async def get_spy_expected_move_statistics(days: int = 30):
    """Get SPY expected move statistical analysis"""
    try:
        if days < 1 or days > 1000:
            raise HTTPException(status_code=400, detail="Days parameter must be between 1 and 1000")
        
        stats = await spy_calculator.calculate_spy_statistics(days)
        
        return {
            "status": "success",
            "days_analyzed": days,
            "statistics": stats
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting SPY expected move statistics: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve SPY expected move statistics")

@app.get("/api/spy-expected-move/statistics/multi-timeframe")
async def get_spy_multi_timeframe_statistics():
    """Get SPY expected move statistics across multiple timeframes"""
    try:
        timeframes = [1, 2, 3, 4, 5, 6, 7, 14, 30, 45, 60, 90, 120, 170, 180, 240, 360, 540, 720]
        results = {}
        
        for days in timeframes:
            try:
                stats = await spy_calculator.calculate_spy_statistics(days)
                
                if stats and 'expected_move' in stats:
                    expected_move_stats = stats['expected_move']
                    results[f"{days}D"] = {
                        "mean": round(expected_move_stats['mean'], 2),
                        "std": round(expected_move_stats['std'], 2),
                        "min": round(expected_move_stats['min'], 2),
                        "max": round(expected_move_stats['max'], 2),
                        "data_points": stats['data_points']
                    }
                    
            except Exception as e:
                logger.warning(f"Failed to get SPY statistics for {days} days: {e}")
                continue
        
        return {
            "status": "success",
            "timeframes": results,
            "timestamp": datetime.now(pytz.timezone('US/Eastern')).isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error getting SPY multi-timeframe statistics: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve SPY multi-timeframe statistics")

@app.get("/api/spy-expected-move/chart-data")
async def get_spy_chart_data(days: int = 730, timeframe: str = "daily"):
    """Get SPY expected move chart data with trend analysis"""
    try:
        if days < 1 or days > 1000:
            raise HTTPException(status_code=400, detail="Days parameter must be between 1 and 1000")
        
        historical_data = await spy_calculator.get_spy_historical_data(days)
        
        if not historical_data:
            return {
                "status": "no_data",
                "message": "No SPY data available for the requested period",
                "days_requested": days
            }
        
        # Process data for charting
        processed_data = _process_spy_chart_data(historical_data, timeframe)
        
        return {
            "status": "success",
            "timeframe": timeframe,
            "days_requested": days,
            "data_points": len(historical_data),
            "chart_data": processed_data
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting SPY chart data: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve SPY chart data")

@app.get("/api/spy-expected-move/chart-config/{chart_type}")
async def get_spy_chart_config(chart_type: str, days: int = 730):
    """Get Chart.js configuration for SPY expected move charts"""
    try:
        # Get chart data
        chart_data_response = await get_spy_chart_data(days=days)
        
        if chart_data_response["status"] != "success":
            raise HTTPException(status_code=404, detail="No SPY data available for chart")
        
        chart_data = chart_data_response["chart_data"]
        
        # Generate Chart.js config based on chart type
        if chart_type == "trend":
            config = _generate_spy_trend_chart_config(chart_data, days)
        elif chart_type == "volatility":
            config = _generate_spy_volatility_chart_config(chart_data, days)
        elif chart_type == "efficiency":
            config = _generate_spy_efficiency_chart_config(chart_data, days)
        else:
            raise HTTPException(status_code=400, detail="Invalid chart type. Use: trend, volatility, efficiency")
        
        return config
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating SPY chart config: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate SPY chart configuration")

def _process_spy_chart_data(data_points, timeframe):
    """Process SPY data for charting"""
    if timeframe == "daily":
        # Sort by date
        sorted_data = sorted(data_points, key=lambda x: x['date'])
        
        dates = [item['date'] for item in sorted_data]
        expected_moves = [item['expected_move_1sigma'] for item in sorted_data]
        straddle_costs = [item['straddle_cost'] for item in sorted_data]
        implied_vols = [item['implied_volatility'] for item in sorted_data if item.get('implied_volatility')]
        
        # Calculate trend line for expected moves
        trend_line = _calculate_trend_line(expected_moves)
        
        # Calculate moving averages
        ma_7 = _calculate_moving_average(expected_moves, 7)
        ma_30 = _calculate_moving_average(expected_moves, 30)
        
        return {
            "dates": dates,
            "expected_moves": expected_moves,
            "straddle_costs": straddle_costs,
            "implied_volatilities": implied_vols,
            "trend_line": trend_line,
            "moving_averages": {
                "ma_7": ma_7,
                "ma_30": ma_30
            },
            "statistics": {
                "min": min(expected_moves) if expected_moves else 0,
                "max": max(expected_moves) if expected_moves else 0,
                "mean": sum(expected_moves) / len(expected_moves) if expected_moves else 0
            }
        }
    
    return {"error": "Unsupported timeframe"}

def _generate_spy_trend_chart_config(chart_data, days):
    """Generate Chart.js config for SPY trend analysis"""
    return {
        "type": "line",
        "data": {
            "labels": chart_data["dates"],
            "datasets": [
                {
                    "label": "Expected Move (1σ)",
                    "data": chart_data["expected_moves"],
                    "borderColor": "rgb(34, 197, 94)",
                    "backgroundColor": "rgba(34, 197, 94, 0.1)",
                    "borderWidth": 2,
                    "fill": False,
                    "tension": 0.1
                },
                {
                    "label": "Trend Line",
                    "data": chart_data["trend_line"],
                    "borderColor": "rgb(220, 38, 38)",
                    "backgroundColor": "transparent",
                    "borderWidth": 3,
                    "borderDash": [8, 4],
                    "fill": False,
                    "tension": 0,
                    "pointRadius": 0
                },
                {
                    "label": "7-Day MA",
                    "data": chart_data["moving_averages"]["ma_7"],
                    "borderColor": "rgb(59, 130, 246)",
                    "backgroundColor": "transparent",
                    "borderWidth": 1.5,
                    "fill": False,
                    "tension": 0.3,
                    "pointRadius": 0
                }
            ]
        },
        "options": {
            "responsive": True,
            "maintainAspectRatio": False,
            "plugins": {
                "title": {
                    "display": True,
                    "text": f"SPY Expected Move Trend Analysis ({days} Days)"
                },
                "legend": {
                    "display": True,
                    "position": "top"
                }
            },
            "scales": {
                "x": {
                    "title": {
                        "display": True,
                        "text": "Date"
                    }
                },
                "y": {
                    "title": {
                        "display": True,
                        "text": "Expected Move ($)"
                    }
                }
            },
            "interaction": {
                "intersect": False,
                "mode": "index"
            }
        }
    }

def _generate_spy_volatility_chart_config(chart_data, days):
    """Generate Chart.js config for SPY volatility analysis"""
    return {
        "type": "line",
        "data": {
            "labels": chart_data["dates"],
            "datasets": [
                {
                    "label": "Implied Volatility",
                    "data": chart_data["implied_volatilities"],
                    "borderColor": "rgb(168, 85, 247)",
                    "backgroundColor": "rgba(168, 85, 247, 0.1)",
                    "borderWidth": 2,
                    "fill": True,
                    "tension": 0.1
                }
            ]
        },
        "options": {
            "responsive": True,
            "maintainAspectRatio": False,
            "plugins": {
                "title": {
                    "display": True,
                    "text": f"SPY Implied Volatility Trend ({days} Days)"
                },
                "legend": {
                    "display": True,
                    "position": "top"
                }
            },
            "scales": {
                "x": {
                    "title": {
                        "display": True,
                        "text": "Date"
                    }
                },
                "y": {
                    "title": {
                        "display": True,
                        "text": "Implied Volatility (%)"
                    }
                }
            }
        }
    }

def _generate_spy_efficiency_chart_config(chart_data, days):
    """Generate Chart.js config for SPY range efficiency analysis"""
    return {
        "type": "scatter",
        "data": {
            "datasets": [
                {
                    "label": "Expected vs Actual Range",
                    "data": [
                        {"x": chart_data["expected_moves"][i], "y": chart_data["straddle_costs"][i]}
                        for i in range(len(chart_data["expected_moves"]))
                    ],
                    "backgroundColor": "rgba(34, 197, 94, 0.6)",
                    "borderColor": "rgb(34, 197, 94)",
                    "borderWidth": 1
                }
            ]
        },
        "options": {
            "responsive": True,
            "maintainAspectRatio": False,
            "plugins": {
                "title": {
                    "display": True,
                    "text": f"SPY Range Efficiency Analysis ({days} Days)"
                },
                "legend": {
                    "display": True,
                    "position": "top"
                }
            },
            "scales": {
                "x": {
                    "title": {
                        "display": True,
                        "text": "Expected Move ($)"
                    }
                },
                "y": {
                    "title": {
                        "display": True,
                        "text": "Straddle Cost ($)"
                    }
                }
            }
        }
    }

# Market day validation endpoints
@app.get("/api/market-days/validate/{date_str}")
async def validate_market_day(date_str: str):
    """
    Validate if a specific date is a valid market day
    
    Args:
        date_str: Date in YYYY-MM-DD format
    """
    try:
        # Parse date string
        target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        
        # Validate market day
        is_valid = calculator.is_valid_market_day(target_date)
        
        et_tz = pytz.timezone('US/Eastern')
        today = datetime.now(et_tz).date()
        
        return {
            "date": date_str,
            "is_valid_market_day": is_valid,
            "day_of_week": target_date.strftime('%A'),
            "weekday_number": target_date.weekday(),
            "is_weekend": target_date.weekday() >= 5,
            "is_holiday": target_date in calculator._market_holidays,
            "is_future": target_date > today,
            "is_today": target_date == today,
            "reason": _get_market_day_reason(target_date, calculator._market_holidays, today)
        }
        
    except ValueError as e:
        raise HTTPException(
            status_code=400, 
            detail=f"Invalid date format. Use YYYY-MM-DD format. Error: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Error validating market day {date_str}: {e}")
        raise HTTPException(status_code=500, detail="Failed to validate market day")

@app.get("/api/market-days/next")
async def get_next_market_day(from_date: str = None):
    """
    Get the next valid market day from a given date or today
    
    Args:
        from_date: Optional date in YYYY-MM-DD format (defaults to today)
    """
    try:
        if from_date:
            start_date = datetime.strptime(from_date, '%Y-%m-%d').date()
        else:
            et_tz = pytz.timezone('US/Eastern')
            start_date = datetime.now(et_tz).date()
        
        next_market_day = calculator.get_next_market_day(start_date)
        
        if next_market_day is None:
            raise HTTPException(
                status_code=404, 
                detail=f"No valid market day found within 30 days from {start_date}"
            )
        
        return {
            "from_date": start_date.isoformat(),
            "next_market_day": next_market_day.isoformat(),
            "days_ahead": (next_market_day - start_date).days,
            "day_of_week": next_market_day.strftime('%A')
        }
        
    except ValueError as e:
        raise HTTPException(
            status_code=400, 
            detail=f"Invalid date format. Use YYYY-MM-DD format. Error: {str(e)}"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting next market day: {e}")
        raise HTTPException(status_code=500, detail="Failed to get next market day")

@app.get("/api/market-days/previous")
async def get_previous_market_day(from_date: str = None):
    """
    Get the previous valid market day from a given date or today
    
    Args:
        from_date: Optional date in YYYY-MM-DD format (defaults to today)
    """
    try:
        if from_date:
            start_date = datetime.strptime(from_date, '%Y-%m-%d').date()
        else:
            et_tz = pytz.timezone('US/Eastern')
            start_date = datetime.now(et_tz).date()
        
        previous_market_day = calculator.get_previous_market_day(start_date)
        
        if previous_market_day is None:
            raise HTTPException(
                status_code=404, 
                detail=f"No valid market day found within 30 days before {start_date}"
            )
        
        return {
            "from_date": start_date.isoformat(),
            "previous_market_day": previous_market_day.isoformat(),
            "days_back": (start_date - previous_market_day).days,
            "day_of_week": previous_market_day.strftime('%A')
        }
        
    except ValueError as e:
        raise HTTPException(
            status_code=400, 
            detail=f"Invalid date format. Use YYYY-MM-DD format. Error: {str(e)}"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting previous market day: {e}")
        raise HTTPException(status_code=500, detail="Failed to get previous market day")

@app.get("/api/market-days/holidays")
async def get_market_holidays():
    """Get list of market holidays"""
    try:
        holidays_list = sorted(list(calculator._market_holidays))
        
        # Group by year for better organization
        holidays_by_year = {}
        for holiday in holidays_list:
            year = holiday.year
            if year not in holidays_by_year:
                holidays_by_year[year] = []
            holidays_by_year[year].append({
                "date": holiday.isoformat(),
                "day_of_week": holiday.strftime('%A')
            })
        
        return {
            "total_holidays": len(holidays_list),
            "date_range": {
                "start": holidays_list[0].isoformat() if holidays_list else None,
                "end": holidays_list[-1].isoformat() if holidays_list else None
            },
            "holidays_by_year": holidays_by_year
        }
        
    except Exception as e:
        logger.error(f"Error getting market holidays: {e}")
        raise HTTPException(status_code=500, detail="Failed to get market holidays")

def _get_market_day_reason(target_date: date, holidays: set, today: date) -> str:
    """Helper function to get reason why a date is/isn't a valid market day"""
    if target_date.weekday() >= 5:
        return f"Weekend ({target_date.strftime('%A')})"
    elif target_date in holidays:
        return "Market holiday"
    elif target_date > today:
        return "Future date"
    else:
        return "Valid market day"

# Discord notification endpoints
@app.post("/api/discord/test")
async def test_discord_notification():
    """Test Discord notification functionality"""
    if not discord_notifier or not discord_notifier.is_enabled():
        raise HTTPException(status_code=400, detail="Discord notifications not enabled or configured")
    
    try:
        test_message = "🧪 **Test Message from SPX Straddle Calculator**\n\nThis is a test notification to verify Discord integration is working correctly."
        success = await discord_notifier.send_message(test_message)
        
        if success:
            return {"status": "success", "message": "Test notification sent successfully"}
        else:
            raise HTTPException(status_code=500, detail="Failed to send test notification")
            
    except Exception as e:
        logger.error(f"Error sending test Discord notification: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to send test notification: {str(e)}")

@app.post("/api/discord/notify/today")
async def notify_discord_today(background_tasks: BackgroundTasks, include_stats: bool = False):
    """Send today's straddle data to Discord"""
    if not discord_notifier or not discord_notifier.is_enabled():
        raise HTTPException(status_code=400, detail="Discord notifications not enabled or configured")
    
    try:
        # Get today's data
        straddle_data = await calculator.get_spx_straddle_cost()
        
        if include_stats:
            stats_data = await calculator.calculate_spx_straddle_statistics(30)
            background_tasks.add_task(discord_notifier.notify_daily_summary, straddle_data, stats_data)
        else:
            background_tasks.add_task(discord_notifier.notify_straddle_result, straddle_data)
        
        return {"status": "success", "message": "Discord notification queued"}
        
    except Exception as e:
        logger.error(f"Error queuing Discord notification: {e}")
        raise HTTPException(status_code=500, detail="Failed to queue Discord notification")

@app.post("/api/discord/notify/multi-timeframe")
async def notify_discord_multi_timeframe(background_tasks: BackgroundTasks):
    """Send multi-timeframe statistics to Discord"""
    if not discord_notifier or not discord_notifier.is_enabled():
        raise HTTPException(status_code=400, detail="Discord notifications not enabled or configured")
    
    try:
        # Get multi-timeframe statistics
        multi_stats = await get_multi_timeframe_statistics()
        
        # Queue Discord notification
        background_tasks.add_task(discord_notifier.notify_multi_timeframe_statistics, multi_stats)
        
        return {"status": "success", "message": "Multi-timeframe Discord notification queued"}
        
    except Exception as e:
        logger.error(f"Error queuing multi-timeframe Discord notification: {e}")
        raise HTTPException(status_code=500, detail="Failed to queue multi-timeframe Discord notification")

@app.get("/api/discord/notify/multi-timeframe")
async def notify_discord_multi_timeframe_get(background_tasks: BackgroundTasks):
    """Send multi-timeframe statistics to Discord (GET version for browser access)"""
    return await notify_discord_multi_timeframe(background_tasks)

@app.post("/api/discord/notify/daily-timeframes")
async def notify_discord_daily_timeframes(background_tasks: BackgroundTasks):
    """Send daily timeframe statistics (1D-14D) to Discord"""
    if not discord_notifier or not discord_notifier.is_enabled():
        raise HTTPException(status_code=400, detail="Discord notifications not enabled or configured")
    
    try:
        # Get multi-timeframe statistics (includes daily timeframes now)
        multi_stats = await get_multi_timeframe_statistics()
        
        # Queue Discord notification for daily timeframes
        background_tasks.add_task(discord_notifier.notify_daily_timeframe_statistics, multi_stats)
        
        return {"status": "success", "message": "Daily timeframe Discord notification queued"}
        
    except Exception as e:
        logger.error(f"Error queuing daily timeframe Discord notification: {e}")
        raise HTTPException(status_code=500, detail="Failed to queue daily timeframe Discord notification")

# Historical backfill endpoints
@app.post("/api/spx-straddle/backfill/scenario/{scenario}")
async def backfill_scenario(scenario: str, background_tasks: BackgroundTasks):
    """Run predefined backfill scenarios"""
    from historical_backfill import HistoricalBackfill
    from datetime import timedelta
    
    et_tz = pytz.timezone('US/Eastern')
    today = datetime.now(et_tz).date()
    
    scenarios = {
        "1week": {"days": 7, "description": "Last 7 days"},
        "1month": {"days": 30, "description": "Last 30 days"},
        "3months": {"days": 90, "description": "Last 3 months"},
        "6months": {"days": 180, "description": "Last 6 months"},
        "1year": {"days": 365, "description": "Last 1 year"},
        "2years": {"days": 730, "description": "Last 2 years"}
    }
    
    if scenario not in scenarios:
        raise HTTPException(
            status_code=400, 
            detail=f"Unknown scenario: {scenario}. Available: {', '.join(scenarios.keys())}"
        )
    
    config = scenarios[scenario]
    start_date = today - timedelta(days=config["days"])
    end_date = today - timedelta(days=1)
    
    # Run backfill in background
    async def run_backfill():
        api_key = os.getenv('POLYGON_API_KEY')
        backfill = HistoricalBackfill(api_key, calculator.redis_url)
        try:
            await backfill.initialize()
            result = await backfill.backfill_date_range(
                start_date=start_date,
                end_date=end_date,
                batch_size=5,
                delay_between_batches=2.0
            )
            logger.info(f"Backfill {scenario} completed: {result['summary']}")
        except Exception as e:
            logger.error(f"Backfill {scenario} failed: {e}")
        finally:
            await backfill.close()
    
    background_tasks.add_task(run_backfill)
    
    return {
        "status": "started",
        "scenario": scenario,
        "description": config["description"],
        "date_range": {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat()
        },
        "message": f"Backfill for {config['description']} started in background"
    }

@app.post("/api/spx-straddle/backfill/custom")
async def backfill_custom(
    background_tasks: BackgroundTasks,
    start_date: str,
    end_date: str = None,
    batch_size: int = 5,
    delay: float = 2.0
):
    """Run custom date range backfill"""
    from historical_backfill import HistoricalBackfill
    
    try:
        # Parse dates
        start_dt = datetime.strptime(start_date, '%Y-%m-%d').date()
        
        if end_date:
            end_dt = datetime.strptime(end_date, '%Y-%m-%d').date()
        else:
            et_tz = pytz.timezone('US/Eastern')
            end_dt = datetime.now(et_tz).date() - timedelta(days=1)
        
        # Validate dates
        today = datetime.now(pytz.timezone('US/Eastern')).date()
        if start_dt >= end_dt:
            raise HTTPException(status_code=400, detail="Start date must be before end date")
        if end_dt >= today:
            raise HTTPException(status_code=400, detail="End date must be before today")
        
        # Run backfill in background
        async def run_backfill():
            api_key = os.getenv('POLYGON_API_KEY')
            backfill = HistoricalBackfill(api_key, calculator.redis_url)
            try:
                await backfill.initialize()
                result = await backfill.backfill_date_range(
                    start_date=start_dt,
                    end_date=end_dt,
                    batch_size=batch_size,
                    delay_between_batches=delay
                )
                logger.info(f"Custom backfill completed: {result['summary']}")
            except Exception as e:
                logger.error(f"Custom backfill failed: {e}")
            finally:
                await backfill.close()
        
        background_tasks.add_task(run_backfill)
        
        return {
            "status": "started",
            "date_range": {
                "start_date": start_dt.isoformat(),
                "end_date": end_dt.isoformat()
            },
            "batch_size": batch_size,
            "delay": delay,
            "message": f"Custom backfill from {start_dt} to {end_dt} started in background"
        }
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid date format. Use YYYY-MM-DD: {e}")
    except Exception as e:
        logger.error(f"Error starting custom backfill: {e}")
        raise HTTPException(status_code=500, detail="Failed to start backfill")

@app.get("/api/dashboard", response_class=HTMLResponse)
async def get_unified_dashboard():
    """Unified dashboard for SPX straddle and SPY expected move data"""
    try:
        # Get SPX current data
        spx_current_data = await calculator.get_spx_straddle_cost()
        
        # Get SPY current data
        today = datetime.now().strftime('%Y-%m-%d')
        spy_current_data = await spy_calculator.get_spy_data_for_date(today)
        
        # Get SPX multi-timeframe statistics
        try:
            spx_multi_stats_response = await get_multi_timeframe_statistics()
            spx_multi_stats = spx_multi_stats_response if isinstance(spx_multi_stats_response, dict) else {}
        except:
            spx_multi_stats = {"status": "error"}
        
        # Get SPY multi-timeframe statistics
        try:
            spy_multi_stats_response = await get_spy_multi_timeframe_statistics()
            spy_multi_stats = spy_multi_stats_response if isinstance(spy_multi_stats_response, dict) else {}
        except:
            spy_multi_stats = {"status": "error"}
        
        # Check if Discord is configured
        discord_enabled = discord_notifier.is_enabled() if discord_notifier else False
        
        # Build HTML response with unified dashboard
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Options Analytics Dashboard</title>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
            <style>
                body {{ 
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; 
                    margin: 0; 
                    padding: 20px; 
                    background-color: #f5f5f5;
                }}
                .container {{ max-width: 1400px; margin: 0 auto; }}
                .header {{ text-align: center; margin-bottom: 30px; }}
                .nav-links {{ text-align: center; margin-bottom: 20px; }}
                .nav-links a {{ 
                    display: inline-block; 
                    margin: 0 10px; 
                    padding: 8px 16px; 
                    background: #007bff; 
                    color: white; 
                    text-decoration: none; 
                    border-radius: 4px; 
                    font-size: 0.9em;
                }}
                .nav-links a:hover {{ background: #0056b3; }}
                .nav-links a.current {{ background: #28a745; }}
                .asset-selector {{ 
                    text-align: center; 
                    margin-bottom: 30px; 
                }}
                .asset-dropdown {{ 
                    padding: 12px 20px; 
                    font-size: 16px; 
                    border: 2px solid #007bff; 
                    border-radius: 8px; 
                    background: white; 
                    color: #007bff;
                    font-weight: bold;
                    cursor: pointer;
                    min-width: 250px;
                }}
                .asset-dropdown:focus {{ outline: none; border-color: #0056b3; }}
                .card {{ 
                    background: white; 
                    border-radius: 8px; 
                    padding: 20px; 
                    margin: 15px 0; 
                    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                }}
                .status-available {{ color: #28a745; font-weight: bold; }}
                .status-error {{ color: #dc3545; font-weight: bold; }}
                .status-calculating {{ color: #007bff; font-weight: bold; }}
                .status-pending {{ color: #ffc107; font-weight: bold; }}
                .status-no_data {{ color: #6c757d; font-weight: bold; }}
                table {{ border-collapse: collapse; width: 100%; margin-top: 15px; }}
                th, td {{ border: 1px solid #ddd; padding: 12px; text-align: left; }}
                th {{ background-color: #f8f9fa; font-weight: 600; }}
                .metric {{ display: inline-block; margin: 10px 20px 10px 0; }}
                .metric-value {{ font-size: 1.5em; font-weight: bold; color: #007bff; }}
                .metric-label {{ font-size: 0.9em; color: #666; }}
                .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 20px; }}
                .btn {{ 
                    background: #007bff; 
                    color: white; 
                    padding: 10px 20px; 
                    border: none; 
                    border-radius: 4px; 
                    cursor: pointer; 
                    text-decoration: none;
                    display: inline-block;
                    margin: 5px;
                }}
                .btn:hover {{ background: #0056b3; }}
                .btn-success {{ background: #28a745; }}
                .btn-success:hover {{ background: #1e7e34; }}
                .btn-spy {{ background: #17a2b8; }}
                .btn-spy:hover {{ background: #138496; }}
                .asset-content {{ display: none; }}
                .asset-content.active {{ display: block; }}
                .chart-container {{ position: relative; height: 400px; margin: 20px 0; }}
                .chart-controls {{ margin: 20px 0; text-align: center; }}
                .chart-controls select, .chart-controls button {{ 
                    margin: 5px; 
                    padding: 8px 12px; 
                    border: 1px solid #ddd; 
                    border-radius: 4px; 
                }}
                .fullscreen-btn {{ 
                    background: #6f42c1; 
                    color: white; 
                    border: none; 
                    padding: 8px 16px; 
                    border-radius: 4px; 
                    cursor: pointer; 
                    margin: 5px;
                }}
                .fullscreen-btn:hover {{ background: #5a359a; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>📊 Options Analytics Dashboard</h1>
                    <p>Real-time SPX straddle costs & SPY expected moves using Polygon.io</p>
                </div>
                
                <div class="nav-links">
                    <a href="/api/spx-straddle/dashboard">📈 SPX Dashboard</a>
                    <a href="/api/spy-expected-move/dashboard">📊 SPY Dashboard</a>
                    <a href="/api/dashboard" class="current">🔄 Unified View</a>
                </div>
                
                <div class="asset-selector">
                    <select id="assetDropdown" class="asset-dropdown" onchange="switchAsset()">
                        <option value="SPX">SPX 0DTE Straddle Analysis</option>
                        <option value="SPY">SPY Expected Move Analysis</option>
                    </select>
                </div>
                
                <!-- SPX Content -->
                <div id="spx-content" class="asset-content active">
                    <div class="card">
                        <h2>🎯 SPX Current Status</h2>
                        <p><strong>Status:</strong> <span class="status-{spx_current_data.get('calculation_status', 'unknown')}">{spx_current_data.get('calculation_status', 'Unknown').upper().replace('_', ' ')}</span></p>
                        <p><strong>Last Update:</strong> {spx_current_data.get('timestamp', 'N/A')}</p>
                        <p><strong>Discord Notifications:</strong> {'✅ Enabled' if discord_enabled else '❌ Disabled'}</p>
        """
        
        # Add current SPX straddle data if available
        if spx_current_data.get('calculation_status') == 'available':
            html_content += f"""
                        <div style="margin-top: 20px;">
                            <div class="metric">
                                <div class="metric-value">${spx_current_data.get('straddle_cost', 0):.2f}</div>
                                <div class="metric-label">Straddle Cost</div>
                            </div>
                            <div class="metric">
                                <div class="metric-value">${spx_current_data.get('spx_price_930am', 0):.2f}</div>
                                <div class="metric-label">SPX @ 9:30 AM</div>
                            </div>
                            <div class="metric">
                                <div class="metric-value">{spx_current_data.get('atm_strike', 0)}</div>
                                <div class="metric-label">ATM Strike</div>
                            </div>
                            <div class="metric">
                                <div class="metric-value">${spx_current_data.get('call_price_931am', 0):.2f}</div>
                                <div class="metric-label">Call Price</div>
                            </div>
                            <div class="metric">
                                <div class="metric-value">${spx_current_data.get('put_price_931am', 0):.2f}</div>
                                <div class="metric-label">Put Price</div>
                            </div>
                        </div>
            """
        
        html_content += """
                        <div style="margin-top: 20px;">
                            <a href="/api/spx-straddle/calculate" class="btn">🔄 Calculate Now</a>
                            <a href="/api/discord/test" class="btn btn-success">🧪 Test Discord</a>
                        </div>
                    </div>
                    
                    <!-- SPX Charts -->
                    <div class="card">
                        <h2>📈 SPX Trend Analysis</h2>
                        <div class="chart-controls">
                            <select id="spx-time-period" onchange="updateSPXChart()">
                                <option value="30">30 Days</option>
                                <option value="90">3 Months</option>
                                <option value="180">6 Months</option>
                                <option value="365">1 Year</option>
                                <option value="730" selected>2 Years</option>
                            </select>
                            <select id="spx-chart-type" onchange="updateSPXChart()">
                                <option value="trend" selected>Trend Analysis</option>
                                <option value="moving-averages">Moving Averages</option>
                                <option value="comparison">Range Analysis</option>
                            </select>
                            <button class="fullscreen-btn" onclick="toggleFullscreen('spx-chart-container')">🔍 Fullscreen</button>
                        </div>
                        <div id="spx-chart-container" class="chart-container">
                            <canvas id="spx-chart"></canvas>
                        </div>
                    </div>
                </div>
                
                <!-- SPY Content -->
                <div id="spy-content" class="asset-content">
                    <div class="card">
                        <h2>🎯 SPY Current Status</h2>
        """
        
        # Add SPY current data
        if spy_current_data:
            html_content += f"""
                        <p><strong>Status:</strong> <span class="status-available">DATA AVAILABLE</span></p>
                        <p><strong>Last Update:</strong> {spy_current_data.get('timestamp', 'N/A')}</p>
                        <p><strong>Timing:</strong> 9:30 AM (price) → 9:32 AM (straddle)</p>
                        
                        <div style="margin-top: 20px;">
                            <div class="metric">
                                <div class="metric-value">±${spy_current_data.get('expected_move_1sigma', 0):.2f}</div>
                                <div class="metric-label">Expected Move (1σ)</div>
                            </div>
                            <div class="metric">
                                <div class="metric-value">${spy_current_data.get('spy_price_930am', 0):.2f}</div>
                                <div class="metric-label">SPY @ 9:30 AM</div>
                            </div>
                            <div class="metric">
                                <div class="metric-value">{spy_current_data.get('atm_strike', 0)}</div>
                                <div class="metric-label">ATM Strike</div>
                            </div>
                            <div class="metric">
                                <div class="metric-value">${spy_current_data.get('straddle_cost', 0):.2f}</div>
                                <div class="metric-label">Straddle Cost</div>
                            </div>
                            <div class="metric">
                                <div class="metric-value">{spy_current_data.get('implied_volatility', 0):.1%}</div>
                                <div class="metric-label">Implied Volatility</div>
                            </div>
                        </div>
            """
        else:
            html_content += """
                        <p><strong>Status:</strong> <span class="status-no_data">NO DATA AVAILABLE</span></p>
                        <p><strong>Message:</strong> No SPY expected move data for today. Calculate to generate data.</p>
            """
        
        html_content += """
                        <div style="margin-top: 20px;">
                            <a href="/api/spy-expected-move/calculate" class="btn btn-spy">🔄 Calculate SPY Move</a>
                            <a href="/api/spy-expected-move/statistics/multi-timeframe" class="btn">📊 View Statistics</a>
                        </div>
                    </div>
                    
                    <!-- SPY Charts -->
                    <div class="card">
                        <h2>📈 SPY Expected Move Analysis</h2>
                        <div class="chart-controls">
                            <select id="spy-time-period" onchange="updateSPYChart()">
                                <option value="30">30 Days</option>
                                <option value="90">3 Months</option>
                                <option value="180">6 Months</option>
                                <option value="365">1 Year</option>
                                <option value="730" selected>2 Years</option>
                            </select>
                            <select id="spy-chart-type" onchange="updateSPYChart()">
                                <option value="trend" selected>Expected Move Trend</option>
                                <option value="volatility">Implied Volatility</option>
                                <option value="efficiency">Range Efficiency</option>
                            </select>
                            <button class="fullscreen-btn" onclick="toggleFullscreen('spy-chart-container')">🔍 Fullscreen</button>
                        </div>
                        <div id="spy-chart-container" class="chart-container">
                            <canvas id="spy-chart"></canvas>
                        </div>
                    </div>
                </div>
        """
        
        # Close the HTML with JavaScript functions
        html_content += """
                
                <script>
                    let spxChart = null;
                    let spyChart = null;
                    
                    // Asset switching functionality
                    function switchAsset() {
                        const dropdown = document.getElementById('assetDropdown');
                        const selectedAsset = dropdown.value;
                        
                        // Hide all content divs
                        document.querySelectorAll('.asset-content').forEach(div => {
                            div.classList.remove('active');
                        });
                        
                        // Show selected asset content
                        const targetDiv = document.getElementById(selectedAsset.toLowerCase() + '-content');
                        if (targetDiv) {
                            targetDiv.classList.add('active');
                        }
                        
                        // Load chart for selected asset
                        if (selectedAsset === 'SPX') {
                            setTimeout(updateSPXChart, 100);
                        } else if (selectedAsset === 'SPY') {
                            setTimeout(updateSPYChart, 100);
                        }
                    }
                    
                    // SPX Chart functionality
                    async function updateSPXChart() {
                        const days = document.getElementById('spx-time-period').value;
                        const chartType = document.getElementById('spx-chart-type').value;
                        
                        try {
                            const response = await fetch(`/api/spx-straddle/chart-config/${chartType}?days=${days}`);
                            const config = await response.json();
                            
                            const ctx = document.getElementById('spx-chart').getContext('2d');
                            
                            if (spxChart) {
                                spxChart.destroy();
                            }
                            
                            spxChart = new Chart(ctx, config);
                            
                        } catch (error) {
                            console.error('Error loading SPX chart:', error);
                        }
                    }
                    
                    // SPY Chart functionality
                    async function updateSPYChart() {
                        const days = document.getElementById('spy-time-period').value;
                        const chartType = document.getElementById('spy-chart-type').value;
                        
                        try {
                            const response = await fetch(`/api/spy-expected-move/chart-config/${chartType}?days=${days}`);
                            const config = await response.json();
                            
                            const ctx = document.getElementById('spy-chart').getContext('2d');
                            
                            if (spyChart) {
                                spyChart.destroy();
                            }
                            
                            spyChart = new Chart(ctx, config);
                            
                        } catch (error) {
                            console.error('Error loading SPY chart:', error);
                        }
                    }
                    
                    // Fullscreen functionality
                    function toggleFullscreen(containerId) {
                        const container = document.getElementById(containerId);
                        
                        if (!document.fullscreenElement) {
                            container.requestFullscreen().then(() => {
                                // Add fullscreen controls
                                const controls = document.createElement('div');
                                controls.id = 'fullscreen-controls';
                                controls.style.cssText = `
                                    position: fixed;
                                    top: 20px;
                                    right: 20px;
                                    z-index: 9999;
                                    background: rgba(0,0,0,0.8);
                                    color: white;
                                    padding: 10px;
                                    border-radius: 8px;
                                `;
                                controls.innerHTML = `
                                    <button onclick="exitFullscreen()" style="background: #dc3545; color: white; border: none; padding: 8px 16px; border-radius: 4px; cursor: pointer;">
                                        ✕ Exit Fullscreen (ESC)
                                    </button>
                                `;
                                container.appendChild(controls);
                                
                                // Resize chart
                                setTimeout(() => {
                                    if (containerId.includes('spx') && spxChart) {
                                        spxChart.resize();
                                    } else if (containerId.includes('spy') && spyChart) {
                                        spyChart.resize();
                                    }
                                }, 100);
                            });
                        } else {
                            document.exitFullscreen();
                        }
                    }
                    
                    function exitFullscreen() {
                        if (document.fullscreenElement) {
                            document.exitFullscreen();
                        }
                    }
                    
                    // Handle ESC key for fullscreen exit
                    document.addEventListener('keydown', (e) => {
                        if (e.key === 'Escape' && document.fullscreenElement) {
                            exitFullscreen();
                        }
                    });
                    
                    // Clean up fullscreen controls when exiting
                    document.addEventListener('fullscreenchange', () => {
                        if (!document.fullscreenElement) {
                            const controls = document.getElementById('fullscreen-controls');
                            if (controls) {
                                controls.remove();
                            }
                            
                            // Resize charts back to normal
                            setTimeout(() => {
                                if (spxChart) spxChart.resize();
                                if (spyChart) spyChart.resize();
                            }, 100);
                        }
                    });
                    
                    // Initialize charts on page load
                    document.addEventListener('DOMContentLoaded', () => {
                        // Load SPX chart by default (since SPX is selected by default)
                        updateSPXChart();
                    });
                </script>
            </div>
        </body>
        </html>
        """
        
        return html_content
        
    except Exception as e:
        logger.error(f"Error generating unified dashboard: {e}")
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Dashboard Error</title>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1">
        </head>
        <body style="font-family: Arial, sans-serif; padding: 20px; background: #f5f5f5;">
            <div style="background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
                <h1 style="color: #dc3545;">❌ Dashboard Error</h1>
                <p>An error occurred while loading the dashboard: {str(e)}</p>
                <p><a href="/api/dashboard" style="color: #007bff;">🔄 Try Again</a></p>
            </div>
        </body>
        </html>
        """

# Original SPX Dashboard - restored functionality
@app.get("/api/spx-straddle/dashboard", response_class=HTMLResponse)
async def get_spx_straddle_dashboard():
    """Original SPX straddle dashboard - kept for compatibility"""
    try:
        # Get current straddle data using the same method as the today endpoint
        current_data = await calculator.get_spx_straddle_cost()
        
        # Ensure current_data is a dictionary
        if isinstance(current_data, str):
            import json
            current_data = json.loads(current_data)
        elif current_data is None:
            current_data = {"calculation_status": "no_data", "message": "No data available"}
        
        # Get multi-timeframe statistics
        try:
            multi_stats_response = await get_multi_timeframe_statistics()
            multi_stats = multi_stats_response if isinstance(multi_stats_response, dict) else {}
        except:
            multi_stats = {"status": "error"}
        
        # Check if Discord is configured
        discord_enabled = discord_notifier.is_enabled() if discord_notifier else False
        
        # Build HTML response
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>SPX 0DTE Straddle Dashboard</title>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
            <style>
                body {{ 
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; 
                    margin: 0; 
                    padding: 20px; 
                    background-color: #f5f5f5;
                }}
                .container {{ max-width: 1400px; margin: 0 auto; }}
                .header {{ text-align: center; margin-bottom: 30px; }}
                .nav-links {{ text-align: center; margin-bottom: 20px; }}
                .nav-links a {{ 
                    display: inline-block; 
                    margin: 0 10px; 
                    padding: 8px 16px; 
                    background: #007bff; 
                    color: white; 
                    text-decoration: none; 
                    border-radius: 4px; 
                    font-size: 0.9em;
                }}
                .nav-links a:hover {{ background: #0056b3; }}
                .nav-links a.current {{ background: #28a745; }}
                .card {{ 
                    background: white; 
                    border-radius: 8px; 
                    padding: 20px; 
                    margin: 15px 0; 
                    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                }}
                .status-available {{ color: #28a745; font-weight: bold; }}
                .status-error {{ color: #dc3545; font-weight: bold; }}
                .status-calculating {{ color: #007bff; font-weight: bold; }}
                .status-pending {{ color: #ffc107; font-weight: bold; }}
                .status-pending_calculation {{ color: #ffc107; font-weight: bold; }}
                .status-no_data {{ color: #6c757d; font-weight: bold; }}
                .btn {{ 
                    background: #007bff; 
                    color: white; 
                    padding: 10px 20px; 
                    border: none; 
                    border-radius: 4px; 
                    cursor: pointer; 
                    text-decoration: none;
                    display: inline-block;
                    margin: 5px;
                }}
                .btn:hover {{ background: #0056b3; }}
                .btn-success {{ background: #28a745; }}
                .btn-success:hover {{ background: #1e7e34; }}
                .metric {{ display: inline-block; margin: 10px 20px 10px 0; }}
                .metric-value {{ font-size: 1.5em; font-weight: bold; color: #007bff; }}
                .metric-label {{ font-size: 0.9em; color: #666; }}
                .chart-container {{ position: relative; height: 400px; margin: 20px 0; }}
                .chart-controls {{ margin: 20px 0; text-align: center; }}
                .chart-controls select, .chart-controls button {{ 
                    margin: 5px; 
                    padding: 8px 12px; 
                    border: 1px solid #ddd; 
                    border-radius: 4px; 
                }}
                .fullscreen-btn {{ 
                    background: #6f42c1; 
                    color: white; 
                    border: none; 
                    padding: 8px 16px; 
                    border-radius: 4px; 
                    cursor: pointer; 
                    margin: 5px;
                }}
                .fullscreen-btn:hover {{ background: #5a359a; }}
                table {{ border-collapse: collapse; width: 100%; margin-top: 15px; }}
                th, td {{ border: 1px solid #ddd; padding: 12px; text-align: left; }}
                th {{ background-color: #f8f9fa; font-weight: 600; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>📊 SPX 0DTE Straddle Dashboard</h1>
                    <p>Real-time straddle costs using Polygon.io</p>
                </div>
                
                <div class="nav-links">
                    <a href="/api/spx-straddle/dashboard" class="current">📈 SPX 0DTE Straddle</a>
                    <a href="/api/spy-expected-move/dashboard">📊 SPY Expected Move</a>
                    <a href="/api/dashboard">🔄 Unified Dashboard</a>
                </div>
                
                <div class="card">
                    <h2>🎯 SPX Current Status</h2>
                    <p><strong>Status:</strong> <span class="status-{current_data.get('calculation_status', 'unknown')}">{current_data.get('calculation_status', 'Unknown').upper().replace('_', ' ')}</span></p>
                    <p><strong>Last Update:</strong> {current_data.get('timestamp', 'N/A')}</p>
                    <p><strong>Discord Notifications:</strong> {'✅ Enabled' if discord_enabled else '❌ Disabled'}</p>
                    {f'<p><strong>Message:</strong> {current_data.get("message", "")}</p>' if current_data.get("message") else ""}
        """
        
        # Add current straddle data if available
        if current_data.get('calculation_status') == 'available':
            html_content += f"""
                    <div style="margin-top: 20px;">
                        <div class="metric">
                            <div class="metric-value">${current_data.get('straddle_cost', 0):.2f}</div>
                            <div class="metric-label">Straddle Cost</div>
                        </div>
                        <div class="metric">
                            <div class="metric-value">${current_data.get('spx_price_930am', 0):.2f}</div>
                            <div class="metric-label">SPX @ 9:30 AM</div>
                        </div>
                        <div class="metric">
                            <div class="metric-value">{current_data.get('atm_strike', 0)}</div>
                            <div class="metric-label">ATM Strike</div>
                        </div>
                        <div class="metric">
                            <div class="metric-value">${current_data.get('call_price_931am', 0):.2f}</div>
                            <div class="metric-label">Call Price</div>
                        </div>
                        <div class="metric">
                            <div class="metric-value">${current_data.get('put_price_931am', 0):.2f}</div>
                            <div class="metric-label">Put Price</div>
                        </div>
                    </div>
            """
        
        html_content += """
                    <div style="margin-top: 20px;">
                        <a href="/api/spx-straddle/calculate" class="btn">🔄 Calculate Now</a>
                        <a href="/api/discord/test" class="btn btn-success">🧪 Test Discord</a>
                    </div>
                </div>
                
                <!-- Historical Data Backfill -->
                <div class="card">
                    <h2>📚 Historical Data Backfill</h2>
                    <p>Populate your database with historical SPX 0DTE straddle costs for better analysis and trending.</p>
                    
                    <div style="margin: 20px 0;">
                        <h4>Quick Scenarios</h4>
                        <div style="display: flex; flex-wrap: wrap; gap: 10px; margin: 15px 0;">
                            <button class="btn" onclick="runBackfill('1week')">📅 1 Week</button>
                            <button class="btn" onclick="runBackfill('1month')">📅 1 Month</button>
                            <button class="btn" onclick="runBackfill('3months')">📅 3 Months</button>
                            <button class="btn" onclick="runBackfill('6months')">📅 6 Months</button>
                            <button class="btn" onclick="runBackfill('1year')">📅 1 Year</button>
                            <button class="btn" onclick="runBackfill('2years')">📅 2 Years</button>
                        </div>
                    </div>
                    
                    <div style="margin: 20px 0;">
                        <h4>Custom Date Range</h4>
                        <div style="display: flex; flex-wrap: wrap; gap: 10px; align-items: center; margin: 15px 0;">
                            <label>Start Date:</label>
                            <input type="date" id="backfill-start-date" style="padding: 8px; border: 1px solid #ddd; border-radius: 4px;">
                            <label>End Date:</label>
                            <input type="date" id="backfill-end-date" style="padding: 8px; border: 1px solid #ddd; border-radius: 4px;">
                            <button class="btn" onclick="runCustomBackfill()">🚀 Start Custom Backfill</button>
                        </div>
                    </div>
                    
                    <div id="backfill-status" style="margin-top: 15px; padding: 10px; border-radius: 4px; display: none;"></div>
                </div>
                
                <!-- Charts -->
                <div class="card">
                    <h2>📈 SPX Trend Analysis</h2>
                    <div class="chart-controls">
                        <select id="time-period" onchange="updateChart()">
                            <option value="30">30 Days</option>
                            <option value="90">3 Months</option>
                            <option value="180">6 Months</option>
                            <option value="365">1 Year</option>
                            <option value="730" selected>2 Years</option>
                        </select>
                        <select id="chart-type" onchange="updateChart()">
                            <option value="trend" selected>Trend Analysis</option>
                            <option value="moving-averages">Moving Averages</option>
                            <option value="comparison">Range Analysis</option>
                        </select>
                        <button class="fullscreen-btn" onclick="toggleFullscreen('chart-container')">🔍 Fullscreen</button>
                    </div>
                    <div id="chart-container" class="chart-container">
                        <canvas id="straddleChart"></canvas>
                    </div>
                    <div id="chart-status" style="text-align: center; margin-top: 10px; padding: 10px; border-radius: 4px;"></div>
                </div>
        """
        
        # Add multi-timeframe statistics if available
        if multi_stats.get("status") == "success":
            html_content += """
                <div class="card">
                    <h2>📊 Multi-Timeframe Statistics</h2>
                    <div style="overflow-x: auto;">
                        <table>
                            <thead>
                                <tr>
                                    <th>Timeframe</th>
                                    <th>Avg Cost</th>
                                    <th>Min Cost</th>
                                    <th>Max Cost</th>
                                    <th>Std Dev</th>
                                    <th>Count</th>
                                    <th>Trend</th>
                                </tr>
                            </thead>
                            <tbody>
            """
            
            for timeframe_key, timeframe in multi_stats.get("timeframes", {}).items():
                stats = timeframe.get("descriptive_stats", {})
                trend = timeframe.get("trend_analysis", {})
                html_content += f"""
                                <tr>
                                    <td>{timeframe.get('period_label', timeframe_key)}</td>
                                    <td>${stats.get('mean', 0):.2f}</td>
                                    <td>${stats.get('min', 0):.2f}</td>
                                    <td>${stats.get('max', 0):.2f}</td>
                                    <td>${stats.get('std_dev', 0):.2f}</td>
                                    <td>{timeframe.get('valid_market_days', 0)}</td>
                                    <td>{'📈' if trend.get('direction') == 'up' else '📉' if trend.get('direction') == 'down' else '➡️'}</td>
                                </tr>
                """
            
            html_content += """
                            </tbody>
                        </table>
                    </div>
                </div>
            """
        
        html_content += """
            </div>
            
            <script>
                let currentChart = null;
                
                async function updateChart() {
                    const days = document.getElementById('time-period').value;
                    const chartType = document.getElementById('chart-type').value;
                    const statusDiv = document.getElementById('chart-status');
                    
                    // Show loading status
                    statusDiv.style.backgroundColor = '#e3f2fd';
                    statusDiv.style.color = '#1976d2';
                    statusDiv.innerHTML = '⏳ Loading chart data...';
                    
                    try {
                        const response = await fetch(`/api/spx-straddle/chart-config/${chartType}?days=${days}`);
                        const result = await response.json();
                        
                        if (currentChart) {
                            currentChart.destroy();
                        }
                        
                        // Create new chart
                        const ctx = document.getElementById('straddleChart').getContext('2d');
                        currentChart = new Chart(ctx, result.config);
                        
                        // Show success status
                        statusDiv.style.backgroundColor = '#d4edda';
                        statusDiv.style.color = '#155724';
                        statusDiv.innerHTML = `✅ Chart updated with ${result.data_points} data points (${result.date_range.start} to ${result.date_range.end})`;
                        
                        // Hide status after 3 seconds
                        setTimeout(() => {
                            statusDiv.innerHTML = '';
                            statusDiv.style.backgroundColor = '';
                        }, 3000);
                        
                    } catch (error) {
                        console.error('Error updating chart:', error);
                        statusDiv.style.backgroundColor = '#f8d7da';
                        statusDiv.style.color = '#721c24';
                        statusDiv.innerHTML = '❌ Error loading chart data';
                    }
                }
                
                function toggleFullscreen(containerId) {
                    const container = document.getElementById(containerId);
                    if (!document.fullscreenElement) {
                        container.requestFullscreen().catch(err => {
                            console.error('Error attempting to enable fullscreen:', err);
                        });
                    } else {
                        document.exitFullscreen();
                    }
                }
                
                // Handle fullscreen exit with ESC key
                document.addEventListener('fullscreenchange', function() {
                    if (!document.fullscreenElement && currentChart) {
                        // Resize chart when exiting fullscreen
                        setTimeout(() => currentChart.resize(), 100);
                    }
                });
                
                // Load initial chart
                updateChart();
            </script>
        </body>
        </html>
        """
        
        return HTMLResponse(content=html_content)
        
    except Exception as e:
        logger.error(f"Error generating SPX dashboard: {e}")
        return HTMLResponse(
            content=f"<html><body><h1>Error</h1><p>Failed to load dashboard: {str(e)}</p></body></html>",
            status_code=500
        )

@app.get("/api/spy-expected-move/dashboard", response_class=HTMLResponse)
async def get_spy_expected_move_dashboard():
    """Dedicated SPY expected move dashboard - matches SPX dashboard structure"""
    try:
        # Get current SPY data
        today = datetime.now().strftime('%Y-%m-%d')
        current_data = await spy_calculator.get_spy_data_for_date(today)
        
        if not current_data:
            current_data = {"calculation_status": "no_data", "message": "No SPY expected move data available. Use calculate to generate data."}
        
        # Get multi-timeframe statistics
        try:
            multi_stats = await get_spy_multi_timeframe_statistics()
            if not isinstance(multi_stats, dict):
                multi_stats = {"status": "error", "message": "Invalid response format"}
        except Exception as e:
            logger.error(f"Error getting SPY multi-timeframe statistics: {e}")
            multi_stats = {"status": "error", "message": str(e)}
        
        # Check if Discord is configured
        discord_enabled = discord_notifier.is_enabled() if discord_notifier else False
        
        # Build HTML response
        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>SPY Expected Move Dashboard</title>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
            <style>
                body {{ 
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; 
                    margin: 0; 
                    padding: 20px; 
                    background-color: #f5f5f5;
                }}
                .container {{ max-width: 1400px; margin: 0 auto; }}
                .header {{ text-align: center; margin-bottom: 30px; }}
                .nav-links {{ text-align: center; margin-bottom: 20px; }}
                .nav-links a {{ 
                    display: inline-block; 
                    margin: 0 10px; 
                    padding: 8px 16px; 
                    background: #007bff; 
                    color: white; 
                    text-decoration: none; 
                    border-radius: 4px; 
                    font-size: 0.9em;
                }}
                .nav-links a:hover {{ background: #0056b3; }}
                .nav-links a.current {{ background: #28a745; }}
                .card {{ 
                    background: white; 
                    border-radius: 8px; 
                    padding: 20px; 
                    margin: 15px 0; 
                    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                }}
                .status-available {{ color: #28a745; font-weight: bold; }}
                .status-error {{ color: #dc3545; font-weight: bold; }}
                .status-calculating {{ color: #007bff; font-weight: bold; }}
                .status-pending {{ color: #ffc107; font-weight: bold; }}
                .status-pending_calculation {{ color: #ffc107; font-weight: bold; }}
                .status-no_data {{ color: #6c757d; font-weight: bold; }}
                .btn {{ 
                    background: #007bff; 
                    color: white; 
                    padding: 10px 20px; 
                    border: none; 
                    border-radius: 4px; 
                    cursor: pointer; 
                    text-decoration: none;
                    display: inline-block;
                    margin: 5px;
                }}
                .btn:hover {{ background: #0056b3; }}
                .btn-success {{ background: #28a745; }}
                .btn-success:hover {{ background: #1e7e34; }}
                .btn-spy {{ background: #6f42c1; }}
                .btn-spy:hover {{ background: #5a359a; }}
                .metric {{ display: inline-block; margin: 10px 20px 10px 0; }}
                .metric-value {{ font-size: 1.5em; font-weight: bold; color: #6f42c1; }}
                .metric-label {{ font-size: 0.9em; color: #666; }}
                .chart-container {{ position: relative; height: 400px; margin: 20px 0; }}
                .chart-controls {{ margin: 20px 0; text-align: center; }}
                .chart-controls select, .chart-controls button {{ 
                    margin: 5px; 
                    padding: 8px 12px; 
                    border: 1px solid #ddd; 
                    border-radius: 4px; 
                }}
                .fullscreen-btn {{ 
                    background: #6f42c1; 
                    color: white; 
                    border: none; 
                    padding: 8px 16px; 
                    border-radius: 4px; 
                    cursor: pointer; 
                    margin: 5px;
                }}
                .fullscreen-btn:hover {{ background: #5a359a; }}
                table {{ border-collapse: collapse; width: 100%; margin-top: 15px; }}
                th, td {{ border: 1px solid #ddd; padding: 12px; text-align: left; }}
                th {{ background-color: #f8f9fa; font-weight: 600; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>📊 SPY Expected Move Dashboard</h1>
                    <p>Expected moves using implied volatility from straddle pricing</p>
                    <p><strong>Timing:</strong> 9:30 AM (price) → 9:32 AM (straddle) for post-ORB analysis</p>
                </div>
                
                <div class="nav-links">
                    <a href="/api/spx-straddle/dashboard">📈 SPX 0DTE Straddle</a>
                    <a href="/api/spy-expected-move/dashboard" class="current">📊 SPY Expected Move</a>
                    <a href="/api/dashboard">🔄 Unified Dashboard</a>
                </div>
                
                <div class="card">
                    <h2>🎯 SPY Current Status</h2>
        """
        
        # Add current SPY data
        if current_data and current_data.get('expected_move_1sigma'):
            html_content += f"""
                    <p><strong>Status:</strong> <span class="status-available">DATA AVAILABLE</span></p>
                    <p><strong>Last Update:</strong> {current_data.get('timestamp', 'N/A')}</p>
                    <p><strong>Date:</strong> {current_data.get('date', 'N/A')}</p>
                    
                    <div style="margin-top: 20px;">
                        <div class="metric">
                            <div class="metric-value">±${current_data.get('expected_move_1sigma', 0):.2f}</div>
                            <div class="metric-label">Expected Move (1σ)</div>
                        </div>
                        <div class="metric">
                            <div class="metric-value">±${current_data.get('expected_move_2sigma', 0):.2f}</div>
                            <div class="metric-label">Expected Move (2σ)</div>
                        </div>
                        <div class="metric">
                            <div class="metric-value">${current_data.get('spy_price_930am', 0):.2f}</div>
                            <div class="metric-label">SPY @ 9:30 AM</div>
                        </div>
                        <div class="metric">
                            <div class="metric-value">{current_data.get('atm_strike', 0)}</div>
                            <div class="metric-label">ATM Strike</div>
                        </div>
                        <div class="metric">
                            <div class="metric-value">${current_data.get('straddle_cost', 0):.2f}</div>
                            <div class="metric-label">Straddle Cost</div>
                        </div>
                        <div class="metric">
                            <div class="metric-value">{current_data.get('implied_volatility', 0):.1%}</div>
                            <div class="metric-label">Implied Volatility</div>
                        </div>
                    </div>
                    
                    <div style="margin-top: 20px; padding: 15px; background: #e7f3ff; border-radius: 4px;">
                        <h4 style="margin: 0 0 10px 0; color: #0066cc;">ORB Analysis</h4>
                        <p style="margin: 5px 0;"><strong>Opening Range (9:30-9:32):</strong> ${current_data.get('orb_low', 0):.2f} - ${current_data.get('orb_high', 0):.2f}</p>
                        <p style="margin: 5px 0;"><strong>Range Size:</strong> ${current_data.get('orb_range', 0):.2f}</p>
                        <p style="margin: 5px 0;"><strong>Range Efficiency:</strong> {current_data.get('range_efficiency', 0) if current_data.get('range_efficiency') != 'None' else 'N/A'}</p>
                    </div>
            """
        else:
            html_content += f"""
                    <p><strong>Status:</strong> <span class="status-no_data">NO DATA AVAILABLE</span></p>
                    <p><strong>Message:</strong> {current_data.get('message', 'No SPY expected move data for today. Calculate to generate data.')}</p>
            """
        
        html_content += """
                    <div style="margin-top: 20px;">
                        <a href="/api/spy-expected-move/calculate" class="btn btn-spy">🔄 Calculate SPY Move</a>
                        <a href="/api/discord/test" class="btn btn-success">🧪 Test Discord</a>
                    </div>
                </div>
                
                <!-- Historical Data Backfill -->
                <div class="card">
                    <h2>📚 Historical Data Backfill</h2>
                    <p>Populate your database with historical SPY expected move data for comprehensive analysis and trending.</p>
                    
                    <div style="margin: 15px 0; padding: 12px; background: #fff3cd; border: 1px solid #ffeaa7; border-radius: 4px;">
                        <strong>⚠️ Important:</strong> SPY daily 0DTE options only became available in 2022. 
                        Historical data is limited to <strong>January 1, 2023</strong> onwards for reliable analysis.
                    </div>
                    
                    <div style="margin: 20px 0;">
                        <h4>Quick Scenarios</h4>
                        <div style="display: flex; flex-wrap: wrap; gap: 10px; margin: 15px 0;">
                            <button class="btn btn-spy" onclick="runSpyBackfill('1week')">📅 1 Week</button>
                            <button class="btn btn-spy" onclick="runSpyBackfill('1month')">📅 1 Month</button>
                            <button class="btn btn-spy" onclick="runSpyBackfill('3months')">📅 3 Months</button>
                            <button class="btn btn-spy" onclick="runSpyBackfill('6months')">📅 6 Months</button>
                            <button class="btn btn-spy" onclick="runSpyBackfill('1year')">📅 1 Year</button>
                            <button class="btn btn-spy" onclick="runSpyBackfill('max')">📅 Max Available</button>
                        </div>
                    </div>
                    
                    <div style="margin: 20px 0;">
                        <h4>Custom Date Range</h4>
                        <div style="display: flex; flex-wrap: wrap; gap: 10px; align-items: center; margin: 15px 0;">
                            <label>Start Date:</label>
                            <input type="date" id="spy-backfill-start-date" min="2023-01-01" style="padding: 8px; border: 1px solid #ddd; border-radius: 4px;">
                            <label>End Date:</label>
                            <input type="date" id="spy-backfill-end-date" min="2023-01-01" style="padding: 8px; border: 1px solid #ddd; border-radius: 4px;">
                            <button class="btn btn-spy" onclick="runCustomSpyBackfill()">🚀 Start Custom Backfill</button>
                        </div>
                        <p style="font-size: 0.9em; color: #666; margin: 5px 0;">
                            <em>Minimum date: January 1, 2023 (SPY 0DTE launch)</em>
                        </p>
                    </div>
                    
                    <div id="spy-backfill-status" style="margin-top: 15px; padding: 10px; border-radius: 4px; display: none;"></div>
                </div>
                
                <!-- Charts -->
                <div class="card">
                    <h2>📈 SPY Expected Move Analysis</h2>
                    <div class="chart-controls">
                        <select id="time-period" onchange="updateChart()">
                            <option value="30">30 Days</option>
                            <option value="90">3 Months</option>
                            <option value="180">6 Months</option>
                            <option value="365">1 Year</option>
                            <option value="730" selected>2 Years</option>
                        </select>
                        <select id="chart-type" onchange="updateChart()">
                            <option value="trend" selected>Expected Move Trend</option>
                            <option value="volatility">Implied Volatility</option>
                            <option value="efficiency">Range Efficiency</option>
                        </select>
                        <button class="fullscreen-btn" onclick="toggleFullscreen('chart-container')">🔍 Fullscreen</button>
                    </div>
                    <div id="chart-container" class="chart-container">
                        <canvas id="spyChart"></canvas>
                    </div>
                    <div id="chart-status" style="text-align: center; margin-top: 10px; padding: 10px; border-radius: 4px;"></div>
                </div>
        """
        
        # Add multi-timeframe statistics if available
        if multi_stats.get("status") == "success":
            html_content += """
                <div class="card">
                    <h2>📊 Multi-Timeframe Statistics</h2>
                    <div style="overflow-x: auto;">
                        <table>
                            <thead>
                                <tr>
                                    <th>Timeframe</th>
                                    <th>Avg Expected Move</th>
                                    <th>Min Expected Move</th>
                                    <th>Max Expected Move</th>
                                    <th>Avg IV</th>
                                    <th>Count</th>
                                    <th>Trend</th>
                                </tr>
                            </thead>
                            <tbody>
            """
            
            # Process each timeframe and display statistics
            timeframes = multi_stats.get("timeframes", {})
            for timeframe_key in sorted(timeframes.keys(), key=lambda x: int(x.replace('D', ''))):
                timeframe_data = timeframes[timeframe_key]
                
                # Extract values with proper error handling
                mean_val = timeframe_data.get('mean', 0.0)
                min_val = timeframe_data.get('min', 0.0)
                max_val = timeframe_data.get('max', 0.0)
                data_points = timeframe_data.get('data_points', 0)
                
                html_content += f"""
                                <tr>
                                    <td>{timeframe_key}</td>
                                    <td>±${mean_val:.2f}</td>
                                    <td>±${min_val:.2f}</td>
                                    <td>±${max_val:.2f}</td>
                                    <td>0.0%</td>
                                    <td>{data_points}</td>
                                    <td>➡️</td>
                                </tr>
                """
            
            html_content += """
                            </tbody>
                        </table>
                    </div>
                </div>
            """
        
        # Close the HTML with JavaScript functions
        html_content += """
                
                <script>
                    let spyChart = null;
                    
                    // Chart update functionality
                    async function updateChart() {
                        const days = document.getElementById('time-period').value;
                        const chartType = document.getElementById('chart-type').value;
                        const statusDiv = document.getElementById('chart-status');
                        
                        statusDiv.innerHTML = '<div style="color: #007bff;">📊 Loading chart data...</div>';
                        
                        try {
                            const response = await fetch(`/api/spy-expected-move/chart-config/${chartType}?days=${days}`);
                            
                            if (!response.ok) {
                                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
                            }
                            
                            const config = await response.json();
                            
                            const ctx = document.getElementById('spyChart').getContext('2d');
                            
                            if (spyChart) {
                                spyChart.destroy();
                            }
                            
                            spyChart = new Chart(ctx, config);
                            statusDiv.innerHTML = '';
                            
                        } catch (error) {
                            console.error('Error loading SPY chart:', error);
                            statusDiv.innerHTML = `<div style="color: #dc3545; background: #f8d7da; padding: 10px; border-radius: 4px;">❌ Error loading chart: ${error.message}</div>`;
                        }
                    }
                    
                    // Fullscreen functionality
                    function toggleFullscreen(containerId) {
                        const container = document.getElementById(containerId);
                        
                        if (!document.fullscreenElement) {
                            container.requestFullscreen().then(() => {
                                // Add fullscreen controls
                                const controls = document.createElement('div');
                                controls.id = 'fullscreen-controls';
                                controls.style.cssText = `
                                    position: fixed;
                                    top: 20px;
                                    right: 20px;
                                    z-index: 9999;
                                    background: rgba(0,0,0,0.8);
                                    color: white;
                                    padding: 10px;
                                    border-radius: 8px;
                                `;
                                controls.innerHTML = `
                                    <button onclick="exitFullscreen()" style="background: #dc3545; color: white; border: none; padding: 8px 16px; border-radius: 4px; cursor: pointer;">
                                        ✕ Exit Fullscreen (ESC)
                                    </button>
                                `;
                                container.appendChild(controls);
                                
                                // Resize chart
                                setTimeout(() => {
                                    if (spyChart) {
                                        spyChart.resize();
                                    }
                                }, 100);
                            });
                        } else {
                            document.exitFullscreen();
                        }
                    }
                    
                    function exitFullscreen() {
                        if (document.fullscreenElement) {
                            document.exitFullscreen();
                        }
                    }
                    
                    // Handle ESC key for fullscreen exit
                    document.addEventListener('keydown', (e) => {
                        if (e.key === 'Escape' && document.fullscreenElement) {
                            exitFullscreen();
                        }
                    });
                    
                    // Clean up fullscreen controls when exiting
                    document.addEventListener('fullscreenchange', () => {
                        if (!document.fullscreenElement) {
                            const controls = document.getElementById('fullscreen-controls');
                            if (controls) {
                                controls.remove();
                            }
                            
                            // Resize chart back to normal
                            setTimeout(() => {
                                if (spyChart) spyChart.resize();
                            }, 100);
                        }
                    });
                    
                    // Initialize chart on page load
                    document.addEventListener('DOMContentLoaded', () => {
                        updateChart();
                    });
                    
                    // Backfill functionality
                    async function runBackfill(scenario) {
                        const statusDiv = document.getElementById('backfill-status');
                        statusDiv.style.display = 'block';
                        statusDiv.innerHTML = `<div style="color: #007bff; background: #e7f3ff; padding: 10px; border-radius: 4px;">🔄 Starting ${scenario} backfill...</div>`;
                        
                        try {
                            const response = await fetch(`/api/spx-straddle/backfill/scenario/${scenario}`, {
                                method: 'POST'
                            });
                            
                            if (response.ok) {
                                const result = await response.json();
                                statusDiv.innerHTML = `<div style="color: #28a745; background: #d4edda; padding: 10px; border-radius: 4px;">✅ ${scenario} backfill started successfully! Check logs for progress.</div>`;
                            } else {
                                const error = await response.json();
                                statusDiv.innerHTML = `<div style="color: #dc3545; background: #f8d7da; padding: 10px; border-radius: 4px;">❌ Error: ${error.detail}</div>`;
                            }
                        } catch (error) {
                            statusDiv.innerHTML = `<div style="color: #dc3545; background: #f8d7da; padding: 10px; border-radius: 4px;">❌ Network error: ${error.message}</div>`;
                        }
                    }
                    
                    async function runCustomBackfill() {
                        const startDate = document.getElementById('backfill-start-date').value;
                        const endDate = document.getElementById('backfill-end-date').value;
                        const statusDiv = document.getElementById('backfill-status');
                        
                        if (!startDate) {
                            statusDiv.style.display = 'block';
                            statusDiv.innerHTML = `<div style="color: #dc3545; background: #f8d7da; padding: 10px; border-radius: 4px;">❌ Please select a start date</div>`;
                            return;
                        }
                        
                        statusDiv.style.display = 'block';
                        statusDiv.innerHTML = `<div style="color: #007bff; background: #e7f3ff; padding: 10px; border-radius: 4px;">🔄 Starting custom backfill from ${startDate}${endDate ? ' to ' + endDate : ''}...</div>`;
                        
                        try {
                            let url = `/api/spx-straddle/backfill/custom?start_date=${startDate}`;
                            if (endDate) {
                                url += `&end_date=${endDate}`;
                            }
                            
                            const response = await fetch(url, {
                                method: 'POST'
                            });
                            
                            if (response.ok) {
                                const result = await response.json();
                                statusDiv.innerHTML = `<div style="color: #28a745; background: #d4edda; padding: 10px; border-radius: 4px;">✅ Custom backfill started successfully! Check logs for progress.</div>`;
                            } else {
                                const error = await response.json();
                                statusDiv.innerHTML = `<div style="color: #dc3545; background: #f8d7da; padding: 10px; border-radius: 4px;">❌ Error: ${error.detail}</div>`;
                            }
                        } catch (error) {
                            statusDiv.innerHTML = `<div style="color: #dc3545; background: #f8d7da; padding: 10px; border-radius: 4px;">❌ Network error: ${error.message}</div>`;
                        }
                    }
                    
                    // SPY Backfill functionality
                    async function runSpyBackfill(scenario) {
                        const statusDiv = document.getElementById('spy-backfill-status');
                        statusDiv.style.display = 'block';
                        statusDiv.innerHTML = `<div style="color: #6f42c1; background: #f3e5f5; padding: 10px; border-radius: 4px;">🔄 Starting SPY ${scenario} backfill...</div>`;
                        
                        try {
                            const response = await fetch(`/api/spy-expected-move/backfill/scenario/${scenario}`, {
                                method: 'POST'
                            });
                            
                            if (response.ok) {
                                const result = await response.json();
                                statusDiv.innerHTML = `<div style="color: #28a745; background: #d4edda; padding: 10px; border-radius: 4px;">✅ SPY ${scenario} backfill started successfully! Check logs for progress.</div>`;
                            } else {
                                const error = await response.json();
                                statusDiv.innerHTML = `<div style="color: #dc3545; background: #f8d7da; padding: 10px; border-radius: 4px;">❌ Error: ${error.detail}</div>`;
                            }
                        } catch (error) {
                            statusDiv.innerHTML = `<div style="color: #dc3545; background: #f8d7da; padding: 10px; border-radius: 4px;">❌ Network error: ${error.message}</div>`;
                        }
                    }
                    
                    async function runCustomSpyBackfill() {
                        const startDate = document.getElementById('spy-backfill-start-date').value;
                        const endDate = document.getElementById('spy-backfill-end-date').value;
                        const statusDiv = document.getElementById('spy-backfill-status');
                        
                        if (!startDate) {
                            statusDiv.style.display = 'block';
                            statusDiv.innerHTML = `<div style="color: #dc3545; background: #f8d7da; padding: 10px; border-radius: 4px;">❌ Please select a start date</div>`;
                            return;
                        }
                        
                        statusDiv.style.display = 'block';
                        statusDiv.innerHTML = `<div style="color: #6f42c1; background: #f3e5f5; padding: 10px; border-radius: 4px;">🔄 Starting custom SPY backfill from ${startDate}${endDate ? ' to ' + endDate : ''}...</div>`;
                        
                        try {
                            let url = `/api/spy-expected-move/backfill/custom?start_date=${startDate}`;
                            if (endDate) {
                                url += `&end_date=${endDate}`;
                            }
                            
                            const response = await fetch(url, {
                                method: 'POST'
                            });
                            
                            if (response.ok) {
                                const result = await response.json();
                                statusDiv.innerHTML = `<div style="color: #28a745; background: #d4edda; padding: 10px; border-radius: 4px;">✅ Custom SPY backfill started successfully! Check logs for progress.</div>`;
                            } else {
                                const error = await response.json();
                                statusDiv.innerHTML = `<div style="color: #dc3545; background: #f8d7da; padding: 10px; border-radius: 4px;">❌ Error: ${error.detail}</div>`;
                            }
                        } catch (error) {
                            statusDiv.innerHTML = `<div style="color: #dc3545; background: #f8d7da; padding: 10px; border-radius: 4px;">❌ Network error: ${error.message}</div>`;
                        }
                    }
                </script>
            </div>
        </body>
        </html>
        """
        
        return HTMLResponse(content=html_content)
        
    except Exception as e:
        logger.error(f"Error generating SPY dashboard: {e}")
        return HTMLResponse(
            content=f"<html><body><h1>Error</h1><p>Failed to load SPY dashboard: {e}</p></body></html>",
            status_code=500
        )

@app.post("/api/spy-expected-move/backfill/scenario/{scenario}")
async def backfill_spy_scenario(scenario: str, background_tasks: BackgroundTasks):
    """Run predefined SPY backfill scenarios"""
    from datetime import timedelta
    
    et_tz = pytz.timezone('US/Eastern')
    today = datetime.now(et_tz).date()
    
    # SPY 0DTE options only available from 2023 onwards
    # Limit scenarios to realistic date ranges
    scenarios = {
        "1week": {"days": 7, "description": "Last 7 days"},
        "1month": {"days": 30, "description": "Last 30 days"},
        "3months": {"days": 90, "description": "Last 3 months"},
        "6months": {"days": 180, "description": "Last 6 months"},
        "1year": {"days": 365, "description": "Last 1 year (limited by SPY 0DTE availability)"},
        "max": {"days": 730, "description": "Maximum available (since Jan 2023)"}
    }
    
    if scenario not in scenarios:
        raise HTTPException(
            status_code=400, 
            detail=f"Unknown scenario: {scenario}. Available: {', '.join(scenarios.keys())}"
        )
    
    config = scenarios[scenario]
    start_date = today - timedelta(days=config["days"])
    end_date = today - timedelta(days=1)
    
    # Ensure we don't go before SPY 0DTE options were available (Jan 1, 2023)
    spy_0dte_launch = date(2023, 1, 1)
    if start_date < spy_0dte_launch:
        start_date = spy_0dte_launch
    
    # Run SPY backfill in background
    async def run_spy_backfill():
        try:
            logger.info(f"Starting SPY backfill scenario: {scenario} ({config['description']})")
            success_count = 0
            error_count = 0
            skipped_count = 0
            
            current_date = start_date
            while current_date <= end_date:
                try:
                    # Check if it's a trading day (basic check - skip weekends)
                    if current_date.weekday() >= 5:  # Saturday = 5, Sunday = 6
                        current_date += timedelta(days=1)
                        continue
                    
                    # Check if data already exists
                    existing_data = await spy_calculator.get_spy_data_for_date(current_date.strftime('%Y-%m-%d'))
                    if existing_data:
                        logger.info(f"SPY data already exists for {current_date}, skipping")
                        skipped_count += 1
                        current_date += timedelta(days=1)
                        continue
                    
                    # Calculate SPY expected move for this date
                    spy_data = await spy_calculator.calculate_spy_expected_move_historical(current_date)
                    
                    if spy_data:
                        await spy_calculator._store_spy_data(spy_data)
                        success_count += 1
                        logger.info(f"Successfully backfilled SPY data for {current_date}")
                    else:
                        error_count += 1
                        logger.warning(f"Failed to calculate SPY data for {current_date}")
                        
                except Exception as e:
                    error_count += 1
                    logger.error(f"Error backfilling SPY data for {current_date}: {e}")
                
                current_date += timedelta(days=1)
                
                # Small delay to avoid overwhelming the API
                await asyncio.sleep(0.5)
            
            # Send Discord notification if enabled
            if discord_notifier and discord_notifier.is_enabled():
                total_days = success_count + error_count + skipped_count
                success_rate = (success_count / total_days * 100) if total_days > 0 else 0
                
                message = f"""🔄 **SPY Expected Move Backfill Completed**
                
**Scenario:** {scenario} ({config['description']})
**Date Range:** {start_date} to {end_date}
**Results:**
• ✅ Successful: {success_count}
• ❌ Failed: {error_count}  
• ⏭️ Skipped: {skipped_count}
• 📊 Success Rate: {success_rate:.1f}%

*Historical SPY expected move data is now available for analysis.*"""
                
                await discord_notifier.send_message(message)
            
            logger.info(f"SPY backfill {scenario} completed: {success_count} success, {error_count} errors, {skipped_count} skipped")
            
        except Exception as e:
            logger.error(f"SPY backfill {scenario} failed: {e}")
    
    background_tasks.add_task(run_spy_backfill)
    
    return {
        "status": "started",
        "scenario": scenario,
        "description": config["description"],
        "date_range": {
            "start": start_date.isoformat(),
            "end": end_date.isoformat()
        },
        "message": f"SPY backfill {scenario} started in background. Check logs for progress."
    }

@app.post("/api/spy-expected-move/backfill/custom")
async def backfill_spy_custom(
    background_tasks: BackgroundTasks,
    start_date: str,
    end_date: str = None,
    batch_size: int = 5,
    delay: float = 2.0
):
    """Run custom date range SPY backfill"""
    try:
        # Parse dates
        start_dt = datetime.strptime(start_date, '%Y-%m-%d').date()
        
        if end_date:
            end_dt = datetime.strptime(end_date, '%Y-%m-%d').date()
        else:
            et_tz = pytz.timezone('US/Eastern')
            end_dt = datetime.now(et_tz).date() - timedelta(days=1)
        
        # Validate dates
        today = datetime.now(pytz.timezone('US/Eastern')).date()
        spy_0dte_launch = date(2023, 1, 1)
        
        if start_dt >= end_dt:
            raise HTTPException(status_code=400, detail="Start date must be before end date")
        if end_dt >= today:
            raise HTTPException(status_code=400, detail="End date must be before today")
        if start_dt < spy_0dte_launch:
            raise HTTPException(
                status_code=400, 
                detail=f"Start date cannot be before {spy_0dte_launch} (SPY 0DTE options launch date)"
            )
        
        # Run SPY backfill in background
        async def run_spy_custom_backfill():
            try:
                logger.info(f"Starting custom SPY backfill: {start_dt} to {end_dt}")
                success_count = 0
                error_count = 0
                skipped_count = 0
                
                current_date = start_dt
                batch_count = 0
                
                while current_date <= end_dt:
                    batch_dates = []
                    
                    # Collect batch of dates
                    for _ in range(batch_size):
                        if current_date > end_dt:
                            break
                        
                        # Skip weekends
                        if current_date.weekday() < 5:  # Monday = 0, Friday = 4
                            batch_dates.append(current_date)
                        
                        current_date += timedelta(days=1)
                    
                    if not batch_dates:
                        break
                    
                    # Process batch
                    batch_count += 1
                    logger.info(f"Processing SPY batch {batch_count}: {len(batch_dates)} dates")
                    
                    for date in batch_dates:
                        try:
                            # Check if data already exists
                            existing_data = await spy_calculator.get_spy_data_for_date(date.strftime('%Y-%m-%d'))
                            if existing_data:
                                logger.info(f"SPY data already exists for {date}, skipping")
                                skipped_count += 1
                                continue
                            
                            # Calculate SPY expected move for this date
                            spy_data = await spy_calculator.calculate_spy_expected_move_historical(date)
                            
                            if spy_data:
                                await spy_calculator._store_spy_data(spy_data)
                                success_count += 1
                                logger.info(f"Successfully backfilled SPY data for {date}")
                            else:
                                error_count += 1
                                logger.warning(f"Failed to calculate SPY data for {date}")
                                
                        except Exception as e:
                            error_count += 1
                            logger.error(f"Error backfilling SPY data for {date}: {e}")
                    
                    # Delay between batches
                    if current_date <= end_dt:
                        await asyncio.sleep(delay)
                
                # Send Discord notification if enabled
                if discord_notifier and discord_notifier.is_enabled():
                    total_days = success_count + error_count + skipped_count
                    success_rate = (success_count / total_days * 100) if total_days > 0 else 0
                    
                    message = f"""🔄 **Custom SPY Expected Move Backfill Completed**
                    
**Date Range:** {start_dt} to {end_dt}
**Results:**
• ✅ Successful: {success_count}
• ❌ Failed: {error_count}  
• ⏭️ Skipped: {skipped_count}
• 📊 Success Rate: {success_rate:.1f}%

*Historical SPY expected move data is now available for analysis.*"""
                    
                    await discord_notifier.send_message(message)
                
                logger.info(f"Custom SPY backfill completed: {success_count} success, {error_count} errors, {skipped_count} skipped")
                
            except Exception as e:
                logger.error(f"Custom SPY backfill failed: {e}")
        
        background_tasks.add_task(run_spy_custom_backfill)
        
        return {
            "status": "started",
            "date_range": {
                "start": start_dt.isoformat(),
                "end": end_dt.isoformat()
            },
            "batch_size": batch_size,
            "delay": delay,
            "message": f"Custom SPY backfill started in background from {start_dt} to {end_dt}. Check logs for progress."
        }
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid date format. Use YYYY-MM-DD: {e}")
    except Exception as e:
        logger.error(f"Error starting custom SPY backfill: {e}")
        raise HTTPException(status_code=500, detail="Failed to start custom SPY backfill")

@app.get("/api/spy-expected-move/test-stats")
async def test_spy_stats():
    """Test endpoint to verify SPY multi-timeframe statistics"""
    try:
        result = await get_spy_multi_timeframe_statistics()
        return {
            "status": "success",
            "function_result": result,
            "test_values": {
                "result_type": str(type(result)),
                "has_status": "status" in result if isinstance(result, dict) else False,
                "status_value": result.get("status") if isinstance(result, dict) else None,
                "has_timeframes": "timeframes" in result if isinstance(result, dict) else False,
                "timeframe_count": len(result.get("timeframes", {})) if isinstance(result, dict) else 0,
                "sample_1d_data": result.get("timeframes", {}).get("1D") if isinstance(result, dict) else None
            }
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "error_type": str(type(e))
        }

@app.get("/api/spy-expected-move/debug-dashboard-data")
async def debug_spy_dashboard_data():
    """Debug endpoint to see exactly what data the SPY dashboard receives"""
    try:
        # Get the same data the dashboard gets
        multi_stats = await get_spy_multi_timeframe_statistics()
        
        # Extract and process exactly like the dashboard does
        timeframes = multi_stats.get("timeframes", {})
        debug_info = {}
        
        for timeframe_key in sorted(timeframes.keys(), key=lambda x: int(x.replace('D', ''))):
            timeframe_data = timeframes[timeframe_key]
            
            # Extract values with proper error handling (same as dashboard)
            mean_val = timeframe_data.get('mean', 0.0)
            min_val = timeframe_data.get('min', 0.0)
            max_val = timeframe_data.get('max', 0.0)
            data_points = timeframe_data.get('data_points', 0)
            
            debug_info[timeframe_key] = {
                "raw_timeframe_data": timeframe_data,
                "extracted_mean": mean_val,
                "extracted_min": min_val,
                "extracted_max": max_val,
                "extracted_data_points": data_points,
                "mean_type": str(type(mean_val)),
                "formatted_mean": f"±${mean_val:.2f}"
            }
        
        return {
            "status": "debug",
            "multi_stats_status": multi_stats.get("status"),
            "multi_stats_type": str(type(multi_stats)),
            "timeframes_count": len(timeframes),
            "sample_debug_info": debug_info,
            "first_timeframe_raw": list(timeframes.values())[0] if timeframes else None
        }
        
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "error_type": str(type(e))
        }

# Run the application
if __name__ == "__main__":
    import uvicorn
    
    host = os.getenv("API_HOST", "0.0.0.0")
    port = int(os.getenv("API_PORT", "8000"))
    
    uvicorn.run(app, host=host, port=port) 