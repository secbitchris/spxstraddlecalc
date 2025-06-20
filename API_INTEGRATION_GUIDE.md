# SPX 0DTE Straddle Calculator - API Integration Guide

## 🚀 Quick Start

### Base URL
```
http://localhost:8000
```

### Authentication
- **Current**: No authentication required
- **Future**: Consider API keys for production deployment

### Rate Limits
- **Current**: No rate limiting
- **Recommendation**: Implement reasonable polling intervals (1-5 seconds minimum)

---

## 📊 Core Data Endpoints

### 1. Current Straddle Cost
Get today's 0DTE straddle cost calculation.

**Endpoint**: `GET /api/spx-straddle/today`

**Response**:
```json
{
  "status": "success",
  "date": "2025-06-19",
  "spx_price_930am": 5432.10,
  "atm_strike": 5430,
  "call_price_931am": 18.50,
  "put_price_931am": 22.19,
  "straddle_cost": 40.69,
  "calculation_status": "available",
  "last_calculation_date": "2025-06-19",
  "timestamp": "2025-06-19T09:31:00-04:00"
}
```

**Trading Bot Usage**:
```python
import requests

def get_current_straddle_cost():
    response = requests.get("http://localhost:8000/api/spx-straddle/today")
    data = response.json()
    
    if data["status"] == "success":
        return {
            "cost": data["straddle_cost"],
            "spx_price": data["spx_price_930am"],
            "strike": data["atm_strike"]
        }
    return None

# Example usage
current = get_current_straddle_cost()
if current and current["cost"] < 35.0:
    print("Straddle cost below threshold - consider entry")
```

### 2. Historical Data
Retrieve historical straddle costs for backtesting and analysis.

**Endpoint**: `GET /api/spx-straddle/history?days={N}`

**Parameters**:
- `days`: Number of days to retrieve (1-1000)

**Response**:
```json
{
  "status": "success",
  "days_requested": 30,
  "data_points": 21,
  "data": [
    {
      "date": "2025-06-19",
      "spx_price_930am": 5432.10,
      "atm_strike": 5430,
      "call_price_931am": 18.50,
      "put_price_931am": 22.19,
      "straddle_cost": 40.69,
      "timestamp": "2025-06-19T09:31:00-04:00"
    }
  ]
}
```

**Backtesting Usage**:
```python
def get_historical_data(days=365):
    response = requests.get(f"http://localhost:8000/api/spx-straddle/history?days={days}")
    data = response.json()
    
    if data["status"] == "success":
        return [(record["date"], record["straddle_cost"]) for record in data["data"]]
    return []

# Get 1 year of data for backtesting
historical_data = get_historical_data(365)
for date, cost in historical_data:
    # Run your backtesting logic here
    signal = your_strategy_function(cost)
```

### 3. Statistical Analysis
Get comprehensive statistics for different timeframes.

**Endpoint**: `GET /api/spx-straddle/statistics/multi-timeframe`

**Response**:
```json
{
  "status": "success",
  "timeframes": {
    "1D": {"mean": 40.69, "std": 0.0, "min": 40.69, "max": 40.69, "data_points": 1},
    "7D": {"mean": 31.32, "std": 4.82, "min": 27.25, "max": 40.69, "data_points": 5},
    "30D": {"mean": 33.67, "std": 6.89, "min": 27.25, "max": 52.87, "data_points": 21},
    "90D": {"mean": 45.23, "std": 25.67, "min": 27.25, "max": 157.25, "data_points": 62}
  }
}
```

**Trading Signal Usage**:
```python
def generate_trading_signal():
    # Get current cost
    current = get_current_straddle_cost()
    
    # Get 30-day statistics
    stats_response = requests.get("http://localhost:8000/api/spx-straddle/statistics/multi-timeframe")
    stats = stats_response.json()["timeframes"]["30D"]
    
    current_cost = current["cost"]
    mean_cost = stats["mean"]
    std_cost = stats["std"]
    
    # Generate signals based on statistical deviation
    if current_cost < mean_cost - std_cost:
        return "BUY_SIGNAL"  # Cost is below 1 standard deviation
    elif current_cost > mean_cost + std_cost:
        return "AVOID_SIGNAL"  # Cost is above 1 standard deviation
    else:
        return "NEUTRAL"

signal = generate_trading_signal()
```

---

## 📈 Chart & Trend Data

### 4. Chart Data for Technical Analysis
Get processed data with trend lines and moving averages.

**Endpoint**: `GET /api/spx-straddle/chart-data?days={N}&timeframe=daily`

**Parameters**:
- `days`: Historical period (30, 90, 180, 365, 730)
- `timeframe`: "daily", "weekly", "monthly"

