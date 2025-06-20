"""
SPY Expected Move Calculator

Calculates daily SPY expected moves using straddle pricing and implied volatility.
Uses 9:32 AM timing to capture post-ORB (Opening Range Breakout) data for more reliable calculations.

Key Features:
- Expected move calculation (1σ and 2σ ranges)
- Implied volatility analysis
- Range efficiency tracking
- Historical move accuracy
"""

import os
import asyncio
import logging
import redis
import json
import math
from datetime import datetime, timedelta, date
from typing import Dict, List, Optional, Tuple
import requests
from dataclasses import dataclass
import pytz

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class SPYMoveData:
    """Data structure for SPY expected move calculations"""
    asset: str
    date: str
    spy_price_930am: float
    atm_strike: int
    call_price_932am: float
    put_price_932am: float
    straddle_cost: float
    expected_move_1sigma: float
    expected_move_2sigma: float
    implied_volatility: float
    range_efficiency: Optional[float]
    orb_high: Optional[float]
    orb_low: Optional[float]
    orb_range: Optional[float]
    timestamp: str

class SPYCalculator:
    def __init__(self):
        # Use environment variable for Redis URL, fallback to localhost for local development
        redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379')
        self.redis_client = redis.from_url(redis_url, decode_responses=True)
        self.polygon_api_key = os.getenv('POLYGON_API_KEY')
        
        if not self.polygon_api_key:
            raise ValueError("POLYGON_API_KEY environment variable is required")
        
        logger.info("[SPY_EXPECTED_MOVE] SPY Calculator initialized")
    
    def _is_spy_0dte_available(self, target_date) -> bool:
        """
        Check if SPY 0DTE options were available for the given date.
        SPY daily 0DTE options launched in 2022.
        """
        try:
            if isinstance(target_date, str):
                check_date = datetime.strptime(target_date, '%Y-%m-%d').date()
            else:
                check_date = target_date
            
            # SPY daily 0DTE options launched in 2022
            # Be conservative and start from January 1, 2023 to ensure full availability
            spy_0dte_launch = date(2023, 1, 1)
            
            if check_date < spy_0dte_launch:
                return False
            
            # Also check if it's a trading day (Monday-Friday)
            weekday = check_date.weekday()
            if weekday >= 5:  # Saturday = 5, Sunday = 6
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"[SPY_EXPECTED_MOVE] Error checking SPY 0DTE availability: {e}")
            return False

    async def calculate_spy_expected_move(self, target_date: str = None) -> Optional[SPYMoveData]:
        """Calculate SPY expected move for current or specified date"""
        try:
            et_tz = pytz.timezone('US/Eastern')
            
            if target_date is None:
                current_time = datetime.now(et_tz)
                target_date = current_time.strftime('%Y-%m-%d')
            
            # SPY 0DTE options available - same API as SPX
            
            logger.info(f"[SPY_EXPECTED_MOVE] Calculating expected move for {target_date}")
            
            # Get SPY price at 9:32 AM for strike selection
            spy_price_932am = await self._get_spy_price_at_time(target_date, "09:32")
            if not spy_price_932am:
                logger.warning(f"[SPY_EXPECTED_MOVE] Could not get SPY price at 9:32 AM for {target_date}")
                return None
            
            logger.info(f"[SPY_EXPECTED_MOVE] SPY price at 9:32 AM: ${spy_price_932am:.2f}")
            
            # Get straddle data at 9:32 AM using the same price for strike selection
            straddle_data = await self._get_spy_straddle_at_time(target_date, spy_price_932am, "09:32")
            if not straddle_data:
                logger.warning(f"[SPY_EXPECTED_MOVE] Could not get straddle data for {target_date}")
                return None
            
            # Get ORB data
            orb_data = await self._get_orb_data(target_date)
            
            # Calculate expected move metrics
            metrics = self._calculate_expected_move_metrics(
                spy_price_932am,
                straddle_data['call_price'],
                straddle_data['put_price'],
                straddle_data['atm_strike']
            )
            
            # Calculate range efficiency (this will be updated throughout the day)
            range_efficiency = await self._calculate_range_efficiency(target_date)
            
            # Create SPY move data object
            spy_data = SPYMoveData(
                asset="SPY",
                date=target_date,
                spy_price_930am=spy_price_932am,
                atm_strike=straddle_data['atm_strike'],
                call_price_932am=straddle_data['call_price'],
                put_price_932am=straddle_data['put_price'],
                straddle_cost=metrics['straddle_cost'],
                expected_move_1sigma=metrics['expected_move_1sigma'],
                expected_move_2sigma=metrics['expected_move_2sigma'],
                implied_volatility=metrics['implied_volatility'],
                range_efficiency=range_efficiency,
                orb_high=orb_data['high'] if orb_data else None,
                orb_low=orb_data['low'] if orb_data else None,
                orb_range=orb_data['range'] if orb_data else None,
                timestamp=datetime.now(pytz.timezone('US/Eastern')).isoformat()
            )
            
            # Store the data
            await self._store_spy_data(spy_data)
            
            logger.info(f"[SPY_EXPECTED_MOVE] Successfully calculated expected move: ±${metrics['expected_move_1sigma']:.2f}")
            return spy_data
            
        except Exception as e:
            logger.error(f"[SPY_EXPECTED_MOVE] Error calculating expected move: {str(e)}")
            return None

    async def calculate_spy_expected_move_historical(self, target_date) -> Optional[SPYMoveData]:
        """Calculate SPY expected move for a historical date"""
        try:
            # Convert date to string if it's a date object
            if hasattr(target_date, 'strftime'):
                target_date_str = target_date.strftime('%Y-%m-%d')
            else:
                target_date_str = target_date
            
            # SPY 0DTE options available - same API as SPX
            
            logger.info(f"[SPY_EXPECTED_MOVE] Calculating historical expected move for {target_date_str}")
            
            # Get SPY price at 9:32 AM for strike selection
            spy_price_932am = await self._get_spy_price_at_time(target_date_str, "09:32")
            if not spy_price_932am:
                logger.warning(f"[SPY_EXPECTED_MOVE] Could not get SPY price at 9:32 AM for {target_date_str}")
                return None
            
            logger.info(f"[SPY_EXPECTED_MOVE] SPY price at 9:32 AM: ${spy_price_932am:.2f}")
            
            # Get straddle data at 9:32 AM using the same price for strike selection
            straddle_data = await self._get_spy_straddle_at_time(target_date_str, spy_price_932am, "09:32")
            if not straddle_data:
                logger.warning(f"[SPY_EXPECTED_MOVE] Could not get straddle data for {target_date_str}")
                return None
            
            # Get ORB data
            orb_data = await self._get_orb_data(target_date_str)
            
            # Calculate expected move metrics
            metrics = self._calculate_expected_move_metrics(
                spy_price_932am,
                straddle_data['call_price'],
                straddle_data['put_price'],
                straddle_data['atm_strike']
            )
            
            # For historical data, calculate range efficiency based on actual day's movement
            range_efficiency = None
            try:
                # Get the actual day's high and low for efficiency calculation
                daily_data = await self._get_spy_daily_data(target_date_str)
                if daily_data and 'high' in daily_data and 'low' in daily_data:
                    actual_range = daily_data['high'] - daily_data['low']
                    expected_range = metrics['expected_move_2sigma']
                    if expected_range > 0:
                        range_efficiency = actual_range / expected_range
            except Exception as e:
                logger.warning(f"[SPY_EXPECTED_MOVE] Could not calculate range efficiency for {target_date_str}: {e}")
            
            # Create SPY move data object
            spy_data = SPYMoveData(
                asset="SPY",
                date=target_date_str,
                spy_price_930am=spy_price_932am,
                atm_strike=straddle_data['atm_strike'],
                call_price_932am=straddle_data['call_price'],
                put_price_932am=straddle_data['put_price'],
                straddle_cost=metrics['straddle_cost'],
                expected_move_1sigma=metrics['expected_move_1sigma'],
                expected_move_2sigma=metrics['expected_move_2sigma'],
                implied_volatility=metrics['implied_volatility'],
                range_efficiency=range_efficiency,
                orb_high=orb_data['high'] if orb_data else None,
                orb_low=orb_data['low'] if orb_data else None,
                orb_range=orb_data['range'] if orb_data else None,
                timestamp=datetime.now(pytz.timezone('US/Eastern')).isoformat()
            )
            
            logger.info(f"[SPY_EXPECTED_MOVE] Successfully calculated historical expected move: ±${metrics['expected_move_1sigma']:.2f}")
            return spy_data
            
        except Exception as e:
            logger.error(f"[SPY_EXPECTED_MOVE] Error calculating historical expected move: {str(e)}")
            return None

    async def _get_spy_daily_data(self, date: str) -> Optional[Dict]:
        """Get SPY daily OHLC data for a specific date using Polygon Python client"""
        try:
            target_date = datetime.strptime(date, '%Y-%m-%d').date()
            
            # Use Polygon client for daily data
            from polygon import RESTClient
            polygon_client = RESTClient(self.polygon_api_key)
            
            aggs = polygon_client.get_aggs(
                ticker="SPY",
                multiplier=1,
                timespan="day",
                from_=target_date.strftime('%Y-%m-%d'),
                to=target_date.strftime('%Y-%m-%d'),
                limit=1
            )
            
            # Handle both list response and object with results attribute
            if not aggs:
                logger.warning(f"[SPY_EXPECTED_MOVE] No SPY daily data received for {date}")
                return None
            
            if isinstance(aggs, list):
                bars = aggs
            elif hasattr(aggs, 'results') and aggs.results:
                bars = aggs.results
            else:
                logger.warning(f"[SPY_EXPECTED_MOVE] No SPY daily data received for {date}")
                return None
            
            if bars:
                bar = bars[0]
                return {
                    'open': bar.open,
                    'high': bar.high,
                    'low': bar.low,
                    'close': bar.close,
                    'volume': bar.volume
                }
            
            return None
            
        except Exception as e:
            logger.error(f"[SPY_EXPECTED_MOVE] Error getting daily data for {date}: {str(e)}")
            return None
    
    async def _get_spy_price_at_time(self, date: str, time: str) -> Optional[float]:
        """Get SPY price at specific time using Polygon Python client (same as SPX)"""
        try:
            et_tz = pytz.timezone('US/Eastern')
            target_date = datetime.strptime(date, '%Y-%m-%d').date()
            
            # Convert to timestamp for Polygon API
            target_hour = 9
            target_minute = 30 if time == "09:30" else 32
            target_datetime = et_tz.localize(datetime.combine(target_date, datetime.min.time().replace(hour=target_hour, minute=target_minute)))
            
            logger.info(f"[SPY_EXPECTED_MOVE] Fetching SPY price at {time} for {date}")
            
            # Get SPY aggregate data using Polygon client (same approach as SPX)
            from polygon import RESTClient
            polygon_client = RESTClient(self.polygon_api_key)
            
            # SPY is an ETF, use ticker "SPY" (not "I:SPY" like SPX index)
            aggs = polygon_client.get_aggs(
                ticker="SPY",
                multiplier=1,
                timespan="minute",
                from_=target_datetime.strftime('%Y-%m-%d'),
                to=target_datetime.strftime('%Y-%m-%d'),
                limit=50000
            )
            
            # Handle both list response and object with results attribute (same as SPX)
            if not aggs:
                logger.warning(f"[SPY_EXPECTED_MOVE] No SPY data received from Polygon")
                return None
            
            # Check if aggs is a list (new format) or has results attribute (old format)
            if isinstance(aggs, list):
                bars = aggs
            elif hasattr(aggs, 'results') and aggs.results:
                bars = aggs.results
            else:
                logger.warning(f"[SPY_EXPECTED_MOVE] No SPY data received from Polygon")
                return None
            
            # Find the target minute candle
            for bar in bars:
                bar_time = datetime.fromtimestamp(bar.timestamp / 1000, tz=et_tz)
                if bar_time.hour == target_hour and bar_time.minute == target_minute:
                    logger.info(f"[SPY_EXPECTED_MOVE] Found {time} SPY candle: open={bar.open}, high={bar.high}, low={bar.low}, close={bar.close}")
                    return float(bar.open)
            
            logger.warning(f"[SPY_EXPECTED_MOVE] No {time} SPY candle found in Polygon data")
            return None
            
        except Exception as e:
            logger.error(f"[SPY_EXPECTED_MOVE] Error getting SPY price at {time}: {str(e)}")
            return None
    
    async def _get_orb_data(self, date: str) -> Optional[Dict]:
        """Get Opening Range Breakout data (9:30-9:32 AM) using Polygon Python client"""
        try:
            et_tz = pytz.timezone('US/Eastern')
            target_date = datetime.strptime(date, '%Y-%m-%d').date()
            target_datetime = et_tz.localize(datetime.combine(target_date, datetime.min.time().replace(hour=9, minute=30)))
            
            # Get minute-level data for ORB calculation using Polygon client
            from polygon import RESTClient
            polygon_client = RESTClient(self.polygon_api_key)
            
            aggs = polygon_client.get_aggs(
                ticker="SPY",
                multiplier=1,
                timespan="minute",
                from_=target_datetime.strftime('%Y-%m-%d'),
                to=target_datetime.strftime('%Y-%m-%d'),
                limit=50000
            )
            
            # Handle both list response and object with results attribute
            if not aggs:
                logger.warning(f"[SPY_EXPECTED_MOVE] No SPY data received for ORB calculation")
                return None
            
            if isinstance(aggs, list):
                bars = aggs
            elif hasattr(aggs, 'results') and aggs.results:
                bars = aggs.results
            else:
                logger.warning(f"[SPY_EXPECTED_MOVE] No SPY data received for ORB calculation")
                return None
            
            # Find the 9:30 and 9:31 candles for ORB (2-minute range)
            orb_bars = []
            for bar in bars:
                bar_time = datetime.fromtimestamp(bar.timestamp / 1000, tz=et_tz)
                if bar_time.hour == 9 and bar_time.minute in [30, 31]:
                    orb_bars.append(bar)
            
            if len(orb_bars) >= 2:
                # Calculate ORB from first 2 minutes (9:30-9:32)
                orb_high = max(bar.high for bar in orb_bars[:2])
                orb_low = min(bar.low for bar in orb_bars[:2])
                
                return {
                    'high': orb_high,
                    'low': orb_low,
                    'range': orb_high - orb_low
                }
            
            return None
            
        except Exception as e:
            logger.error(f"[SPY_EXPECTED_MOVE] Error getting ORB data: {str(e)}")
            return None
    
    async def _get_spy_straddle_at_time(self, date: str, spy_price: float, time: str) -> Optional[Dict]:
        """Get SPY straddle prices at specific time (e.g., 9:32 AM)"""
        try:
            # Determine ATM strike (round to nearest $1 for SPY)
            atm_strike = round(spy_price)
            
            # Get options data for the ATM strike
            # For 0DTE, expiration date is the same as trade date
            # Convert date to YYMMDD format (same as SPX)
            date_obj = datetime.strptime(date, '%Y-%m-%d').date()
            expiry_short = date_obj.strftime('%y%m%d')  # YYMMDD format
            
            # Format strike price (same as SPX: strike * 1000, 8 digits)
            strike_formatted = f"{int(atm_strike * 1000):08d}"
            
            # Get call option price - SPY uses O:SPY{YYMMDD}C{strike*1000}
            call_ticker = f"O:SPY{expiry_short}C{strike_formatted}"
            call_price = await self._get_option_price(call_ticker, date, time)
            
            # Get put option price  
            put_ticker = f"O:SPY{expiry_short}P{strike_formatted}"
            put_price = await self._get_option_price(put_ticker, date, time)
            
            if call_price and put_price:
                return {
                    'atm_strike': int(atm_strike),
                    'call_price': call_price,
                    'put_price': put_price
                }
            
            return None
            
        except Exception as e:
            logger.error(f"[SPY_EXPECTED_MOVE] Error getting straddle data: {str(e)}")
            return None
    
    async def _get_option_price(self, ticker: str, date: str, time: str) -> Optional[float]:
        """Get option price at specific time using Polygon Python client (same as SPX)"""
        try:
            et_tz = pytz.timezone('US/Eastern')
            target_date = datetime.strptime(date, '%Y-%m-%d').date()
            
            logger.info(f"[SPY_EXPECTED_MOVE] Fetching option price for {ticker} at {time}")
            
            # Target the specific minute candle
            target_hour = 9
            target_minute = 32 if time == "09:32" else 31
            target_datetime = et_tz.localize(datetime.combine(target_date, datetime.min.time().replace(hour=target_hour, minute=target_minute)))
            
            # Get option aggregate data using Polygon client (same as SPX)
            from polygon import RESTClient
            polygon_client = RESTClient(self.polygon_api_key)
            
            aggs = polygon_client.get_aggs(
                ticker=ticker,
                multiplier=1,
                timespan="minute",
                from_=target_datetime.strftime('%Y-%m-%d'),
                to=target_datetime.strftime('%Y-%m-%d'),
                limit=50000
            )
            
            # Handle both list response and object with results attribute (same as SPX)
            if not aggs:
                logger.warning(f"[SPY_EXPECTED_MOVE] No option data received for {ticker}")
                return None
            
            # Check if aggs is a list (new format) or has results attribute (old format)
            if isinstance(aggs, list):
                bars = aggs
            elif hasattr(aggs, 'results') and aggs.results:
                bars = aggs.results
            else:
                logger.warning(f"[SPY_EXPECTED_MOVE] No option data received for {ticker}")
                return None
            
            # Find the target minute candle
            for bar in bars:
                bar_time = datetime.fromtimestamp(bar.timestamp / 1000, tz=et_tz)
                if bar_time.hour == target_hour and bar_time.minute == target_minute:
                    logger.info(f"[SPY_EXPECTED_MOVE] Found {time} option candle for {ticker}: "
                               f"open={bar.open}, high={bar.high}, low={bar.low}, close={bar.close}")
                    
                    # Use the opening price from the target minute candle (same as SPX)
                    if bar.open and bar.open > 0:
                        logger.info(f"[SPY_EXPECTED_MOVE] Using {time} opening price: {bar.open}")
                        return float(bar.open)
                    else:
                        logger.warning(f"[SPY_EXPECTED_MOVE] Invalid opening price in {time} candle: {bar.open}")
                        return None
            
            logger.warning(f"[SPY_EXPECTED_MOVE] No {time} candle found for option {ticker}")
            return None
            
        except Exception as e:
            logger.error(f"[SPY_EXPECTED_MOVE] Error getting option price for {ticker}: {str(e)}")
            return None
    
    def _calculate_expected_move_metrics(self, spy_price: float, call_price: float, put_price: float, atm_strike: int) -> Dict:
        """Calculate expected move metrics from straddle pricing"""
        
        # Calculate straddle cost
        straddle_cost = call_price + put_price
        
        # Expected move approximation: straddle cost ≈ 1σ move
        expected_move_1sigma = straddle_cost
        expected_move_2sigma = straddle_cost * 2
        
        # Calculate implied volatility (reverse-engineered from straddle)
        # For 0DTE at 9:32 AM, approximately 6.47 hours remaining until 4 PM close
        # Time to expiry as fraction of year: (6.47 hours / 6.5 hours per day) / 252 trading days
        time_to_expiry_years = (6.47 / 6.5) / 252  # About 0.004 years remaining
        
        # Standard Black-Scholes approximation for ATM straddle:
        # Straddle ≈ 0.8 × Stock × IV × √T
        # Solving for IV: IV = Straddle / (0.8 × Stock × √T)
        if time_to_expiry_years > 0:
            implied_volatility = straddle_cost / (0.8 * spy_price * math.sqrt(time_to_expiry_years))
        else:
            implied_volatility = 0
        
        return {
            'straddle_cost': straddle_cost,
            'expected_move_1sigma': expected_move_1sigma,
            'expected_move_2sigma': expected_move_2sigma,
            'implied_volatility': implied_volatility
        }
    
    async def _calculate_range_efficiency(self, target_date: str) -> Optional[float]:
        """Calculate historical range efficiency (actual vs expected moves)"""
        try:
            # Get last 30 days of SPY data for efficiency calculation
            historical_data = await self.get_spy_historical_data(30)
            
            if len(historical_data) < 10:  # Need minimum data
                return None
            
            efficiency_ratios = []
            
            for record in historical_data:
                # Calculate actual move from opening price
                if 'actual_high' in record and 'actual_low' in record:
                    actual_range = record['actual_high'] - record['actual_low']
                    expected_range = record.get('expected_move_2sigma', 0)
                    
                    if expected_range > 0:
                        efficiency = actual_range / expected_range
                        efficiency_ratios.append(efficiency)
            
            if efficiency_ratios:
                return sum(efficiency_ratios) / len(efficiency_ratios)
            
            return None
            
        except Exception as e:
            logger.error(f"[SPY_EXPECTED_MOVE] Error calculating range efficiency: {str(e)}")
            return None
    
    async def _store_spy_data(self, spy_data: SPYMoveData):
        """Store SPY data in Redis"""
        try:
            # Store daily data
            key = f"spy_expected_move:{spy_data.date}"
            data_dict = {
                'asset': spy_data.asset,
                'date': spy_data.date,
                'spy_price_930am': spy_data.spy_price_930am,
                'atm_strike': spy_data.atm_strike,
                'call_price_932am': spy_data.call_price_932am,
                'put_price_932am': spy_data.put_price_932am,
                'straddle_cost': spy_data.straddle_cost,
                'expected_move_1sigma': spy_data.expected_move_1sigma,
                'expected_move_2sigma': spy_data.expected_move_2sigma,
                'implied_volatility': spy_data.implied_volatility,
                'range_efficiency': spy_data.range_efficiency if spy_data.range_efficiency is not None else 'None',
                'orb_high': spy_data.orb_high if spy_data.orb_high is not None else 'None',
                'orb_low': spy_data.orb_low if spy_data.orb_low is not None else 'None',
                'orb_range': spy_data.orb_range if spy_data.orb_range is not None else 'None',
                'timestamp': spy_data.timestamp
            }
            
            self.redis_client.hset(key, mapping=data_dict)
            self.redis_client.expire(key, 86400 * 365)  # Expire after 1 year
            
            # Add to historical list
            self.redis_client.lpush("spy_history", spy_data.date)
            self.redis_client.ltrim("spy_history", 0, 1000)  # Keep last 1000 records
            
            logger.info(f"[SPY_EXPECTED_MOVE] Stored data for {spy_data.date}")
            
        except Exception as e:
            logger.error(f"[SPY_EXPECTED_MOVE] Error storing data: {str(e)}")
    
    async def get_spy_data_for_date(self, date: str) -> Optional[Dict]:
        """Get SPY data for a specific date"""
        try:
            key = f"spy_expected_move:{date}"
            data = self.redis_client.hgetall(key)
            
            if data:
                # Convert string values back to appropriate types
                for field in ['spy_price_930am', 'call_price_932am', 'put_price_932am', 
                             'straddle_cost', 'expected_move_1sigma', 'expected_move_2sigma', 
                             'implied_volatility', 'range_efficiency', 'orb_high', 'orb_low', 'orb_range']:
                    if field in data and data[field] and data[field] != 'None':
                        data[field] = float(data[field])
                
                if 'atm_strike' in data:
                    data['atm_strike'] = int(data['atm_strike'])
                
                return data
            
            return None
            
        except Exception as e:
            logger.error(f"[SPY_EXPECTED_MOVE] Error getting data for {date}: {str(e)}")
            return None
    
    async def get_spy_historical_data(self, days: int = 30) -> List[Dict]:
        """Get historical SPY expected move data for the most recent N days"""
        try:
            logger.info(f"[SPY_EXPECTED_MOVE] Retrieving {days} days of historical data...")
            
            # Calculate date range for the most recent N days
            et_tz = pytz.timezone('US/Eastern')
            end_date = datetime.now(et_tz).date()
            start_date = end_date - timedelta(days=days)
            
            # Get all dates from Redis list and filter by date range
            all_dates = self.redis_client.lrange("spy_history", 0, -1)
            
            # Filter dates to only include those in our target range
            target_dates = []
            for date_str in all_dates:
                try:
                    date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
                    if start_date <= date_obj <= end_date:
                        target_dates.append(date_str)
                except ValueError:
                    continue
            
            # Sort dates in descending order (most recent first) and limit
            target_dates.sort(reverse=True)
            target_dates = target_dates[:days]
            
            historical_data = []
            for date in target_dates:
                data = await self.get_spy_data_for_date(date)
                if data:
                    historical_data.append(data)
            
            logger.info(f"[SPY_EXPECTED_MOVE] Retrieved {len(historical_data)} historical records")
            return historical_data
            
        except Exception as e:
            logger.error(f"[SPY_EXPECTED_MOVE] Error getting historical data: {str(e)}")
            return []
    
    async def calculate_spy_statistics(self, days: int = 30) -> Dict:
        """Calculate statistical metrics for SPY expected moves"""
        try:
            logger.info(f"[SPY_EXPECTED_MOVE] Calculating statistics for {days} days...")
            
            historical_data = await self.get_spy_historical_data(days)
            
            if not historical_data:
                return {}
            
            # Extract metrics for analysis
            expected_moves = [record['expected_move_1sigma'] for record in historical_data if 'expected_move_1sigma' in record]
            straddle_costs = [record['straddle_cost'] for record in historical_data if 'straddle_cost' in record]
            implied_vols = [record['implied_volatility'] for record in historical_data if 'implied_volatility' in record]
            
            stats = {}
            
            if expected_moves:
                stats['expected_move'] = {
                    'mean': sum(expected_moves) / len(expected_moves),
                    'min': min(expected_moves),
                    'max': max(expected_moves),
                    'std': self._calculate_std(expected_moves)
                }
            
            if straddle_costs:
                stats['straddle_cost'] = {
                    'mean': sum(straddle_costs) / len(straddle_costs),
                    'min': min(straddle_costs),
                    'max': max(straddle_costs),
                    'std': self._calculate_std(straddle_costs)
                }
            
            if implied_vols:
                stats['implied_volatility'] = {
                    'mean': sum(implied_vols) / len(implied_vols),
                    'min': min(implied_vols),
                    'max': max(implied_vols),
                    'std': self._calculate_std(implied_vols)
                }
            
            stats['data_points'] = len(historical_data)
            
            return stats
            
        except Exception as e:
            logger.error(f"[SPY_EXPECTED_MOVE] Error calculating statistics: {str(e)}")
            return {}
    
    def _calculate_std(self, values: List[float]) -> float:
        """Calculate standard deviation"""
        if len(values) < 2:
            return 0.0
        
        mean = sum(values) / len(values)
        variance = sum((x - mean) ** 2 for x in values) / (len(values) - 1)
        return math.sqrt(variance)

# Utility functions for external use
async def get_spy_calculator():
    """Get SPY calculator instance"""
    return SPYCalculator()

async def calculate_daily_spy_expected_move():
    """Calculate today's SPY expected move"""
    calculator = SPYCalculator()
    return await calculator.calculate_spy_expected_move()

if __name__ == "__main__":
    # Test the calculator
    async def test_spy_calculator():
        calculator = SPYCalculator()
        result = await calculator.calculate_spy_expected_move()
        if result:
            print(f"SPY Expected Move: ±${result.expected_move_1sigma:.2f}")
            print(f"Total Range: ${result.expected_move_2sigma:.2f}")
            print(f"Implied Volatility: {result.implied_volatility:.1%}")
        else:
            print("Failed to calculate SPY expected move")
    
    asyncio.run(test_spy_calculator()) 