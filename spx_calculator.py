import asyncio
import json
import logging
import math
import pytz
from datetime import datetime, timedelta, date
from typing import Dict, Any, Optional, List
import redis
import aioredis
from polygon import RESTClient
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)

class SPXStraddleCalculator:
    """
    SPX 0DTE Straddle Cost Calculator using Polygon.io
    
    This class handles all SPX straddle calculations including:
    - SPX price fetching at 9:30 AM ET
    - ATM strike calculation
    - Option price fetching at 9:31 AM ET
    - Straddle cost computation
    - Historical data storage and analysis
    """
    
    def __init__(self, polygon_api_key: str, redis_url: str = "redis://localhost:6379"):
        """
        Initialize the SPX straddle calculator
        
        Args:
            polygon_api_key: Polygon.io API key
            redis_url: Redis connection URL for data storage
        """
        self.polygon_client = RESTClient(polygon_api_key)
        self.redis_url = redis_url
        self.redis = None
        
        # SPX Straddle Data Storage
        self.spx_straddle_data = {
            'timestamp': None,
            'timezone': 'US/Eastern',
            'calculation_status': 'pending_initialization',
            'spx_price_930am': None,
            'atm_strike': None,
            'call_price_931am': None,
            'put_price_931am': None,
            'straddle_cost': None,
            'error_message': None,
            'spx_price_timestamp': None,
            'options_price_timestamp': None,
            'last_calculation_date': None
        }
    
    async def initialize(self):
        """Initialize Redis connection"""
        try:
            self.redis = await aioredis.from_url(self.redis_url)
            logger.info("Redis connection established")
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            raise
    
    async def close(self):
        """Close Redis connection"""
        if self.redis:
            await self.redis.close()
    
    async def get_spx_price_at_930am(self, target_date: date = None) -> Optional[float]:
        """
        Fetch SPX price at 9:30 AM ET using Polygon.io
        
        Args:
            target_date: Date to fetch data for (defaults to today)
            
        Returns:
            SPX opening price at 9:30 AM ET or None if not available
        """
        try:
            et_tz = pytz.timezone('US/Eastern')
            if target_date is None:
                target_date = datetime.now(et_tz).date()
            
            # Convert to timestamp for Polygon API
            target_datetime = et_tz.localize(datetime.combine(target_date, datetime.min.time().replace(hour=9, minute=30)))
            
            logger.info(f"[SPX_STRADDLE] Fetching SPX price at 9:30 AM ET for {target_date}")
            
            # Get SPX aggregate data for the specific minute
            # Polygon uses 'I:SPX' for SPX index
            aggs = self.polygon_client.get_aggs(
                ticker="I:SPX",
                multiplier=1,
                timespan="minute",
                from_=target_datetime.strftime('%Y-%m-%d'),
                to=target_datetime.strftime('%Y-%m-%d'),
                limit=50000
            )
            
            if not aggs or not hasattr(aggs, 'results') or not aggs.results:
                logger.warning("[SPX_STRADDLE] No SPX data received from Polygon")
                return None
            
            # Find the 9:30 AM candle
            target_timestamp = int(target_datetime.timestamp() * 1000)  # Polygon uses milliseconds
            
            for bar in aggs.results:
                # Polygon timestamps are in milliseconds
                bar_time = datetime.fromtimestamp(bar.timestamp / 1000, tz=et_tz)
                if bar_time.hour == 9 and bar_time.minute == 30:
                    logger.info(f"[SPX_STRADDLE] Found 9:30 AM SPX candle: open={bar.open}, high={bar.high}, low={bar.low}, close={bar.close}")
                    return float(bar.open)
            
            logger.warning("[SPX_STRADDLE] No 9:30 AM SPX candle found in Polygon data")
            return None
            
        except Exception as e:
            logger.error(f"[SPX_STRADDLE] Error fetching SPX price at 9:30 AM: {e}", exc_info=True)
            return None
    
    def get_atm_strike_for_spx(self, spx_price: float) -> Optional[float]:
        """
        Calculate the ATM strike for SPX options
        
        SPX options typically have strikes in increments of 5 points.
        
        Args:
            spx_price: The SPX price to find the closest strike for
            
        Returns:
            The closest available strike price, or None if calculation fails
        """
        try:
            if not spx_price or spx_price <= 0:
                logger.error(f"[SPX_STRADDLE] Invalid SPX price for ATM calculation: {spx_price}")
                return None
            
            # SPX options typically have strikes in increments of 5
            atm_strike = round(spx_price / 5) * 5
            
            logger.info(f"[SPX_STRADDLE] Calculated ATM strike: {atm_strike} (from SPX price: {spx_price})")
            return float(atm_strike)
            
        except Exception as e:
            logger.error(f"[SPX_STRADDLE] Error calculating ATM strike: {e}", exc_info=True)
            return None
    
    def get_0dte_expiry_string(self, target_date: date = None) -> str:
        """
        Get the expiry string for 0DTE SPX options
        
        Args:
            target_date: Date to get expiry for (defaults to today)
            
        Returns:
            Date string in YYYYMMDD format for 0DTE options
        """
        et_tz = pytz.timezone('US/Eastern')
        if target_date is None:
            target_date = datetime.now(et_tz).date()
        return target_date.strftime('%Y%m%d')
    
    async def get_spx_option_price_at_931am(self, strike: float, right: str, expiry: str, target_date: date = None) -> Optional[float]:
        """
        Fetch SPX option price at 9:31 AM ET using Polygon.io
        
        Args:
            strike: Option strike price
            right: 'C' for call, 'P' for put
            expiry: Expiry date in YYYYMMDD format
            target_date: Date to fetch data for (defaults to today)
            
        Returns:
            Option price at 9:31 AM ET or None if not available
        """
        try:
            et_tz = pytz.timezone('US/Eastern')
            if target_date is None:
                target_date = datetime.now(et_tz).date()
            
            # Build option ticker for Polygon
            # SPX options format: O:SPX{YYMMDD}{C/P}{strike*1000}
            expiry_short = expiry[2:]  # Convert YYYYMMDD to YYMMDD
            strike_formatted = f"{int(strike * 1000):08d}"  # Strike in thousandths, 8 digits
            option_ticker = f"O:SPX{expiry_short}{right}{strike_formatted}"
            
            logger.info(f"[SPX_STRADDLE] Fetching option price for {option_ticker} at 9:31 AM ET")
            
            # Target the 9:31 AM candle
            target_datetime = et_tz.localize(datetime.combine(target_date, datetime.min.time().replace(hour=9, minute=31)))
            
            # Get option aggregate data
            aggs = self.polygon_client.get_aggs(
                ticker=option_ticker,
                multiplier=1,
                timespan="minute",
                from_=target_datetime.strftime('%Y-%m-%d'),
                to=target_datetime.strftime('%Y-%m-%d'),
                limit=50000
            )
            
            if not aggs or not hasattr(aggs, 'results') or not aggs.results:
                logger.warning(f"[SPX_STRADDLE] No option data received for {option_ticker}")
                return None
            
            # Find the 9:31 AM candle
            for bar in aggs.results:
                bar_time = datetime.fromtimestamp(bar.timestamp / 1000, tz=et_tz)
                if bar_time.hour == 9 and bar_time.minute == 31:
                    logger.info(f"[SPX_STRADDLE] Found 9:31 AM option candle for {option_ticker}: "
                               f"open={bar.open}, high={bar.high}, low={bar.low}, close={bar.close}")
                    
                    # Use the opening price from the 9:31 AM candle
                    if bar.open and bar.open > 0:
                        logger.info(f"[SPX_STRADDLE] Using 9:31 AM opening price: {bar.open}")
                        return float(bar.open)
                    else:
                        logger.warning(f"[SPX_STRADDLE] Invalid opening price in 9:31 AM candle: {bar.open}")
                        return None
            
            logger.warning(f"[SPX_STRADDLE] No 9:31 AM candle found for option {option_ticker}")
            return None
            
        except Exception as e:
            logger.error(f"[SPX_STRADDLE] Error fetching SPX option price at 9:31 AM: {e}", exc_info=True)
            return None

    async def calculate_spx_straddle_cost(self, target_date: date = None) -> Dict[str, Any]:
        """
        Calculate SPX 0DTE straddle cost
        
        Orchestrates the calculation by:
        1. Fetching SPX price at 9:30 AM ET
        2. Calculating ATM strike
        3. Fetching call and put prices at 9:31 AM ET
        4. Computing straddle cost
        
        Args:
            target_date: Date to calculate for (defaults to today)
            
        Returns:
            Dict containing calculation result with straddle cost or error information
        """
        try:
            et_tz = pytz.timezone('US/Eastern')
            if target_date is None:
                target_date = datetime.now(et_tz).date()
            
            # Update calculation status
            self.spx_straddle_data['calculation_status'] = 'calculating'
            self.spx_straddle_data['timestamp'] = datetime.now(et_tz).isoformat()
            self.spx_straddle_data['error_message'] = None
            
            logger.info(f"[SPX_STRADDLE] Starting straddle cost calculation for {target_date}")
            
            # Step 1: Get SPX price at 9:30 AM
            spx_price_930 = await self.get_spx_price_at_930am(target_date)
            if spx_price_930 is None:
                error_msg = "Failed to fetch SPX price at 9:30 AM"
                logger.error(f"[SPX_STRADDLE] {error_msg}")
                self.spx_straddle_data['calculation_status'] = 'error'
                self.spx_straddle_data['error_message'] = error_msg
                return {'error': error_msg}
            
            self.spx_straddle_data['spx_price_930am'] = spx_price_930
            self.spx_straddle_data['spx_price_timestamp'] = datetime.now(et_tz).isoformat()
            
            # Step 2: Calculate ATM strike
            atm_strike = self.get_atm_strike_for_spx(spx_price_930)
            if atm_strike is None:
                error_msg = f"Failed to calculate ATM strike for SPX price {spx_price_930}"
                logger.error(f"[SPX_STRADDLE] {error_msg}")
                self.spx_straddle_data['calculation_status'] = 'error'
                self.spx_straddle_data['error_message'] = error_msg
                return {'error': error_msg}
            
            self.spx_straddle_data['atm_strike'] = atm_strike
            
            # Step 3: Get 0DTE expiry string
            expiry_str = self.get_0dte_expiry_string(target_date)
            
            # Step 4: Fetch call price at 9:31 AM
            call_price = await self.get_spx_option_price_at_931am(atm_strike, 'C', expiry_str, target_date)
            if call_price is None:
                error_msg = f"Failed to fetch call price for strike {atm_strike}"
                logger.error(f"[SPX_STRADDLE] {error_msg}")
                self.spx_straddle_data['calculation_status'] = 'error'
                self.spx_straddle_data['error_message'] = error_msg
                return {'error': error_msg}
            
            self.spx_straddle_data['call_price_931am'] = call_price
            
            # Step 5: Fetch put price at 9:31 AM
            put_price = await self.get_spx_option_price_at_931am(atm_strike, 'P', expiry_str, target_date)
            if put_price is None:
                error_msg = f"Failed to fetch put price for strike {atm_strike}"
                logger.error(f"[SPX_STRADDLE] {error_msg}")
                self.spx_straddle_data['calculation_status'] = 'error'
                self.spx_straddle_data['error_message'] = error_msg
                return {'error': error_msg}
            
            self.spx_straddle_data['put_price_931am'] = put_price
            
            # Step 6: Calculate straddle cost
            straddle_cost = call_price + put_price
            self.spx_straddle_data['straddle_cost'] = straddle_cost
            self.spx_straddle_data['options_price_timestamp'] = datetime.now(et_tz).isoformat()
            self.spx_straddle_data['calculation_status'] = 'available'
            self.spx_straddle_data['last_calculation_date'] = target_date.isoformat()
            
            # Step 7: Store in Redis
            await self.store_straddle_data(target_date)
            
            logger.info(f"[SPX_STRADDLE] Calculation successful! Straddle cost: ${straddle_cost:.2f}")
            
            return {
                'success': True,
                'straddle_cost': straddle_cost,
                'spx_price_930am': spx_price_930,
                'atm_strike': atm_strike,
                'call_price_931am': call_price,
                'put_price_931am': put_price,
                'expiry': expiry_str,
                'calculation_date': target_date.isoformat(),
                'timestamp': datetime.now(et_tz).isoformat()
            }
            
        except Exception as e:
            error_msg = f"Unexpected error during straddle calculation: {str(e)}"
            logger.error(f"[SPX_STRADDLE] {error_msg}", exc_info=True)
            self.spx_straddle_data['calculation_status'] = 'error'
            self.spx_straddle_data['error_message'] = error_msg
            return {'error': error_msg}

    async def store_straddle_data(self, target_date: date):
        """Store straddle calculation data in Redis"""
        try:
            if not self.redis:
                logger.warning("[SPX_STRADDLE] Redis not available, skipping data storage")
                return
            
            # Create storage record
            storage_data = {
                'date': target_date.isoformat(),
                'spx_price_930am': self.spx_straddle_data['spx_price_930am'],
                'atm_strike': self.spx_straddle_data['atm_strike'],
                'call_price_931am': self.spx_straddle_data['call_price_931am'],
                'put_price_931am': self.spx_straddle_data['put_price_931am'],
                'straddle_cost': self.spx_straddle_data['straddle_cost'],
                'timestamp': self.spx_straddle_data['timestamp'],
                'calculation_status': self.spx_straddle_data['calculation_status']
            }
            
            # Store with date-based key
            redis_key = f'spx_straddle_cost_{target_date.strftime("%Y%m%d")}'
            await self.redis.set(redis_key, json.dumps(storage_data))
            
            # Add to chronological index
            date_ordinal = target_date.toordinal()
            await self.redis.zadd('spx_straddle_chronological', {redis_key: date_ordinal})
            
            logger.info(f"[SPX_STRADDLE] Stored straddle data for {target_date}")
            
        except Exception as e:
            logger.error(f"[SPX_STRADDLE] Error storing straddle data: {e}", exc_info=True)

    async def get_spx_straddle_cost(self, target_date: date = None) -> Dict[str, Any]:
        """
        Get current SPX straddle cost data
        
        Args:
            target_date: Date to get data for (defaults to today)
            
        Returns:
            Current straddle data or instruction to calculate
        """
        try:
            et_tz = pytz.timezone('US/Eastern')
            if target_date is None:
                target_date = datetime.now(et_tz).date()
            
            # Check if we have data for the target date
            if (self.spx_straddle_data.get('last_calculation_date') == target_date.isoformat() and
                self.spx_straddle_data.get('calculation_status') == 'available'):
                logger.info("[SPX_STRADDLE] Returning cached straddle data")
                return self.spx_straddle_data
            
            # Try to load from Redis
            if self.redis:
                try:
                    redis_key = f'spx_straddle_cost_{target_date.strftime("%Y%m%d")}'
                    cached_data = await self.redis.get(redis_key)
                    if cached_data:
                        if isinstance(cached_data, bytes):
                            cached_data = cached_data.decode('utf-8')
                        loaded_data = json.loads(cached_data)
                        if loaded_data.get('calculation_status') == 'available':
                            logger.info("[SPX_STRADDLE] Loaded straddle data from Redis")
                            # Update internal state
                            self.spx_straddle_data.update(loaded_data)
                            return loaded_data
                except Exception as redis_error:
                    logger.warning(f"[SPX_STRADDLE] Error loading from Redis: {redis_error}")
            
            # No valid data available
            return {
                'calculation_status': 'pending_calculation',
                'message': 'No straddle cost data available. Use calculate_spx_straddle_cost to compute.',
                'timestamp': datetime.now(et_tz).isoformat()
            }

        except Exception as e:
            logger.error(f"[SPX_STRADDLE] Error getting straddle cost: {e}", exc_info=True)
            return {
                'calculation_status': 'error',
                'error_message': str(e),
                'timestamp': datetime.now(et_tz).isoformat()
            }

    async def get_spx_straddle_history(self, days: int = 30) -> Dict[str, Any]:
        """
        Retrieve historical SPX straddle data
        
        Args:
            days: Number of days to retrieve (default 30)
            
        Returns:
            Dict containing historical data and metadata
        """
        try:
            logger.info(f"[SPX_STRADDLE] Retrieving {days} days of historical straddle data...")
            
            if not self.redis:
                return {
                    'status': 'error',
                    'error_message': 'Redis not available for historical data',
                    'timestamp': datetime.now(pytz.timezone('US/Eastern')).isoformat()
                }
            
            # Get chronological keys from Redis sorted set
            et_tz = pytz.timezone('US/Eastern')
            end_date = datetime.now(et_tz).date()
            start_date = end_date - timedelta(days=days)
            
            start_ordinal = start_date.toordinal()
            end_ordinal = end_date.toordinal()
            
            # Get keys in date range
            historical_keys = await self.redis.zrangebyscore(
                'spx_straddle_chronological', 
                start_ordinal, 
                end_ordinal
            )
            
            historical_data = []
            
            # Fetch data for each key
            for key in historical_keys:
                if isinstance(key, bytes):
                    key = key.decode('utf-8')
                
                data_json = await self.redis.get(key)
                if data_json:
                    if isinstance(data_json, bytes):
                        data_json = data_json.decode('utf-8')
                    record = json.loads(data_json)
                    historical_data.append(record)
            
            # Sort by date
            historical_data.sort(key=lambda x: x['date'])
            
            logger.info(f"[SPX_STRADDLE] Retrieved {len(historical_data)} historical records")
            
            return {
                'status': 'success',
                'data': historical_data,
                'count': len(historical_data),
                'date_range': {
                    'start': start_date.isoformat(),
                    'end': end_date.isoformat()
                },
                'timestamp': datetime.now(et_tz).isoformat()
            }
            
        except Exception as e:
            logger.error(f"[SPX_STRADDLE] Error retrieving historical data: {e}", exc_info=True)
            et_tz = pytz.timezone('US/Eastern')
            return {
                'status': 'error',
                'error_message': str(e),
                'timestamp': datetime.now(et_tz).isoformat()
            }

    async def calculate_spx_straddle_statistics(self, days: int = 30) -> Dict[str, Any]:
        """
        Calculate statistical analysis of SPX straddle costs
        
        Args:
            days: Number of days to analyze (default 30)
            
        Returns:
            Dict containing statistical analysis
        """
        try:
            logger.info(f"[SPX_STRADDLE] Calculating statistics for {days} days...")
            
            # Get historical data
            history_result = await self.get_spx_straddle_history(days)
            
            if history_result['status'] != 'success' or not history_result['data']:
                et_tz = pytz.timezone('US/Eastern')
                return {
                    'status': 'error',
                    'error_message': 'No historical data available for analysis',
                    'timestamp': datetime.now(et_tz).isoformat()
                }
            
            historical_data = history_result['data']
            
            # Extract straddle costs for analysis
            straddle_costs = [
                float(record['straddle_cost']) 
                for record in historical_data 
                if record.get('straddle_cost') is not None
            ]
            
            if not straddle_costs:
                et_tz = pytz.timezone('US/Eastern')
                return {
                    'status': 'error',
                    'error_message': 'No valid straddle cost data for analysis',
                    'timestamp': datetime.now(et_tz).isoformat()
                }
            
            # Calculate basic statistics
            mean_cost = sum(straddle_costs) / len(straddle_costs)
            sorted_costs = sorted(straddle_costs)
            median_cost = sorted_costs[len(sorted_costs) // 2]
            min_cost = min(straddle_costs)
            max_cost = max(straddle_costs)
            
            # Calculate standard deviation
            variance = sum((x - mean_cost) ** 2 for x in straddle_costs) / len(straddle_costs)
            std_dev = variance ** 0.5
            
            # Calculate percentiles
            def percentile(data, p):
                index = int(len(data) * p / 100)
                return data[min(index, len(data) - 1)]
            
            p25 = percentile(sorted_costs, 25)
            p75 = percentile(sorted_costs, 75)
            p90 = percentile(sorted_costs, 90)
            p95 = percentile(sorted_costs, 95)
            
            # Calculate trend (simple linear regression)
            n = len(straddle_costs)
            x_values = list(range(n))
            x_mean = sum(x_values) / n
            y_mean = mean_cost
            
            numerator = sum((x_values[i] - x_mean) * (straddle_costs[i] - y_mean) for i in range(n))
            denominator = sum((x - x_mean) ** 2 for x in x_values)
            
            if denominator != 0:
                slope = numerator / denominator
                trend_direction = 'increasing' if slope > 0.1 else 'decreasing' if slope < -0.1 else 'stable'
            else:
                slope = 0
                trend_direction = 'stable'
            
            # Volatility analysis
            coefficient_of_variation = (std_dev / mean_cost) * 100 if mean_cost != 0 else 0
            volatility_category = (
                'high' if coefficient_of_variation > 20 else
                'medium' if coefficient_of_variation > 10 else
                'low'
            )
            
            # Recent vs historical comparison (last 7 days vs rest)
            recent_costs = straddle_costs[-7:] if len(straddle_costs) >= 7 else straddle_costs
            recent_avg = sum(recent_costs) / len(recent_costs) if recent_costs else 0
            
            et_tz = pytz.timezone('US/Eastern')
            
            return {
                'status': 'success',
                'period_days': days,
                'data_points': len(straddle_costs),
                'descriptive_stats': {
                    'mean': round(mean_cost, 2),
                    'median': round(median_cost, 2),
                    'min': round(min_cost, 2),
                    'max': round(max_cost, 2),
                    'std_dev': round(std_dev, 2),
                    'percentile_25': round(p25, 2),
                    'percentile_75': round(p75, 2),
                    'percentile_90': round(p90, 2),
                    'percentile_95': round(p95, 2)
                },
                'trend_analysis': {
                    'slope': round(slope, 4),
                    'direction': trend_direction,
                    'interpretation': f"Straddle costs are {trend_direction} over the {days}-day period"
                },
                'volatility_analysis': {
                    'coefficient_of_variation': round(coefficient_of_variation, 2),
                    'category': volatility_category,
                    'interpretation': f"Straddle cost volatility is {volatility_category} ({coefficient_of_variation:.1f}%)"
                },
                'recent_comparison': {
                    'recent_7day_avg': round(recent_avg, 2),
                    'historical_avg': round(mean_cost, 2),
                    'difference': round(recent_avg - mean_cost, 2),
                    'percentage_change': round(((recent_avg - mean_cost) / mean_cost) * 100, 2) if mean_cost != 0 else 0
                },
                'timestamp': datetime.now(et_tz).isoformat()
            }
            
        except Exception as e:
            logger.error(f"[SPX_STRADDLE] Error calculating statistics: {e}", exc_info=True)
            et_tz = pytz.timezone('US/Eastern')
            return {
                'status': 'error',
                'error_message': str(e),
                'timestamp': datetime.now(et_tz).isoformat()
            }

    async def cleanup_old_data(self, keep_days: int = 90):
        """
        Clean up old straddle data from Redis
        
        Args:
            keep_days: Number of days of data to keep (default 90)
        """
        try:
            if not self.redis:
                logger.warning("[SPX_STRADDLE] Redis not available for cleanup")
                return
            
            et_tz = pytz.timezone('US/Eastern')
            cutoff_date = datetime.now(et_tz).date() - timedelta(days=keep_days)
            cutoff_ordinal = cutoff_date.toordinal()
            
            # Get old keys
            old_keys = await self.redis.zrangebyscore(
                'spx_straddle_chronological',
                0,
                cutoff_ordinal
            )
            
            if old_keys:
                # Remove old data
                for key in old_keys:
                    if isinstance(key, bytes):
                        key = key.decode('utf-8')
                    await self.redis.delete(key)
                
                # Remove from chronological index
                await self.redis.zremrangebyscore(
                    'spx_straddle_chronological',
                    0,
                    cutoff_ordinal
                )
                
                logger.info(f"[SPX_STRADDLE] Cleaned up {len(old_keys)} old records")
            else:
                logger.info("[SPX_STRADDLE] No old data to clean up")
                
        except Exception as e:
            logger.error(f"[SPX_STRADDLE] Error during cleanup: {e}", exc_info=True) 