#!/usr/bin/env python3
"""
Simplified SPX Straddle Calculator
Works with indices subscription only - estimates option prices using Black-Scholes
"""

import asyncio
import os
import math
import pytz
from datetime import date, datetime, timedelta
from polygon import RESTClient
from scipy.stats import norm
import numpy as np

class SimplifiedSPXStraddleCalculator:
    def __init__(self, api_key: str):
        self.client = RESTClient(api_key)
        self.et_tz = pytz.timezone('US/Eastern')
        
    def black_scholes_call(self, S, K, T, r, sigma):
        """Calculate Black-Scholes call option price"""
        if T <= 0:
            return max(S - K, 0)
        
        d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
        d2 = d1 - sigma * np.sqrt(T)
        
        call_price = S * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2)
        return call_price
    
    def black_scholes_put(self, S, K, T, r, sigma):
        """Calculate Black-Scholes put option price"""
        if T <= 0:
            return max(K - S, 0)
        
        d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
        d2 = d1 - sigma * np.sqrt(T)
        
        put_price = K * np.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)
        return put_price
    
    def estimate_volatility(self, prices, days=30):
        """Estimate volatility from recent price data"""
        if len(prices) < 2:
            return 0.20  # Default 20% volatility
        
        returns = []
        for i in range(1, len(prices)):
            returns.append(np.log(prices[i] / prices[i-1]))
        
        if not returns:
            return 0.20
        
        daily_vol = np.std(returns)
        annual_vol = daily_vol * np.sqrt(252)  # Annualize
        
        # For 0DTE, scale volatility appropriately
        return min(max(annual_vol, 0.10), 1.0)  # Cap between 10% and 100%
    
    async def get_spx_price_at_930(self, target_date: date):
        """Get SPX price at 9:30 AM ET"""
        try:
            # Get minute-level data for the target date
            aggs = self.client.list_aggs(
                ticker="I:SPX",
                multiplier=1,
                timespan="minute",
                from_=target_date,
                to=target_date,
                limit=50000
            )
            
            # Convert to list to handle both formats
            if hasattr(aggs, '__iter__'):
                bars = list(aggs)
            else:
                bars = []
            
            if not bars:
                print(f"❌ No SPX data for {target_date}")
                return None
            
            # Find 9:30 AM ET candle
            target_datetime = self.et_tz.localize(
                datetime.combine(target_date, datetime.min.time().replace(hour=9, minute=30))
            )
            target_timestamp = int(target_datetime.timestamp() * 1000)
            
            for bar in bars:
                if bar.timestamp == target_timestamp:
                    print(f"✅ Found 9:30 AM SPX price: ${bar.open}")
                    return bar.open
            
            # If exact match not found, use first available bar
            if bars:
                print(f"⚠️ Using first available price: ${bars[0].open}")
                return bars[0].open
            
            return None
            
        except Exception as e:
            print(f"❌ Error fetching SPX data: {e}")
            return None
    
    async def get_recent_prices(self, days=30):
        """Get recent SPX prices for volatility calculation"""
        try:
            end_date = date.today() - timedelta(days=1)
            start_date = end_date - timedelta(days=days)
            
            aggs = self.client.list_aggs(
                ticker="I:SPX",
                multiplier=1,
                timespan="day",
                from_=start_date,
                to=end_date,
                limit=50
            )
            
            bars = list(aggs) if hasattr(aggs, '__iter__') else []
            prices = [bar.close for bar in bars if hasattr(bar, 'close')]
            
            return prices
            
        except Exception as e:
            print(f"⚠️ Error fetching recent prices: {e}")
            return []
    
    async def calculate_estimated_straddle(self, target_date: date):
        """Calculate estimated straddle cost using Black-Scholes"""
        print(f"🔄 Calculating estimated straddle for {target_date}")
        
        # Get SPX price at 9:30 AM
        spx_price = await self.get_spx_price_at_930(target_date)
        if not spx_price:
            return None
        
        # Calculate ATM strike (round to nearest 5)
        atm_strike = round(spx_price / 5) * 5
        print(f"📊 ATM Strike: ${atm_strike} (SPX: ${spx_price})")
        
        # Get recent prices for volatility estimation
        recent_prices = await self.get_recent_prices()
        volatility = self.estimate_volatility(recent_prices)
        print(f"📈 Estimated volatility: {volatility:.1%}")
        
        # 0DTE options - time to expiration
        market_open = self.et_tz.localize(
            datetime.combine(target_date, datetime.min.time().replace(hour=9, minute=30))
        )
        market_close = self.et_tz.localize(
            datetime.combine(target_date, datetime.min.time().replace(hour=16, minute=0))
        )
        
        time_to_expiry = (market_close - market_open).total_seconds() / (365.25 * 24 * 3600)
        print(f"⏰ Time to expiry: {time_to_expiry:.4f} years ({(market_close - market_open).total_seconds() / 3600:.1f} hours)")
        
        # Risk-free rate (approximate)
        risk_free_rate = 0.05  # 5% assumption
        
        # Calculate option prices
        call_price = self.black_scholes_call(spx_price, atm_strike, time_to_expiry, risk_free_rate, volatility)
        put_price = self.black_scholes_put(spx_price, atm_strike, time_to_expiry, risk_free_rate, volatility)
        
        straddle_cost = call_price + put_price
        
        result = {
            "date": target_date.isoformat(),
            "spx_price_930am": spx_price,
            "atm_strike": atm_strike,
            "estimated_volatility": volatility,
            "time_to_expiry_hours": (market_close - market_open).total_seconds() / 3600,
            "estimated_call_price": call_price,
            "estimated_put_price": put_price,
            "estimated_straddle_cost": straddle_cost,
            "method": "Black-Scholes estimation"
        }
        
        print(f"💰 Estimated Straddle Cost: ${straddle_cost:.2f}")
        print(f"   Call: ${call_price:.2f}, Put: ${put_price:.2f}")
        
        return result

async def main():
    """Test the simplified calculator"""
    api_key = os.getenv('POLYGON_API_KEY')
    if not api_key:
        print("❌ POLYGON_API_KEY not found")
        return
    
    calculator = SimplifiedSPXStraddleCalculator(api_key)
    
    # Test with recent trading days
    test_dates = [
        date(2024, 12, 16),
        date(2024, 12, 13),
        date(2024, 12, 12),
    ]
    
    for test_date in test_dates:
        print(f"\n{'='*60}")
        print(f"🧮 Testing Simplified SPX Straddle Calculator")
        print(f"📅 Date: {test_date}")
        print(f"{'='*60}")
        
        result = await calculator.calculate_estimated_straddle(test_date)
        
        if result:
            print(f"\n✅ SUCCESS!")
            print(f"📊 Results:")
            print(f"   SPX @ 9:30 AM: ${result['spx_price_930am']:.2f}")
            print(f"   ATM Strike: ${result['atm_strike']}")
            print(f"   Volatility: {result['estimated_volatility']:.1%}")
            print(f"   Estimated Straddle: ${result['estimated_straddle_cost']:.2f}")
        else:
            print(f"❌ Failed to calculate straddle for {test_date}")

if __name__ == "__main__":
    asyncio.run(main()) 