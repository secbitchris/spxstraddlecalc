from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, HTMLResponse
import asyncio
import json
import io
import csv
import logging
from datetime import datetime, date
import pytz
from spx_calculator import SPXStraddleCalculator
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
discord_notifier = None
gist_publisher = None

@app.on_event("startup")
async def startup_event():
    """Initialize the SPX calculator, Discord notifier, and Gist publisher on startup"""
    global calculator, discord_notifier, gist_publisher
    
    # Initialize calculator
    polygon_api_key = os.getenv("POLYGON_API_KEY")
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
    
    if not polygon_api_key:
        raise ValueError("POLYGON_API_KEY environment variable is required")
    
    calculator = SPXStraddleCalculator(polygon_api_key, redis_url)
    await calculator.initialize()
    logger.info("SPX Straddle Calculator initialized")
    
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
    global calculator, discord_notifier, gist_publisher
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
        # Include all timeframes - let users decide what's useful based on actual data points
        weekly_monthly_timeframes = [30, 45, 60, 90, 120, 180, 240, 360, 540, 720, 900]
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
                
                if stats.get('status') == 'success' and stats.get('data_points', 0) >= 5:
                    # Determine timeframe key (YTD gets special treatment)
                    if days == ytd_days:
                        timeframe_key = "ytd"
                        timeframe_label = f"YTD ({days}d)"
                    else:
                        timeframe_key = f"{days}d"
                        timeframe_label = f"{days}d"
                    
                    # Track actual data points - no confusing "coverage" calculations
                    data_points = stats.get('data_points', 0)
                    
                    # Only include timeframes with sufficient data (5+ points)
                    results["timeframes"][timeframe_key] = {
                        "period_days": days,
                        "period_label": timeframe_label,
                        "is_ytd": days == ytd_days,
                        "data_points": data_points,
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
                        "data_points": data_points,
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
                                   key=lambda x: results["timeframes"][x]["data_points"])
            
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
Total Historical Data: {summary.get('total_data_points', 'N/A')} trading days

## Executive Summary
This comprehensive analysis covers {len(timeframes)} timeframes from daily (1D) to long-term (900D) perspectives, providing insights into SPX 0DTE straddle cost volatility patterns across different time horizons.

## Detailed Timeframe Analysis

