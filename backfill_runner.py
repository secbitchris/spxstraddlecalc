#!/usr/bin/env python3
"""
Convenient runner for historical backfill with predefined scenarios
"""

import asyncio
import os
from datetime import date, timedelta, datetime
import pytz
from historical_backfill import HistoricalBackfill

async def run_backfill_scenario(scenario: str):
    """Run predefined backfill scenarios"""
    
    api_key = os.getenv('POLYGON_API_KEY')
    if not api_key:
        print("❌ POLYGON_API_KEY environment variable not set")
        return
    
    et_tz = pytz.timezone('US/Eastern')
    today = datetime.now(et_tz).date()
    
    scenarios = {
        "1week": {
            "start_date": today - timedelta(days=7),
            "end_date": today - timedelta(days=1),
            "description": "Last 7 days"
        },
        "1month": {
            "start_date": today - timedelta(days=30),
            "end_date": today - timedelta(days=1),
            "description": "Last 30 days"
        },
        "3months": {
            "start_date": today - timedelta(days=90),
            "end_date": today - timedelta(days=1),
            "description": "Last 3 months"
        },
        "6months": {
            "start_date": today - timedelta(days=180),
            "end_date": today - timedelta(days=1),
            "description": "Last 6 months"
        },
        "1year": {
            "start_date": today - timedelta(days=365),
            "end_date": today - timedelta(days=1),
            "description": "Last 1 year"
        },
        "2years": {
            "start_date": today - timedelta(days=730),
            "end_date": today - timedelta(days=1),
            "description": "Last 2 years"
        }
    }
    
    if scenario not in scenarios:
        print(f"❌ Unknown scenario: {scenario}")
        print(f"Available scenarios: {', '.join(scenarios.keys())}")
        return
    
    config = scenarios[scenario]
    print(f"🚀 Running backfill scenario: {scenario}")
    print(f"📅 {config['description']}: {config['start_date']} to {config['end_date']}")
    
    backfill = HistoricalBackfill(api_key)
    
    try:
        await backfill.initialize()
        result = await backfill.backfill_date_range(
            start_date=config['start_date'],
            end_date=config['end_date'],
            batch_size=5,  # Conservative batch size
            delay_between_batches=2.0  # 2 second delay between batches
        )
        
        # Print summary
        print("\n" + "="*60)
        print(f"BACKFILL SUMMARY - {scenario.upper()}")
        print("="*60)
        stats = result['summary']
        print(f"Date Range: {stats['start_date']} to {stats['end_date']}")
        print(f"Total Days: {stats['total_days']}")
        print(f"Successful: {stats['successful_days']}")
        print(f"Failed: {stats['failed_days']}")
        print(f"Skipped: {stats['skipped_days']}")
        print(f"Success Rate: {stats['success_rate']:.1f}%")
        print(f"Duration: {stats['duration_seconds']:.0f} seconds")
        print("="*60)
        
        if stats['success_rate'] > 80:
            print("✅ Backfill completed successfully!")
        else:
            print("⚠️ Backfill completed with some failures")
            
    except Exception as e:
        print(f"❌ Backfill failed: {e}")
    finally:
        await backfill.close()

async def main():
    """Main function"""
    import sys
    
    if len(sys.argv) != 2:
        print("Usage: python backfill_runner.py <scenario>")
        print("\nAvailable scenarios:")
        print("  1week   - Last 7 days")
        print("  1month  - Last 30 days") 
        print("  3months - Last 3 months")
        print("  6months - Last 6 months")
        print("  1year   - Last 1 year")
        print("  2years  - Last 2 years")
        return
    
    scenario = sys.argv[1]
    await run_backfill_scenario(scenario)

if __name__ == "__main__":
    asyncio.run(main()) 