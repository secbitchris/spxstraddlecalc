# SPX Straddle Historical Data Backfill Guide

## Overview

The SPX Straddle Calculator now includes powerful historical data backfill capabilities that allow you to populate your database with historical SPX 0DTE straddle costs going back up to **2 years** (limited by Polygon.io data availability since July 2014).

## Why Backfill Historical Data?

Historical data enables:

- **Meaningful Statistical Analysis**: Trend detection, volatility analysis, and pattern recognition
- **Better Decision Making**: Understanding historical ranges and typical behavior
- **Performance Benchmarking**: Compare current costs against historical averages
- **Risk Assessment**: Analyze volatility patterns and extreme events

## Available Methods

### 1. Web Dashboard (Easiest)

Visit `http://localhost:8000/api/spx-straddle/dashboard` and use the **Historical Data Backfill** section:

- **Quick Scenarios**: One-click buttons for common periods
- **Custom Date Range**: Specify exact start/end dates
- **Real-time Status**: See progress and results immediately

### 2. API Endpoints

#### Predefined Scenarios
```bash
# Available scenarios: 1week, 1month, 3months, 6months, 1year, 2years
curl -X POST http://localhost:8000/api/spx-straddle/backfill/scenario/1month
```

#### Custom Date Range
```bash
curl -X POST "http://localhost:8000/api/spx-straddle/backfill/custom?start_date=2024-01-01&end_date=2024-12-31"
```

### 3. Command Line Scripts

#### Quick Scenarios
```bash
# Inside Docker container
docker compose exec spx-api python backfill_runner.py 1month

# Available scenarios:
# 1week   - Last 7 days
# 1month  - Last 30 days  
# 3months - Last 3 months
# 6months - Last 6 months
# 1year   - Last 1 year
# 2years  - Last 2 years
```

#### Advanced Custom Backfill
```bash
# Inside Docker container
docker compose exec spx-api python historical_backfill.py --start-date 2024-01-01 --end-date 2024-12-31

# Options:
# --start-date YYYY-MM-DD  : Start date (required)
# --end-date YYYY-MM-DD    : End date (defaults to yesterday)
# --days N                 : Alternative to start-date (N days back)
# --batch-size N           : Parallel processing batch size (default: 5)
# --delay N.N              : Delay between batches in seconds (default: 2.0)
```

## How It Works

### Data Collection Process

1. **Trading Day Identification**: Automatically excludes weekends and major US holidays
2. **SPX Index Data**: Fetches SPX price at 9:30 AM ET (market open)
3. **ATM Strike Calculation**: Rounds SPX price to nearest $5 increment
4. **Options Data**: Fetches SPXW call and put prices at 9:31 AM ET
5. **Straddle Cost**: Calculates total cost (call + put)
6. **Storage**: Saves to Redis with same format as daily calculations

### Technical Details

- **Ticker Format**: Uses `O:SPXW{YYMMDD}{C/P}{strike*1000}` for 0DTE options
- **Time Precision**: 9:30 AM for SPX, 9:31 AM for options (Eastern Time)
- **Strike Selection**: ATM strike rounded to nearest $5 (e.g., 6000.56 → 6000)
- **Data Source**: Polygon.io historical minute-level data
- **Rate Limiting**: Built-in delays to respect API limits
- **Error Handling**: Continues processing even if individual dates fail

## Performance and Limitations

### Expected Performance
- **1 week**: ~30 seconds (5 trading days)
- **1 month**: ~2-3 minutes (20-22 trading days)
- **3 months**: ~6-8 minutes (65-70 trading days)
- **1 year**: ~20-25 minutes (250-260 trading days)
- **2 years**: ~40-50 minutes (500-520 trading days)

### API Requirements
- **Polygon.io Subscription**: Options subscription required ($29/month minimum)
- **Rate Limits**: Respects Polygon.io rate limits with built-in delays
- **Data Availability**: SPX options data available since July 18, 2014

### System Requirements
- **Redis Storage**: Each day requires ~1KB of storage
- **Memory**: Minimal impact, processes in batches
- **Network**: Stable internet connection for API calls

## Monitoring Progress

### Real-time Logs
```bash
# View live backfill progress
docker compose logs -f spx-api
```

### Discord Notifications
If Discord is enabled, you'll receive completion notifications with:
- Date range processed
- Success/failure counts
- Success rate percentage
- Total duration

### API Status Check
```bash
# Check system status
curl http://localhost:8000/api/spx-straddle/status
```

## Data Quality and Validation

