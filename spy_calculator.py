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
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import requests
from dataclasses import dataclass

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
    timestamp: str

class SPYCalculator:
    def __init__(self):
        self.redis_client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
        self.polygon_api_key = os.getenv('POLYGON_API_KEY')
        
        if not self.polygon_api_key:
            raise ValueError("POLYGON_API_KEY environment variable is required")
        
        logger.info("[SPY_EXPECTED_MOVE] SPY Calculator initialized")
    
    async def calculate_spy_expected_move(self, target_date: str = None) -> Optional[SPYMoveData]:
        """
        Calculate SPY expected move for a given date using 9:32 AM timing.
        
        Args:
            target_date: Date in YYYY-MM-DD format. Defaults to today.
            
        Returns:
            SPYMoveData object with all calculated metrics
        """
        if not target_date:
            target_date = datetime.now().strftime('%Y-%m-%d')
        
        logger.info(f"[SPY_EXPECTED_MOVE] Calculating expected move for {target_date}")
        
        try:
            # Step 1: Get SPY price at 9:30 AM
            spy_price_930 = await self._get_spy_price_at_time(target_date, "09:30")
            if not spy_price_930:
                logger.error(f"[SPY_EXPECTED_MOVE] Failed to get SPY price at 9:30 AM for {target_date}")
                return None
            
            # Step 2: Get ORB data (9:30-9:32 AM range)
            orb_data = await self._get_orb_data(target_date)
            
            # Step 3: Get straddle prices at 9:32 AM (post-ORB)
            straddle_data = await self._get_spy_straddle_at_time(target_date, spy_price_930, "09:32")
            if not straddle_data:
                logger.error(f"[SPY_EXPECTED_MOVE] Failed to get straddle data at 9:32 AM for {target_date}")
                return None
            
            # Step 4: Calculate expected move metrics
            move_data = self._calculate_expected_move_metrics(
                spy_price_930, 
                straddle_data['call_price'], 
                straddle_data['put_price'],
                straddle_data['atm_strike']
            )
            
            # Step 5: Calculate historical range efficiency
            range_efficiency = await self._calculate_range_efficiency(target_date)
            
            # Step 6: Create SPYMoveData object
            spy_move_data = SPYMoveData(
                asset="SPY",
                date=target_date,
                spy_price_930am=spy_price_930,
                atm_strike=straddle_data['atm_strike'],
                call_price_932am=straddle_data['call_price'],
                put_price_932am=straddle_data['put_price'],
                straddle_cost=move_data['straddle_cost'],
                expected_move_1sigma=move_data['expected_move_1sigma'],
                expected_move_2sigma=move_data['expected_move_2sigma'],
                implied_volatility=move_data['implied_volatility'],
                range_efficiency=range_efficiency,
                orb_high=orb_data.get('high') if orb_data else None,
                orb_low=orb_data.get('low') if orb_data else None,
                timestamp=f"{target_date}T09:32:00-04:00"
            )
            
            # Step 7: Store data in Redis
            await self._store_spy_data(spy_move_data)
            
            logger.info(f"[SPY_EXPECTED_MOVE] Successfully calculated expected move: ±${move_data['expected_move_1sigma']:.2f}")
            return spy_move_data
            
        except Exception as e:
            logger.error(f"[SPY_EXPECTED_MOVE] Error calculating expected move for {target_date}: {str(e)}")
            return None
    
    async def _get_spy_price_at_time(self, date: str, time: str) -> Optional[float]:
        """Get SPY price at specific time (e.g., 9:30 AM)"""
        try:
            # Convert to timestamp for Polygon API
            dt = datetime.strptime(f"{date} {time}", "%Y-%m-%d %H:%M")
            timestamp = int(dt.timestamp() * 1000)
            
            url = f"https://api.polygon.io/v1/open-close/SPY/{date}"
            params = {
                'adjusted': 'true',
                'apikey': self.polygon_api_key
            }
            
            response = requests.get(url, params=params)
            response.raise_for_status()
            
            data = response.json()
            
            # For 9:30 AM, use the opening price
            if time == "09:30":
                return data.get('open')
            
            # For other times, we'd need minute-level data
            # For now, return opening price as approximation
            return data.get('open')
            
        except Exception as e:
            logger.error(f"[SPY_EXPECTED_MOVE] Error getting SPY price at {time}: {str(e)}")
            return None
    
    async def _get_orb_data(self, date: str) -> Optional[Dict]:
        """Get Opening Range Breakout data (9:30-9:32 AM)"""
        try:
            # Get minute-level data for ORB calculation
            url = f"https://api.polygon.io/v2/aggs/ticker/SPY/range/1/minute/{date}/{date}"
            params = {
                'adjusted': 'true',
                'sort': 'asc',
                'limit': 5,  # First few minutes
                'apikey': self.polygon_api_key
            }
            
            response = requests.get(url, params=params)
            response.raise_for_status()
            
            data = response.json()
            results = data.get('results', [])
            
            if len(results) >= 2:
                # Calculate ORB from first 2 minutes (9:30-9:32)
                orb_high = max(bar['h'] for bar in results[:2])
                orb_low = min(bar['l'] for bar in results[:2])
                
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
            # Determine ATM strike (round to nearest $5 for SPY)
            atm_strike = round(spy_price / 5) * 5
            
            # Get options data for the ATM strike
            # For 0DTE, expiration date is the same as trade date
            expiry_date = date
            
            # Get call option price
            call_ticker = f"O:SPY{expiry_date.replace('-', '')}C{int(atm_strike * 1000):08d}"
            call_price = await self._get_option_price(call_ticker, date, time)
            
            # Get put option price  
            put_ticker = f"O:SPY{expiry_date.replace('-', '')}P{int(atm_strike * 1000):08d}"
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
        """Get option price at specific time"""
        try:
            # Get option data from Polygon
            url = f"https://api.polygon.io/v2/aggs/ticker/{ticker}/range/1/minute/{date}/{date}"
            params = {
                'adjusted': 'true',
                'sort': 'asc',
                'limit': 10,
                'apikey': self.polygon_api_key
            }
            
            response = requests.get(url, params=params)
            response.raise_for_status()
            
            data = response.json()
            results = data.get('results', [])
            
            if results:
                # For 9:32 AM, get the price from the appropriate minute
                # Use the close price of the relevant minute bar
                target_minute = 2 if time == "09:32" else 1  # 0-indexed
                if len(results) > target_minute:
                    return results[target_minute]['c']  # Close price
                else:
                    return results[-1]['c']  # Last available price
            
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
        # IV ≈ straddle_cost / (spy_price × √(T/252))
        # For 0DTE: T = 1/252 (fraction of trading day remaining)
        time_to_expiry = 1/252  # Approximate for 0DTE
        implied_volatility = straddle_cost / (spy_price * math.sqrt(time_to_expiry))
        
        # Annualize the IV
        implied_volatility_annualized = implied_volatility * math.sqrt(252)
        
        return {
            'straddle_cost': straddle_cost,
            'expected_move_1sigma': expected_move_1sigma,
            'expected_move_2sigma': expected_move_2sigma,
            'implied_volatility': implied_volatility_annualized
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
                'range_efficiency': spy_data.range_efficiency,
                'orb_high': spy_data.orb_high,
                'orb_low': spy_data.orb_low,
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
                             'implied_volatility', 'range_efficiency', 'orb_high', 'orb_low']:
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
        """Get historical SPY expected move data"""
        try:
            logger.info(f"[SPY_EXPECTED_MOVE] Retrieving {days} days of historical data...")
            
            # Get date list from Redis
            dates = self.redis_client.lrange("spy_history", 0, days - 1)
            
            historical_data = []
            for date in dates:
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