**Response**:
```json
{
  "status": "success",
  "timeframe": "daily",
  "days_requested": 90,
  "data_points": 62,
  "chart_data": {
    "dates": ["2025-03-21", "2025-03-24", "..."],
    "costs": [50.14, 34.8, 29.6, "..."],
    "trend_line": [49.2, 48.8, 48.4, "..."],
    "moving_averages": {
      "ma_7": [null, null, null, null, null, null, 39.83, "..."],
      "ma_30": [null, "...", 66.0, 65.7, "..."]
    },
    "statistics": {
      "min": 27.25,
      "max": 157.25,
      "mean": 45.23
    }
  }
}
```

**Technical Analysis Usage**:
```python
def analyze_trend(days=90):
    response = requests.get(f"http://localhost:8000/api/spx-straddle/chart-data?days={days}")
    data = response.json()["chart_data"]
    
    # Get recent trend direction
    trend_line = data["trend_line"]
    recent_trend = trend_line[-5:]  # Last 5 days
    
    if recent_trend[-1] < recent_trend[0]:
        return "DOWNTREND"
    elif recent_trend[-1] > recent_trend[0]:
        return "UPTREND"
    else:
        return "SIDEWAYS"

# Check if straddle costs are trending down (good for entry)
trend = analyze_trend()
if trend == "DOWNTREND":
    print("Straddle costs trending down - favorable for entry")
```

---

## 📅 Market Day Validation

### 5. Trading Day Validation
Validate if a date is a valid trading day before making calculations.

**Endpoint**: `GET /api/market-days/validate/{date}`

**Example**: `GET /api/market-days/validate/2025-06-20`

**Response**:
```json
{
  "date": "2025-06-20",
  "is_valid_market_day": true,
  "day_of_week": "Friday",
  "weekday_number": 4,
  "is_weekend": false,
  "is_holiday": false,
  "is_future": false,
  "is_today": false,
  "reason": "Valid trading day"
}
```

**Bot Integration**:
```python
def is_trading_day(date_str):
    response = requests.get(f"http://localhost:8000/api/market-days/validate/{date_str}")
    return response.json()["is_valid_market_day"]

# Only run trading logic on valid trading days
from datetime import datetime
today = datetime.now().strftime('%Y-%m-%d')

if is_trading_day(today):
    # Run your trading logic
    signal = generate_trading_signal()
else:
    print(f"{today} is not a trading day - skipping")
```

### 6. Next/Previous Trading Day
Get the next or previous valid trading day.

**Endpoints**:
- `GET /api/market-days/next?from_date=2025-06-20`
- `GET /api/market-days/previous?from_date=2025-06-20`

**Response**:
```json
{
  "from_date": "2025-06-20",
  "next_market_day": "2025-06-23",
  "days_ahead": 3,
  "day_of_week": "Monday"
}
```

---

## 💾 Data Export

### 7. CSV Export for Backtesting
Download historical data in CSV format for external analysis.

**Endpoint**: `GET /api/spx-straddle/export/csv?days={N}`

**Response**: CSV file download

**Usage**:
```python
def download_csv_data(days=365, filename="spx_data.csv"):
    response = requests.get(f"http://localhost:8000/api/spx-straddle/export/csv?days={days}")
    
    with open(filename, 'wb') as f:
        f.write(response.content)
    
    return filename

# Download 2 years of data for comprehensive backtesting
csv_file = download_csv_data(730, "spx_2year_data.csv")
```

---

## 🔧 System Health & Monitoring

### 8. Health Check
Monitor API availability and system status.

**Endpoint**: `GET /health`

**Response**:
```json
{
  "status": "healthy",
  "timestamp": "2025-06-19T19:06:49-04:00",
  "services": {
    "calculator": true,
    "discord": true,
    "gist_publisher": true
  }
}
```

### 9. System Status
Get detailed system status and last calculation info.

**Endpoint**: `GET /api/spx-straddle/status`

**Response**:
```json
{
  "system_status": "operational",
  "last_calculation": "2025-06-19",
  "calculation_status": "available",
  "redis_connected": true,
  "polygon_configured": true,
  "discord_enabled": true,
  "gist_publisher_enabled": true
}
```

---

## 🎯 Integration Patterns

### Real-Time Trading Bot
```python
import time
import requests
from datetime import datetime

class SPXStraddleBot:
    def __init__(self, base_url="http://localhost:8000"):
        self.base_url = base_url
        
    def should_enter_position(self):
        # Get current cost
        current = self.get_current_cost()
        if not current:
            return False
            
        # Get 30-day statistics
        stats = self.get_statistics()
        
        # Entry logic: cost below 30-day mean
        return current["cost"] < stats["30D"]["mean"] * 0.9
    
    def get_current_cost(self):
        try:
            response = requests.get(f"{self.base_url}/api/spx-straddle/today")
            data = response.json()
            return {"cost": data["straddle_cost"]} if data["status"] == "success" else None
        except:
            return None
    
    def get_statistics(self):
        try:
            response = requests.get(f"{self.base_url}/api/spx-straddle/statistics/multi-timeframe")
            return response.json()["timeframes"]
        except:
            return {}
    
    def run(self):
        while True:
            if self.should_enter_position():
                print("Entry signal generated!")
                # Execute your trade logic here
            
            time.sleep(60)  # Check every minute

# Usage
bot = SPXStraddleBot()
bot.run()
```