"""
        
        # Sort timeframes by period days for logical progression
        sorted_timeframes = sorted(timeframes.items(), key=lambda x: x[1].get('period_days', 0))
        
        for timeframe_key, tf_data in sorted_timeframes:
            period_label = tf_data.get('period_label', timeframe_key)
            period_days = tf_data.get('period_days', 0)
            data_points = tf_data.get('data_points', 0)
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
**Data Coverage:** {data_points} data points

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
                "total_data_points": summary.get('total_data_points', 0),
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

@app.get("/api/spx-straddle/dashboard", response_class=HTMLResponse)
async def get_spx_straddle_dashboard():
    """Simple HTML dashboard for SPX straddle data"""
    try:
        # Get current data
        current_data = await calculator.get_spx_straddle_cost()
        
        # Get recent history
        history_data = await calculator.get_spx_straddle_history(7)
        
        # Get statistics
        stats_data = await calculator.calculate_spx_straddle_statistics(30)
        
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
            <style>
                body {{ 
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; 
                    margin: 0; 
                    padding: 20px; 
                    background-color: #f5f5f5;
                }}
                .container {{ max-width: 1200px; margin: 0 auto; }}
                .header {{ text-align: center; margin-bottom: 30px; }}
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

            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>📊 SPX 0DTE Straddle Dashboard</h1>
                    <p>Real-time SPX straddle cost tracking using Polygon.io</p>
                </div>
                
                <div class="card">
                    <h2>🎯 Current Status</h2>
                    <p><strong>Status:</strong> <span class="status-{current_data.get('calculation_status', 'unknown')}">{current_data.get('calculation_status', 'Unknown').upper().replace('_', ' ')}</span></p>
                    <p><strong>Last Update:</strong> {current_data.get('timestamp', 'N/A')}</p>
                    <p><strong>Discord Notifications:</strong> {'✅ Enabled' if discord_enabled else '❌ Disabled'}</p>
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
        """
        
        # Add multi-timeframe statistics if available
        if multi_stats.get('status') == 'success' and multi_stats.get('timeframes'):
            timeframes = multi_stats.get('timeframes', {})
            summary = multi_stats.get('summary', {})
            
            html_content += f"""
                <div class="card">
                    <h2>📈 Multi-Timeframe Statistics</h2>
                    <p><strong>Available Timeframes:</strong> {len(timeframes)} periods with sufficient data</p>
                    <p><strong>Recommended Analysis Period:</strong> {summary.get('recommended_timeframe', 'N/A')}</p>
                    <p><strong>Trend Consistency:</strong> {'✅ Consistent' if summary.get('trend_consistency') else '⚠️ Mixed'}</p>
                    
                    <div style="overflow-x: auto; margin-top: 20px;">
                        <table style="min-width: 100%;">
                            <thead>
                                <tr>
                                    <th>Period</th>
                                    <th>Data Points</th>
                                    <th>Average</th>
                                    <th>Range</th>
                                    <th>Trend</th>
                                    <th>Volatility</th>
                                </tr>
                            </thead>
                            <tbody>
            """
            
            # Sort timeframes by period length
            sorted_timeframes = sorted(timeframes.items(), key=lambda x: x[1]['period_days'])
            
            for period_key, data in sorted_timeframes:
                period_days = data['period_days']
                data_points = data['data_points']
                coverage = summary.get('data_coverage', {}).get(period_key, {}).get('coverage_percentage', 0)
                
                desc_stats = data.get('descriptive_stats', {})
                trend = data.get('trend_analysis', {})
                volatility = data.get('volatility_analysis', {})
                
                # Format period name (use period_label if available, especially for YTD)
                if data.get('is_ytd', False):
                    period_name = f"📅 {data.get('period_label', 'YTD')}"
                elif period_days < 30:
                    period_name = f"{period_days}d"
                elif period_days < 365:
                    period_name = f"{period_days//30}m" if period_days % 30 == 0 else f"{period_days}d"
                else:
                    period_name = f"{period_days//365}y" if period_days % 365 == 0 else f"{period_days}d"
                
                # Trend emoji
                trend_emoji = "📈" if trend.get('direction') == 'increasing' else "📉" if trend.get('direction') == 'decreasing' else "➡️"
                
                # Volatility color
                vol_category = volatility.get('category', 'unknown')
                vol_color = '#28a745' if vol_category == 'low' else '#ffc107' if vol_category == 'medium' else '#dc3545'
                
                html_content += f"""
                                <tr>
                                    <td><strong>{period_name}</strong></td>
                                    <td>{data_points}</td>
                                    <td>${desc_stats.get('mean', 0):.2f}</td>
                                    <td>${desc_stats.get('min', 0):.2f} - ${desc_stats.get('max', 0):.2f}</td>
                                    <td>{trend_emoji} {trend.get('direction', 'Unknown').title()}</td>
                                    <td><span style="color: {vol_color};">{vol_category.title()}</span></td>
                                </tr>
                """
            
            html_content += """
                            </tbody>
                        </table>
                    </div>
                    
                    <div style="margin-top: 20px;">
                        <a href="/api/spx-straddle/statistics/multi-timeframe" class="btn">📊 View Full Multi-Timeframe Data</a>
                        <a href="/api/spx-straddle/export/csv?days=720" class="btn">📥 Export 2-Year CSV</a>
                    </div>
                </div>
            """
        elif stats_data.get('status') == 'success':
            # Fallback to single timeframe if multi-timeframe fails
            stats = stats_data.get('descriptive_stats', {})
            trend = stats_data.get('trend_analysis', {})
            volatility = stats_data.get('volatility_analysis', {})
            
            html_content += f"""
                <div class="grid">
                    <div class="card">
                        <h2>📈 30-Day Statistics</h2>
                        <div class="metric">
                            <div class="metric-value">${stats.get('mean', 0):.2f}</div>
                            <div class="metric-label">Average Cost</div>
                        </div>
                        <div class="metric">
                            <div class="metric-value">${stats.get('median', 0):.2f}</div>
                            <div class="metric-label">Median Cost</div>
                        </div>
                        <div class="metric">
                            <div class="metric-value">${stats.get('min', 0):.2f} - ${stats.get('max', 0):.2f}</div>
                            <div class="metric-label">Range</div>
                        </div>
                        <div class="metric">
                            <div class="metric-value">${stats.get('std_dev', 0):.2f}</div>
                            <div class="metric-label">Std Deviation</div>
                        </div>
                    </div>
                    
                    <div class="card">
                        <h2>📊 Analysis</h2>
                        <p><strong>Trend:</strong> {trend.get('direction', 'Unknown').title()}</p>
                        <p><strong>Volatility:</strong> {volatility.get('category', 'Unknown').title()} ({volatility.get('coefficient_of_variation', 0):.1f}%)</p>
                        <p><em>{trend.get('interpretation', '')}</em></p>
                        <p><em>{volatility.get('interpretation', '')}</em></p>
                    </div>
                </div>
            """
        
        # Add recent history table
        if history_data.get('status') == 'success' and history_data.get('data'):
            html_content += """
                <div class="card">
                    <h2>📅 Recent History (Last 7 Days)</h2>
                    <table>
                        <thead>
                            <tr>
                                <th>Date</th>
                                <th>SPX Price</th>
                                <th>Strike</th>
                                <th>Call Price</th>
                                <th>Put Price</th>
                                <th>Straddle Cost</th>
                            </tr>
                        </thead>
                        <tbody>
            """
            
            for record in history_data.get('data', []):
                html_content += f"""
                            <tr>
                                <td>{record.get('date', 'N/A')}</td>
                                <td>${record.get('spx_price_930am', 'N/A')}</td>
                                <td>{record.get('atm_strike', 'N/A')}</td>
                                <td>${record.get('call_price_931am', 'N/A')}</td>
                                <td>${record.get('put_price_931am', 'N/A')}</td>
                                <td>${record.get('straddle_cost', 'N/A')}</td>
                            </tr>
                """
            
            html_content += """
                        </tbody>
                    </table>
                </div>
            """
        
        html_content += """
                <div class="card">
                    <h2>📊 Historical Data Backfill</h2>
                    <p>Backfill historical SPX straddle data for trend and volatility analysis.</p>
                    
                    <div class="grid">
                        <div>
                            <h3>Quick Scenarios</h3>
                            <p>Run predefined backfill scenarios:</p>
                            <button onclick="runBackfill('1week')" class="btn">📅 Last Week</button>
                            <button onclick="runBackfill('1month')" class="btn">📅 Last Month</button>
                            <button onclick="runBackfill('3months')" class="btn">📅 Last 3 Months</button>
                            <button onclick="runBackfill('6months')" class="btn">📅 Last 6 Months</button>
                            <button onclick="runBackfill('1year')" class="btn">📅 Last Year</button>
                            <button onclick="runBackfill('2years')" class="btn">📅 Last 2 Years</button>
                        </div>
                        <div>
                            <h3>Custom Date Range</h3>
                            <p>Specify custom date range:</p>
                            <input type="date" id="startDate" style="margin: 5px; padding: 8px;">
                            <input type="date" id="endDate" style="margin: 5px; padding: 8px;">
                            <br>
                            <button onclick="runCustomBackfill()" class="btn" style="margin-top: 10px;">🚀 Start Custom Backfill</button>
                        </div>
                    </div>
                    
                    <div id="backfillStatus" style="margin-top: 15px; padding: 10px; border-radius: 4px; display: none;"></div>
                    
                    <script>
                        async function runBackfill(scenario) {
                            const statusDiv = document.getElementById('backfillStatus');
                            statusDiv.style.display = 'block';
                            statusDiv.style.backgroundColor = '#d1ecf1';
                            statusDiv.style.color = '#0c5460';
                            statusDiv.innerHTML = `🔄 Starting ${scenario} backfill...`;
                            
                            try {
                                const response = await fetch(`/api/spx-straddle/backfill/scenario/${scenario}`, {
                                    method: 'POST'
                                });
                                const result = await response.json();
                                
                                if (response.ok) {
                                    statusDiv.style.backgroundColor = '#d4edda';
                                    statusDiv.style.color = '#155724';
                                    statusDiv.innerHTML = `✅ ${result.message}<br>Date range: ${result.date_range.start_date} to ${result.date_range.end_date}`;
                                } else {
                                    throw new Error(result.detail || 'Unknown error');
                                }
                            } catch (error) {
                                statusDiv.style.backgroundColor = '#f8d7da';
                                statusDiv.style.color = '#721c24';
                                statusDiv.innerHTML = `❌ Error: ${error.message}`;
                            }
                        }
                        
                        async function runCustomBackfill() {
                            const startDate = document.getElementById('startDate').value;
                            const endDate = document.getElementById('endDate').value;
                            const statusDiv = document.getElementById('backfillStatus');
                            
                            if (!startDate) {
                                alert('Please select a start date');
                                return;
                            }
                            
                            statusDiv.style.display = 'block';
                            statusDiv.style.backgroundColor = '#d1ecf1';
                            statusDiv.style.color = '#0c5460';
                            statusDiv.innerHTML = '🔄 Starting custom backfill...';
                            
                            try {
                                const params = new URLSearchParams({ start_date: startDate });
                                if (endDate) params.append('end_date', endDate);
                                
                                const response = await fetch(`/api/spx-straddle/backfill/custom?${params}`, {
                                    method: 'POST'
                                });
                                const result = await response.json();
                                
                                if (response.ok) {
                                    statusDiv.style.backgroundColor = '#d4edda';
                                    statusDiv.style.color = '#155724';
                                    statusDiv.innerHTML = `✅ ${result.message}`;
                                } else {
                                    throw new Error(result.detail || 'Unknown error');
                                }
                            } catch (error) {
                                statusDiv.style.backgroundColor = '#f8d7da';
                                statusDiv.style.color = '#721c24';
                                statusDiv.innerHTML = `❌ Error: ${error.message}`;
                            }
                        }
                    </script>
                </div>
                
                <div class="card">
                    <h2>🔗 API Endpoints</h2>
                    <div class="grid">
                        <div>
                            <h3>Data Endpoints</h3>
                            <ul>
                                <li><a href="/api/spx-straddle/today">Today's Data</a></li>
                                <li><a href="/api/spx-straddle/history?days=30">30-Day History</a></li>
                                <li><a href="/api/spx-straddle/statistics?days=30">30-Day Statistics</a></li>
                                <li><a href="/api/spx-straddle/statistics/multi-timeframe">Multi-Timeframe Statistics</a></li>
                                <li><a href="/api/spx-straddle/statistics/full-report">📋 Full Analysis Report (for Gist)</a></li>
                                <li><a href="/api/spx-straddle/export/csv?days=30">Export CSV</a></li>
                                <li><a href="/api/spx-straddle/status">System Status</a></li>
                            </ul>
                        </div>
                        <div>
                            <h3>Actions</h3>
                            <ul>
                                <li><a href="/api/spx-straddle/calculate">Calculate Straddle</a></li>
                                <li><a href="/api/discord/test">Test Discord</a></li>
                                <li><a href="/api/discord/notify/today">Notify Discord</a></li>
                                <li><a href="/api/discord/notify/multi-timeframe">📊 Send Multi-Timeframe to Discord</a></li>
                                <li><a href="/api/discord/notify/daily-timeframes">⚡ Send Daily Analysis to Discord</a></li>
                                <li><a href="/api/spx-straddle/statistics/publish-gist">🔗 Publish Analysis to GitHub Gist</a></li>
                                <li><a href="/docs">API Documentation</a></li>
                            </ul>
                        </div>
                    </div>
                </div>
                
                <div class="card" style="text-align: center; color: #666; font-size: 0.9em;">
                    <p>SPX 0DTE Straddle Calculator | Powered by Polygon.io | Last updated: {datetime.now(pytz.timezone('US/Eastern')).strftime('%Y-%m-%d %H:%M:%S ET')}</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        return html_content
        
    except Exception as e:
        logger.error(f"Error generating dashboard: {e}")
        return f"""
        <html>
        <body style="font-family: Arial, sans-serif; padding: 20px;">
            <h1>❌ Dashboard Error</h1>
            <p>Failed to load dashboard: {str(e)}</p>
            <p><a href="/docs">View API Documentation</a></p>
        </body>
        </html>
        """

if __name__ == "__main__":
    import uvicorn
    
    host = os.getenv("API_HOST", "0.0.0.0")
    port = int(os.getenv("API_PORT", "8000"))
    
    uvicorn.run(app, host=host, port=port) 