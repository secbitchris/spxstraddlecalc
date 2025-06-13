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

@app.on_event("startup")
async def startup_event():
    """Initialize the SPX calculator and Discord notifier on startup"""
    global calculator, discord_notifier
    
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

@app.on_event("shutdown")
async def shutdown_event():
    """Clean up on shutdown"""
    global calculator, discord_notifier
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
            "discord": discord_notifier.is_enabled() if discord_notifier else False
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
        if days < 1 or days > 365:
            raise HTTPException(status_code=400, detail="Days parameter must be between 1 and 365")
        
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
        if days < 1 or days > 365:
            raise HTTPException(status_code=400, detail="Days parameter must be between 1 and 365")
        
        result = await calculator.calculate_spx_straddle_statistics(days)
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting straddle statistics: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve SPX straddle statistics")

@app.get("/api/spx-straddle/patterns")
async def get_spx_straddle_patterns(days: int = 30):
    """Get SPX straddle pattern analysis"""
    try:
        if days < 1 or days > 365:
            raise HTTPException(status_code=400, detail="Days parameter must be between 1 and 365")
        
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
        if days < 1 or days > 365:
            raise HTTPException(status_code=400, detail="Days parameter must be between 1 and 365")
        
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
            "discord_status": discord_notifier.get_status() if discord_notifier else {"enabled": False},
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
        backfill = HistoricalBackfill(calculator.polygon_api_key, calculator.redis_url)
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
            backfill = HistoricalBackfill(calculator.polygon_api_key, calculator.redis_url)
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
        
        # Get Discord status
        discord_status = discord_notifier.get_status() if discord_notifier else {"enabled": False}
        
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
                .discord-status {{ 
                    padding: 8px 12px; 
                    border-radius: 4px; 
                    font-size: 0.9em;
                    display: inline-block;
                }}
                .discord-enabled {{ background: #d4edda; color: #155724; }}
                .discord-disabled {{ background: #f8d7da; color: #721c24; }}
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
                    
                    <div class="discord-status {'discord-enabled' if discord_status.get('enabled') else 'discord-disabled'}">
                        Discord: {'✅ Connected' if discord_status.get('connected') else '❌ Disabled/Disconnected'}
                        {f" (#{discord_status.get('channel_name', 'unknown')})" if discord_status.get('connected') else ''}
                    </div>
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
        
        # Add statistics if available
        if stats_data.get('status') == 'success':
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