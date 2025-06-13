# SPX 0DTE Straddle Calculator

A comprehensive Python application for calculating and tracking SPX (S&P 500 Index) 0DTE (zero days to expiration) straddle costs using **real market data** from Polygon.io, with Discord webhook notifications and automated scheduling.

## ✅ **FULLY OPERATIONAL** 

**Status**: ✅ **Working with Real Market Data**
- ✅ **SPX Index Data**: Real-time 9:30 AM market open prices
- ✅ **SPX Options Data**: Real 0DTE option prices (15-minute delayed)
- ✅ **Accurate Calculations**: Verified with live market data
- ✅ **Discord Integration**: Notifications working
- ✅ **Web Dashboard**: Live at http://localhost:8000/api/spx-straddle/dashboard

**Latest Test Results** (June 13, 2025):
- SPX Price at 9:30 AM: $6,000.56
- ATM Strike: $6,000.00
- Call Price: $18.60 | Put Price: $17.30
- **Total Straddle Cost: $35.90**

## 🚀 Features

- **Real-time SPX Data**: Fetches SPX index prices at 9:30 AM ET using Polygon.io
- **Real SPX Options Data**: Retrieves SPXW (SPX 0DTE) call and put option prices at 9:31 AM ET
- **Straddle Calculation**: Automatically calculates ATM (at-the-money) straddle costs
- **Historical Analysis**: Stores and analyzes historical straddle cost data
- **Statistical Insights**: Provides trend analysis, volatility metrics, and pattern recognition
- **Discord Webhooks**: Sends automated notifications to Discord channels via webhooks
- **REST API**: Full-featured API with web dashboard
- **Automated Scheduling**: Daily calculations and weekly data cleanup
- **Docker Support**: Complete containerized deployment
- **Data Persistence**: Redis-based storage with configurable retention

## 📋 Prerequisites

