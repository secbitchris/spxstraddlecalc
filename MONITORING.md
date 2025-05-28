# SPX Straddle Calculator - Monitoring Integration Guide

## 🔍 Overview

This guide explains how to integrate the SPX Straddle Calculator with your existing Loki/Prometheus/Grafana monitoring stack for comprehensive observability.

## 📊 What You'll Get

### **Logs (Loki)**
- Structured JSON logs with context
- Calculation success/failure events
- API request logs
- Discord notification status
- Error tracking and debugging

### **Metrics (Prometheus)**
- SPX straddle cost trends
- SPX index price tracking
- Calculation success rates
- API performance metrics
- Discord notification statistics
- Redis operation metrics

### **Dashboards (Grafana)**
- Real-time straddle cost monitoring
- Historical trend analysis
- Success rate tracking
- Performance monitoring
- Log aggregation and search

## ⚙️ Configuration

### **1. Environment Variables**

Add these to your `.env` file:

```bash
# Loki Integration
LOKI_ENABLED=true
LOKI_URL=http://your-loki-server:3100
ENVIRONMENT=production

# Prometheus Metrics
PROMETHEUS_METRICS_ENABLED=true
PROMETHEUS_METRICS_PORT=9090

# Enhanced Logging
LOG_LEVEL=INFO
LOG_FILE=logs/spx_calculator.log
```

### **2. Docker Compose Integration**

The system automatically exposes:
- **Port 9090**: Prometheus metrics (API server)
- **Port 9091**: Prometheus metrics (scheduler)

### **3. Prometheus Configuration**

Add these scrape configs to your `prometheus.yml`:

```yaml
scrape_configs:
  - job_name: 'spx-straddle-api'
    static_configs:
      - targets: ['your-lxc-ip:9090']
    scrape_interval: 30s
    metrics_path: /metrics
    
  - job_name: 'spx-straddle-scheduler'
    static_configs:
      - targets: ['your-lxc-ip:9091']
    scrape_interval: 30s
    metrics_path: /metrics
```

### **4. Loki Configuration**

Ensure your Loki instance can receive logs from the SPX calculator. The logs will be sent with these labels:

```yaml
labels:
  application: spx-straddle-calculator
  environment: production
  service: spx-calculator
  version: 1.0.0
```

## 📈 Available Metrics

### **Business Metrics**
- `spx_straddle_cost_dollars` - Current SPX straddle cost
- `spx_price_dollars` - Current SPX index price
- `spx_calculations_total{status}` - Total calculations (success/failure)
- `spx_calculation_duration_seconds` - Time to complete calculations

### **System Metrics**
- `discord_notifications_total{status}` - Discord notification count
- `api_requests_total{method,endpoint,status}` - API request metrics
- `redis_operations_total{operation,status}` - Redis operation metrics

### **Performance Metrics**
- Calculation duration histograms
- API response times
- Error rates and success rates

## 🎨 Grafana Dashboard

### **Import Dashboard**

1. **Copy the dashboard JSON** from `grafana-dashboard.json`
2. **Import in Grafana**:
   - Go to Grafana → Dashboards → Import
   - Paste the JSON content
   - Configure data sources (Prometheus + Loki)

### **Dashboard Panels**

The dashboard includes:

1. **Current Values**
   - SPX Straddle Cost
   - SPX Index Price
   - Success Rate (24h)
   - Discord Notifications

2. **Trends (7 days)**
   - Straddle cost over time
   - SPX price movements
   - Calculation duration
   - API request rates

3. **Logs**
   - Recent calculation logs
   - Error logs (last 24h)

## 🚨 Alerting

### **Recommended Alerts**

Add these to your Prometheus alerting rules:

```yaml
groups:
  - name: spx-straddle-alerts
    rules:
      - alert: SPXCalculationFailure
        expr: rate(spx_calculations_total{status="failure"}[5m]) > 0
        for: 1m
        labels:
          severity: warning
        annotations:
          summary: "SPX calculation failing"
          description: "SPX straddle calculations are failing"

      - alert: SPXCalculationMissing
        expr: increase(spx_calculations_total[25h]) == 0
        for: 1h
        labels:
          severity: critical
        annotations:
          summary: "No SPX calculations in 24h"
          description: "No SPX calculations have occurred in the last 24 hours"

      - alert: DiscordNotificationFailure
        expr: rate(discord_notifications_total{status="failure"}[5m]) > 0
        for: 2m
        labels:
          severity: warning
        annotations:
          summary: "Discord notifications failing"
          description: "Discord webhook notifications are failing"

      - alert: HighCalculationDuration
        expr: histogram_quantile(0.95, rate(spx_calculation_duration_seconds_bucket[5m])) > 10
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "SPX calculations taking too long"
          description: "95th percentile calculation time is over 10 seconds"
```

## 🔧 Log Queries

### **Useful Loki Queries**

**Successful Calculations:**
```logql
{application="spx-straddle-calculator"} |= "calculation" |= "success"
```

**Failed Calculations:**
```logql
{application="spx-straddle-calculator"} |= "calculation" |= "failed"
```

**Discord Notifications:**
```logql
{application="spx-straddle-calculator"} |= "discord" |= "notification"
```

**API Errors:**
```logql
{application="spx-straddle-calculator"} |= "ERROR" |= "api"
```

**Polygon.io API Issues:**
```logql
{application="spx-straddle-calculator"} |= "polygon" |= "error"
```

## 🚀 Deployment with Monitoring

### **1. Update Environment**

```bash
# In your .env file
LOKI_ENABLED=true
LOKI_URL=http://your-loki-vm-ip:3100
PROMETHEUS_METRICS_ENABLED=true
ENVIRONMENT=production
```

### **2. Deploy with Monitoring**

```bash
# Deploy the full system
docker-compose --profile scheduler up -d

# Verify metrics endpoint
curl http://localhost:9090/metrics

# Check logs are being sent
docker-compose logs spx-api | grep -i loki
```

### **3. Configure Prometheus**

Add the scrape configs to your Prometheus instance and restart it.

### **4. Import Grafana Dashboard**

Import the provided dashboard JSON into your Grafana instance.

## 📊 Monitoring Best Practices

### **Log Retention**
- Configure appropriate log retention in Loki
- Recommended: 30-90 days for detailed logs

### **Metric Retention**
- Configure Prometheus retention based on your needs
- Recommended: 15 days for detailed metrics, longer for aggregated data

### **Alerting**
- Set up alerts for calculation failures
- Monitor Discord notification success
- Alert on missing daily calculations

### **Dashboard Refresh**
- Set dashboard refresh to 30s-1m for real-time monitoring
- Use longer intervals for historical analysis

## 🔍 Troubleshooting

### **Loki Not Receiving Logs**
```bash
# Check Loki configuration
curl http://your-loki-ip:3100/ready

# Verify network connectivity
docker exec spx-api curl -v http://your-loki-ip:3100/loki/api/v1/push
```

### **Prometheus Not Scraping**
```bash
# Check metrics endpoint
curl http://your-lxc-ip:9090/metrics

# Verify Prometheus targets
# Go to Prometheus UI → Status → Targets
```

### **Missing Metrics**
```bash
# Check if metrics are enabled
docker-compose logs spx-api | grep -i prometheus

# Verify environment variables
docker exec spx-api env | grep PROMETHEUS
```

## 📈 Sample Queries

### **Prometheus Queries**

**Average daily straddle cost:**
```promql
avg_over_time(spx_straddle_cost_dollars[1d])
```

**Calculation success rate (last 7 days):**
```promql
rate(spx_calculations_total{status="success"}[7d]) / rate(spx_calculations_total[7d]) * 100
```

**API request rate:**
```promql
rate(api_requests_total[5m])
```

---

**🎉 Your SPX Straddle Calculator is now fully integrated with your monitoring stack!** 