### Backtesting System
```python
import pandas as pd
import requests

class SPXStraddleBacktester:
    def __init__(self, base_url="http://localhost:8000"):
        self.base_url = base_url
        
    def get_historical_data(self, days=365):
        response = requests.get(f"{self.base_url}/api/spx-straddle/history?days={days}")
        data = response.json()["data"]
        
        df = pd.DataFrame(data)
        df['date'] = pd.to_datetime(df['date'])
        return df.set_index('date')
    
    def backtest_strategy(self, entry_threshold=0.8, exit_threshold=1.2):
        # Get 2 years of data
        df = self.get_historical_data(730)
        
        # Calculate rolling 30-day mean
        df['ma_30'] = df['straddle_cost'].rolling(30).mean()
        
        # Generate signals
        df['entry_signal'] = df['straddle_cost'] < (df['ma_30'] * entry_threshold)
        df['exit_signal'] = df['straddle_cost'] > (df['ma_30'] * exit_threshold)
        
        # Calculate returns
        position = 0
        entry_price = 0
        returns = []
        
        for date, row in df.iterrows():
            if row['entry_signal'] and position == 0:
                position = 1
                entry_price = row['straddle_cost']
            elif row['exit_signal'] and position == 1:
                position = 0
                trade_return = (entry_price - row['straddle_cost']) / entry_price
                returns.append(trade_return)
        
        return {
            "total_trades": len(returns),
            "avg_return": sum(returns) / len(returns) if returns else 0,
            "win_rate": len([r for r in returns if r > 0]) / len(returns) if returns else 0
        }

# Usage
backtester = SPXStraddleBacktester()
results = backtester.backtest_strategy()
print(f"Backtest Results: {results}")
```

---

## ⚡ Best Practices

### 1. Error Handling
Always check response status and handle errors gracefully:

```python
def safe_api_call(url):
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()  # Raises HTTPError for bad responses
        
        data = response.json()
        if data.get("status") != "success":
            print(f"API Error: {data.get('message', 'Unknown error')}")
            return None
            
        return data
    except requests.exceptions.RequestException as e:
        print(f"Network Error: {e}")
        return None
    except ValueError as e:
        print(f"JSON Parse Error: {e}")
        return None
```

### 2. Efficient Polling
Implement smart polling to avoid overwhelming the API:

```python
import time
from datetime import datetime, time as dt_time

def smart_polling_loop():
    while True:
        now = datetime.now()
        
        # Only poll during market hours (9:30 AM - 4:00 PM ET)
        market_open = dt_time(9, 30)
        market_close = dt_time(16, 0)
        
        if market_open <= now.time() <= market_close:
            # Poll every 30 seconds during market hours
            check_for_signals()
            time.sleep(30)
        else:
            # Poll every 5 minutes outside market hours
            time.sleep(300)
```

### 3. Data Caching
Cache frequently accessed data to reduce API calls:

```python
import time
from functools import lru_cache

@lru_cache(maxsize=128)
def get_cached_statistics(cache_key):
    # Cache statistics for 5 minutes
    response = requests.get("http://localhost:8000/api/spx-straddle/statistics/multi-timeframe")
    return response.json()

def get_statistics_with_cache():
    # Create cache key that changes every 5 minutes
    cache_key = int(time.time() // 300)
    return get_cached_statistics(cache_key)
```

---

## 📚 Additional Resources

### Interactive API Documentation
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

### Dashboard
- **Web Interface**: http://localhost:8000/api/spx-straddle/dashboard

### Support
For integration support or feature requests, refer to the main repository documentation.

---

## 🔄 Response Status Codes

| Code | Meaning | Action |
|------|---------|--------|
| 200 | Success | Process response data |
| 400 | Bad Request | Check parameters |
| 404 | Not Found | Verify endpoint URL |
| 500 | Server Error | Retry after delay |

## 📝 Example Integration Checklist

- [ ] Test health endpoint connectivity
- [ ] Validate market day checking
- [ ] Implement error handling and retries
- [ ] Set up appropriate polling intervals
- [ ] Test with historical data endpoints
- [ ] Implement your trading/analysis logic
- [ ] Add logging and monitoring
- [ ] Test edge cases (weekends, holidays)

---

*Last Updated: June 2025*
*API Version: 1.0* 