- Python 3.11+
- **[Polygon.io API key](https://polygon.io/) with Options subscription** (minimum Options Starter $29/month)
- Redis server (or use Docker Compose)
- Discord webhook URL (optional, for notifications)

## 🛠️ Quick Start

### Option 1: Docker Compose (Recommended)

1. **Clone and setup**:
   ```bash
   git clone <repository-url>
   cd spxstraddle
   cp env.example .env
   ```

2. **Configure environment variables** in `.env`:
   ```bash
   POLYGON_API_KEY=your_polygon_api_key_here
   DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/YOUR_WEBHOOK_ID/YOUR_WEBHOOK_TOKEN  # Optional
   DISCORD_ENABLED=true  # Set to false to disable Discord
   ```

3. **Start the application**:
   ```bash
   # Start API server and Redis
   docker-compose up

   # Or start with scheduler for automated calculations
   docker-compose --profile scheduler up

   # Or run example usage
   docker-compose --profile example up spx-example
   ```

4. **Access the dashboard**: http://localhost:8000/api/spx-straddle/dashboard

### Option 2: Local Installation

1. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Start Redis** (if not using Docker):
   ```bash
   redis-server
   ```

3. **Configure environment**:
   ```bash
   cp env.example .env
   # Edit .env with your API keys
   ```

4. **Run the application**:
   ```bash
   # Run example usage
   python example_usage.py

   # Start API server
   python api_server.py

   # Start scheduler
   python scheduler.py
   ```

## 📊 Usage Examples

### Basic Calculation

```python
import asyncio
from spx_calculator import SPXStraddleCalculator

async def calculate_straddle():
    calculator = SPXStraddleCalculator("your_polygon_api_key")
    await calculator.initialize()
    
    result = await calculator.calculate_spx_straddle_cost()
    
    if 'error' not in result:
        print(f"Straddle Cost: ${result['straddle_cost']:.2f}")
        print(f"SPX Price: ${result['spx_price_930am']:.2f}")
        print(f"ATM Strike: {result['atm_strike']}")
    
    await calculator.close()

asyncio.run(calculate_straddle())
```

### Discord Webhook Notifications

```python
from discord_notifier import DiscordNotifier

async def send_notification():
    notifier = DiscordNotifier("https://discord.com/api/webhooks/YOUR_WEBHOOK_ID/YOUR_WEBHOOK_TOKEN")
    await notifier.initialize()
    
    if notifier.is_enabled():
        await notifier.notify_straddle_result(result)
    
    await notifier.close()
```

## 🌐 API Endpoints

The REST API provides comprehensive access to all functionality:

### Core Endpoints

- `GET /api/spx-straddle/today` - Get today's straddle data
- `POST /api/spx-straddle/calculate` - Trigger new calculation
- `GET /api/spx-straddle/history?days=30` - Get historical data
- `GET /api/spx-straddle/statistics?days=30` - Get statistical analysis
- `GET /api/spx-straddle/export/csv?days=30` - Export data as CSV
- `GET /api/spx-straddle/status` - System health check

### Discord Endpoints

- `POST /api/discord/test` - Test Discord integration
- `POST /api/discord/notify/today` - Send today's data to Discord

### Dashboard

- `GET /api/spx-straddle/dashboard` - Web dashboard
- `GET /docs` - API documentation (Swagger UI)

## 📅 Automated Scheduling

The scheduler runs daily calculations and sends Discord notifications:

### Configuration

Set these environment variables:

```bash
ENABLE_SCHEDULER=true
CALCULATION_TIME=09:32  # Time in ET for daily calculation
CLEANUP_DAY=sunday      # Day for weekly cleanup
CLEANUP_TIME=02:00      # Time for cleanup
KEEP_DAYS=90           # Days of data to retain
```

### Schedule

- **Daily**: Calculates straddle cost at 9:32 AM ET (weekdays only)
- **Weekly**: Cleans up old data (configurable day/time)
- **Notifications**: Sends results to Discord automatically

## 🔧 Configuration

### Environment Variables

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `POLYGON_API_KEY` | Polygon.io API key with Options subscription | - | ✅ |
| `REDIS_URL` | Redis connection URL | `redis://localhost:6379` | ❌ |
| `DISCORD_WEBHOOK_URL` | Discord webhook URL | - | ❌ |
| `DISCORD_ENABLED` | Enable Discord notifications | `false` | ❌ |
| `LOG_LEVEL` | Logging level | `INFO` | ❌ |
| `CALCULATION_TIME` | Daily calculation time (ET) | `09:32` | ❌ |
| `CLEANUP_DAY` | Weekly cleanup day | `sunday` | ❌ |
| `KEEP_DAYS` | Data retention days | `90` | ❌ |

### Polygon.io Subscription Requirements

**For SPX Options Data**, you need:
- **Minimum**: Options Starter ($29/month) 
- **Includes**: 15-minute delayed SPX options data
- **Data Available**: 9:47 AM ET onwards (for 9:31 AM option prices)

### Discord Setup

1. **Create a Discord Webhook**:
   - Go to your Discord server
   - Right-click on the channel where you want notifications
   - Select "Edit Channel" → "Integrations" → "Webhooks"
   - Click "New Webhook"
   - Copy the webhook URL

2. **Configure the Application**:
   ```bash
   DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/YOUR_WEBHOOK_ID/YOUR_WEBHOOK_TOKEN
   DISCORD_ENABLED=true
   ```

## 🔍 Technical Details

### SPX Options Implementation

- **Index Data**: Uses `I:SPX` ticker for S&P 500 index prices
- **Options Data**: Uses `O:SPXW{YYMMDD}{C/P}{strike*1000}` format for 0DTE options
- **Timing**: 
  - SPX price fetched at 9:30 AM ET (market open)
  - Option prices fetched at 9:31 AM ET (1 minute after open)
- **Strike Calculation**: Rounds SPX price to nearest $5 increment

### Data Flow

1. **9:30 AM**: Fetch SPX opening price
2. **Calculate**: ATM strike (nearest $5)
3. **9:31 AM**: Fetch call and put option prices
4. **Calculate**: Straddle cost = call price + put price
5. **Store**: Save results to Redis
6. **Notify**: Send Discord notification (if enabled)

### Statistical Analysis

- **Trend Analysis**: Linear regression on historical straddle costs
- **Volatility**: Coefficient of variation (std dev / mean)
- **Data Source**: Only uses collected data (not historical backfill)
- **Meaningful Results**: Requires 7+ days of collected data

## 🐳 Docker Deployment

### Services

The Docker Compose setup includes:

- **spx-api**: REST API server
- **spx-scheduler**: Automated scheduler (optional)
- **redis**: Data storage
- **spx-example**: Example usage (for testing)

### Commands

```bash
# Start API only
docker-compose up spx-api redis

# Start with scheduler
docker-compose --profile scheduler up

# Run example
docker-compose --profile example up spx-example

# View logs
docker-compose logs -f spx-api

# Scale services
docker-compose up --scale spx-api=2
```

## 🔍 Monitoring and Logging

### Health Checks

- API: `GET /health`
- Docker: Built-in health checks
- Redis: Connection monitoring

### Logging

Structured logging with configurable levels:

```bash
LOG_LEVEL=DEBUG  # DEBUG, INFO, WARNING, ERROR
```

### Metrics

- Calculation success/failure rates
- API response times
- Discord notification status
- Data storage metrics

## 🚨 Error Handling

The application includes comprehensive error handling:

- **API Errors**: Graceful HTTP error responses
- **Data Errors**: Validation and retry logic
- **Discord Errors**: Fallback notification strategies
- **Network Errors**: Automatic retry with exponential backoff

## 📝 API Documentation

Full API documentation is available at `/docs` when running the server. The API follows REST conventions and includes:

- Request/response schemas
- Error codes and messages
- Example requests and responses
- Authentication requirements (if any)

## 🔒 Security Considerations

- **API Keys**: Store in environment variables, never in code
- **Docker**: Runs as non-root user
- **Redis**: Configure authentication in production
- **Discord**: Use bot tokens, not user tokens
- **Network**: Consider firewall rules for production

## 🧪 Testing

Run the example script to test all functionality:

```bash
python example_usage.py
```

This will:
- Test calculator initialization
- Perform a sample calculation
- Test Discord integration
- Demonstrate all API features
- Show system status

## 📊 Performance

### Polygon.io Rate Limits

- **Free Tier**: 5 requests/minute
- **Paid Tiers**: Higher limits available
- **Optimization**: Application caches results to minimize API calls

### Resource Usage

- **Memory**: ~50MB base + Redis storage
- **CPU**: Minimal (calculation bursts)
- **Storage**: ~1MB per month of daily data
- **Network**: ~1KB per calculation

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🆘 Support

### Common Issues

1. **"No SPX data received"**: Check if markets are open and Polygon.io API key is valid
2. **Discord not working**: Verify bot token and channel ID
3. **Redis connection failed**: Ensure Redis is running and accessible

### Getting Help

- Check the logs for detailed error messages
- Verify environment variables are set correctly
- Test with the example script first
- Check Polygon.io API status

### Troubleshooting

```bash
# Check system status
curl http://localhost:8000/api/spx-straddle/status

# Test Discord
curl -X POST http://localhost:8000/api/discord/test

# View logs
docker-compose logs spx-api

# Check Redis
redis-cli ping
```

## 🔮 Future Enhancements

- [ ] Support for other indices (NDX, RUT)
- [ ] Multiple expiration dates
- [ ] Advanced pattern recognition
- [ ] Slack integration
- [ ] Grafana dashboards
- [ ] Machine learning predictions
- [ ] Mobile app
- [ ] Real-time WebSocket updates

---

**Built with ❤️ for options traders and quantitative analysts** 