### Automatic Validation
- **Data Completeness**: Ensures all required fields are present
- **Price Reasonableness**: Basic sanity checks on option prices
- **Time Alignment**: Verifies correct timestamp matching
- **Duplicate Prevention**: Skips dates that already have data

### Manual Verification
```bash
# Check recent history
curl http://localhost:8000/api/spx-straddle/history?days=30

# View statistics
curl http://localhost:8000/api/spx-straddle/statistics?days=30

# Export to CSV for analysis
curl http://localhost:8000/api/spx-straddle/export/csv?days=365 > historical_data.csv
```

## Troubleshooting

### Common Issues

#### "Connection refused" Error
```bash
# Ensure Redis is running
docker compose ps
docker compose up -d redis
```

#### "API key not found" Error
```bash
# Check environment variables
docker compose exec spx-api env | grep POLYGON
```

#### "No data available" Error
- Check if date is a trading day (not weekend/holiday)
- Verify Polygon.io subscription includes options data
- Ensure date is not too recent (use yesterday or earlier)

#### Rate Limiting
- Increase `--delay` parameter for slower processing
- Reduce `--batch-size` for more conservative API usage

### Recovery from Failures

Backfill is designed to be resumable:
- **Duplicate Detection**: Automatically skips dates that already have data
- **Partial Success**: Saves successful dates even if others fail
- **Retry Strategy**: Simply re-run the same command to retry failed dates

## Best Practices

### Initial Setup
1. **Start Small**: Begin with 1-week backfill to test functionality
2. **Verify Data**: Check a few dates manually before large backfills
3. **Monitor Progress**: Watch logs during first large backfill

### Production Usage
1. **Off-Peak Hours**: Run large backfills during market closed hours
2. **Incremental Updates**: Use smaller date ranges for regular updates
3. **Data Backup**: Export CSV files periodically for backup

### Performance Optimization
1. **Batch Size**: Use 3-5 for conservative API usage, 10+ for faster processing
2. **Delay Timing**: 2-3 seconds between batches is usually optimal
3. **Parallel Processing**: Multiple small backfills can be faster than one large one

## Integration with Analysis

Once historical data is backfilled, the system provides enhanced analytics:

### Statistical Analysis
- **Trend Detection**: Identifies increasing/decreasing patterns
- **Volatility Metrics**: Coefficient of variation and categories
- **Distribution Analysis**: Percentiles, mean, median, standard deviation

### Pattern Recognition
- **Seasonal Patterns**: Monthly and weekly trends
- **Volatility Clustering**: Periods of high/low volatility
- **Extreme Events**: Identification of outliers and unusual costs

### Comparative Analysis
- **Historical Context**: Current costs vs. historical averages
- **Performance Tracking**: Monitor changes over time
- **Risk Assessment**: Understand typical ranges and extremes

## Example Workflows

### Quick Start (1 Month)
```bash
# 1. Start 1-month backfill
curl -X POST http://localhost:8000/api/spx-straddle/backfill/scenario/1month

# 2. Wait 2-3 minutes for completion

# 3. View enhanced statistics
curl http://localhost:8000/api/spx-straddle/statistics?days=30
```

### Comprehensive Historical Analysis (1 Year)
```bash
# 1. Start 1-year backfill (will take 20-25 minutes)
curl -X POST http://localhost:8000/api/spx-straddle/backfill/scenario/1year

# 2. Monitor progress
docker compose logs -f spx-api

# 3. Export full dataset
curl http://localhost:8000/api/spx-straddle/export/csv?days=365 > spx_straddle_1year.csv

# 4. View comprehensive statistics
curl http://localhost:8000/api/spx-straddle/statistics?days=365
```

### Custom Analysis Period
```bash
# Backfill specific period (e.g., 2024 election year)
curl -X POST "http://localhost:8000/api/spx-straddle/backfill/custom?start_date=2024-01-01&end_date=2024-12-31"

# Analyze the period
curl "http://localhost:8000/api/spx-straddle/history?days=365" | grep "2024"
```

## Support and Maintenance

### Regular Maintenance
- **Weekly**: Small backfills to catch any missed days
- **Monthly**: Verify data integrity and export backups
- **Quarterly**: Large backfills to extend historical coverage

### Monitoring
- **Discord Alerts**: Enable for backfill completion notifications
- **Log Analysis**: Regular review of backfill success rates
- **Data Validation**: Periodic spot checks of historical data

The historical backfill system transforms the SPX Straddle Calculator from a daily monitoring tool into a comprehensive analytical platform for understanding SPX 0DTE straddle behavior over time. 